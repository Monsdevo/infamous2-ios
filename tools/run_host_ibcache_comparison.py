#!/usr/bin/env python3
"""Real-game shadow verification, then five interleaved profiler-free arms."""
import argparse,json,time
from pathlib import Path
from host_research_control import read,command,capture
from measure_host_research import measure
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);a=p.parse_args();run=a.run.resolve();deadline=time.monotonic()+1200
while not (run/'scene-ready.json').exists():
 if time.monotonic()>deadline:raise RuntimeError('scene deadline')
 time.sleep(1)
command(run,light_far=1,light_mask=1,spu_math=0,dispatch=1,vertex=0,texture=0,depth_only=0,normals_nowb=0,ib_cache=0)
ready=quiet=time.monotonic();last=read(run)['pipeline_started']
while time.monotonic()-ready<60 or time.monotonic()-quiet<20:
 d=read(run)
 if d['pipeline_started']!=last:last=d['pipeline_started'];quiet=time.monotonic()
 if time.monotonic()>deadline:raise RuntimeError('warmup deadline')
 time.sleep(1)
out=run/'ibcache-comparison';out.mkdir(exist_ok=False);results=[]
try:
 before=command(run,ib_cache=2);time.sleep(15);after=read(run)
 check=dict(before=before,after=after,valid=after['ib_cache']['mode']==2 and not after['ib_cache']['fault'] and after['ib_cache']['validated']-before['ib_cache']['validated']>=10000)
 (out/'validation.json').write_text(json.dumps(check,indent=2)+'\n')
 if not check['valid']:raise RuntimeError('real-game pointer/base validation failed or insufficient coverage')
 command(run,ib_cache=0);capture(run,'ib-reference')
 for i,mode in enumerate((0,1,0,1,0)):
  command(run,ib_cache=mode);time.sleep(10)
  r=measure(run,out/(chr(65+i)+'-'+str(mode)),1,seconds=30,minimum=240,light_far=1,light_mask=1,ib_cache=mode)
  results.append(r)
  if not r['valid']:raise RuntimeError(r['failure'])
  if i==1:capture(run,'ib-candidate')
 if len({r['thermal'] for r in results})!=1:raise RuntimeError('thermal categories differ')
 fps=lambda mode:sum(r['frames']['frame_intervals'] for r in results if r['ib_cache']==mode)/sum(r['frames']['present_seconds'] for r in results if r['ib_cache']==mode)
 ref,fast=fps(0),fps(1);report=dict(valid=True,reference_fps=ref,candidate_fps=fast,reference_ms=1000/ref,candidate_ms=1000/fast,gain_percent=(fast/ref-1)*100,windows=results,device_performance_claim=False,scope='Full existing fast-resolver result cache with conservative residency snapshot; dispatch=1 in both arms. Not the entire newer upstream runtime.')
 (out/'comparison.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='windows'},indent=2),flush=True)
finally:
 try:command(run,ib_cache=0)
 except RuntimeError as e:(out/'cleanup-error.txt').write_text(str(e)+'\n')
