#!/usr/bin/env python3
"""Run actual Edge instrumentation and validate range-analysis semantics."""
import subprocess,json
import csv
import re
from prepare_edge_flow import instrument
from pathlib import Path
from analyze_edge_flow import analyze
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'build/bces01229/spu/jobmod_d0d15ec83992_ea2a0/spu_recomp.c').read_text()
derived=instrument(source).removeprefix('#include "EdgeFlow.h"\n')
restored=derived.replace('\n    bces_edge_job_begin(ctx);','').replace('        bces_edge_job_end(ctx);\n','')
restored=re.sub(r'BCESEdgeSpan _edge_span=bces_edge_span_begin\(ctx,0x[0-9A-F]+,0x[0-9A-F]+\); ','',restored)
restored=restored.replace('bces_edge_span_end(_edge_span,ctx); ','')
assert restored==source
print('PASS: all original lifted instructions, call/drain pairs and exits preserved after stripping hooks')
work=ROOT/'build/bces01229/edge-test';work.mkdir(exist_ok=True)
binary=work/'flow-test'
subprocess.run(['clang','-std=gnu17','-O2','-DSPU_USE_DISPATCH_MT','-fsanitize=address,undefined',
    '-I'+str(ROOT/'src/platform'),'-I'+str(ROOT/'build/bces01229/ios-prepared/trace-include'),
    '-I'+str(ROOT/'upstream/infamous2-recomp/ps3recomp-fork/runtime/spu'),
    str(ROOT/'src/platform/EdgeFlow.c'),str(ROOT/'tools/tests/edge_flow.c'),'-o',str(binary)],check=True)
with (ROOT/'out/edge-flow-host-test.csv').open('w') as out:
    subprocess.run([str(binary)],stdout=out,check=True)
r,details=analyze(ROOT/'out/edge-flow-host-test.csv')
assert r['valid_recording'] and r['complete_job_spans']==1 and r['dma_counts']=={'GET':1,'PUT':1}
assert r['renderer_reads_with_prior_edge_put_overlap']==1 and r['matched_reader_kinds']=={1:1}
assert details['range_associations'][0]['overlap_bytes']==32
assert r['dma_without_completed_job']==0
assert r['targets']['0x5740']['count']==1 and r['targets']['0xE2A0']['count']==1
(ROOT/'out/edge-flow-host-analysis.json').write_text(json.dumps(r,indent=2)+'\n')
print('PASS: actual hooks + analyzer; inclusive scopes not summed; known PUT/vertex overlap; complete metadata')
with (ROOT/'out/edge-flow-host-test.csv').open() as f:
    metadata=next(f);rows=list(csv.DictReader(f))
def check_case(name,modified,match_count,valid=True,header=metadata):
    path=work/(name+'.csv')
    with path.open('w') as f:
        f.write(header);w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(modified)
    result,_=analyze(path)
    assert result['renderer_reads_with_prior_edge_put_overlap']==match_count and result['valid_recording']==valid,name
put_time=next(x['end_s'] for x in rows if x['kind']=='211' and x['a']=='512')
case=[dict(x) for x in rows]
for x in case:
    if x['kind']=='220':x['start_s']=x['end_s']=str(float(put_time)-.001)
check_case('reader-before-put',case,0)
case=[dict(x) for x in rows]
for x in case:
    if x['kind']=='220':x['a']='576' # Exact end of [512,576): no overlap.
check_case('half-open-boundary',case,0)
case=[dict(x) for x in rows]
for x in case:
    if x['kind']=='212':x['b']='64' # GET is not an output write.
check_case('get-only',case,0)
check_case('missing-dma-metadata',[x for x in rows if x['kind']!='215'],0,False)
check_case('dropped-records',rows,1,False,metadata.replace('"dropped":0','"dropped":1'))
print('PASS: no future-writer association; half-open ranges; GET exclusion; missing metadata/dropped capture rejection')
