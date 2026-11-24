#!/usr/bin/env python3
"""Match actual DMA label writes to RSX acquire completion; keep ambiguity visible."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import subprocess
import tempfile
from analyze_frame_trace import analyze, stats


def match_writers(events, meta):
    groups=defaultdict(dict)
    for e in events:
        if 21<=e['kind']<=24 or 64<=e['kind']<76:
            if e['kind'] in groups[e['who']]:
                raise ValueError('Repeated dependency tag/kind')
            groups[e['who']][e['kind']]=e
    writes=[];incomplete=0
    for tag,g in groups.items():
        if not all(k in g for k in (21,22,23,24)):
            incomplete+=1;continue
        e=g[21]
        writes.append(dict(tag=tag,label=hex(e['a']),value=e['b'],start=e['t0'],end=e['t1'],
            spu_id=g[22]['a'],image_id=g[22]['b'],guest_pc=hex(g[23]['a']),guest_lr=hex(g[23]['b']),
            lsa=hex(g[24]['a']),size=g[24]['b'],
            native_pcs=[g[k]['a']+(g[k]['b']<<32) for k in sorted(g) if 64<=k<76]))
    matches=[]
    for e in events:
        if e['kind']!=5 or e['a'] not in (0x870,0x890):continue
        # A successful write must overlap the observed blocked interval. The
        # bracket encloses the actual copy, not its later backtrace collection.
        candidates=[w for w in writes if w['label']==hex(e['a']) and w['value']==e['b']
                    and w['start']<=e['t1'] and w['end']>=e['t0']]
        matches.append(dict(label=hex(e['a']),value=e['b'],wait_start=e['t0'],wait_end=e['t1'],
            wait_ms=(e['t1']-e['t0'])*1000,candidate_tags=[w['tag'] for w in candidates],
            status='unique' if len(candidates)==1 else 'unmatched' if not candidates else 'ambiguous',
            write_end_to_observed_acquire_ms=(e['t1']-candidates[0]['end'])*1000 if len(candidates)==1 else None))
    counts=Counter(m['status'] for m in matches)
    unique_tags={m['candidate_tags'][0] for m in matches if m['status']=='unique'}
    producer_counts=Counter((w['label'],w['spu_id'],w['image_id'],w['guest_pc'])
                            for w in writes if w['tag'] in unique_tags)
    return dict(metadata=meta,writes=writes,matches=matches,incomplete_groups=incomplete,
        match_counts=dict(counts),
        acquire_poll_delay_ms=stats([m['write_end_to_observed_acquire_ms'] for m in matches if m['status']=='unique']),
        producers=[dict(label=k[0],spu_id=k[1],image_id=k[2],guest_pc=k[3],matched_writes=n)
                   for k,n in producer_counts.most_common()],
        interpretation=[
            'Records are successful ordinary PUT copies of full 32-bit words only; atomic/partial/PPU writes are not covered.',
            'Unique means one recorded SPU write of the expected value during this acquire interval; it is not a job-duration measurement.',
            'Guest PC/image may reflect the dispatcher. Check native call ancestry before assigning the lifted issuer.',
            'An issuer may publish results prepared by other jobs. Issuer identification does not prove where all upstream time was spent.',
            'No matching write does not prove a PPU writer; edge filtering, unsupported paths or missing instrumentation can explain it.'])


def symbolize(report,binary):
    meta=report['metadata'];uuid=meta.get('uuid','').upper()
    found=re.findall(r'UUID: ([0-9A-Fa-f-]+) \(arm64\)',subprocess.check_output(['xcrun','dwarfdump','--uuid',str(binary)],text=True))
    if uuid not in [s.upper() for s in found]:raise ValueError('Trace and binary UUID differ')
    base,end=meta['app_base'],meta['app_end']
    offsets=sorted({pc-base for w in report['writes'] for pc in w['native_pcs'] if base<=pc<end})
    names=[]
    if offsets:
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'pcs';p.write_text(''.join(hex(pc)+'\n' for pc in offsets))
            names=subprocess.check_output(['xcrun','atos','-arch','arm64','-o',str(binary),'--offset','-f',str(p)],text=True).splitlines()
        if len(names)!=len(offsets):raise ValueError('Symbol count differs')
    symbols={base+pc:name.split(' (in ')[0] for pc,name in zip(offsets,names)}
    for w in report['writes']:
        w['native_app_stack']=[symbols[pc] for pc in w['native_pcs'] if pc in symbols]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('trace',type=Path);p.add_argument('--binary',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();summary,events=analyze(a.trace)
    result=match_writers(events,summary['metadata'])
    if a.binary:symbolize(result,a.binary)
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('match_counts','incomplete_groups','acquire_poll_delay_ms','producers')},indent=2))


if __name__=='__main__':main()
