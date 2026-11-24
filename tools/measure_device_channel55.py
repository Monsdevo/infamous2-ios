#!/usr/bin/env python3
"""Uncooled iPhone channel inline A/B/A (optionally A/B/A/B/A) after natural warmup."""
import argparse,json,time
from pathlib import Path
from geometry_device_control import report,command
from measure_geometry import measure
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device',required=True);p.add_argument('--run',required=True,type=Path)
p.add_argument('--windows',type=int,choices=(3,5),default=3);p.add_argument('--warmup-seconds',type=int,default=90)
a=p.parse_args();R=a.run;R.mkdir(exist_ok=True,parents=True)
if a.warmup_seconds<60:p.error('Warmup must be at least 60 seconds')
deadline=time.monotonic()+1500;proof=R/'tutorial/scene-ready.json'
while not proof.exists():
 if time.monotonic()>deadline:raise RuntimeError('No verified gameplay scene')
 time.sleep(2)
identity=json.loads(proof.read_text());all_windows=[]
def send(fields,path):return command(a.device,fields,R/path)
def guard(d):
 if (d['pid'],d['geometry_control_session'])!=(identity['pid'],identity['session']):raise RuntimeError('Scene process changed')
 if not d.get('channel_inline_control_enabled') or not d.get('channel_inline',{}).get('compiled'):raise RuntimeError('Channel inline experiment missing')
 if d['channel_inline']['mismatches'] or d['channel_inline']['forced']:raise RuntimeError('Channel diagnostic forced or mismatch; no FPS claim')
 if d.get('dma_original_scan_build')!=1 or d['dma_poison']['enabled'] or d.get('mfc_hint',{}).get('mode') or d.get('overlay_filter',{}).get('mode'):raise RuntimeError('DMA/MFC baseline differs')
 if d['light_mask']['mode']!=1 or d['light_far']['enabled']!=1 or d['spu_dispatch']['enabled']!=1 or not d.get('ssao_depth_cleanup_enabled'):raise RuntimeError('Combined baseline differs')
