#!/usr/bin/env python3
"""Request exactly one full guest frame of opt-in GPU stage timestamps."""
import argparse,json,time,uuid
from pathlib import Path
from host_research_control import read,write
from analyze_gpu_passes import analyze
def capture(run,output):
 run=Path(run);output=Path(output);output.mkdir(parents=True,exist_ok=False);before=read(run)
 if before.get('gpu_probe_state') in (1,2) or before['cpu_profile_state'] in (1,2) or before['frame_trace_state'] in (1,2):raise RuntimeError('diagnostic already active')
 token=uuid.uuid4().hex;write(run/'gpu-pass-request.txt',token+'\n');source=run/f'gpu-pass-{token}.json'
 try:
  for _ in range(100):
   after=read(run)
   if (after['pid'],after['session'])!=(before['pid'],before['session']):raise RuntimeError('process changed')
   if source.exists():
    result=json.loads(source.read_text());(output/'gpu-passes.json').write_text(json.dumps(result,indent=2)+'\n')
    context=dict(before=before,after=after,session=json.loads((run/'session.json').read_text()),performance_window=False,token=token)
    (output/'context.json').write_text(json.dumps(context,indent=2)+'\n')
    if not result.get('valid'):raise RuntimeError('GPU timestamp record invalid: '+str(result.get('error',result.get('invalid_samples'))))
    if result.get('token')!=token:raise RuntimeError('token mismatch')
    normalized=analyze(result);(output/'analysis.json').write_text(json.dumps(normalized,indent=2)+'\n')
    if not normalized['valid']:raise RuntimeError('raw stage counter analysis invalid')
    rows=sorted(normalized['rows'],key=lambda r:r.get('fragment_ms',0) or 0,reverse=True)
    print(json.dumps(dict(valid=True,rows=len(rows),top=rows[:12]),indent=2));return result
   time.sleep(.2)
  raise RuntimeError('GPU timestamp deadline')
 finally:
  if (run/'gpu-pass-request.txt').exists():(run/'gpu-pass-request.txt').unlink()
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();capture(a.run,a.output)
