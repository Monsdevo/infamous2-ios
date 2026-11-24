#!/usr/bin/env python3
"""One controlled fixed-scene sweep; no relaunch, installation or scene changes.

Qualify every non-reference pair first. A second fresh-process sweep requires
the user to confirm the same gameplay scene again before running this tool.
"""
import argparse,json,time
from pathlib import Path
from geometry_device_control import command,report
from measure_geometry import measure

def sweep(device,output,thermal_state,reverse=False):
 output=Path(output);output.mkdir(parents=True,exist_ok=False)
 pairs=[(1,1),(1,2),(2,2),(2,1)]
 if reverse:pairs.reverse()
 results=[];session=None;pid=None
 for index,pair in enumerate([(0,0),*pairs,(0,0)]):
  name=f'{index:02}-{pair[0]}-{pair[1]}';folder=output/name
  d=command(device,{'skin':pair[0],'cull':pair[1],'validation':False,'capture':False},output/(name+'-control'))
  if session is None:session=d['geometry_control_session'];pid=d['pid']
  if d['geometry_control_session']!=session or d['pid']!=pid:raise RuntimeError('Process changed in sweep')
  # Drain calls started under the prior config, ensure actual new frames,
  # and retain the intermediate reports to audit thermal/compilation state.
  first=d['performance'];ready=False
  for warmup in range(12):
   time.sleep(2);d=report(device,output/(name+f'-warmup-{warmup:02}.json'));p=d['performance']
   if d['pid']!=pid or d['geometry_control_session']!=session:raise RuntimeError('Process changed during warmup')
   if p['thermal_state']!=thermal_state:raise RuntimeError('Thermal condition changed; stop sweep and review completed windows')
   if p['present_total']-first['present_total']>=12 and p['sample_monotonic_seconds']-first['sample_monotonic_seconds']>=4 and not p['skin_calibrating'] and not p['cull_calibrating']:
    ready=True;break
  if not ready:raise RuntimeError('No stable frame-producing warmup')
  print('BEGIN '+name,flush=True)
  result=measure(device,pair,False,folder,'first-gameplay-fixed-camera',30,120,60,thermal_state,True)
  results.append({'name':name,**result})
  (output/'summary.json').write_text(json.dumps({'pid':pid,'session':session,'reverse':reverse,'results':results},indent=2)+'\n')
  if not result['valid']:raise RuntimeError('Rejected window: '+str(result['failure']))
 return results

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--thermal-state',type=int,choices=(0,1),default=0);p.add_argument('--reverse',action='store_true');a=p.parse_args();sweep(a.device,a.output,a.thermal_state,a.reverse)
