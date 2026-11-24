#!/usr/bin/env python3
"""Actual iPhone presentation intervals for the opt-in far-light shader."""
import argparse,json
from pathlib import Path
from measure_geometry import measure
from rsx_measurement import validate_rsx
def validate(d,first,mode):
 e=validate_rsx(d,True,first)
 if not d.get('light_far_control_enabled'):e.append('light far control absent')
 s=d.get('light_far',{})
 if s.get('enabled')!=mode or s.get('faults',0):e.append('light far mode differs/faulted')
 if d.get('spu_dispatch',{}).get('enabled'):e.append('SPU dispatch experiment enabled')
 for k in ('vertex','texture'):
  m=d.get('renderer_memo',{}).get(k,{})
  if m.get('mode')!=0 or m.get('mismatches',0):e.append(k+' memo differs/faulted')
 if first and bool(d.get('runtime_log_capped'))!=bool(first.get('runtime_log_capped')):e.append('log cap transition')
 return e
def capture(device,mode,output,thermal,scene,seconds=45):
 output=Path(output);proof=json.loads(Path(scene).read_text())
 if not(proof.get('free_gameplay_verified') and proof.get('right_up_completed') and proof.get('right_left_completed')):raise ValueError('camera tutorial not verified')
 def check(d,first):
  e=validate(d,first,mode)
  if (d.get('pid'),d.get('geometry_control_session'))!=(proof['pid'],proof['session']):e.append('scene proof belongs to another process')
  return e
 r=measure(device,(0,0),False,output,'first-free-gameplay-camera-tutorial-completed',seconds,180,90,thermal,False,check)
 # A rejected last report is evidence of failure, not an admitted endpoint.
 files=sorted(output.glob('[0-9][0-9][0-9].json'))[:r['samples']]
 if len(files)>1:
  a,b=[json.loads(p.read_text()) for p in (files[0],files[-1])]
  delta={k:b['light_far'][k]-a['light_far'][k] for k in ('reference','fast','faults')}
  r.update(light_far_mode=mode,light_far_delta=delta,runtime_log_capped=bool(a.get('runtime_log_capped')))
  selected='fast' if mode else 'reference';other='reference' if mode else 'fast'
  if delta[selected]<=0 or delta[other] or delta['faults']:r.update(valid=False,failure='light far executed path coverage differs')
  for name in ('metal_lighting_passes','metal_ssao_passes'):
   if b.get(name,0)<=a.get(name,0):r.update(valid=False,failure=name+' has no execution coverage')
 r['limitations']=[s for s in r['limitations'] if s!='Same scene/camera requires user confirmation.']
 r['limitations']+=['Scene verified by saved real game-surface captures and OCR; static character/camera within this same process.','Actual iPhone display presentation events; not directly equal to Mac offscreen GPU-completion metric.','Same thermal class does not guarantee identical clock frequencies.']
 (output/'summary.json').write_text(json.dumps(r,indent=2)+'\n');return r
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device',required=True);p.add_argument('--mode',type=int,choices=(0,1),required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--scene',type=Path,required=True);p.add_argument('--thermal-state',type=int,choices=(0,1,2),required=True);a=p.parse_args();r=capture(a.device,a.mode,a.output,a.thermal_state,a.scene);print(json.dumps(r,indent=2));raise SystemExit(0 if r['valid'] else 1)
