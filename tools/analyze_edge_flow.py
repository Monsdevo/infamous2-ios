#!/usr/bin/env python3
"""Coarse Edge spans and temporal buffer-range associations, not a GPU proof."""
import argparse,csv,json,hashlib
from collections import defaultdict,Counter
from pathlib import Path
from analyze_frame_trace import union_seconds,stats

def analyze(path):
    with path.open() as f:
        meta=json.loads(next(f).lstrip('# '));raw=list(csv.DictReader(f))
    rows=[{k:(float(v) if k.endswith('_s') else int(v)) for k,v in r.items()} for r in raw]
    groups=defaultdict(dict)
    for r in rows:
        if 200<=r['kind']<=222 and r['kind']!=209:groups[r['who']][r['kind']]=r
    lo,hi=meta['start'],meta['end'];calls=[];incomplete=Counter();descriptors=Counter()
    for r in rows:
        if r['kind']==209:descriptors[r['who']]+=1
    for tag,g in groups.items():
        if 200 not in g:continue
        if any(k not in g for k in range(200,209)):incomplete['call']+=1;continue
        r=g[200];a,b=r['start_s'],r['end_s'];cpu=g[201]['a']+(g[201]['b']<<32)
        calls.append({'id':tag,'target':f"0x{r['a']:04X}",'spu':r['b'],'start':a,'end':b,'wall_ms':1000*(b-a),
            'thread_cpu_ms':None if cpu==2**64-1 else cpu/1e6,'native_tid':g[203]['a']+(g[203]['b']<<32),
            'return_pc':hex(g[202]['a']),'host_depth':g[202]['b']&0x7fffffff,'detail_sampled':bool(g[202]['b']&0x80000000),'boundary':a<lo or b>hi,
            'args_r3_r10':[g[k][p] for k in range(204,208) for p in ('a','b')],
            'return_r3_r4':[g[208]['a'],g[208]['b']]})
    completed={c['id']:c for c in calls};dmas=[];readers=[]
    for tag,g in groups.items():
        if 211 in g:
            if any(k not in g for k in range(211,216)):incomplete['dma']+=1;continue
            r=g[211];cmd=g[212]['b'];ea=r['a']+(g[215]['a']<<32)
            dmas.append({'id':tag,'job':g[213]['a'],'spu':g[213]['b'],'time':r['end_s'],'ea':ea,'size':r['b'],
                         'lsa':g[212]['a'],'cmd':cmd,'direction':'GET' if cmd&0x40 else 'PUT' if cmd&0x20 else 'other',
                         'pc':hex(g[214]['a']),'lr':hex(g[214]['b']),'image':g[215]['b']})
        if 220 in g:
            if 221 not in g or 222 not in g:incomplete['reader']+=1;continue
            r=g[220];readers.append({'id':tag,'time':r['end_s'],'ea':r['a'],'size':r['b'],'kind':g[221]['a'],'location':g[221]['b'],'offset':g[222]['a'],'sampling_denominator':g[222]['b'] or 1})
    by_target=defaultdict(list)
    for c in calls:
        if not c['boundary']:by_target[c['target']].append(c)
    summaries={target:{'count':len(cs),'inclusive_wall_ms':stats([c['wall_ms'] for c in cs]),
        'inclusive_thread_cpu_ms':stats([c['thread_cpu_ms'] for c in cs if c['thread_cpu_ms'] is not None]),
        'inclusive_wall_sum_ms_do_not_sum_targets':sum(c['wall_ms'] for c in cs),
        'inclusive_thread_cpu_sum_ms_do_not_sum_targets':sum(c['thread_cpu_ms'] or 0 for c in cs)} for target,cs in by_target.items()}
    def completed_job_dma(d):
        c=completed.get(d['job'])
        return c is not None and c['target']=='0xE2A0' and not c['boundary'] and c['start']<=d['time']<=c['end']
    puts=sorted([d for d in dmas if d['direction']=='PUT' and completed_job_dma(d)],key=lambda d:d['time']);matches=[]
    # Sparse page index avoids quadratic comparisons across unrelated DMA buffers.
    pages=defaultdict(list)
    for p in puts:
        for page in range(p['ea']//4096,(p['ea']+p['size']+4095)//4096):pages[page].append(p)
    for r in readers:
        candidates={p['id']:p for page in range(r['ea']//4096,(r['ea']+r['size']+4095)//4096) for p in pages[page]}
        overlaps=[p for p in candidates.values() if p['time']<=r['time'] and p['ea']<r['ea']+r['size'] and r['ea']<p['ea']+p['size']]
        if not overlaps:continue
        p=max(overlaps,key=lambda x:x['time'])
        matches.append({'reader':r['id'],'kind':r['kind'],'put':p['id'],'job':p['job'],
            'overlap_bytes':min(p['ea']+p['size'],r['ea']+r['size'])-max(p['ea'],r['ea']),
            'lag_ms':1000*(r['time']-p['time']),'put_ea':hex(p['ea']),'reader_ea':hex(r['ea'])})
    jobs=[c for c in calls if c['target']=='0xE2A0'];presents=sorted(r['start_s'] for r in rows if r['kind']==9 and lo+.25<=r['start_s']<=hi-.25)
    full_jobs=[c for c in jobs if not c['boundary']]
    native_jobs=defaultdict(list)
    for c in full_jobs:native_jobs[c['native_tid']].append(c)
    native_summary={str(t):{'jobs':len(cs),'inclusive_thread_cpu_sum_ms':sum(c['thread_cpu_ms'] or 0 for c in cs),
        'job_wall_union_ms':1000*union_seconds([(c['start'],c['end']) for c in cs],lo,hi)} for t,cs in native_jobs.items()}
    detailed_jobs=[c for c in full_jobs if c['detail_sampled']];sampled_cpu=sum(c['thread_cpu_ms'] or 0 for c in detailed_jobs)
    by_native=defaultdict(list)
    for c in detailed_jobs:by_native[c['native_tid']].append(c)
    sampled_children=defaultdict(float)
    for c in calls:
        if c['target']=='0xE2A0' or c['boundary']:continue
        if any(p['start']<=c['start'] and c['end']<=p['end'] for p in by_native[c['native_tid']]):sampled_children[c['target']]+=c['thread_cpu_ms'] or 0
    frames=[{'frame_ms':1000*(b-a),'edge_job_union_ms':1000*union_seconds([(c['start'],c['end']) for c in jobs],a,b)} for a,b in zip(presents,presents[1:]) if b>a]
    result={'metadata':meta,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'incomplete_record_groups':dict(incomplete),
        'valid_recording':meta.get('dropped',0)==0 and not incomplete,'targets':summaries,'complete_job_spans':len(jobs),
        'thread_cpu_unavailable_calls':sum(c['thread_cpu_ms'] is None for c in calls),
        'thread_cpu_exceeds_wall_by_over_0_1ms_calls':sum(c['thread_cpu_ms'] is not None and c['thread_cpu_ms']>c['wall_ms']+.1 for c in calls),
        'job_native_threads':sorted({c['native_tid'] for c in jobs}),'dma_count':len(dmas),
        'jobs_with_detail_sampling':sum(c['detail_sampled'] for c in jobs),
        'complete_nonboundary_jobs':len(full_jobs),'root_jobs_by_native_thread':native_summary,
        'sampled_complete_job_thread_cpu_ms':sampled_cpu,
        'child_inclusive_share_of_sampled_root_cpu_do_not_sum':{target:100*v/sampled_cpu for target,v in sampled_children.items()} if sampled_cpu else {},
        'dma_counts':dict(Counter(d['direction'] for d in dmas)),
        'dma_bytes':{k:sum(d['size'] for d in dmas if d['direction']==k) for k in ('GET','PUT')},
        'dma_without_completed_job':sum(d['job'] not in completed for d in dmas),
        'puts_eligible_for_range_association':len(puts),
        'renderer_read_count':len(readers),'renderer_reads_with_prior_edge_put_overlap':len(matches),
        'matched_reader_kinds':dict(Counter(m['kind'] for m in matches)),
        'matched_unique_puts':len({m['put'] for m in matches}),'matched_read_lag_ms':stats([m['lag_ms'] for m in matches]),
        'descriptors_captured':dict(descriptors),'frames':frames,'frame_edge_job_union_ms':stats([f['edge_job_union_ms'] for f in frames]),
        'limitations':['Inclusive spans overlap; do not add targets or CPU/wall columns.',
          'All root job spans are requested; child calls/DMA use first-eight then deterministic hash 1/16 job sampling. No extrapolated child totals.',
          'Renderer requests use first-eight then deterministic hash 1/64 sampling. Associations are positive examples, not coverage percentages.',
          'Association lag is between sampled events; it is not first-consumption latency or producer stall time.',
          'Thread CPU includes nested calls/interrupt work on the same native thread.',
          'Edge wall union is overlap with a frame, not causal critical-path delay.',
          'Range association uses latest overlapping recorded Edge PUT; other writers and PPU readers are not completely tracked.',
          'Only PUTs inside a completed non-boundary Edge job are eligible for association.',
          'Vertex kind1/index kind2 are CPU renderer read requests, not GPU execution or full buffer equivalence.',
          'No matched consumer does not prove GPU-only use or unused output.']}
    return result,{'calls':calls,'dmas':dmas,'readers':readers,'range_associations':matches}

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('trace',type=Path);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    result,details=analyze(args.trace);args.output.write_text(json.dumps(result,indent=2)+'\n')
    args.output.with_suffix('.details.json').write_text(json.dumps(details,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('metadata','frames','limitations')},indent=2))
