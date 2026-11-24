#!/usr/bin/env python3
"""Profiler-free fixed-scene Mac comparison using actual GPU completion events."""
import argparse,csv,json,plistlib,time
from pathlib import Path
from host_research_control import read,command
from geometry_measurement import frame_statistics
def errors(d,first,mode,scene,light_far=0,depth_only=0,light_mask=0,spu_math=0,normals_nowb=0,ib_cache=0):
 e=[]
 if d.get('ib_cache',{}).get('mode',0)!=ib_cache or d.get('ib_cache',{}).get('fault',0):e.append('indirect cache mode differs/faulted')
 if first and d.get('ib_cache',{}).get('validated',0)!=first.get('ib_cache',{}).get('validated',0):e.append('indirect cache validation during FPS window')
 if d.get('normals_nowb',{}).get('enabled',0)!=normals_nowb:e.append('normals writeback mode differs')
 if (Path(__file__).resolve().parents[1]/'out/host-research/measurement-inhibit.json').exists():e.append('research build/test active; FPS window prohibited')
 if (d['pid'],d['session'])!=(scene['pid'],scene['session']):e.append('scene proof belongs to another process')
 if not scene.get('right_up_completed') or not scene.get('right_left_completed') or not scene.get('free_gameplay_verified'):e.append('camera tutorial not verified complete')
 if d['dispatch']['enabled']!=mode:e.append('wrong dispatch mode')
 far=d.get('light_far',{})
 if light_far and not far:e.append('light far control absent')
 if far and (far.get('enabled')!=light_far or far.get('faults',0)):e.append('light far mode differs/faulted')
 depth=d.get('depth_only',{})
 if depth_only and not depth:e.append('depth-only control absent')
 if depth and (depth.get('enabled')!=depth_only or depth.get('faults',0)):e.append('depth-only mode differs/faulted')
 math=d.get('spu_math',{})
 if spu_math and not math:e.append('SPU math control absent')
 if math and (math.get('mode')!=spu_math or math.get('mismatches',0)):e.append('SPU math mode differs/faulted')
 mask=d.get('light_mask',{})
 if light_mask and not mask:e.append('light mask control absent')
 if mask and (mask.get('enabled')!=light_mask or mask.get('faults',0)):e.append('light mask mode differs/faulted')
 for k in ('vertex','texture'):
  if d[k]['mode']!=0 or d[k]['mismatches']:e.append(k+' memo active/faulted')
 if d['low_power']:e.append('low power mode')
 if d['thermal']>=2:e.append('Mac thermal serious/critical')
 if d['cpu_profile_state'] in (1,2) or d['frame_trace_state'] in (1,2):e.append('profiler active')
 if d.get('gpu_probe_state',0) in (1,2):e.append('GPU pass probe active')
 if d.get('mask_capture_state',0)==1:e.append('mask input readback active')
 if d['gpu_errors'] or d['lighting_faults'] or d['ssao_faults']:e.append('GPU/compute fault')
 if first:
  if d['monotonic_s']<=first['monotonic_s']:e.append('stale report')
  for k in ('thermal','log_capped','pipeline_started'):
   if d[k]!=first[k]:e.append(k+' changed during window')
  if math.get('validated',0)!=first.get('spu_math',{}).get('validated',0):e.append('SPU math validation during FPS window')
  if mask.get('validations',0)!=first.get('light_mask',{}).get('validations',0):e.append('mask validation still active during FPS window')
  if d.get('mask_capture_state',0)!=first.get('mask_capture_state',0):e.append('mask input capture during FPS window')
  for k in ('present_total','present_time'):
   if d[k]<first[k]:e.append(k+' regressed')
 return e
