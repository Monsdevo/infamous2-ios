#!/usr/bin/env python3
"""One iPhone baseline arm. No optimization or input changes during windows."""
import argparse,json,time
from pathlib import Path
from geometry_device_control import report,command
from measure_geometry import measure

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--device',required=True);p.add_argument('--proof',type=Path,required=True)
p.add_argument('--output',type=Path,required=True);p.add_argument('--original-build',type=int,choices=(0,1),required=True)
p.add_argument('--thermal-state',type=int,choices=(0,1),default=0)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);deadline=time.monotonic()+1500
while not a.proof.exists():
 if time.monotonic()>deadline:raise RuntimeError('No scene proof; no measurement')
 time.sleep(2)
proof=json.loads(a.proof.read_text())
command(a.device,dict(skin=0,cull=0,validation=False,dma_poison_skip=0,light_mask=1,light_far=1,spu_dispatch=1),a.output/'control')
start=quiet=thermal_quiet=time.monotonic();last=None
while True:
 d=report(a.device,a.output/'warm.json')
 if (d['pid'],d['geometry_control_session'])!=(proof['pid'],proof['session']):raise RuntimeError('Scene process changed')
 n=d['performance']['pipeline_started']
 if n!=last:last=n;quiet=time.monotonic()
 if d['performance']['thermal_state']!=a.thermal_state:thermal_quiet=time.monotonic()
 if time.monotonic()-start>=30 and time.monotonic()-quiet>=15 and time.monotonic()-thermal_quiet>=15 and d['performance']['thermal_state']==a.thermal_state:break
 if time.monotonic()>deadline:raise RuntimeError('Warmup timeout')
 time.sleep(3)
thermal=d['performance']['thermal_state']
if thermal>1:raise RuntimeError('Serious/critical thermal condition; no benchmark')
def check(d,first):
 e=[];s=d.get('dma_poison',{})
 if (d['pid'],d['geometry_control_session'])!=(proof['pid'],proof['session']):e.append('scene process changed')
 if int(d.get('dma_original_scan_build',0))!=a.original_build or s.get('enabled')!=0:e.append('wrong compiled DMA baseline')
 if a.original_build and any(s.get(k,0) for k in ('sampled_scanned','sampled_skipped')):e.append('reference still has DMA counters')
 if d.get('light_mask',{}).get('mode')!=1 or d.get('light_far',{}).get('enabled')!=1 or d.get('spu_dispatch',{}).get('enabled')!=1:e.append('combined profile differs')
 if not d.get('ssao_depth_cleanup_enabled'):e.append('depth cleanup disabled')
 if d.get('cpu_profile_state',0) in (1,2) or d.get('frame_trace_state',0) in (1,2):e.append('profiler active')
 for k in ('light_mask','light_far'):
  if d.get(k,{}).get('faults') or d.get(k,{}).get('mismatches'):e.append(k+' fault')
 for k in ('vertex','texture'):
  if d.get('renderer_memo',{}).get(k,{}).get('mode',0):e.append('memo active')
 if first:
  if bool(d.get('runtime_log_capped'))!=bool(first.get('runtime_log_capped')):e.append('log cap transition')
  if d['light_mask']['validations']!=first['light_mask']['validations']:e.append('mask validation active')
 return e
for attempt in range(2):
 r=measure(a.device,(0,0),False,a.output/('window-'+str(attempt)),'verified stationary first dock gameplay',30,180,90,thermal,False,check)
 if r['valid']:break
 if r['failure']!='log cap transition':raise RuntimeError(r['failure'])
 time.sleep(10)
if not r['valid']:raise RuntimeError(r['failure'])
files=sorted((a.output/('window-'+str(attempt))).glob('[0-9][0-9][0-9].json'))[:r['samples']]
x,y=[json.loads(f.read_text()) for f in (files[0],files[-1])]
if not a.original_build and y['dma_poison']['sampled_scanned']<=x['dma_poison']['sampled_scanned']:raise RuntimeError('Instrumented baseline lacks path coverage')
for key in ('metal_lighting_passes','metal_ssao_passes'):
 if y[key]<=x[key]:raise RuntimeError(key+' lacks coverage')
r['original_scan_build']=a.original_build;r['proof']=str(a.proof.resolve())
(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(dict(valid=True,fps=r['fps'],thermal=r['thermal_states'],original_build=a.original_build)),flush=True)
