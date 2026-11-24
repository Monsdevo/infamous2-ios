#!/usr/bin/env python3
"""Mac-only omission pilot. No proof of other guest consumers or whole-game safety."""
import argparse,json,time
from pathlib import Path
from host_research_control import read,command,capture
from measure_host_research import measure
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);a=p.parse_args();run=a.run.resolve()
deadline=time.monotonic()+1200
while not (run/'scene-ready.json').exists():
 if time.monotonic()>deadline:raise RuntimeError('scene deadline')
 time.sleep(1)
command(run,light_far=1,light_mask=1,spu_math=0,dispatch=0,vertex=0,texture=0,depth_only=0,normals_nowb=0)
ready=quiet=time.monotonic();last=read(run)['pipeline_started']
while time.monotonic()-ready<60 or time.monotonic()-quiet<20:
 d=read(run)
 if d['pipeline_started']!=last:last=d['pipeline_started'];quiet=time.monotonic()
 if time.monotonic()>deadline:raise RuntimeError('warmup deadline')
 time.sleep(1)
output=run/'normals-comparison';output.mkdir(exist_ok=False);results=[]
try:
 capture(run,'normals-reference')
 for i,mode in enumerate((0,1,0,1,0)):
  command(run,normals_nowb=mode);time.sleep(10)
  result=measure(run,output/(chr(65+i)+'-'+str(mode)),0,seconds=30,minimum=240,light_far=1,light_mask=1,normals_nowb=mode)
  results.append(result)
  if not result['valid']:raise RuntimeError(result['failure'])
  if i==1:capture(run,'normals-candidate')
 if len({r['thermal'] for r in results})!=1:raise RuntimeError('thermal category changed')
 fps=lambda mode:sum(r['frames']['frame_intervals'] for r in results if r['normals_nowb']==mode)/sum(r['frames']['present_seconds'] for r in results if r['normals_nowb']==mode)
 ref,fast=fps(0),fps(1)
 report=dict(valid=True,reference_fps=ref,candidate_fps=fast,reference_ms=1000/ref,candidate_ms=1000/fast,gain_percent=(fast/ref-1)*100,windows=results,device_performance_claim=False,correctness='Fallback fail-stop only; screenshots are visual sanity checks. Unknown consumers and moving-scene/full-game coverage remain unproven; opt-in research only.')
 (output/'comparison.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='windows'},indent=2),flush=True)
finally:
 try:command(run,normals_nowb=0)
 except RuntimeError as error:
  # Preserve the primary measurement failure when the guarded game exited.
  (output/'cleanup-error.txt').write_text(str(error)+'\n')
