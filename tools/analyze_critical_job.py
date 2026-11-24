#!/usr/bin/env python3
"""Guest-call/job lifetime timing and observed queue overlap; no FPS prediction."""
import argparse,json,re,hashlib
from bisect import bisect_right
from collections import defaultdict,Counter
from pathlib import Path
from analyze_frame_trace import analyze as timeline,stats,union_seconds
from analyze_progress_writers import decode,words
from correlate_progress_cpu import owner_mapping
from analyze_progress_overlap import merged,overlap,length

def scopes(events,meta):
 groups=defaultdict(dict)
 for e in events:
  if 400<=e['kind']<=412 or e['kind']==418:
   if e['kind'] in groups[e['who']]:raise ValueError('Duplicate scope tag/kind')
   groups[e['who']][e['kind']]=e
 calls=[];missing=[]
 for tag,g in groups.items():
  if 418 in g:
   missing.append(dict(id=tag,kinds=sorted(g),start=g[min(g)]['t0'],cancelled=True));continue
  required=set(range(400,410))
  if any(k in g for k in (410,411,412)):required.update((410,411,412))
  if set(g)!=required:
   missing.append(dict(id=tag,kinds=sorted(g),start=g[min(g)]['t0']));continue
  e=g[401];cpu=g[402]['a']+(g[402]['b']<<32)
  logical=bool(e['a']&0x40000000)
  if e['t0']!=g[400]['t0'] or g[404]['a']!=g[404]['b'] or (not logical and g[406]['a']!=g[406]['b']):
   raise ValueError('Guest call did not return to expected PC/depth')
  if not g[408]['b'] or cpu==2**64-1:raise ValueError('Thread CPU clock or native identity invalid')
  calls.append(dict(id=tag,target=hex(e['a']),whole_job=bool(e['a']&0x80000000),entry=e['a']&0x3ffff,spu=e['b'],native_tid=g[403]['a']+(g[403]['b']<<32),context=g[407]['a']+(g[407]['b']<<32),start=e['t0'],end=e['t1'],wall_ms=(e['t1']-e['t0'])*1000,cpu_ms=cpu/1e6,depth=g[406]['a'],return_pc=hex(g[404]['a']),args=[g[405]['a'],g[405]['b']],sampling_denominator=g[408]['a'],boundary=e['t0']<meta['start'] or e['t1']>meta['end'],ovl_start=g[410]['a'] if 410 in g else None,ovl_end=g[410]['b'] if 410 in g else None))
 return calls,missing

