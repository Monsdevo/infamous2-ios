#!/usr/bin/env python3
"""Read-only own-process CPU samples plus a bounded overlapping frame trace."""
import argparse,json,time,uuid,shutil
from pathlib import Path
from host_research_control import read,write
def capture(run,output,trace_seconds=1):
 run=Path(run);output=Path(output);output.mkdir(parents=True,exist_ok=False)
 if not 1<=trace_seconds<=15:raise ValueError("trace_seconds outside1..15")
 before=read(run);token=uuid.uuid4().hex
 if before['cpu_profile_state'] in (1,2) or before['frame_trace_state'] in (1,2):raise RuntimeError('profiler already active')
 try:
  write(run/'cpu-profile-control.txt',f'start {token} {max(15,trace_seconds+3)}\n')
  time.sleep(2)
  write(run/'frame-trace-control.txt',f'start {token} {trace_seconds}\n')
  deadline=time.monotonic()+40
  while time.monotonic()<deadline:
   d=read(run)
   if (d['pid'],d['session'])!=(before['pid'],before['session']):raise RuntimeError('process changed')
   found={}
   for kind in ('cpu-profile','frame-trace'):
    p=run/(kind+'.csv')
    if p.exists():
     with p.open() as f:line=f.readline()
     if line.startswith('# '):
      m=json.loads(line[2:])
      if m.get('token')==token:found[kind]=m
   if len(found)==2 and d['cpu_profile_state']==3 and d['frame_trace_state']==3:break
   time.sleep(.5)
  else:raise RuntimeError('diagnostic did not finish')
  for name,m in found.items():
   if m.get('dropped',0) or m.get('errors',0) or m.get('truncated',0):raise RuntimeError('incomplete '+name+' '+repr(m))
   shutil.copy2(run/(name+'.csv'),output/(name+'.csv'))
  if found['cpu-profile']['uuid']!=found['frame-trace']['uuid']:raise RuntimeError('UUID differs between diagnostics')
  shutil.copy2(run/'frame-thread-map.csv',output/'frame-thread-map.csv')
  result=dict(pid=before['pid'],session=before['session'],token=token,before=before,after=d,metadata=found,performance_window=False)
  (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(found,indent=2))
 finally:
  write(run/'cpu-profile-control.txt','idle\n');write(run/'frame-trace-control.txt','idle\n')
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--trace-seconds',type=int,default=1);a=p.parse_args();capture(a.run,a.output,a.trace_seconds)
