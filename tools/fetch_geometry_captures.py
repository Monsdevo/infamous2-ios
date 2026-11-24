#!/usr/bin/env python3
"""Fetch only the current process's bounded diagnostic fixtures, never game data.

Arm capture in SPU/SPU, disarm it and wait for pending=0 before invoking.
The resulting binary files contain game-derived data and belong under out/.
"""
import argparse,csv,json,re
from pathlib import Path
from geometry_device_control import report,call,BUNDLE

def fetch(device,output):
 output=Path(output);output.mkdir(parents=True,exist_ok=False)
 d=report(device,output/'report.json')
 if d.get('geometry_capture_enabled') or d.get('geometry_capture_pending',0):
  raise RuntimeError('Disarm captures and wait until all captures are flushed')
 pid=d['pid'];manifest=output/'manifest.csv'
 call(['device','copy','from','--device',device,'--domain-type','appDataContainer','--domain-identifier',BUNDLE,'--source','Documents/geometry-captures.csv','--destination',str(manifest.resolve())])
 files={}
 for row in csv.reader(manifest.read_text().splitlines()):
  if len(row)!=6:continue
  name=row[0];match=re.fullmatch(r'geometry-(\d+)-(skin|cull)-(\d{2})\.bin',name)
  if not match or int(match[1])!=pid:continue
  if int(match[3])>=64:raise ValueError('Invalid capture slot')
  files[name]={'file':name,'kind':int(row[1]),'slot':int(row[2]),'image_id':int(row[3]),'argument':int(row[4]),'fpcr':int(row[5])}
 if not files:raise RuntimeError('No captures for the current process')
 if len(files)>64:raise ValueError('Capture bound exceeded')
 for name in sorted(files):
  call(['device','copy','from','--device',device,'--domain-type','appDataContainer','--domain-identifier',BUNDLE,'--source','Documents/'+name,'--destination',str((output/name).resolve())])
  size=(output/name).stat().st_size
  if not 512*1024<=size<=2*1024*1024:raise ValueError('Unexpected fixture size')
 result={'pid':pid,'session':d.get('geometry_control_session'),'captures':list(files.values())}
 (output/'captures.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2));return result

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();fetch(a.device,a.output)
