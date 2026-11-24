#!/usr/bin/env python3
"""Explicit, session-bound development control for build42+ only."""
import argparse,json,os,subprocess,time,uuid
from pathlib import Path
BUNDLE='dev.infamous2.iosprobe'
ENV=dict(os.environ,DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer')
def call(args):
 for attempt in range(3):
  run=subprocess.run(['xcrun','devicectl','--timeout','20',*args],env=ENV,capture_output=True,text=True,timeout=25)
  if not run.returncode:return run
  message=run.stderr[-1500:]+run.stdout[-1000:]
  transient=any(x in message for x in ('Connection reset by peer','Connection was invalidated','device could not be established','Command timeout of'))
  if args[:2]!=['device','copy'] or not transient or attempt==2:raise RuntimeError(message)
  time.sleep(1)
 raise RuntimeError('device transfer failed')

def report(device,destination):
 destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
 call(['device','copy','from','--device',device,'--domain-type','appDataContainer','--domain-identifier',BUNDLE,'--source','Documents/bces-device-report.json','--destination',str(destination.resolve())])
 return json.loads(destination.read_text())

def command(device,fields,output):
 output=Path(output);output.mkdir(parents=True,exist_ok=True)
 initial=report(device,output/'before.json')
 if not initial.get('geometry_control_enabled'):raise RuntimeError('Launch build42+ with --geometry-control; this process has no development control enabled')
 session=initial['geometry_control_session'];token=uuid.uuid4().hex
 packet={'session':session,'token':token,**fields};path=output/'command.json';path.write_text(json.dumps(packet)+'\n')
 call(['device','copy','to','--device',device,'--domain-type','appDataContainer','--domain-identifier',BUNDLE,'--source',str(path.resolve()),'--destination','Documents/geometry-control.json'])
 for index in range(15):
  d=report(device,output/f'ack-{index:02}.json')
  if d.get('geometry_control_session')!=session or d.get('pid')!=initial.get('pid'):raise RuntimeError('Process changed before control acknowledgement')
  if d.get('geometry_control_ack')==token:return d
  time.sleep(1)
 raise RuntimeError('Control not acknowledged: '+str(d.get('geometry_control_error')))

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--device',required=True);ap.add_argument('--output',type=Path,required=True)
 ap.add_argument('--pair',nargs=2,type=int,choices=(0,1,2));ap.add_argument('--validation',choices=('on','off'))
 ap.add_argument('--capture',choices=('on','off'));ap.add_argument('--prepare-metal',action='store_true');ap.add_argument('--frames-since',type=int)
 ap.add_argument('--vertex-memo',type=int,choices=(0,1,2));ap.add_argument('--texture-memo',type=int,choices=(0,1,2))
 ap.add_argument('--spu-dispatch',type=int,choices=(0,1))
 ap.add_argument('--light-far',type=int,choices=(0,1))
 a=ap.parse_args();fields={}
 if (a.pair is None)!=(a.validation is None):ap.error('--pair and --validation are required together')
 if a.pair:fields.update(skin=a.pair[0],cull=a.pair[1],validation=a.validation=='on')
 if a.capture is not None:fields['capture']=a.capture=='on'
 if a.prepare_metal:fields['prepare_metal']=True
 if a.frames_since is not None:fields['frames_since']=a.frames_since
 if a.vertex_memo is not None:fields['vertex_memo']=a.vertex_memo
 if a.texture_memo is not None:fields['texture_memo']=a.texture_memo
 if a.spu_dispatch is not None:fields['spu_dispatch']=a.spu_dispatch
 if a.light_far is not None:fields['light_far']=a.light_far
 d=command(a.device,fields,a.output);print(json.dumps({k:d.get(k) for k in ('pid','geometry_control_ack','geometry_control_applied_s','geometry_frame_export','geometry_control_error')},indent=2))
if __name__=='__main__':main()