def warm(path):
 start=time.monotonic();history=[];output=R/path;output.mkdir()
 for i in range(240):
  d=report(a.device,output/f'{i:03}.json');guard(d);v=d['performance'];history.append(d)
  if v['thermal_state']==3:raise RuntimeError('Critical thermal state; stress result retained, no optimization comparison')
  recent=[x for x in history if v['sample_monotonic_seconds']-x['performance']['sample_monotonic_seconds']<=65]
  if time.monotonic()-start>=a.warmup_seconds and len(recent)>=12:
   steady=all(x['performance']['thermal_state']==v['thermal_state'] and x['performance']['application_active'] and not x['performance']['settings_panel_open'] and not x['performance']['low_power_mode'] and x['performance']['pipeline_started']==v['pipeline_started'] and bool(x.get('runtime_log_capped'))==bool(d.get('runtime_log_capped')) for x in recent)
   groups=[recent[:len(recent)//3],recent[len(recent)//3:2*len(recent)//3],recent[2*len(recent)//3:]];fps=[]
   for g in groups:
    x,y=g[0]['performance'],g[-1]['performance'];seconds=y['present_time']-x['present_time']
    if seconds>=12:fps.append((y['present_total']-x['present_total'])/seconds)
   if steady and len(fps)==3 and min(fps)>0 and max(fps)/min(fps)<=1.08:
    (output/'steady.json').write_text(json.dumps(dict(valid=True,thermal=v['thermal_state'],recent_fps=fps,warmup_seconds=time.monotonic()-start,scope='Natural uncooled steady-state screen; thermal label is coarse, clocks unmeasured'),indent=2)+'\n');return d
  time.sleep(4)
 raise RuntimeError('Natural workload did not stabilize; no comparison')
def validate(path):
 x=send({'channel_inline':2},path+'-start');time.sleep(3);y=report(a.device,R/(path+'-after.json'));guard(y)
 counts=[b-a for a,b in zip(x['channel_inline']['counts'],y['channel_inline']['counts'])]
 checks=y['channel_inline']['parameter_read_checks']-x['channel_inline']['parameter_read_checks']
 valid=y['channel_inline']['mode']==2 and not y['channel_inline']['forced'] and checks>=100 and all(counts[i]>0 for i in (0,2,3,4,5,6,7,8)) and not y['channel_inline']['mismatches']
 (R/(path+'.json')).write_text(json.dumps(dict(valid=valid,counts=counts,parameter_read_checks=checks,mismatches=y['channel_inline']['mismatches'],scope='Parameters/read checked live; side-effectful Cmd/tag-update executed once, state-equivalence covered in native fixture'),indent=2)+'\n');send({'channel_inline':0},path+'-off')
 if not valid:raise RuntimeError('Missing actual channel coverage or parameter/read mismatch')

try:
 send(dict(skin=0,cull=0,validation=False,dma_poison_skip=0,mfc_hint=0,overlay_filter=0,channel_inline=0,light_mask=1,light_far=1,spu_dispatch=1),'initial')
 validate('oracle-before')
 for trial in range(2):
  d=warm('warm-'+str(trial));thermal=d['performance']['thermal_state'];cap=bool(d.get('runtime_log_capped'));results=[];failure=None
  for i,mode in enumerate((0,1,0,1,0)[:a.windows]):
   send({'channel_inline':mode},f'trial{trial}-switch{i}');time.sleep(10)
   def check(d,first):
    try:guard(d)
    except RuntimeError as error:return [str(error)]
    e=[]
    if d['channel_inline']['mode']!=mode:e.append('channel mode differs')
    if bool(d.get('runtime_log_capped'))!=cap:e.append('log condition changed')
    if d.get('cpu_profile_state',0) in (1,2) or d.get('frame_trace_state',0) in (1,2):e.append('profiler active')
    if d['light_mask']['faults'] or d['light_mask']['mismatches'] or d['light_far']['faults']:e.append('lighting fault')
    for k in ('vertex','texture'):
     if d.get('renderer_memo',{}).get(k,{}).get('mode',0):e.append('memo active')
    if first:
     if any(d['channel_inline'][k]!=first['channel_inline'][k] for k in ('counts','parameter_read_checks','mismatches')):e.append('channel validation active')
     if d['light_mask']['validations']!=first['light_mask']['validations']:e.append('mask validation active')
    return e
   out=R/(f'trial{trial}-'+chr(65+i)+('-inline' if mode else '-base'))
   r=measure(a.device,(0,0),False,out,identity.get('scene','stationary verified gameplay')+', naturally warmed uncooled iPhone',30,120,75,thermal,False,check);r['channel_inline_mode']=mode;r['runtime_log_capped']=cap
   (out/'summary.json').write_text(json.dumps(r,indent=2)+'\n');all_windows.append(r)
   if not r['valid']:failure=r['failure'];break
   f=sorted(out.glob('[0-9][0-9][0-9].json'))[:r['samples']];x,y=[json.loads(t.read_text()) for t in (f[0],f[-1])]
   for k in ('metal_lighting_passes','metal_ssao_passes'):
    if y[k]<=x[k]:raise RuntimeError(k+' lacks coverage')
   results.append(r)
  if failure:
   (R/f'trial{trial}-invalid.json').write_text(json.dumps(dict(reason=failure,windows=results),indent=2)+'\n');send({'channel_inline':0},f'trial{trial}-off')
   if trial==0 and ('thermal state differs' in failure or 'log condition changed' in failure):continue
   raise RuntimeError(failure)
  break
 else:raise RuntimeError('No stable complete comparison')
 after=report(a.device,R/'post-window.json')
 if after['performance']['thermal_state']<3:validate('oracle-after')
 else:(R/'oracle-after-skipped.json').write_text(json.dumps(dict(reason='Critical after completed FPS windows; avoid additional diagnostic CPU work'),indent=2)+'\n')
 fps=lambda mode:sum(r['raw_frame_stats']['frame_intervals'] for r in results if r['channel_inline_mode']==mode)/sum(r['raw_frame_stats']['present_seconds'] for r in results if r['channel_inline_mode']==mode)
 base,fast=fps(0),fps(1);summary=dict(valid=True,baseline_fps=base,inline_fps=fast,baseline_ms=1000/base,inline_ms=1000/fast,gain_percent=(fast/base-1)*100,thermal_state=thermal,windows=results,scope='Natural uncooled steady-state iPhone. Same PID/camera, fixed thermal class per comparison; equal label does not prove equal clocks. Diagnostic counters frozen during FPS windows.')
 (R/'comparison.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k!='windows'},indent=2),flush=True)
finally:
 try:send({'channel_inline':0},'restore-original')
 except RuntimeError as error:(R/'restore-error.txt').write_text(str(error))