def analyze(path):
 base,events=timeline(path);meta=base['metadata'];lo,hi=meta['start'],meta['end']
 calls,missing=scopes(events,meta);complete=[c for c in calls if not c['boundary']]
 registry=Path(__file__).resolve().parents[1]/'build/bces01229/spu/jobmods_register.c'
 entries=defaultdict(list)
 for match in re.finditer(r'spu_begin_image\((\d+)\); (jobmod_\w+)_spu_recomp_register\(\);\s+spu_overlay_register_sig\(sig, \d+\);[^\n]* entry (0x[0-9A-Fa-f]+)',registry.read_text()):
  image,module,entry=match.groups();entries[int(entry,16)].append(dict(image=int(image),module=module))
 for c in complete:
  matches=entries.get(c['entry'],[]) if c['whole_job'] else []
  same=[x for x in matches if x['image']==c['ovl_start']]
  chosen=same if len(same)==1 else matches
  c['module']=chosen[0]['module'] if len(chosen)==1 else None
 root=[c for c in complete if c['whole_job']] or [c for c in complete if c['target']=='0x6b90']
 if any(m['start']<hi-.25 and not m.get('cancelled') for m in missing):raise ValueError('Unclosed scope away from end boundary; inspect capture')
 if not root:raise ValueError('No completed measured root calls; no budget claim')
 by_target=defaultdict(list)
 for c in complete:by_target[c['module'] or c['target']].append(c)
 targets={k:dict(count=len(v),sampling_denominators=sorted({c['sampling_denominator'] for c in v}),inclusive_wall_ms=stats([c['wall_ms'] for c in v]),inclusive_thread_cpu_ms=stats([c['cpu_ms'] for c in v]),inclusive_cpu_sum_ms=sum(c['cpu_ms'] for c in v),inclusive_wall_sum_ms=sum(c['wall_ms'] for c in v),mean_cpu_fraction=sum(c['cpu_ms'] for c in v)/sum(c['wall_ms'] for c in v) if sum(c['wall_ms'] for c in v)>0 else None) for k,v in by_target.items()}
 native_sets=defaultdict(set)
 for e in events:
  if e['kind']==18:native_sets[e['who']&0x7fffffff].add(e['a']+(e['b']<<32))
 for c in complete:native_sets[c['spu']].add(c['native_tid'])
 native={spu:next(iter(tids)) for spu,tids in native_sets.items() if len(tids)==1}
 progress=decode(events,meta)
 if progress['incomplete_groups']:raise ValueError('Incomplete progress groups')
 mapping=owner_mapping(progress,native,True)
 owner={}
 for tid,item in mapping.items():
  for row,lanes in item['rows'].items():
   for lane in lanes:owner[row,int(lane)]=(tid,item['spu_id'])
 changes=defaultdict(list)
 for w in progress['writes']:
  for lane,value in w['lane_values'].items():changes[w['row'],int(lane)].append((w['end'],value))
 times={k:[x[0] for x in v] for k,v in changes.items()}
 poll_groups=defaultdict(dict)
 for e in events:
  if 310<=e['kind']<=313:
   if e['kind'] in poll_groups[e['who']]:raise ValueError('Duplicate poll tag/kind')
   poll_groups[e['who']][e['kind']]=e
 roots_by_spu=defaultdict(list)
 for c in root:roots_by_spu[c['spu']].append(c)
 polls=[];qualified=[];linked=[];linked_modules=defaultdict(list);linked_jobs=[];rejected=Counter()
 for tag,g in poll_groups.items():
  if set(g)!=set(range(310,314)):rejected['incomplete_poll']+=1;continue
  e=g[310];a,b=e['t0'],e['t1'];row=hex(e['a']);target=e['b'];read_end=g[313]['t1']
  if a<lo or b>hi:rejected['boundary_poll']+=1;continue
  polls.append((a,b))
  if target>65535:rejected['unknown_or_wrapped_target']+=1;continue
  if not 0<=g[313]['t0']-b<=.001:rejected['post_read_delayed']+=1;continue
  data=words(g[311]['a'],g[311]['b'])+words(g[312]['a'],g[312]['b'])
  lanes=[int.from_bytes(data[i:i+2],'big') for i in range(0,16,2)]
  lag=[i for i in range(1,8) if lanes[i]<target]
  if len(lag)!=1 or lag[0]<=1:rejected['not_one_private_lagging_lane']+=1;continue
  issuer=owner.get((row,lag[0]))
  if issuer is None:rejected['ambiguous_or_unmapped_issuer']+=1;continue
  stable=True
  for lane in range(1,8):
   key=row,lane;values=changes.get(key,[]);ts=times.get(key,[]);i=bisect_right(ts,a)-1;j=bisect_right(ts,read_end)
   if i<0 or any(v!=lanes[lane] for _,v in values[i:j]):stable=False;break
  if not stable:rejected['observed_lane_change_or_missing_prior_value']+=1;continue
  qualified.append((a,b));tid,spu=issuer;hits=[]
  for c in roots_by_spu[spu]:
   x,y=max(a,c['start']),min(b,c['end'])
   if c['native_tid']==tid and y>x:
    linked.append((x,y));hits.append(c['id']);linked_modules[c['module'] or c['target']].append((x,y))
    linked_jobs.append(dict(job=c['id'],start=x,end=y))
  if not hits:rejected['qualified_but_outside_root_scope']+=1
  else:rejected['qualified_with_root_scope']+=1
 gpu=[(e['t0'],e['t1']) for e in events if e['kind']==15]
 main=[(e['t0'],e['t1']) for e in events if e['kind']==2 and e['who']==1]
 intervals=[(c['start'],c['end']) for c in root];frames=[]
 for f in base['frame_windows']:
  a,b=f['start'],f['end'];r=merged(intervals,a,b);g=merged(gpu,a,b);m=merged(main,a,b)
  frames.append(dict(start=a,end=b,interval_ms=(b-a)*1000,root_all_workers_wall_union_ms=length(r)*1000,root_gpu_overlap_union_ms=overlap(r,g)*1000,root_main_poll_overlap_union_ms=overlap(r,m)*1000,root_unique_issuer_poll_overlap_union_ms=union_seconds(linked,a,b)*1000))
 channel=[(e['who'],e['t0'],e['t1']) for e in events if e['kind']==3]
 for c in root:c['same_spu_channel_wait_union_ms']=union_seconds([(a,b) for who,a,b in channel if who==c['spu']],c['start'],c['end'])*1000
 frame_metrics={k:stats([f[k] for f in frames]) for k in ('interval_ms','root_all_workers_wall_union_ms','root_gpu_overlap_union_ms','root_main_poll_overlap_union_ms','root_unique_issuer_poll_overlap_union_ms')}
 module_dependency={k:dict(observed_qualified_poll_overlap_union_ms=union_seconds(v,lo,hi)*1000,per_guest_frame_ms=stats([union_seconds(v,f['start'],f['end'])*1000 for f in frames])) for k,v in linked_modules.items()}
 result=dict(metadata=meta,scope_definitions={'0x6b90':'8648 call through drain return866C; all calls','0x68d8':'6B90 child through drain return6BD8; all calls','0x5a98':'inner call through drain return6B88; systematic 1/16 samples, no extrapolation'},targets=targets,root_calls=len(root),missing_boundary_scopes=missing,root_spu_channel_wait_ms=stats([c['same_spu_channel_wait_union_ms'] for c in root]),native_issuer_mapping=mapping,poll_counts=dict(total=len(polls),qualified=len(qualified)),poll_rejections=dict(rejected),poll_union_ms=union_seconds(polls,lo,hi)*1000,qualified_poll_union_ms=union_seconds(qualified,lo,hi)*1000,root_linked_qualified_poll_union_ms=union_seconds(linked,lo,hi)*1000,frame_metrics=frame_metrics,frames=frames,limitations=['Inclusive nested timings must not be summed. Host-thread CPU includes nested calls/interrupts; wall minus CPU is not specifically DMA wait.','Root union and GPU/poll overlap are temporal overlap, not milliseconds proven removable from the critical path.','Post-poll queue states are qualified only by observed unchanged SPU lane values and unique issuer evidence; unobserved PPU writes and whole-row snapshot races remain possible.','Only exactly one total lagging lane, private lane>1, >=50 observed increases and99% unique issuer are linked. Rejected/unknown intervals are not extrapolated.','Inner 5A98 is sampled 1/16; no sampled-child total is scaled to all work.','This instrumented trace is a work/dependency diagnosis, not an uninstrumented FPS benchmark or an FPS prediction.'])
 result.update(whole_job_scopes=any(c['whole_job'] for c in root),module_dependency=module_dependency,module_entry_registry_sha256=hashlib.sha256(registry.read_bytes()).hexdigest(),scope_coverage=dict(completed_in_window=len(complete),completed_crossing_boundary=len(calls)-len(complete),cancelled=sum(bool(m.get('cancelled')) for m in missing),unclosed=sum(not m.get('cancelled') for m in missing),mapped_root_modules=len({c['module'] for c in root if c['module']}),unmapped_roots=sum(c['module'] is None for c in root)))
 result['qualified_job_poll_spans'] = linked_jobs
 result['scope_definitions']['0x80000000|entry']='Full WWS guest job call through spu_indirect_branch + drain to3218 and image restoration; all entries, no sampling'
 result['scope_definitions']['0xC0000000|entry']='Logical registered ELF entry through guest CRT return to3218; survives abandoned native continuation; no sampling. Nested runtime/interrupt CPU is inclusive.'
 result['limitations'].append('Only jobs entering while capture is active are timed. Cancelled, unclosed and boundary-crossing jobs are excluded from completed-job budgets; inspect scope_coverage. No event loss does not prove coverage of unregistered or bypassed job implementations.')
 return result,dict(calls=complete,progress=progress)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('trace',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r,detail=analyze(a.trace)
 a.output.write_text(json.dumps(r,indent=2)+'\n');a.output.with_suffix('.details.json').write_text(json.dumps(detail,indent=2)+'\n')
 print(json.dumps({k:r[k] for k in ('targets','poll_counts','root_linked_qualified_poll_union_ms','frame_metrics')},indent=2))
