#!/usr/bin/env python3
"""Session-bound local controls and token-checked one-shot game captures."""
import argparse,json,time,uuid,subprocess
from pathlib import Path
from capture_device_frame import parse_frame
def read(run):return json.loads((Path(run)/'report.json').read_text())
def write(path,data):
 path=Path(path);tmp=path.with_suffix('.tmp');tmp.write_text(data);tmp.replace(path)
def command(run,**fields):
 run=Path(run);r=read(run);token=uuid.uuid4().hex
 write(run/'control.json',json.dumps(dict(session=r['session'],token=token,**fields)))
 for _ in range(40):
  d=read(run)
  if (d['pid'],d['session'])!=(r['pid'],r['session']):raise RuntimeError('process changed')
  if d['ack']==token:return d
  time.sleep(.25)
 raise RuntimeError('control not acknowledged')
def capture(run,label):
 run=Path(run);destination=run/'captures'/label;destination.mkdir(parents=True,exist_ok=False)
 token=uuid.uuid4().hex;before=read(run);write(run/'frame-request.txt',token+'\n')
 for _ in range(50):
  try:
   source=run/'frame.ppm';dimensions=parse_frame(source,token)
   data=source.read_bytes();p=destination/'frame.ppm';p.write_bytes(data);parse_frame(p,token)
   after=read(run);assert after['pid']==before['pid']
   png=destination/'frame.png';subprocess.run(['sips','-s','format','png',str(p),'--out',str(png)],capture_output=True,check=True)
   (destination/'report.json').write_text(json.dumps(after,indent=2)+'\n');return str(png.resolve())
  except (OSError,ValueError):time.sleep(.5)
 raise RuntimeError('matching complete capture not received')
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True,type=Path)
 p.add_argument('--dispatch',type=int,choices=(0,1));p.add_argument('--vertex',type=int,choices=(0,1,2));p.add_argument('--texture',type=int,choices=(0,1,2))
 p.add_argument('--light-far',type=int,choices=(0,1))
 p.add_argument('--input',help='PS3_PAD_FILE text, e.g. CROSS or RY=0; empty centres/releases')
 p.add_argument('--capture');a=p.parse_args()
 if a.input is not None:write(a.run/'pad.txt',a.input+'\n')
 fields={n:getattr(a,n) for n in ('dispatch','vertex','texture','light_far') if getattr(a,n) is not None}
 if fields:command(a.run,**fields)
 if a.capture:print(capture(a.run,a.capture))
 else:print(json.dumps(read(a.run),indent=2))
if __name__=='__main__':main()
