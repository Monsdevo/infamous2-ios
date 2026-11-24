#!/usr/bin/env python3
"""Measure selected cache modes in a confirmed, fixed gameplay scene."""
import argparse
import json
from pathlib import Path
from measure_geometry import measure
from memo_measurement import validate_memo,FIELDS
from rsx_measurement import validate_rsx

def capture(device,modes,output,thermal,seconds=30,correctness=False):
    output=Path(output)
    def check(d,first):
        return validate_memo(d,modes,first,correctness)+validate_rsx(d,True,first)
    r=measure(device,(0,0),False,output,'first-gameplay-fixed-camera',seconds,
              0 if correctness else 120,60,thermal,False,check)
    r.update(memo_modes=list(modes),is_performance_measurement=not correctness)
    files=sorted(output.glob('[0-9][0-9][0-9].json'))
    r['memo']={}
    if len(files)>1:
        a=json.loads(files[0].read_text());b=json.loads(files[-1].read_text())
        r['runtime_log_capped']=bool(a.get('runtime_log_capped'))
        for kind,mode in zip(('vertex','texture'),modes):
            x,y=a['renderer_memo'][kind],b['renderer_memo'][kind]
            delta={k:y[k]-x[k] for k in FIELDS if k!='resident_bytes'}
            r['memo'][kind]={'mode':mode,**delta,'resident_bytes':y['resident_bytes'],
                'hit_fraction_of_calls':delta['hits']/delta['calls'] if delta['calls'] else None}
            if mode and (delta['calls']<=0 or delta['hits']<=0):r.update(valid=False,failure=kind+' selected memo produced no calls/hits')
            if mode==2 and delta['validations']<=0:r.update(valid=False,failure=kind+' reference validation did not run')
        r['physical_footprint_range_bytes']=[min(json.loads(p.read_text()).get('physical_footprint',0) for p in files),max(json.loads(p.read_text()).get('physical_footprint',0) for p in files)]
    if correctness:
        r['comparison_scope']='correctness_only'
        r.pop('fps',None);r.pop('raw_frame_stats',None)
        r['limitations'].append('Reference validation active: timings are not an FPS benchmark.')
    r['limitations']+=['Live switches only select stateless reference/exact-input memo behavior; cached entries always recheck bytes.',
        'No background/temperature or camera manipulation during the window; same category does not prove identical clocks.']
    (output/'summary.json').write_text(json.dumps(r,indent=2)+'\n')
    print('MEMO_RESULT '+json.dumps(r),flush=True)
    return r

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device',required=True)
    p.add_argument('--modes',type=int,nargs=2,choices=(0,1,2),required=True);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--thermal-state',type=int,choices=(0,1,2,3),required=True);p.add_argument('--seconds',type=int,default=30)
    p.add_argument('--correctness-only',action='store_true');a=p.parse_args()
    if 2 in a.modes and not a.correctness_only:p.error('mode 2 requires --correctness-only')
    r=capture(a.device,a.modes,a.output,a.thermal_state,a.seconds,a.correctness_only);raise SystemExit(0 if r['valid'] else 1)
