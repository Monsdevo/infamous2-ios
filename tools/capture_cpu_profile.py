#!/usr/bin/env python3
"""Bounded opt-in CPU capture, separate from FPS windows; no app launch."""
import argparse,json,time,uuid
from pathlib import Path
from geometry_device_control import call,report,BUNDLE

def capture(device,output,seconds=15):
 output=Path(output);output.mkdir(parents=True,exist_ok=False)
 first=report(device,output/'before.json');token='rsx'+uuid.uuid4().hex
 control=output/'control.txt';control.write_text(f'start {token} {seconds}\n')
 def write(path):call(['device','copy','to','--device',device,'--domain-type','appDataContainer','--domain-identifier',BUNDLE,'--source',str(path.resolve()),'--destination','Documents/cpu-profile-control.txt'])
 write(control);seen=False;failure=None;last=first
 try:
  for i in range(30):
   time.sleep(2);d=report(device,output/f'{i:02}.json');last=d
   if d['pid']!=first['pid'] or d.get('geometry_control_session')!=first.get('geometry_control_session'):raise RuntimeError('CPU profile process changed')
   state=d.get('cpu_profile_state',0)
   if state in (1,2):seen=True
   if state<0:raise RuntimeError('CPU sampler error')
   if seen and state==3:break
  else:raise RuntimeError('CPU capture did not complete before timeout')
  destination=output/'cpu-profile.csv'
  call(['device','copy','from','--device',device,'--domain-type','appDataContainer','--domain-identifier',BUNDLE,'--source','Documents/cpu-profile.csv','--destination',str(destination.resolve())])
  with destination.open() as f:metadata=json.loads(f.readline().removeprefix('# '))
  if metadata.get('token')!=token or metadata.get('errors') or metadata.get('truncated'):raise RuntimeError('CPU token mismatch/errors/truncation')
  result={'valid':True,'pid':first['pid'],'session':first.get('geometry_control_session'),'token':token,'metadata':metadata,'thermal_states':sorted({json.loads(p.read_text())['performance']['thermal_state'] for p in output.glob('[0-9][0-9].json')}),'limitation':'Profiler-active recording is not an FPS benchmark.'}
  (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True);return result
 finally:
  idle=output/'idle.txt';idle.write_text('idle\n');write(idle)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--seconds',type=int,choices=range(3,31),default=15);a=p.parse_args();capture(a.device,a.output,a.seconds)
