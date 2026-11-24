#!/usr/bin/env python3
"""iPhone only: isolate post-copy diagnostic poison scan from combined profile."""
import argparse,json,time
from pathlib import Path
from geometry_device_control import report,command
from measure_geometry import measure
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device',required=True);p.add_argument('--run',type=Path,required=True);a=p.parse_args();run=a.run;run.mkdir(parents=True,exist_ok=True);deadline=time.monotonic()+1500
proof_path=run/'tutorial/scene-ready.json'
while not proof_path.exists():
 if time.monotonic()>deadline:raise RuntimeError('scene deadline')
 time.sleep(2)
proof=json.loads(proof_path.read_text());d=command(a.device,{'skin':0,'cull':0,'validation':False,'dma_poison_skip':0,'light_mask':1,'light_far':1,'spu_dispatch':1},run/'initial-control')
ready=quiet=time.monotonic();last=d['performance']['pipeline_started']
while time.monotonic()-ready<30 or time.monotonic()-quiet<15:
 d=report(a.device,run/'warm.json');now=d['performance']['pipeline_started']
 if now!=last:last=now;quiet=time.monotonic()
 if time.monotonic()>deadline:raise RuntimeError('warmup deadline')
 time.sleep(3)
results=[]
try:
 for i,on in enumerate((0,1,0,1,0)):
  command(a.device,{'dma_poison_skip':on},run/('switch-'+str(i)));time.sleep(10)
  before=report(a.device,run/('pre-'+str(i)+'.json'));thermal=before['performance']['thermal_state']
  if thermal>1:raise RuntimeError('iPhone serious/critical; cooling required before measurement')
  def check(d,first):
   e=[];s=d.get('dma_poison',{})
   if (d.get('pid'),d.get('geometry_control_session'))!=(proof['pid'],proof['session']):e.append('scene/process changed')
   if not d.get('dma_poison_control_enabled') or s.get('enabled')!=on or s.get('forced') or s.get('sample_period')!=256:e.append('DMA mode/control differs or forced diagnostics active')
   m=d.get('light_mask',{});f=d.get('light_far',{})
   if m.get('mode')!=1 or m.get('faults') or m.get('mismatches') or f.get('enabled')!=1 or f.get('faults') or d.get('spu_dispatch',{}).get('enabled')!=1:e.append('combined profile differs/faulted')
   if not d.get('ssao_depth_cleanup_enabled'):e.append('SSAO cleanup disabled')
   if d.get('cpu_profile_state',0) in (1,2) or d.get('frame_trace_state',0) in (1,2):e.append('profiler active')
   if first and m.get('validations')!=first.get('light_mask',{}).get('validations'):e.append('mask validation active during FPS window')
   if first and d.get('runtime_log_capped')!=first.get('runtime_log_capped'):e.append('log cap transition')
   for k in ('vertex','texture'):
    if d.get('renderer_memo',{}).get(k,{}).get('mode',0):e.append('memo active')
   return e
  out=run/(chr(65+i)+('-skip' if on else '-scan'))
  r=measure(a.device,(0,0),False,out,'same first-free-gameplay camera',30,180,90,thermal,False,check);r['dma_poison_skip']=on
  files=sorted(out.glob('[0-9][0-9][0-9].json'))[:r['samples']]
  if len(files)>1:
   first,last=[json.loads(f.read_text()) for f in (files[0],files[-1])]
   fields=('sampled_scanned','sampled_skipped','sampled_bytes_scanned','sampled_bytes_skipped')
   delta={k:last['dma_poison'][k]-first['dma_poison'][k] for k in fields};r['dma_sample_deltas']=delta
   wanted='sampled_skipped' if on else 'sampled_scanned';other='sampled_scanned' if on else 'sampled_skipped'
   if delta[wanted]<=0 or delta[other]:r.update(valid=False,failure='DMA sampled path coverage differs')
   for k in ('metal_lighting_passes','metal_ssao_passes'):
    if last.get(k,0)<=first.get(k,0):r.update(valid=False,failure=k+' lacks coverage')
  (out/'summary.json').write_text(json.dumps(r,indent=2)+'\n');results.append(r)
  if not r['valid']:raise RuntimeError(r['failure'])
 if len({tuple(r['thermal_states']) for r in results})!=1:raise RuntimeError('thermal categories differ; no gain claim')
 fps=lambda mode:sum(r['raw_frame_stats']['frame_intervals'] for r in results if r['dma_poison_skip']==mode)/sum(r['raw_frame_stats']['present_seconds'] for r in results if r['dma_poison_skip']==mode)
 ref,fast=fps(0),fps(1);summary=dict(valid=True,reference_fps=ref,candidate_fps=fast,reference_ms=1000/ref,candidate_ms=1000/fast,gain_percent=(fast/ref-1)*100,windows=results,scope='Actual iPhone presented intervals, same process/camera. Combined build50 paths stay on. New path counters sampled at 1/256 in both arms; counts are not exact PUT totals. Single-scene pilot; thermal class does not guarantee identical clocks.')
 (run/'comparison.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k!='windows'},indent=2),flush=True)
finally:
 try:command(a.device,{'dma_poison_skip':0},run/'restore-reference')
 except RuntimeError as e:(run/'cleanup-error.txt').write_text(str(e)+'\n')
