"""Pure checks/statistics for coherent build42+ presentation events."""
import math

def validate_sample(d,pair,validation,first=None,thermal_state=0):
 p=d['performance'];errors=[]
 if p.get('geometry_timer_version')!=2:errors.append('full-call timer schema missing')
 if [p.get('skin_route'),p.get('cull_route')]!=list(pair):errors.append('unexpected geometry routes')
 if any(pair) and bool(p.get('geometry_validation_all'))!=validation:errors.append('unexpected validation mode')
 if p.get('thermal_state')!=thermal_state:errors.append('thermal state differs from requested comparison condition')
 if p.get('low_power_mode'):errors.append('low-power mode enabled')
 if not p.get('application_active') or p.get('settings_panel_open'):errors.append('application inactive or settings panel open')
 if d.get('geometry_capture_enabled') or d.get('geometry_capture_pending',0):errors.append('reference capture still armed/pending')
 if 2 in pair and p.get('geometry_metal_state')!=2:errors.append('geometry shader not ready')
 if not validation and any(p.get(k+'_calibrating',0) for k in ('skin','cull')):errors.append('GPU calibration in progress')
 if not d.get('metal_lighting_requested') or not d.get('metal_ssao_requested'):errors.append('lighting/SSAO baseline differs')
 if d.get('Metal_errors',0) or d.get('metal_lighting_faults',0) or d.get('metal_ssao_faults',0):errors.append('renderer/compute fault')
 for prefix,route in zip(('skin','cull'),pair):
  if route and p.get(prefix+'_blocked',0)&(1<<route):errors.append(prefix+' selected route blocked')
 if first:
  f=first['performance']
  if (d.get('pid'),d.get('geometry_control_session'))!=(first.get('pid'),first.get('geometry_control_session')):errors.append('process/session changed')
  if p.get('geometry_revision')!=f.get('geometry_revision'):errors.append('configuration changed')
  if p['present_total']<f['present_total'] or p['present_time']<f['present_time']:errors.append('presentation counter/time regressed')
  if (p['present_total']==f['present_total'])!=(p['present_time']==f['present_time']):errors.append('incoherent presentation counter/time')
  if p.get('memory_warning_count',0)>f.get('memory_warning_count',0):errors.append('memory pressure during window')
  if not validation and p.get('pipeline_started',0)>f.get('pipeline_started',0):errors.append('new renderer shader compilation during window')
  for prefix,route in zip(('skin','cull'),pair):
   for field in ('mismatches','failures'):
    if p.get(prefix+'_'+field,0)>f.get(prefix+'_'+field,0):errors.append(prefix+' '+field+' increased')
   if not validation:
    for field in ('calibration_batches','validations'):
     if p.get(prefix+'_'+field,0)>f.get(prefix+'_'+field,0):errors.append(prefix+' '+field+' still active in performance window')
 return errors

def frame_statistics(rows,first,last):
 selected=sorted((int(r['sequence']),float(r['monotonic_s'])) for r in rows if first<=int(r['sequence'])<=last)
 if len(selected)!=last-first+1:raise ValueError('raw frame events missing')
 for i,(sequence,t) in enumerate(selected):
  if sequence!=first+i or not math.isfinite(t):raise ValueError('duplicate/noncontiguous/invalid frame event')
 intervals=[(b[1]-a[1])*1000 for a,b in zip(selected,selected[1:])]
 if not intervals or min(intervals)<=0:raise ValueError('not enough strictly increasing frames')
 ordered=sorted(intervals);n=len(ordered);median=(ordered[n//2]+ordered[(n-1)//2])/2
 return {'frame_intervals':n,'present_seconds':selected[-1][1]-selected[0][1],'fps':n/(selected[-1][1]-selected[0][1]),'frame_mean_ms':sum(intervals)/n,'frame_median_ms':median,'frame_p95_ms':ordered[math.ceil(.95*n)-1],'frame_max_ms':ordered[-1]}
