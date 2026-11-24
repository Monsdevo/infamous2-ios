#!/usr/bin/env python3
"""Autonomous, bracketed whole-frame comparison after camera tutorial proof."""
import argparse,json,time
from pathlib import Path
from host_research_control import read,command
from measure_host_research import measure
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--label',default='far-reject');p.add_argument('--sequence',default='0,1,0,1,0');p.add_argument('--warm-seconds',type=int,default=60);a=p.parse_args();run=a.run.resolve()
 sequence=[int(x) for x in a.sequence.split(',')]
 if not 2<=len(sequence)<=8 or set(sequence)!={0,1} or not 0<=a.warm_seconds<=180:p.error('need2..8 modes0/1 including both; warm0..180 seconds')
 deadline=time.monotonic()+1200
 while not (run/'scene-ready.json').exists():
  if time.monotonic()>deadline:raise RuntimeError('camera tutorial proof deadline')
  time.sleep(1)
 # Let initial story/light transients settle. Reset quiet timer on new PSOs.
 ready=time.monotonic();last=read(run)['pipeline_started'];quiet=ready
 while time.monotonic()-ready<a.warm_seconds or time.monotonic()-quiet<20:
  d=read(run)
  if d['pipeline_started']!=last:last=d['pipeline_started'];quiet=time.monotonic()
  if time.monotonic()>deadline:raise RuntimeError('shader warmup deadline')
  time.sleep(1)
 output=run/a.label;output.mkdir(exist_ok=False);results=[]
 try:
  for index,mode in enumerate(sequence):
   name=chr(65+index)+('-fast' if mode else '-reference')
   command(run,dispatch=0,vertex=0,texture=0,light_far=mode);time.sleep(10)
   result=measure(run,output/name,0,light_far=mode)
   results.append(result)
   if not result['valid']:raise RuntimeError(name+': '+str(result['failure']))
  if len({r['thermal'] for r in results})!=1:raise RuntimeError('thermal categories differ across comparison arms')
  references=[r for r in results if not r['light_far']];fast=[r for r in results if r['light_far']]
  fps=lambda rows:sum(r['frames']['frame_intervals'] for r in rows)/sum(r['frames']['present_seconds'] for r in rows)
  ref_fps,fast_fps=fps(references),fps(fast)
  result=dict(valid=True,reference_fps=ref_fps,fast_fps=fast_fps,reference_frame_ms=1000/ref_fps,fast_frame_ms=1000/fast_fps,frame_time_reduction_percent=(1-ref_fps/fast_fps)*100,windows=results,device_performance_claim=False,limitation='GPU-completed offscreen Mac frames; same thermal category does not guarantee identical clocks. Inspect bracket consistency and visuals before accepting.')
  (output/'comparison.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='windows'},indent=2),flush=True)
 finally:command(run,light_far=0)
if __name__=='__main__':main()
