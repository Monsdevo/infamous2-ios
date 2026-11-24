#!/usr/bin/env python3
"""Validate a route pair before performance testing; requires a fixed gameplay scene.

Leaves validation ON. Inspect outputs, then disable validation explicitly before
measure_geometry.py. Calibration results never count as performance samples.
"""
import argparse,json,time
from pathlib import Path
from geometry_device_control import command,report

def qualify(device,pair,output,seconds=15):
 output=Path(output);output.mkdir(parents=True,exist_ok=False)
 initial=command(device,{'skin':pair[0],'cull':pair[1],'validation':True},output/'select')
 first=None;last=initial;failure=None
 for i in range(24):
  d=report(device,output/f'{i:02}.json');p=d['performance'];last=d
  if d['pid']!=initial['pid'] or d['geometry_control_session']!=initial['geometry_control_session']:
   failure='process changed';break
  if [p['skin_route'],p['cull_route']]!=list(pair) or not p['geometry_validation_all']:
   failure='configuration changed';break
  if not p['application_active'] or p['settings_panel_open']:
   failure='not active gameplay';break
  if 2 in pair and p['geometry_metal_state']==3:
   failure='geometry shader preparation failed';break
  if 2 in pair and p['geometry_metal_state']!=2:
   time.sleep(3);continue
  if first is None:first=d
  for prefix,route in zip(('skin','cull'),pair):
   if route and (p[prefix+'_blocked']&(1<<route) or p[prefix+'_mismatches'] or p[prefix+'_failures']):failure=prefix+' correctness/backend failure'
  if failure:break
  elapsed=p['sample_monotonic_seconds']-first['performance']['sample_monotonic_seconds']
  if elapsed>=seconds:break
  time.sleep(3)
 p=last['performance'];result={'pair':list(pair),'valid':failure is None,'failure':failure,'pid':last['pid'],'session':last['geometry_control_session'],'thermal_state':p['thermal_state'],'performance_eligible':False,'geometry':{}}
 eligible=True
 for prefix,route in zip(('skin','cull'),pair):
  base=first['performance'] if first else p
  delta={field:p.get(prefix+'_'+field,0)-base.get(prefix+'_'+field,0) for field in ('entry_count','validations','fallbacks','unsupported_calls','mismatches','failures','calibration_batches','gpu_batches')}
  result['geometry'][prefix]={**delta,'blocked':p[prefix+'_blocked'],'gates':p[prefix+'_gates']}
  if route and delta['validations']<64:result.update(valid=False,failure='insufficient validated '+prefix+' calls')
  if route==2 and (not p[prefix+'_admitted_mask'] or delta['gpu_batches']==0):eligible=False
 result['performance_eligible']=bool(result['valid'] and eligible and p['thermal_state']==0)
 (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return result

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device',required=True);p.add_argument('--pair',type=int,nargs=2,choices=(0,1,2),required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--seconds',type=int,default=15);a=p.parse_args();r=qualify(a.device,a.pair,a.output,a.seconds);raise SystemExit(0 if r['valid'] else 1)
