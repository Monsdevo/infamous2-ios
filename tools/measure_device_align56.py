#!/usr/bin/env python3
"""Separate-build MFC slot-layout A/B/A on a naturally warmed iPhone.

The operator reviews actual game frames and writes scene-ready.json per boot.
No input other than neutral is sent; no game files or saves are replaced.
"""
import argparse,json,os,subprocess,time
from pathlib import Path
from geometry_device_control import report,command
from drive_device_gameplay import pad
from capture_device_frame import capture
from measure_geometry import measure
ROOT=Path(__file__).resolve().parents[1]
ENV=dict(os.environ,DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer')
BUNDLE='dev.infamous2.iosprobe'
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--device',required=True);p.add_argument('--run',type=Path,required=True)
a=p.parse_args();R=a.run.resolve();R.mkdir(parents=True,exist_ok=False)
def state(stage,**fields):
 (R/'state.json').write_text(json.dumps(dict(stage=stage,**fields),indent=2)+'\n')
def device(args,output,timeout=90):
 command=['xcrun','devicectl','--timeout',str(timeout),*args,'--json-output',str(output)]
 r=subprocess.run(command,env=ENV,capture_output=True,text=True,timeout=timeout+10)
 (output.with_suffix('.stdout.txt')).write_text(r.stdout+r.stderr)
 if r.returncode:raise RuntimeError(r.stderr[-2000:]+r.stdout[-1000:])
def guard(d,mode,identity):
 if (d['pid'],d['geometry_control_session'])!=identity:raise RuntimeError('Process/session changed')
 layout=d['mfc_layout'];expected=(640,128,81920) if mode else (528,8,67584)
 if layout['aligned128']!=mode or (layout['slot_bytes'],layout['slot_alignment'],layout['table_bytes'])!=expected or layout['stride_bytes']!=layout['slot_bytes'] or layout['engine_offset']!=8 or layout['engine_bytes']!=520:raise RuntimeError('Wrong actual registry layout')
 if mode and layout['base_mod128']:raise RuntimeError('Actual slot array not aligned')
 if d.get('dma_original_scan_build')!=1 or d['dma_poison']['enabled'] or d['mfc_hint']['mode'] or d['overlay_filter']['mode'] or d['channel_inline']['compiled'] or d['channel_inline']['mode']:raise RuntimeError('Other DMA experiment active')
 if not d['light_mask']['mode']==d['light_far']['enabled']==d['spu_dispatch']['enabled']==1 or not d.get('ssao_depth_cleanup_enabled'):raise RuntimeError('Combined baseline changed')
 if d['light_mask']['faults'] or d['light_mask']['mismatches'] or d['light_far']['faults']:raise RuntimeError('Lighting fault')
 if d.get('cpu_profile_state',0) in (1,2) or d.get('frame_trace_state',0) in (1,2):raise RuntimeError('Profiler active')
 for k in ('vertex','texture'):
  if d.get('renderer_memo',{}).get(k,{}).get('mode',0):raise RuntimeError('Memo active')
def warm(out,mode,identity,required):
 out.mkdir();history=[];start=time.monotonic()
 for i in range(70):
  d=report(a.device,out/f'{i:03}.json');guard(d,mode,identity);v=d['performance'];history.append(d)
  if v['thermal_state']==3:raise RuntimeError('Critical thermal; no optimization comparison')
  recent=[x for x in history if v['sample_monotonic_seconds']-x['performance']['sample_monotonic_seconds']<=65]
  if time.monotonic()-start>=90 and len(recent)>=12 and (required is None or v['thermal_state']==required):
   steady=all(x['performance']['thermal_state']==v['thermal_state'] and x['performance']['application_active'] and not x['performance']['settings_panel_open'] and not x['performance']['low_power_mode'] and x['performance']['pipeline_started']==v['pipeline_started'] and bool(x.get('runtime_log_capped'))==bool(d.get('runtime_log_capped')) for x in recent)
   groups=[recent[:len(recent)//3],recent[len(recent)//3:2*len(recent)//3],recent[2*len(recent)//3:]];fps=[]
   for g in groups:
    x,y=g[0]['performance'],g[-1]['performance'];seconds=y['present_time']-x['present_time']
    if seconds>=12:fps.append((y['present_total']-x['present_total'])/seconds)
   if steady and len(fps)==3 and min(fps)>0 and max(fps)/min(fps)<=1.08:
    (out/'steady.json').write_text(json.dumps(dict(thermal=v['thermal_state'],recent_fps=fps,seconds=time.monotonic()-start),indent=2)+'\n');return d
  time.sleep(4)
 raise RuntimeError('Natural workload did not stabilize within bounded warmup')
results=[];thermal=None
try:
 for label,mode in (('A',0),('B',1),('C',0)):
  out=R/(label+('-aligned' if mode else '-base'));out.mkdir();state('installing',label=label,mode=mode)
  app=ROOT/'build/bces01229/baselines'/('align56-aligned' if mode else 'align56-reference')/'Infamous2Game.app'
  device(['device','install','app','--device',a.device,str(app)],out/'install.json')
  env={'PS3_PAD_FILE':'../ios48-pad.txt','PS3RECOMP_METAL_FRAME_DUMP':'../critical45-frame.ppm','PS3RECOMP_METAL_FRAME_DUMP_TRIGGER':'../critical45-frame-request.txt'}
  launch=['device','process','launch','--device',a.device,'--terminate-existing','--environment-variables',json.dumps(env),BUNDLE,'--boot','--geometry-control','--renderer-memo-control','--light-far-control','--spu-dispatch-control','--light-mask-control','--dma-poison-control','--mfc-hint-control','--overlay-filter-control','--channel-inline-control','--rsx-legacy-on']
  # Global options must precede the bundle; otherwise the app receives them.
  launch[launch.index(BUNDLE):launch.index(BUNDLE)]=['--json-output',str(out/'launch.json')]
  r=subprocess.run(['xcrun','devicectl','--timeout','30',*launch],env=ENV,capture_output=True,text=True,timeout=40)
  (out/'launch.stdout.txt').write_text(r.stdout+r.stderr)
  if r.returncode:raise RuntimeError(r.stderr+r.stdout)
  launch_pid=json.loads((out/'launch.json').read_text())['result']['process']['processIdentifier']
  state('booting',label=label,mode=mode,pid=launch_pid);pad(a.device,out,'');time.sleep(45)
  for i in range(3):
   d=report(a.device,out/f'boot-{i}.json')
   if d['pid']==launch_pid and d.get('game_booted') and d.get('mfc_layout'):break
   time.sleep(10)
  else:raise RuntimeError('No fresh boot report')
  identity=(d['pid'],d['geometry_control_session']);guard(d,mode,identity)
  capture(a.device,out/'scene-0','Documents/critical45-frame-request.txt','Documents/critical45-frame.ppm');time.sleep(10)
  capture(a.device,out/'scene-1','Documents/critical45-frame-request.txt','Documents/critical45-frame.ppm')
  state('awaiting-scene-review',label=label,mode=mode,pid=identity[0],session=identity[1],directory=str(out))
  start=time.monotonic()
  while not (out/'scene-ready.json').exists():
   if time.monotonic()-start>420:raise RuntimeError('Scene review missing; no benchmark')
   time.sleep(2)
  proof=json.loads((out/'scene-ready.json').read_text())
  if (proof['pid'],proof['session'])!=identity or not proof['free_gameplay_verified'] or not proof['neutral_input']:raise RuntimeError('Unverified scene')
  state('warming',label=label,mode=mode);d=warm(out/'warm',mode,identity,thermal)
  if thermal is None:thermal=d['performance']['thermal_state']
  cap=bool(d.get('runtime_log_capped'))
  def check(d,first):
   try:guard(d,mode,identity)
   except RuntimeError as error:return [str(error)]
   errors=[]
   if bool(d.get('runtime_log_capped'))!=cap:errors.append('Log condition changed')
   if first and d['light_mask']['validations']!=first['light_mask']['validations']:errors.append('Validation active')
   return errors
  state('measuring',label=label,mode=mode,thermal=thermal)
  r=measure(a.device,(0,0),False,out/'measurement',proof['scene']+', separate-build natural warmup',30,120,75,thermal,False,check)
  r.update(aligned128=mode,runtime_log_capped=cap)
  (out/'summary.json').write_text(json.dumps(r,indent=2)+'\n')
  if not r['valid']:raise RuntimeError(r['failure'])
  files=sorted((out/'measurement').glob('[0-9][0-9][0-9].json'))[:r['samples']];x,y=[json.loads(z.read_text()) for z in (files[0],files[-1])]
  if any(y[k]<=x[k] for k in ('metal_lighting_passes','metal_ssao_passes')):raise RuntimeError('Missing real compute coverage')
  results.append(r)
  (R/'partial.json').write_text(json.dumps(results,indent=2)+'\n')
  state('window-complete',label=label,mode=mode,fps=r['raw_frame_stats']['fps'])
 base=sum(x['raw_frame_stats']['frame_intervals'] for x in results if not x['aligned128'])/sum(x['raw_frame_stats']['present_seconds'] for x in results if not x['aligned128'])
 fast=results[1]['raw_frame_stats']['fps'];summary=dict(valid=True,baseline_fps=base,aligned_fps=fast,baseline_ms=1000/base,aligned_ms=1000/fast,gain_percent=(fast/base-1)*100,thermal_state=thermal,windows=results,scope='Three fresh processes, same saved scene and compiler; fixed thermal label does not prove equal clocks. No hot per-call experiment switches.')
 if len({x['runtime_log_capped'] for x in results})!=1:raise RuntimeError('Log conditions differ across builds')
 (R/'comparison.json').write_text(json.dumps(summary,indent=2)+'\n');state('complete',**{k:v for k,v in summary.items() if k!='windows'})
except Exception as error:
 state('failed',error=str(error),completed_windows=len(results));raise
