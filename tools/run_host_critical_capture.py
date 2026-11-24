#!/usr/bin/env python3
"""One coherent long compact-progress/CPU record, outside FPS benchmarks."""
import argparse,json,time
from pathlib import Path
from host_research_control import read,command
from capture_host_diagnostics import capture
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);a=p.parse_args();run=a.run.resolve();deadline=time.monotonic()+1200
while not (run/'scene-ready.json').exists():
 if time.monotonic()>deadline:raise RuntimeError('scene proof deadline')
 time.sleep(1)
ready=quiet=time.monotonic();last=read(run)['pipeline_started']
while time.monotonic()-ready<60 or time.monotonic()-quiet<20:
 d=read(run)
 if d['pipeline_started']!=last:last=d['pipeline_started'];quiet=time.monotonic()
 if time.monotonic()>deadline:raise RuntimeError('shader warmup deadline')
 time.sleep(1)
d=command(run,light_far=1,light_mask=1,spu_math=0,dispatch=0,vertex=0,texture=0,depth_only=0)
if d.get('progress_trace_compact')!=1:raise RuntimeError('compact progress capture unavailable')
time.sleep(5);capture(run,run/'critical-progress',trace_seconds=15)
print('Completed compact15s progress +18s CPU; no FPS claim',flush=True)
