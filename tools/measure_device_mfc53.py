#!/usr/bin/env python3
"""Same-process iPhone MFC hint A/B/A/B/A; oracle only outside FPS windows."""
import argparse,json,time
from pathlib import Path
from geometry_device_control import report,command
from measure_geometry import measure
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device',required=True);p.add_argument('--run',required=True,type=Path);a=p.parse_args();R=a.run;R.mkdir(exist_ok=True,parents=True);deadline=time.monotonic()+1500
proof=R/'tutorial/scene-ready.json'
while not proof.exists():
 if time.monotonic()>deadline:raise RuntimeError('No verified scene')
 time.sleep(2)
identity=json.loads(proof.read_text())
def send(fields,path):return command(a.device,fields,R/path)
def validate(path):
 before=send({'mfc_hint':2},path+'-start');time.sleep(5);after=report(a.device,R/(path+'-after.json'))
 stats={k:after['mfc_hint'][k]-before['mfc_hint'][k] for k in ('checks','hits','mismatches')}
 valid=after['mfc_hint']['mode']==2 and stats['checks']>=100 and stats['hits']>=100 and not after['mfc_hint']['mismatches']
 (R/(path+'.json')).write_text(json.dumps(dict(valid=valid,**stats),indent=2)+'\n')
 if not valid:raise RuntimeError('MFC oracle mismatch or missing actual hit coverage')
 return stats
results=[]
try:
 d=send(dict(skin=0,cull=0,validation=False,dma_poison_skip=0,mfc_hint=0,light_mask=1,light_far=1,spu_dispatch=1),'initial')
 start=quiet=thermalquiet=time.monotonic();last=None
 while True:
  d=report(a.device,R/'warm.json');n=d['performance']['pipeline_started']
  if n!=last:last=n;quiet=time.monotonic()
  if d['performance']['thermal_state']!=0:thermalquiet=time.monotonic()
  if time.monotonic()-start>=30 and time.monotonic()-quiet>=15 and time.monotonic()-thermalquiet>=15 and d['performance']['thermal_state']==0:break
  if time.monotonic()>deadline:raise RuntimeError('Warmup/cooling deadline')
  time.sleep(3)
 validate('oracle-before');send({'mfc_hint':0},'oracle-off')
 for index,mode in enumerate((0,1,0,1,0)):
  send({'mfc_hint':mode},'switch-'+str(index));time.sleep(10)
  def check(d,first):
   e=[];m=d.get('mfc_hint',{})
   if (d['pid'],d['geometry_control_session'])!=(identity['pid'],identity['session']):e.append('scene process changed')
   if not d.get('mfc_hint_control_enabled') or m.get('mode')!=mode or m.get('mismatches'):e.append('MFC mode differs or mismatch')
   if d.get('dma_original_scan_build')!=1 or d['dma_poison']['enabled'] or d['dma_poison']['sampled_scanned'] or d['dma_poison']['sampled_skipped']:e.append('DMA poison baseline differs')
   if d['light_mask']['mode']!=1 or d['light_far']['enabled']!=1 or d['spu_dispatch']['enabled']!=1 or not d.get('ssao_depth_cleanup_enabled'):e.append('combined baseline differs')
   if d['light_mask']['faults'] or d['light_mask']['mismatches'] or d['light_far']['faults']:e.append('lighting fault')
   if d.get('cpu_profile_state',0) in (1,2) or d.get('frame_trace_state',0) in (1,2):e.append('profiler active')
   for k in ('vertex','texture'):
    if d.get('renderer_memo',{}).get(k,{}).get('mode',0):e.append('memo active')
   if first:
    if bool(d.get('runtime_log_capped'))!=bool(first.get('runtime_log_capped')):e.append('log cap transition')
    if d['light_mask']['validations']!=first['light_mask']['validations']:e.append('mask validation active')
    if any(m[k]!=first['mfc_hint'][k] for k in ('checks','hits','mismatches')):e.append('MFC validation active')
   return e
  for attempt in range(2):
   name=chr(65+index)+('-hint' if mode else '-scan')+('-retry' if attempt else '')
   r=measure(a.device,(0,0),False,R/name,'stationary verified first dock, same process',30,180,90,0,False,check)
   if r['valid']:break
   if r['failure']!='log cap transition':raise RuntimeError(r['failure'])
   time.sleep(10)
  if not r['valid']:raise RuntimeError(r['failure'])
  f=sorted((R/name).glob('[0-9][0-9][0-9].json'))[:r['samples']];x,y=[json.loads(t.read_text()) for t in (f[0],f[-1])]
  for k in ('metal_lighting_passes','metal_ssao_passes'):
   if y[k]<=x[k]:raise RuntimeError(k+' lacks coverage')
  r['mfc_hint_mode']=mode;r['runtime_log_capped']=bool(x.get('runtime_log_capped'));results.append(r);(R/name/'summary.json').write_text(json.dumps(r,indent=2)+'\n')
 if len({r['runtime_log_capped'] for r in results})!=1:raise RuntimeError('Logging conditions differ across windows; no comparison')
 validate('oracle-after')
 fps=lambda mode:sum(r['raw_frame_stats']['frame_intervals'] for r in results if r['mfc_hint_mode']==mode)/sum(r['raw_frame_stats']['present_seconds'] for r in results if r['mfc_hint_mode']==mode)
 base,hint=fps(0),fps(1);d=dict(valid=True,reference_fps=base,hint_fps=hint,reference_ms=1000/base,hint_ms=1000/hint,gain_percent=(hint/base-1)*100,windows=results,scope='iPhone same-process pilot; TLS last-slot owner validated. No per-call counters/oracle in FPS windows. Nominal thermal state does not establish identical clocks.')
 (R/'comparison.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps({k:v for k,v in d.items() if k!='windows'},indent=2),flush=True)
finally:
 try:send({'mfc_hint':0},'restore-original')
 except RuntimeError as error:(R/'restore-error.txt').write_text(str(error))
