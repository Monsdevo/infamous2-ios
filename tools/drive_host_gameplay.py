#!/usr/bin/env python3
"""Closed-loop CROSS -> right-up -> right-left macro, with saved OCR evidence.

Only recognizes explicit camera instructions. A world frame alone never marks
free gameplay. Unrecognized prompts preserve evidence and eventually fail.
"""
import argparse,json,subprocess,time,unicodedata
from pathlib import Path
from host_research_control import capture,read,write
ROOT=Path(__file__).resolve().parents[1]
def normalize(s):return ''.join(c for c in unicodedata.normalize('NFKD',s.upper()) if not unicodedata.combining(c)).replace('İ','I')
def classify(rows):
 text=normalize(' '.join(r['text'] for r in rows))
 menu=('YENI BIR OYUNA BASLA' in text or 'START A NEW GAME' in text)
 instruction=('CUBU' in text or 'STICK' in text or 'BAK' in text or 'LOOK' in text)
 up=instruction and ('YUKARI' in text or 'LOOK UP' in text)
 left=instruction and ('SOLA' in text or 'SOL TARAFA' in text or 'LOOK LEFT' in text)
 free=('KARGAS' in text and 'DOGRU' in text) or ('CHAOS' in text and ('HEAD' in text or 'TOWARD' in text))
 return text,menu,up,left,free
def pulse(run,value,seconds):
 try:write(run/'pad.txt',value+'\n');time.sleep(seconds)
 finally:write(run/'pad.txt','\n')
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--after-cross',action='store_true');p.add_argument('--resume',action='store_true');p.add_argument('--maximum-seconds',type=int,default=1200);a=p.parse_args()
 run=a.run.resolve();identity=read(run);stage='up' if a.after_cross else 'menu';actions=[];no_prompt=0;start=time.monotonic()
 start_index=0
 if a.resume:
  previous=json.loads((run/'macro.json').read_text())
  if (previous['pid'],previous['session'])!=(identity['pid'],identity['session']):raise RuntimeError('resume belongs to another process')
  stage=previous['stage'];actions=previous['actions']
  if stage=='done':return
  start_index=1+max((int(p.name.split('-')[1]) for p in (run/'captures').glob('macro-*')),default=-1)
 def save():write(run/'macro.json',json.dumps(dict(pid=identity['pid'],session=identity['session'],stage=stage,actions=actions),indent=2)+'\n')
 try:
  for index in range(start_index,start_index+100):
   if time.monotonic()-start>a.maximum_seconds:raise RuntimeError('gameplay macro deadline')
   r=read(run)
   if (r['pid'],r['session'])!=(identity['pid'],identity['session']):raise RuntimeError('process changed')
   image=capture(run,f'macro-{index:03}')
   try:ocr=subprocess.run([str(ROOT/'build/bces01229/host-research/HostFrameOCR'),image],capture_output=True,text=True,check=True,timeout=40)
   except subprocess.TimeoutExpired:
    Path(image).with_name('ocr-error.json').write_text(json.dumps(dict(error='OCR deadline; no input issued',stage=stage)))
    save();continue
   rows=json.loads(ocr.stdout);Path(image).with_name('ocr.json').write_text(ocr.stdout)
   text,menu,up,left,free=classify(rows);print(json.dumps(dict(stage=stage,text=text,image=image)),flush=True)
   if stage=='menu' and menu:
    pulse(run,'CROSS',.6);actions.append(dict(input='CROSS',evidence=image));stage='up'
   elif stage=='up' and up:
    pulse(run,'RY=0',1.0);actions.append(dict(input='RY=0',evidence=image));stage='left'
   elif stage=='left' and left:
    pulse(run,'RX=0',1.0);actions.append(dict(input='RX=0',evidence=image));stage='verify'
   elif stage=='verify':
    no_prompt=no_prompt+1 if not(up or left or menu) else 0
    if no_prompt>=2 and free and (run/'world-mark.txt').exists():
     proof=dict(pid=r['pid'],session=r['session'],right_up_completed=True,right_left_completed=True,free_gameplay_verified=True,neutral_input=True,actions=actions,final_capture=image,verification='Explicit up then left instructions observed before inputs; both absent on two later captures, then free-gameplay mission objective recognized')
     write(run/'scene-ready.json',json.dumps(proof,indent=2)+'\n');stage='done';save();print('Camera tutorial completed; input centred; free gameplay evidence saved',flush=True);return
   save();time.sleep(10)
  raise RuntimeError('unrecognized gameplay state; inspect saved captures')
 finally:write(run/'pad.txt','\n')
if __name__=='__main__':main()
