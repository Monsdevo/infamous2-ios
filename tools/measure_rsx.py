#!/usr/bin/env python3
"""Measure already-selected build43 RSX mode in a confirmed fixed scene.

No app launch or setting changes. The existing session control only exports
raw presentation events. Thermal0/1/2/3 windows are explicitly labeled;
changes between categories reject a window rather than mixing conditions.
"""
import argparse,json
from pathlib import Path
from measure_geometry import measure
from rsx_measurement import validate_rsx,FIELDS

def capture(device,enabled,output,scene,thermal_state,seconds=30):
 output=Path(output)
 result=measure(device,(0,0),False,output,scene,seconds,120,60,thermal_state,False,
                lambda d,first:validate_rsx(d,enabled,first))
 files=sorted(output.glob('[0-9][0-9][0-9].json'))
 result['rsx_requested']=enabled
 if len(files)>1:
  a=json.loads(files[0].read_text())['performance'];b=json.loads(files[-1].read_text())['performance']
  delta={field:b['rsx_legacy_'+field]-a['rsx_legacy_'+field] for field in FIELDS}
  result['rsx']=delta
  if enabled and delta['state_skipped']<=0:result.update(valid=False,failure='new RSX path did not skip state during window')
  if delta['draw_forwarded']<=0:result.update(valid=False,failure='no original draw notifications during window')
 result['limitations']+=['RSX mode is fixed at launch; sessions are separate.','Identical thermal category does not guarantee identical chip clocks.','A hot/critical window describes throttled conditions and is not a cool-device performance claim.']
 (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print('RSX_RESULT '+json.dumps(result),flush=True);return result

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device',required=True);p.add_argument('--mode',choices=('on','off'),required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--thermal-state',type=int,choices=(0,1,2,3),required=True);p.add_argument('--scene',required=True);p.add_argument('--seconds',type=int,default=30);a=p.parse_args();r=capture(a.device,a.mode=='on',a.output,a.scene,a.thermal_state,a.seconds);raise SystemExit(0 if r['valid'] else 1)
