"""Pure checks for build43's launch-fixed RSX comparison."""
FIELDS=('methods','state_skipped','forwarded','sync_forwarded','draw_forwarded')
def validate_rsx(d,enabled,first=None):
 p=d['performance'];errors=[]
 if not p.get('rsx_legacy_configured'):errors.append('RSX selection not configured')
 if p.get('rsx_legacy_requested')!=int(enabled) or p.get('rsx_legacy_enabled')!=int(enabled):errors.append('unexpected RSX launch mode')
 if p.get('rsx_legacy_debug_fallback'):errors.append('RSX diagnostic full-path fallback active')
 if any('rsx_legacy_'+field not in p for field in FIELDS):return errors+['RSX counters missing']
 if p['rsx_legacy_methods']!=p['rsx_legacy_state_skipped']+p['rsx_legacy_forwarded']:errors.append('RSX counter snapshot inconsistent')
 if p['rsx_legacy_sync_forwarded']>p['rsx_legacy_forwarded'] or p['rsx_legacy_draw_forwarded']>p['rsx_legacy_forwarded']:errors.append('invalid forwarded subset')
 if not enabled and p['rsx_legacy_state_skipped']:errors.append('reference process has skipped state')
 if d.get('cpu_profile_state',0) in (1,2) or d.get('frame_trace_state',0) in (1,2):errors.append('profiler/trace active during FPS window')
 if first:
  f=first['performance']
  for field in FIELDS:
   if p['rsx_legacy_'+field]<f['rsx_legacy_'+field]:errors.append('RSX counter regressed: '+field)
 return errors
