#!/usr/bin/env python3
"""Recheck the verified resolver path after the new GPU/CPU bottleneck changes."""
import argparse,json,time
from pathlib import Path
from host_research_control import read,command
from measure_host_research import measure
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);a=p.parse_args();run=a.run.resolve();deadline=time.monotonic()+1200
comparison=run/'math-comparison/comparison.json'
while not comparison.exists():
 if time.monotonic()>deadline:raise RuntimeError('math comparison deadline')
 time.sleep(1)
prior=json.loads(comparison.read_text())
if not prior['valid']:raise RuntimeError('prior comparison invalid')
math=1 if prior['cpu_fps_gain_percent']>=1 else 0
out=run/'dispatch-after-math';out.mkdir(exist_ok=False);results=[]
try:
 for i,mode in enumerate((0,1,0,1,0)):
  command(run,dispatch=mode,light_far=1,light_mask=1,spu_math=math,depth_only=0,vertex=0,texture=0);time.sleep(10)
  r=measure(run,out/(chr(65+i)+('-candidate' if mode else '-reference')),mode,seconds=30,minimum=240,light_far=1,light_mask=1,spu_math=math);results.append(r)
  if not r['valid']:raise RuntimeError(r['failure'])
 if len({r['thermal'] for r in results})!=1:raise RuntimeError('thermal differs')
 def fps(mode):
  rows=[r for r in results if r['dispatch']==mode]
  return sum(r['frames']['frame_intervals'] for r in rows)/sum(r['frames']['present_seconds'] for r in rows)
 ref,fast=fps(0),fps(1)
 result=dict(valid=True,spu_math=math,reference_fps=ref,candidate_fps=fast,fps_gain_percent=(fast/ref-1)*100,windows=results,device_performance_claim=False)
 (out/'comparison.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='windows'},indent=2),flush=True)
finally:command(run,dispatch=0,spu_math=0,light_mask=0)
