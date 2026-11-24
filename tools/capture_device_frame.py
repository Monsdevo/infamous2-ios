#!/usr/bin/env python3
"""Explicit one-shot rendered-surface capture, outside all FPS windows."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
import uuid
from geometry_device_control import call,report,BUNDLE


def parse_frame(path,token):
    with path.open('rb') as f:
        if f.readline()!=b'P6\n':raise ValueError('not binary PPM')
        comment=f.readline().decode('ascii')
        if not re.fullmatch(r'# bces-request='+re.escape(token)+r' frame=\d+\n',comment):raise ValueError('stale capture token')
        width,height=map(int,f.readline().split())
        if not(0<width<=4096 and 0<height<=4096) or f.readline()!=b'255\n':raise ValueError('unsupported PPM dimensions/range')
        if len(f.read())!=width*height*3:raise ValueError('partial PPM payload')
    return width,height


def capture(device,output,trigger,source):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    before=report(device,output/'before.json');token='frame'+uuid.uuid4().hex
    request=output/'request.txt';request.write_text(token+'\n')
    # The renderer consumes/unlinks the request immediately. CoreDevice may
    # report a missing destination during its post-copy stat even though the
    # transfer succeeded. Only a matching complete frame proves success.
    last_error=None
    try:
        call(['device','copy','to','--device',device,'--domain-type','appDataContainer','--domain-identifier',BUNDLE,
              '--source',str(request.resolve()),'--destination',trigger])
    except RuntimeError as error:
        last_error=str(error)
        (output/'request-transfer-warning.txt').write_text(last_error+'\n')
    for attempt in range(12):
        time.sleep(1)
        try:
            path=output/'frame.ppm'
            call(['device','copy','from','--device',device,'--domain-type','appDataContainer','--domain-identifier',BUNDLE,
                  '--source',source,'--destination',str(path.resolve())])
            width,height=parse_frame(path,token)
            after=report(device,output/'after.json')
            if after['pid']!=before['pid']:raise RuntimeError('Process changed during capture')
            png=output/'frame.png'
            subprocess.run(['sips','-s','format','png',str(path),'--out',str(png)],check=True,capture_output=True)
            result={'pid':after['pid'],'token':token,'width':width,'height':height,'png':str(png.resolve()),
                    'limitation':'Actual game surface, without UIKit HUD; GPU fence/readback used only for this capture.'}
            (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return result
        except (RuntimeError,ValueError,OSError) as error:last_error=str(error)
    raise RuntimeError('One-shot capture did not finish: '+str(last_error))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device',required=True);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--trigger',default='Documents/critical45-frame-request.txt');p.add_argument('--source',default='Documents/critical45-frame.ppm')
    a=p.parse_args();capture(a.device,a.output,a.trigger,a.source)
