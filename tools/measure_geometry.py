#!/usr/bin/env python3
"""Bounded, coherent device measurement after a confirmed fixed scene.
Does not select modes. Development control is used only to export raw frames.
"""
import argparse,csv,json,time
from pathlib import Path
from geometry_device_control import report,command,call,BUNDLE
from geometry_measurement import validate_sample,frame_statistics

def measure(device,pair,validation,output,scene,seconds=30,min_intervals=120,max_seconds=60,thermal_state=0,profile_only=False,extra_validator=None):
 output=Path(output);output.mkdir(parents=True,exist_ok=False);samples=[];failure=None
 for index in range(100):
  d=report(device,output/f'{index:03}.json');p=d['performance']
  errors=validate_sample(d,pair,validation,samples[0] if samples else None,thermal_state)
  if extra_validator:errors+=extra_validator(d,samples[0] if samples else None)
  if samples and p['sample_monotonic_seconds']<=samples[-1]['performance']['sample_monotonic_seconds']:errors.append('stale app report')
  if errors:failure='; '.join(errors);break
  samples.append(d);first=samples[0]['performance'];elapsed=p['sample_monotonic_seconds']-first['sample_monotonic_seconds'];frames=p['present_total']-first['present_total']
  if elapsed>=seconds and (validation or frames>=min_intervals):break
  if elapsed>=max_seconds:break
  time.sleep(3)
 result={'scene':scene,'pair':list(pair),'validation':validation,'valid':failure is None,'failure':failure,'samples':len(samples),'raw_frame_stats':None,'requested_thermal_state':thermal_state,'comparison_scope':'requested_profile' if profile_only else 'executed_routes','gpu_coverage':{},'limitations':['Same scene/camera requires user confirmation.','Nominal thermal classification does not prove identical chip clocks.','Only admitted GPU batches count as actual GPU coverage.']}
 if len(samples)>1:
  a,b=samples[0],samples[-1];x,y=a['performance'],b['performance'];wall=y['sample_monotonic_seconds']-x['sample_monotonic_seconds'];frames=y['present_total']-x['present_total'];present_seconds=y['present_time']-x['present_time']
  result.update(pid=a['pid'],session=a['geometry_control_session'],wall_seconds=wall,frames=frames,present_seconds=present_seconds,fps=frames/present_seconds if present_seconds>0 else 0,thermal_states=sorted({s['performance']['thermal_state'] for s in samples}))
  result['geometry']={}
  fields=['calls','entry_count','total_ms','trial_ms','gpu_ms','fallbacks','unsupported_calls','validations','mismatches','failures','gpu_batches','batch_candidates','cpu_only_calls','cpu_small_batches','cpu_busy_batches','cpu_dependency_batches','cpu_cost_rejected_batches','calibration_batches','input_bytes','output_bytes','sampled_calls','copy_ms','execute_ms','commit_ms','input_ms','submit_ms','wait_ms','output_ms']
  for prefix,route in zip(('skin','cull'),pair):
   delta={field:y.get(prefix+'_'+field,0)-x.get(prefix+'_'+field,0) for field in fields};result['geometry'][prefix]={'route':route,**delta}
   if route==2:
    result['gpu_coverage'][prefix]=delta['gpu_batches']>0
    if not validation and delta['gpu_batches']<=0:
     result['limitations'].append(prefix+' Metal profile executed CPU fallback only; this is not a GPU speed result')
     if not profile_only:result.update(valid=False,failure=prefix+' has no admitted GPU coverage; not a GPU performance result')
  if not validation and frames<min_intervals:result.update(valid=False,failure=failure or 'insufficient raw intervals for requested comparison')
  # Report count/time pair is coherent; export actual events to derive jitter.
  if result['valid'] and frames>0:
   ack=command(device,{'frames_since':max(0,x['present_total']-1)},output/'frame-export-control');export=ack.get('geometry_frame_export',{})
   if export.get('dropped'):result.update(valid=False,failure='raw frame ring overflow')
   else:
    path=output/'frames.csv';call(['device','copy','from','--device',device,'--domain-type','appDataContainer','--domain-identifier',BUNDLE,'--source','Documents/'+export['file'],'--destination',str(path.resolve())])
    try:
     with path.open() as f:stats=frame_statistics(list(csv.DictReader(f)),x['present_total'],y['present_total'])
     if abs(stats['present_seconds']-present_seconds)>2e-6:raise ValueError('raw event time differs from coherent snapshot')
     result['raw_frame_stats']=stats
    except ValueError as e:result.update(valid=False,failure=str(e))
 else:result.update(valid=False,failure=failure or 'no usable sample interval')
 (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True);return result

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--device',required=True);ap.add_argument('--pair',type=int,nargs=2,choices=(0,1,2),required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--scene',required=True);ap.add_argument('--validation',action='store_true');ap.add_argument('--seconds',type=int,default=30);ap.add_argument('--minimum-intervals',type=int,default=120);ap.add_argument('--max-seconds',type=int,default=60);ap.add_argument('--thermal-state',type=int,choices=(0,1),default=0);ap.add_argument('--profile-only',action='store_true',help='Compare requested hybrid profiles even when all work was kept on CPU; never label as GPU performance')
 a=ap.parse_args();r=measure(a.device,a.pair,a.validation,a.output,a.scene,a.seconds,a.minimum_intervals,a.max_seconds,a.thermal_state,a.profile_only);return 0 if r['valid'] else 1
if __name__=='__main__':raise SystemExit(main())
