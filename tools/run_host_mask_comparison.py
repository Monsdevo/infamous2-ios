#!/usr/bin/env python3
"""Validate the actual game masks, then bracket the candidate with reference windows."""
import argparse,json,time
from pathlib import Path
from host_research_control import read,command
from measure_host_research import measure

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--label',default='mask-interval');a=p.parse_args();run=a.run.resolve()
 deadline=time.monotonic()+1200
 while not (run/'scene-ready.json').exists():
  if time.monotonic()>deadline:raise RuntimeError('scene proof deadline')
  time.sleep(1)
 last=read(run)['pipeline_started'];quiet=time.monotonic();ready=quiet
 while time.monotonic()-ready<60 or time.monotonic()-quiet<20:
  d=read(run)
  if d['pipeline_started']!=last:last=d['pipeline_started'];quiet=time.monotonic()
  if time.monotonic()>deadline:raise RuntimeError('warmup deadline')
  time.sleep(1)
 out=run/a.label;out.mkdir(exist_ok=False)
 before=command(run,light_far=1,depth_only=0,dispatch=0,vertex=0,texture=0,light_mask=2)
 time.sleep(5);after=command(run,light_mask=0);time.sleep(5);settled=read(run)
 delta={k:settled['light_mask'][k]-before['light_mask'][k] for k in ('validations','mismatches','compared_tiles','faults')}
 (out/'validation.json').write_text(json.dumps(dict(before=before,after=settled,delta=delta),indent=2)+'\n')
 if delta['validations']<10 or delta['mismatches'] or delta['faults'] or delta['compared_tiles']<7200:raise RuntimeError('actual mask validation failed/insufficient')
 results=[]
 try:
  for i,mode in enumerate((0,1,0,1,0)):
   command(run,light_mask=mode);time.sleep(10)
   result=measure(run,out/(chr(65+i)+('-candidate' if mode else '-reference')),0,seconds=30,minimum=240,light_far=1,light_mask=mode)
   results.append(result)
   if not result['valid']:raise RuntimeError(result['failure'])
  if len({r['thermal'] for r in results})!=1:raise RuntimeError('thermal differs across arms')
  fps=lambda mode:sum(r['frames']['frame_intervals'] for r in results if r['light_mask']==mode)/sum(r['frames']['present_seconds'] for r in results if r['light_mask']==mode)
  ref,fast=fps(0),fps(1)
  result=dict(valid=True,reference_fps=ref,candidate_fps=fast,fps_gain_percent=(fast/ref-1)*100,reference_ms=1000/ref,candidate_ms=1000/fast,windows=results,device_performance_claim=False)
  (out/'comparison.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='windows'},indent=2),flush=True)
 finally:command(run,light_mask=0)
if __name__=='__main__':main()
