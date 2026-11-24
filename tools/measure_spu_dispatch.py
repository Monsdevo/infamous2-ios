#!/usr/bin/env python3
"""Actual-present A/B window for the opt-in SPU dispatch/reset fast path."""
import argparse
import json
from pathlib import Path
from measure_geometry import measure
from rsx_measurement import validate_rsx

FIELDS=('eligible','fast','fallback','reset_checks','reset_bypasses')


def validate(d,mode,first=None,vertex=0):
    errors=validate_rsx(d,True,first)
    if not d.get('spu_dispatch_control_enabled'):errors.append('SPU control absent')
    s=d.get('spu_dispatch',{})
    if s.get('enabled')!=mode:errors.append('SPU dispatch mode differs')
    if any(not isinstance(s.get(k),int) or s[k]<0 for k in FIELDS):errors.append('SPU counters absent/invalid')
    for name in ('cpu_profile_state','frame_trace_state'):
        if d.get(name) in (1,2):errors.append(name+' active during FPS window')
    for kind,wanted in (('vertex',vertex),('texture',0)):
        memo=d.get('renderer_memo',{}).get(kind,{})
        if memo.get('mode')!=wanted or memo.get('mismatches',0):errors.append(kind+' memo baseline differs/faulted')
    if first:
        if bool(d.get('runtime_log_capped'))!=bool(first.get('runtime_log_capped')):errors.append('log output changed during window')
        old=first['spu_dispatch']
        if all(k in s for k in FIELDS) and any(s[k]<old[k] for k in FIELDS):errors.append('SPU counter regressed')
        if not mode and s.get('reset_bypasses')!=old['reset_bypasses']:errors.append('reset bypass unexpectedly active in reference')
    return errors


def capture(device,mode,output,thermal,seconds=30,vertex=0):
    output=Path(output)
    result=measure(device,(0,0),False,output,'first-gameplay-fixed-camera',seconds,120,60,thermal,False,
                   lambda d,first:validate(d,mode,first,vertex))
    files=sorted(output.glob('[0-9][0-9][0-9].json'))
    if len(files)>1:
        a=json.loads(files[0].read_text());b=json.loads(files[-1].read_text())
        delta={k:b['spu_dispatch'][k]-a['spu_dispatch'][k] for k in FIELDS}
        result.update(spu_dispatch_mode=mode,vertex_memo_mode=vertex,spu_dispatch=delta,
                      runtime_log_capped=bool(a.get('runtime_log_capped')))
        if delta['eligible']<=0:result.update(valid=False,failure='no eligible WWS dispatch coverage')
        if mode and (delta['fast']<=0 or delta['reset_bypasses']<=0):result.update(valid=False,failure='candidate paths had no actual coverage')
        if not mode and delta['fast']>0:result.update(valid=False,failure='fast dispatch unexpectedly active in reference')
    result['limitations']+=['Same thermal category is not equal clocks; use bracketing and repeated controls.',
        'Counters prove paths executed, not time saved. No interval profiler/capture is permitted in this FPS window.']
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result.get(k) for k in ('valid','failure','fps','raw_frame_stats','spu_dispatch','thermal_states','runtime_log_capped')},indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device',required=True)
    p.add_argument('--mode',type=int,choices=(0,1),required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--thermal-state',type=int,choices=(0,1,2),required=True)
    p.add_argument('--seconds',type=int,default=30);p.add_argument('--vertex-memo',type=int,choices=(0,1),default=0)
    a=p.parse_args();r=capture(a.device,a.mode,a.output,a.thermal_state,a.seconds,a.vertex_memo);raise SystemExit(0 if r['valid'] else 1)
