#!/usr/bin/env python3
"""Closed-loop iPhone camera tutorial through the existing PS3_PAD_FILE API."""
import argparse,json,time,subprocess
from pathlib import Path
from geometry_device_control import call,report,BUNDLE
from capture_device_frame import capture
from drive_host_gameplay import classify
ROOT=Path(__file__).resolve().parents[1]
def pad(device,run,text):
 p=Path(run)/'pad-transfer.txt';p.write_text(text+'\n')
 call(['device','copy','to','--device',device,'--domain-type','appDataContainer','--domain-identifier',BUNDLE,'--source',str(p.resolve()),'--destination','Documents/ios48-pad.txt'])
def pulse(device,run,value):
 try:pad(device,run,value);time.sleep(1)
 finally:pad(device,run,'')
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run=a.output;run.mkdir(parents=True,exist_ok=False)
 initial=report(a.device,run/'initial.json');stage='menu';actions=[];gone=0;free_seen=0;start=time.monotonic()
 if not initial.get('light_far_control_enabled'):raise RuntimeError('not the build48 test process')
 pad(a.device,run,'')
 try:
  for i in range(90):
   if time.monotonic()-start>1200:raise RuntimeError('tutorial deadline')
   d=report(a.device,run/'latest.json')
   if (d['pid'],d['geometry_control_session'])!=(initial['pid'],initial['geometry_control_session']):raise RuntimeError('process changed')
   result=capture(a.device,run/f'capture-{i:03}','Documents/critical45-frame-request.txt','Documents/critical45-frame.ppm');image=result['png']
   ocr=subprocess.run([str(ROOT/'build/bces01229/host-research/HostFrameOCR'),image],capture_output=True,text=True,check=True,timeout=40)
   Path(image).with_name('ocr.json').write_text(ocr.stdout);text,menu,up,left,free=classify(json.loads(ocr.stdout));print(json.dumps(dict(stage=stage,text=text,image=image)),flush=True)
   if stage=='menu' and menu:pulse(a.device,run,'CROSS');actions.append(dict(input='CROSS',evidence=image));stage='up'
   elif stage in ('menu','up') and up:pulse(a.device,run,'RY=0');actions.append(dict(input='RY=0',evidence=image));stage='left'
   elif stage=='left' and left:pulse(a.device,run,'RX=0');actions.append(dict(input='RX=0',evidence=image));stage='verify'
   elif stage in ('menu','up','left','verify'):
    gone=gone+1 if not(up or left or menu) else 0
    if free and not(up or left or menu):free_seen+=1
    if gone>=2 and free and free_seen>=2:
     proof=dict(pid=d['pid'],session=d['geometry_control_session'],right_up_completed=True,right_left_completed=True,free_gameplay_verified=True,actions=actions,final_capture=image,neutral_input=True,verification='Two actual unlocked free-gameplay mission objectives establish that no camera tutorial gate remains; only recorded inputs are claimed to have been automated.',left_input_automated=any(x['input']=='RX=0' for x in actions),up_input_automated=any(x['input']=='RY=0' for x in actions))
     (run/'scene-ready.json').write_text(json.dumps(proof,indent=2)+'\n');print('Verified iPhone free gameplay; input centred',flush=True);return
   (run/'actions.json').write_text(json.dumps(dict(stage=stage,actions=actions),indent=2)+'\n')
   time.sleep(8)
  raise RuntimeError('unrecognized tutorial state; inspect captures')
 finally:pad(a.device,run,'')
if __name__=='__main__':main()