def measure(run,output,mode,seconds=45,minimum=240,light_far=0,depth_only=0,light_mask=0,spu_math=0,normals_nowb=0,ib_cache=0):
 run=Path(run);output=Path(output);output.mkdir(parents=True,exist_ok=False)
 scene=json.loads((run/'scene-ready.json').read_text());samples=[];failure=None
 capture_mtime=(run/'frame.ppm').stat().st_mtime_ns if (run/'frame.ppm').exists() else None
 for i in range(100):
  d=read(run);(output/f'{i:03}.json').write_text(json.dumps(d,indent=2)+'\n')
  bad=errors(d,samples[0] if samples else None,mode,scene,light_far,depth_only,light_mask,spu_math,normals_nowb,ib_cache)
  if (run/'gpu-pass-request.txt').exists():bad.append('GPU pass probe pending')
  if (run/'mask-input-request.txt').exists():bad.append('mask input capture pending')
  if (run/'frame-request.txt').exists() or ((run/'frame.ppm').exists() and (run/'frame.ppm').stat().st_mtime_ns!=capture_mtime):bad.append('surface capture during FPS window')
  if bad:failure='; '.join(bad);break
  samples.append(d)
  if len(samples)>1:
   duration=d['monotonic_s']-samples[0]['monotonic_s'];frames=d['present_total']-samples[0]['present_total']
   if duration>=seconds and frames>=minimum:break
   if duration>=max(seconds*2,90):failure='insufficient frame intervals';break
  time.sleep(1)
 result=dict(valid=not failure,failure=failure,dispatch=mode,light_far=light_far,normals_nowb=normals_nowb,ib_cache=ib_cache,metric='GPU-completed offscreen guest frames',samples=len(samples),device_performance_claim=False)
 if len(samples)>1:
  a,b=samples[0],samples[-1];result.update(pid=a['pid'],session=a['session'],thermal=a['thermal'],log_capped=a['log_capped'])
  ib_delta={k:b.get('ib_cache',{}).get(k,0)-a.get('ib_cache',{}).get(k,0) for k in ('hit','miss','validated','fault')}
  result['ib_cache_delta']=ib_delta
  if (ib_cache and ib_delta['hit']<=0) or (not ib_cache and (ib_delta['hit'] or ib_delta['miss'])):result.update(valid=False,failure='indirect cache path coverage differs')
  skipped=b.get('normals_nowb',{}).get('skipped',0)-a.get('normals_nowb',{}).get('skipped',0)
  result['normals_skipped_delta']=skipped
  if (normals_nowb and skipped<=0) or (not normals_nowb and skipped):result.update(valid=False,failure='normals omission path coverage differs')
  delta={k:b['dispatch'][k]-a['dispatch'][k] for k in ('eligible','fast','fallback','reset_checks','reset_bypasses')};result['dispatch_delta']=delta
  if delta['eligible']<=0 or (mode and (delta['fast']<=0 or delta['reset_bypasses']<=0)) or (not mode and (delta['fast'] or delta['reset_bypasses'])):result.update(valid=False,failure='dispatch path coverage differs')
  if b['lighting_passes']<=a['lighting_passes'] or b['ssao_passes']<=a['ssao_passes']:result.update(valid=False,failure='Metal lighting/SSAO baseline had no executed coverage')
  if 'light_far' in a:
   result['light_far_delta']={k:b['light_far'][k]-a['light_far'][k] for k in ('reference','fast','faults')}
   selected='fast' if light_far else 'reference';other='reference' if light_far else 'fast'
   if result['light_far_delta'][selected]<=0 or result['light_far_delta'][other]:result.update(valid=False,failure='light far path coverage differs')
  if 'depth_only' in a:
   result['depth_only']=depth_only
   result['depth_only_delta']={k:b['depth_only'][k]-a['depth_only'][k] for k in ('reference','fast','faults')}
   selected='fast' if depth_only else 'reference';other='reference' if depth_only else 'fast'
   if result['depth_only_delta'][selected]<=0 or result['depth_only_delta'][other] or result['depth_only_delta']['faults']:result.update(valid=False,failure='depth-only actual draw coverage differs')
  if 'spu_math' in a:
   result['spu_math']=spu_math
   result['spu_math_delta']={k:b['spu_math'][k]-a['spu_math'][k] for k in ('reference','fast','validated','mismatches','fallback')}
   selected='fast' if spu_math else 'reference';other='reference' if spu_math else 'fast'
   if result['spu_math_delta'][selected]<=0 or result['spu_math_delta'][other] or result['spu_math_delta']['validated'] or result['spu_math_delta']['mismatches']:result.update(valid=False,failure='SPU math path coverage differs')
  if 'light_mask' in a:
   result['light_mask']=light_mask
   result['light_mask_delta']={k:b['light_mask'][k]-a['light_mask'][k] for k in ('reference','fast','faults')}
   selected='fast' if light_mask else 'reference';other='reference' if light_mask else 'fast'
   if result['light_mask_delta'][selected]<=0 or result['light_mask_delta'][other] or result['light_mask_delta']['faults']:result.update(valid=False,failure='light mask actual compute coverage differs')
  if result['valid']:
   command(run,export_after=max(0,a['present_total']-1));export=plistlib.loads((run/'export.plist').read_bytes())
   if export['dropped']:result.update(valid=False,failure='frame ring overflow')
   else:
    data=(run/export['file']).read_text();(output/'frames.csv').write_text(data)
    result['frames']=frame_statistics(list(csv.DictReader(data.splitlines())),a['present_total'],b['present_total'])
    if abs(result['frames']['present_seconds']-(b['present_time']-a['present_time']))>2e-6:result.update(valid=False,failure='raw frames disagree with snapshot')
 (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return result
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--dispatch',type=int,choices=(0,1),required=True);p.add_argument('--light-far',type=int,choices=(0,1),default=0);p.add_argument('--seconds',type=int,default=45);a=p.parse_args();r=measure(a.run,a.output,a.dispatch,a.seconds,light_far=a.light_far);raise SystemExit(0 if r['valid'] else 1)
