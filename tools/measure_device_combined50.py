#!/usr/bin/env python3
"""Build50 combined profile; GPU mask equivalence then same-process A/B/A."""
import argparse,json,time
from pathlib import Path
from geometry_device_control import report,command
from measure_geometry import measure
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device',required=True);p.add_argument('--run',type=Path,required=True);a=p.parse_args();run=a.run;run.mkdir(parents=True,exist_ok=True)
proof_path=run/'tutorial/scene-ready.json';deadline=time.monotonic()+1500
while not proof_path.exists():
 if time.monotonic()>deadline:raise RuntimeError('scene proof deadline')
 time.sleep(2)
proof=json.loads(proof_path.read_text());initial=report(a.device,run/'initial.json');ready=quiet=time.monotonic();last=initial['performance']['pipeline_started']
while time.monotonic()-ready<30 or time.monotonic()-quiet<15:
 d=report(a.device,run/'warm.json');now=d['performance']['pipeline_started']
 if now!=last:last=now;quiet=time.monotonic()
 if time.monotonic()>deadline:raise RuntimeError('warmup deadline')
 time.sleep(3)
# All advanced geometry remains original SPU; no profiling/capture in windows.
before=command(a.device,{'skin':0,'cull':0,'validation':False,'light_mask':2,'light_far':1,'spu_dispatch':1},run/'validate-command')
time.sleep(15);after=report(a.device,run/'validation-after.json');m=after['light_mask'];n=m['validations']-before['light_mask']['validations'];tiles=m['compared_tiles']-before['light_mask']['compared_tiles']
valid=m['mode']==2 and not m['faults'] and not m['mismatches'] and n>=20 and tiles>=14400
(run/'mask-validation.json').write_text(json.dumps(dict(valid=valid,passes=n,tiles=tiles,before=before,after=after),indent=2)+'\n')
if not valid:raise RuntimeError('iPhone mask equivalence failed or insufficient coverage; no FPS claim')
results=[]
try:
 for i,on in enumerate((1,0,1)):
  fields={'light_mask':on,'light_far':on,'spu_dispatch':on}
  command(a.device,fields,run/('switch-'+str(i)));time.sleep(10)
  d=report(a.device,run/('pre-'+str(i)+'.json'));thermal=d['performance']['thermal_state']
  if thermal>1:raise RuntimeError('Phone serious/critical: cool before measuring')
  def check(d,first):
   e=[];mask=d.get('light_mask',{});far=d.get('light_far',{});dispatch=d.get('spu_dispatch',{})
   if (d.get('pid'),d.get('geometry_control_session'))!=(proof['pid'],proof['session']):e.append('scene/process changed')
   if mask.get('mode')!=on or mask.get('faults') or mask.get('mismatches'):e.append('mask differs/faulted')
   if far.get('enabled')!=on or far.get('faults'):e.append('far differs/faulted')
   if dispatch.get('enabled')!=on:e.append('dispatch differs')
   if not d.get('ssao_depth_cleanup_enabled'):e.append('SSAO cleanup disabled')
   if d.get('cpu_profile_state',0) in (1,2) or d.get('frame_trace_state',0) in (1,2):e.append('profiler active')
   for k in ('vertex','texture'):
    if d.get('renderer_memo',{}).get(k,{}).get('mode',0):e.append('memo active')
   if first:
    if mask['validations']!=first['light_mask']['validations']:e.append('mask validation during FPS window')
    if d.get('runtime_log_capped')!=first.get('runtime_log_capped'):e.append('log cap transition')
   return e
  out=run/(chr(65+i)+('-combined' if on else '-base'))
  r=measure(a.device,(0,0),False,out,'first-free-gameplay verified fixed camera',45,180,100,thermal,False,check)
  r['combined']=on
  files=sorted(out.glob('[0-9][0-9][0-9].json'))[:r['samples']]
  if len(files)>1:
   first,last=[json.loads(f.read_text()) for f in (files[0],files[-1])]
   r['path_deltas']={k:{x:last[k][x]-first[k][x] for x in keys} for k,keys in [('light_mask',['fast','reference','validations','faults']),('light_far',['fast','reference','faults']),('spu_dispatch',['fast','fallback','reset_bypasses'])]}
   for k in ('light_mask','light_far'):
    wanted='fast' if on else 'reference';other='reference' if on else 'fast'
    if r['path_deltas'][k][wanted]<=0 or r['path_deltas'][k][other]:r.update(valid=False,failure=k+' executed coverage differs')
   for k in ('metal_lighting_passes','metal_ssao_passes'):
    if last.get(k,0)<=first.get(k,0):r.update(valid=False,failure=k+' missing execution')
  (out/'summary.json').write_text(json.dumps(r,indent=2)+'\n');results.append(r)
  if not r['valid']:raise RuntimeError(r['failure'])
 if len({tuple(r['thermal_states']) for r in results})!=1:raise RuntimeError('thermal categories differ; no combined gain claim')
 fps=lambda mode:sum(r['raw_frame_stats']['frame_intervals'] for r in results if r['combined']==mode)/sum(r['raw_frame_stats']['present_seconds'] for r in results if r['combined']==mode)
 base,combined=fps(0),fps(1);summary=dict(valid=True,baseline_fps=base,combined_fps=combined,baseline_ms=1000/base,combined_ms=1000/combined,gain_percent=(combined/base-1)*100,windows=results,scope='Physical iPhone display presentations; single fixed scene. Baseline retains O2, Metal lighting/SSAO and SSAO cleanup. Same thermal class does not guarantee identical clocks.')
 (run/'comparison.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k!='windows'},indent=2),flush=True)
finally:
 command(a.device,{'light_mask':1,'light_far':1,'spu_dispatch':1},run/'restore-combined')
