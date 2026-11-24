#!/usr/bin/env python3
"""Bounded counter window; no profiler/trace is armed by this command.

Run only after manually confirming the scene and a fixed camera. FPS is the
change in guest presents divided by the report's monotonic time, not HUD mean.
"""
import argparse,json,os,subprocess,time
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--device',required=True)
    ap.add_argument('--output',required=True,type=Path)
    ap.add_argument('--seconds',type=int,default=30,choices=range(10,61))
    ap.add_argument('--scene',required=True)
    ap.add_argument('--max-thermal-state',type=int,choices=(0,1,2),default=2,
                    help='0 requires normal throughout; 1 also allows fair; default 2 allows serious')
    ap.add_argument('--geometry-pair',type=int,nargs=2,choices=(0,1,2),metavar=('SKIN','CULL'),help='Expected skinning/culling routes: 0 SPU, 1 ARM64, 2 Metal')
    ap.add_argument('--geometry-check',choices=('performance','validation'),default='performance')
    args=ap.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer')
    snapshots=[];failure=None
    for index in range(100):
        dest=args.output/f'{index:03}.json'
        command=['xcrun','devicectl','--timeout','15','device','copy','from','--device',args.device,
                 '--domain-type','appDataContainer','--domain-identifier','dev.infamous2.iosprobe',
                 '--source','Documents/bces-device-report.json','--destination',str(dest.resolve())]
        run=subprocess.run(command,env=env,capture_output=True,text=True,timeout=20)
        if run.returncode:
            failure='device read failed: '+run.stderr[-1000:];break
        current=json.loads(dest.read_text());perf=current['performance']
        if snapshots:
            first=snapshots[0];last=snapshots[-1]
            if current['pid']!=first['pid'] or current['session']!=first['session']:
                failure='process/session changed';break
            if perf['sample_monotonic_seconds']<=last['performance']['sample_monotonic_seconds']:
                failure='stale telemetry (app may be inactive)';break
            if current['guest_present_calls']<last['guest_present_calls']:
                failure='guest counter regressed';break
            if current.get('ssao_depth_cleanup_enabled')!=first.get('ssao_depth_cleanup_enabled'):
                failure='SSAO depth cleanup mode changed during window';break
            if current.get('edge_arm64_enabled')!=first.get('edge_arm64_enabled'):
                failure='Edge mode changed during window';break
        if args.geometry_pair is not None:
            actual=[perf.get('skin_route'),perf.get('cull_route')]
            if actual!=args.geometry_pair:
                failure=f'geometry route changed/unexpected: {actual}; expected {args.geometry_pair}';break
            active=any(args.geometry_pair)
            if active and bool(perf.get('geometry_validation_all'))!=(args.geometry_check=='validation'):
                failure='geometry validation mode differs from requested measurement';break
            if 2 in args.geometry_pair and perf.get('geometry_metal_state')!=2:
                failure='geometry Metal not ready';break
            for prefix,route in zip(('skin','cull'),args.geometry_pair):
                if route and (perf.get(prefix+'_blocked',0)&(1<<route)):
                    failure=prefix+' route blocked; reference fallback is not a measurement of selected route';break
                if snapshots and any(perf.get(prefix+'_'+field,0)>snapshots[0]['performance'].get(prefix+'_'+field,0) for field in ('mismatches','failures')):
                    failure=prefix+' differential mismatch or kernel failure';break
            if failure:break
        snapshots.append(current)
        if perf['thermal_state']>args.max_thermal_state:
            failure=('critical thermal state; measurement stopped' if perf['thermal_state']>=3 else
                     'thermal state exceeds requested limit; measurement stopped');break
        if current.get('metal_lighting_faults',0) or current.get('metal_ssao_faults',0) or current.get('Metal_errors',0):
            failure='Metal fault; measurement stopped';break
        if current.get('edge_arm64_mismatches',0):
            failure='Edge differential mismatch; measurement stopped';break
        duration=perf['sample_monotonic_seconds']-snapshots[0]['performance']['sample_monotonic_seconds']
        if duration>=args.seconds:break
        time.sleep(3)
    result={'scene':args.scene,'max_thermal_state':args.max_thermal_state,'samples':len(snapshots),'valid_counter_window':failure is None,'failure':failure,
            'limitations':['Scene/camera must be independently confirmed.','No raw frame median/p95 is derived from telemetry averages.','This window alone is not a matched A/B result.']}
    if len(snapshots)>1:
        a,b=snapshots[0],snapshots[-1]
        seconds=b['performance']['sample_monotonic_seconds']-a['performance']['sample_monotonic_seconds']
        frames=b['guest_present_calls']-a['guest_present_calls']
        result.update(pid=a['pid'],session=a['session'],seconds=seconds,guest_frames=frames,fps=frames/seconds,
          metal_requested=a.get('metal_lighting_requested'),
          metal_ssao_requested=a.get('metal_ssao_requested'),
          ssao_depth_cleanup_enabled=a.get('ssao_depth_cleanup_enabled'),
          edge_arm64_enabled=a.get('edge_arm64_enabled'),
          thermal_states=sorted({s['performance']['thermal_state'] for s in snapshots}),
          footprint_min=min(s['physical_footprint'] for s in snapshots),footprint_max=max(s['physical_footprint'] for s in snapshots),
          pipeline_started_delta=b['performance']['pipeline_started']-a['performance']['pipeline_started'],
          gpu_window_ms_mean=sum(s['performance']['gpu_mean_ms'] for s in snapshots)/len(snapshots))
        for key in ('Metal_presented','Metal_completed','Metal_submitted','metal_lighting_passes','metal_lighting_bindings','metal_lighting_skipped_tiles','metal_lighting_fallback_jobs',
                    'metal_ssao_passes','metal_ssao_bindings','metal_ssao_skipped_tiles','metal_ssao_fallback_jobs',
                    'ssao_depth_original_calls','ssao_depth_boundary_blocks',
                    'edge_arm64_d808_calls','edge_arm64_d8a8_calls','edge_arm64_da28_calls',
                    'edge_arm64_validations','edge_arm64_mismatches'):
            result[key+'_delta']=(b[key]-a[key]) if key in a and key in b else None
        if frames==0 and not (args.geometry_pair is not None and args.geometry_check=='validation'):result.update(valid_counter_window=False,failure='no guest frames')
    if args.geometry_pair is not None and len(snapshots)>1:
        a,b=snapshots[0]['performance'],snapshots[-1]['performance'];geometry={}
        for prefix,route in zip(('skin','cull'),args.geometry_pair):
            delta={field:b.get(prefix+'_'+field,0)-a.get(prefix+'_'+field,0) for field in ('calls','fallbacks','validations','mismatches','failures','trial_ms','gpu_ms','reference_ms')}
            geometry[prefix]={'requested_route':route,**delta}
            if route and delta['calls']<=0:result.update(valid_counter_window=False,failure=prefix+' selected route produced no successful trial calls')
            if route and args.geometry_check=='performance' and delta['validations']:
                result.update(valid_counter_window=False,failure=prefix+' validation still running inside performance window')
            if route and args.geometry_check=='validation' and delta['validations']<=0:
                result.update(valid_counter_window=False,failure=prefix+' no differential validation observed')
        result['geometry']=geometry;result['geometry_check']=args.geometry_check
        result['limitations'].append('Fallback counts indicate partial optimization coverage; cumulative per-job CPU/GPU times overlap and are not frame savings.')
    (args.output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)
    return 0 if result['valid_counter_window'] else 1
if __name__=='__main__':raise SystemExit(main())
