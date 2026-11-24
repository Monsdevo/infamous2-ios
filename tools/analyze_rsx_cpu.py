#!/usr/bin/env python3
"""UUID-checked renderer CPU attribution from a completed recording; no device IO."""
import argparse,csv,json,hashlib,subprocess,tempfile,re
from pathlib import Path
from collections import Counter
p=argparse.ArgumentParser();p.add_argument('--profile',required=True);p.add_argument('--binary',required=True);p.add_argument('--tid');p.add_argument('--output',required=True);a=p.parse_args()
profile,binary=Path(a.profile),Path(a.binary)
with profile.open() as f:meta=json.loads(f.readline()[2:]);all_rows=list(csv.DictReader(f))
assert len(all_rows)==meta['rows'] and not meta['errors'] and not meta['truncated']
rows=[r for r in all_rows if a.tid is None or r['thread_id']==a.tid]
uuid_text=subprocess.check_output(['xcrun','dwarfdump','--uuid',str(binary)],text=True)
assert meta['uuid'].lower() in uuid_text.lower()
base,end=meta['app_base'],meta['app_end'];offsets=sorted({int(v,16)-base for r in rows for v in r['pcs'].split(';') if base<=int(v,16)<end})
with tempfile.TemporaryDirectory() as temp:
 addresses=Path(temp)/'offsets.txt';addresses.write_text(''.join(hex(v)+'\n' for v in offsets))
 names=subprocess.check_output(['xcrun','atos','-arch','arm64','-o',str(binary),'--offset','-f',str(addresses)],text=True).splitlines()
assert len(names)==len(offsets)
symbols={offset:name.split(' (in ')[0] for offset,name in zip(offsets,names)}
if a.tid is None:
 clocks=Counter()
 for row in rows:
  if row['state']!='1':continue
  stack=[symbols.get(int(v,16)-base,'') for v in row['pcs'].split(';')]
  if any('frame_clock' in name for name in stack):clocks[row['thread_id']]+=1
 if not clocks:raise ValueError('No frame_clock ancestry: renderer thread cannot be assigned safely')
 a.tid=clocks.most_common(1)[0][0];rows=[r for r in rows if r['thread_id']==a.tid]
else:clocks=Counter()
running=[r for r in rows if r['state']=='1'];delta=(int(rows[-1]['cpu_us'])-int(rows[0]['cpu_us']))/1e6;weight=delta/len(running)
exclusive=Counter();system_callers=Counter();ancestry=Counter()
for row in running:
 pcs=[int(v,16) for v in row['pcs'].split(';')];leaf=symbols.get(pcs[0]-base,'<system/unresolved>');exclusive[leaf]+=weight
 app=[symbols[v-base] for v in pcs if v-base in symbols]
 for name in set(app):ancestry[name]+=weight
 if leaf=='<system/unresolved>':system_callers[app[0] if app else '<unknown>']+=weight
rank=lambda c:[{'function':n,'estimated_cpu_seconds':v,'percent_of_thread_cpu':100*v/delta} for n,v in c.most_common()]
result={'method':'Completed CPU recording, UUID-checked; per-thread CPU delta weighted evenly over running PC samples. Analysis does not capture new data.','profile':str(profile.resolve()),'profile_sha256':hashlib.sha256(profile.read_bytes()).hexdigest(),'binary':str(binary.resolve()),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'binary_uuid':meta['uuid'],'metadata':meta,'thread_id':a.tid,'frame_clock_samples_by_tid':dict(clocks),'thread_sampled_wall_seconds':float(rows[-1]['monotonic_s'])-float(rows[0]['monotonic_s']) if 'monotonic_s' in rows[0] else None,'samples':len(rows),'running_pc_samples':len(running),'thread_observed_cpu_seconds':delta,'sample_weight_seconds':weight,'window_wall_seconds':meta['end']-meta['start'],'exclusive':rank(exclusive),'system_leaf_first_app_ancestor_do_not_add':rank(system_callers),'inclusive_ancestry_do_not_sum':rank(ancestry),'limitations':['This is a profiler-active window, not an FPS benchmark; scene confirmation is external.','TH_STATE_RUNNING includes runnable; CPU-time deltas are real but per-function attribution is statistical.','Unsuspended FP ancestry may be truncated or inconsistent.','System leaf ancestry is explanatory only, not an additional disjoint cost.','Do not divide aggregate multi-thread Edge CPU by renderer frame intervals to claim critical path savings.','Cross-window approximate renderer CPU per frame is not an exact timeline critical path.']}
Path(a.output).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['thread_id','thread_observed_cpu_seconds','running_pc_samples','window_wall_seconds']},indent=2))
