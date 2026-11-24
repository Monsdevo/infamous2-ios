"""Exact-input renderer experiment gates; modes 2 are correctness runs only."""
FIELDS=('calls','lookups','hits','misses','bypasses','evictions','validations','mismatches',
        'compared_bytes','snapshot_bytes','output_bytes','resident_bytes')

def validate_memo(d,modes,first=None,correctness=False):
    errors=[]
    if not d.get('renderer_memo_control_enabled'):errors.append('memo development control absent')
    if first and bool(d.get('runtime_log_capped'))!=bool(first.get('runtime_log_capped')):
        errors.append('runtime log output changed during window')
    for field in ('cpu_profile_state','frame_trace_state'):
        if d.get(field) in (1,2):errors.append(field+' active during memo window')
    for kind,mode in zip(('vertex','texture'),modes):
        s=d.get('renderer_memo',{}).get(kind,{})
        if s.get('mode')!=mode:errors.append(kind+' memo mode differs')
        if not correctness and mode==2:errors.append('reference validation is not a performance run')
        if any(k not in s for k in FIELDS):errors.append(kind+' counters missing');continue
        if any(not isinstance(s[k],int) or s[k]<0 for k in FIELDS):errors.append(kind+' invalid counters');continue
        if s['lookups']!=s['hits']+s['misses']+s['bypasses']:errors.append(kind+' lookup accounting differs')
        if s['lookups']>s['calls']:errors.append(kind+' lookup count exceeds calls')
        if s['mismatches']:errors.append(kind+' reference mismatch recorded')
        if s['resident_bytes']>128*1024*1024:errors.append(kind+' cache byte budget exceeded')
        if first:
            old=first['renderer_memo'][kind]
            if any(s[k]<old[k] for k in FIELDS if k!='resident_bytes'):errors.append(kind+' cumulative counter regressed')
            if not correctness and s['validations']!=old['validations']:errors.append(kind+' validation still active')
    return errors
