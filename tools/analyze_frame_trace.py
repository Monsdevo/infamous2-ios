#!/usr/bin/env python3
"""Frame-cadence and overlapping CPU/GPU spans; never add nested wall times."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics

KINDS={1:'syscall wall',2:'usleep wall',3:'SPU channel wait',4:'SPU between-waits wall',
       5:'RSX acquire wait',6:'RSX acquire gave up',7:'RSX drain',8:'flip reached FIFO',
       9:'flip request',10:'CPU present call',11:'Metal encode',12:'CPU GPU wait',
       13:'readback',14:'legacy approximate GPU time',15:'actual GPU execution',
       16:'Metal commit',18:'SPU native thread map',19:'Metal completion',20:'drawable presented'}
KINDS.update({21:'label DMA write',22:'label writer SPU/image',23:'label writer guest PC/LR',24:'label DMA LSA/size'})
KINDS.update({64+i:f'label writer native stack {i}' for i in range(12)})
KINDS.update({200:'Edge logical call wall',201:'Edge inclusive thread CPU ns',202:'Edge caller/depth',203:'Edge native thread',
              204:'Edge input r3/r4',205:'Edge input r5/r6',206:'Edge input r7/r8',207:'Edge input r9/r10',
              208:'Edge return r3/r4',209:'Edge driver raw LS window',211:'Edge DMA EA/bytes',212:'Edge DMA LSA/cmd',
              213:'Edge DMA job/SPU',214:'Edge DMA PC/LR',215:'Edge DMA EAH/image',220:'Renderer read EA/bytes',
              221:'Renderer read kind/location',222:'Renderer read RSX offset'})
WAIT_SYSCALLS={44,85,92,97,102,107,113,122,125,130,178}


def union_seconds(intervals,lo,hi):
    spans=sorted((max(lo,a),min(hi,b)) for a,b in intervals if b>lo and a<hi and b>=a)
    total=0;end=lo
    for a,b in spans:
        if b>max(a,end):total+=b-max(a,end)
        end=max(end,b)
    return total


def stats(values):
    values=sorted(values)
    return {'count':len(values),'median':statistics.median(values),'min':values[0],
            'max':values[-1],'p95':values[math.ceil(.95*len(values))-1]} if values else None


def analyze(path):
    with path.open() as f:
        meta=json.loads(f.readline().removeprefix('# '));raw=list(csv.DictReader(f))
    if len(raw)!=meta['rows'] or meta['dropped']:
        raise ValueError('Incomplete trace or dropped events; shorten/repeat capture')
    lo,hi=meta['start'],meta['end']
    events=[]
    for r in raw:
        e={k:int(r[k]) for k in ('kind','who','a','b')}
        e.update(t0=float(r['start_s']),t1=float(r['end_s']))
        if not all(math.isfinite(e[k]) for k in ('t0','t1')) or e['t1']<e['t0']:
            raise ValueError('Invalid event timestamps')
        if e['t1']>=lo and e['t0']<=hi:events.append(e)
    bykind=defaultdict(list)
    for e in events:bykind[e['kind']].append(e)
    def intervals(kind):return [(e['t0'],e['t1']) for e in bykind[kind]]
    def frame_spans(kind,a,b):return 1000*union_seconds(intervals(kind),a,b)
    requests=sorted(e['t0'] for e in bykind[9] if lo+.25<=e['t0']<=hi-.25)
    frames=[]
    for a,b in zip(requests,requests[1:]):
        if b<=a:continue
        frames.append({'start':a,'end':b,'interval_ms':(b-a)*1000,
            'gpu_busy_union_ms':frame_spans(15,a,b),'rsx_acquire_union_ms':frame_spans(5,a,b),
            'cpu_gpu_wait_union_ms':frame_spans(12,a,b),'drain_union_ms':frame_spans(7,a,b),
            'present_call_union_ms':frame_spans(10,a,b),'readback_union_ms':frame_spans(13,a,b)})
    ppu=defaultdict(list);spu=defaultdict(list)
    for e in events:
        if e['kind'] in (1,2):ppu[e['who']].append(e)
        if e['kind'] in (3,4):spu[e['who']].append(e)
    ppu_report=[]
    for who,rows in ppu.items():
        calls=defaultdict(list)
        for e in rows:calls[(e['kind'],e['a'],e['b'])].append((e['t0'],e['t1']))
        ppu_report.append({'logical_id':who,'syscall_wall_union_ms':1000*union_seconds([(e['t0'],e['t1']) for e in rows],lo,hi),
          'wait_named_syscall_wall_union_ms':1000*union_seconds([(e['t0'],e['t1']) for e in rows if e['kind']==2 or e['a'] in WAIT_SYSCALLS],lo,hi),
          'call_sites':sorted([{'kind':key[0],'syscall_or_count':key[1],'guest_lr':hex(key[2]),
               'wall_ms':1000*union_seconds(spans,lo,hi),'events':len(spans)} for key,spans in calls.items()],key=lambda x:-x['wall_ms'])[:12]})
    commits={e['who']:e for e in bykind[16]}
    gpus={e['who']:e for e in bykind[15]}
    site=defaultdict(list);queue=[]
    for tag,e in gpus.items():
        site[e['a']].append((e['t1']-e['t0'])*1000)
        if tag in commits:queue.append((e['t0']-commits[tag]['t0'])*1000)
    report={'source':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
      'metadata':meta,'event_counts':{KINDS.get(k,str(k)):len(v) for k,v in bykind.items()},
      'frame_windows':frames,'frame_metrics':{key:stats([f[key] for f in frames]) for key in ('interval_ms','gpu_busy_union_ms','rsx_acquire_union_ms','cpu_gpu_wait_union_ms','drain_union_ms','present_call_union_ms','readback_union_ms')},
      'gpu_union_busy_ms':1000*union_seconds(intervals(15),lo,hi),
      'gpu_window_busy_fraction':union_seconds(intervals(15),lo,hi)/(hi-lo),
      'gpu_commit_to_start_ms':stats(queue),'gpu_commits':len(commits),'gpu_executions':len(gpus),
      'gpu_commit_without_execution':len(set(commits)-set(gpus)),
      'gpu_sites':sorted([{'source_line':line,'duration_ms':stats(values),'total_ms':sum(values)} for line,values in site.items()],key=lambda x:-x['total_ms']),
      'ppu':sorted(ppu_report,key=lambda x:-x['syscall_wall_union_ms']),
      'spu':[{'spu_id':who,'channel_wait_union_ms':1000*union_seconds([(e['t0'],e['t1']) for e in rows if e['kind']==3],lo,hi),
              'between_waits_wall_union_ms':1000*union_seconds([(e['t0'],e['t1']) for e in rows if e['kind']==4],lo,hi)} for who,rows in spu.items()],
      'spu_thread_map':{str(e['who']&0x7fffffff):e['a']+(e['b']<<32) for e in bykind[18]},
      'interpretation':['Frame windows are intervals between guest flip requests, not simulation ticks.',
        'Nested/parallel wall times overlap; never sum these columns into a frame budget.',
        'Syscall wall time includes CPU and scheduling time; it is an upper bound for blocking.',
        'SPU between-waits wall is NOT a job duration or CPU time; edge intervals may be censored.',
        'GPU busy is union of measured backend command buffers, not a hardware utilization counter.',
        'Legacy GPU_EXEC kind 14 is excluded; kind 15 uses actual Metal timestamps.',
        'A critical dependency producer cannot be identified from temporal overlap alone.']}
    return report,events


def export_chrome(events,path):
    out=[]
    for e in events:
        kind=e['kind']
        if kind==14:continue
        pid=1 if kind in (1,2) else 2 if kind in (3,4,18) else 4 if kind==15 else 3
        tid=e['who'] if pid in (1,2) else 1
        name=KINDS.get(kind,str(kind))
        args={'who':e['who'],'a':hex(e['a']),'b':hex(e['b'])}
        out.append({'name':name,'cat':str(kind),'ph':'X','pid':pid,'tid':tid,
                    'ts':e['t0']*1e6,'dur':max(1,(e['t1']-e['t0'])*1e6),'args':args})
    path.write_text(json.dumps({'traceEvents':out}))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('trace',type=Path);p.add_argument('--output',required=True,type=Path)
    args=p.parse_args();report,events=analyze(args.trace)
    args.output.write_text(json.dumps(report,indent=2)+'\n');export_chrome(events,args.output.with_suffix('.chrome.json'))
    print(json.dumps({k:report[k] for k in ('event_counts','frame_metrics','gpu_window_busy_fraction','gpu_commit_without_execution')},indent=2))


if __name__=='__main__':main()
