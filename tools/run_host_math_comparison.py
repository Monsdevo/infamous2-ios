#!/usr/bin/env python3
"""Actual-input CPU validation, then separate mask/CPU/combined FPS windows."""
import argparse,json,time
from pathlib import Path
from host_research_control import read,command
from measure_host_research import measure

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--label',default='math-comparison');p.add_argument('--skip-validation',action='store_true');a=p.parse_args();run=a.run.resolve();deadline=time.monotonic()+1200
 while not (run/'scene-ready.json').exists():
  if time.monotonic()>deadline:raise RuntimeError('scene deadline')
  time.sleep(1)
 ready=quiet=time.monotonic();last=read(run)['pipeline_started']
 while time.monotonic()-ready<60 or time.monotonic()-quiet<20:
  d=read(run)
  if d['pipeline_started']!=last:last=d['pipeline_started'];quiet=time.monotonic()
  time.sleep(1)
 out=run/a.label;out.mkdir(exist_ok=False)
 if not a.skip_validation:
  before=command(run,light_far=1,light_mask=0,spu_math=2,depth_only=0,dispatch=0,vertex=0,texture=0);time.sleep(10)
  command(run,spu_math=0);time.sleep(5);after=read(run)
  delta={k:after['spu_math'][k]-before['spu_math'][k] for k in ('validated','mismatches','fallback')}
  selection=json.loads((Path('build/bces01229/host-research-prepared/host-spu-math.json')).read_text())['selected'];seen=after['spu_math']['seen'];covered=[s['name'] for s in selection if seen&(1<<s['index'])]
  (out/'validation.json').write_text(json.dumps(dict(before=before,after=after,delta=delta,covered=covered),indent=2)+'\n')
  if delta['mismatches'] or delta['validated']<100:raise RuntimeError('CPU differential validation failed/insufficient')
 else:
  d=read(run)['spu_math']
  if d['validated']<100 or d['mismatches']:raise RuntimeError('prior validation absent/faulted')
 results=[]
 sequence=[('A-original',0,0),('B-mask-only',1,0),('C-combined',1,1),('D-mask-only',1,0),('E-combined',1,1),('F-original',0,0)]
 try:
  for name,mask,math in sequence:
   command(run,light_mask=mask,spu_math=math);time.sleep(10)
   r=measure(run,out/name,0,seconds=30,minimum=240,light_far=1,light_mask=mask,spu_math=math);results.append(r)
   if not r['valid']:raise RuntimeError(name+': '+str(r['failure']))
  if len({r['thermal'] for r in results})!=1:raise RuntimeError('thermal categories differ')
  def fps(mask,math):
   rows=[r for r in results if r['light_mask']==mask and r['spu_math']==math]
   return sum(r['frames']['frame_intervals'] for r in rows)/sum(r['frames']['present_seconds'] for r in rows)
  original,mask,combined=fps(0,0),fps(1,0),fps(1,1)
  result=dict(valid=True,original_fps=original,mask_only_fps=mask,combined_fps=combined,cpu_fps_gain_percent=(combined/mask-1)*100,combined_gain_percent=(combined/original-1)*100,windows=results,device_performance_claim=False)
  (out/'comparison.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='windows'},indent=2),flush=True)
 finally:command(run,spu_math=0,light_mask=0)
if __name__=='__main__':main()
