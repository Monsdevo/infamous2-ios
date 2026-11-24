#!/usr/bin/env python3
"""Interpret raw Metal stage counters; zero/zero is an absent stage, not epoch0."""
import argparse,json,math
from pathlib import Path
from analyze_frame_trace import union_seconds
def analyze(d):
 scale=d['gpu_ticks_to_cpu_ns']/1e6
 if not math.isfinite(scale) or scale<=0:raise ValueError('invalid timestamp calibration')
 rows=[];vs=[];fs=[];cs=[];invalid=0
 for original in d['rows']:
  r={k:v for k,v in original.items() if k not in ('span_ms','vertex_ms','fragment_ms','valid')};ticks=r['raw_gpu_ticks'];r['valid']=True;present=[]
  stages=[('compute',(0,1),cs)] if r.get('encoder_kind')=='compute' else [('vertex',(0,1),vs),('fragment',(2,3),fs)]
  for name,indices,spans in stages:
   a,b=(int(ticks[i]) for i in indices)
   if a==0 and b==0:r[name+'_present']=False;r[name+'_ms']=0;continue
   good=0<a<=b<(1<<64)-1;r[name+'_present']=good
   if not good:r['valid']=False;r[name+'_ms']=None;continue
   r[name+'_ms']=(b-a)*scale;spans.append((a,b));present.extend((a,b))
  r['timestamp_span_ms']=(max(present)-min(present))*scale if present else 0
  invalid+=not r['valid'];rows.append(r)
 all_spans=vs+fs;lo=min((a for a,b in all_spans),default=0);hi=max((b for a,b in all_spans),default=0)
 clo=min((a for a,b in cs),default=0);chi=max((b for a,b in cs),default=0)
 return dict(valid=not invalid and not d.get('dropped_encoders',0),invalid_rows=invalid,rows=rows,vertex_union_ms=union_seconds(vs,lo,hi)*scale,fragment_union_ms=union_seconds(fs,lo,hi)*scale,compute_union_ms=union_seconds(cs,clo,chi)*scale,all_render_stage_union_ms=union_seconds(all_spans,lo,hi)*scale,render_timestamp_extent_ms=(hi-lo)*scale,scope='Render stages and tagged compute encoder boundaries. Wall spans may overlap or include waits; do not add them as isolated shader cost.')
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=analyze(json.loads(a.input.read_text()));a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r[k] for k in ('valid','invalid_rows','vertex_union_ms','fragment_union_ms','all_render_stage_union_ms','render_timestamp_extent_ms')},indent=2))
