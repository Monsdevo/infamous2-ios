#!/usr/bin/env python3
"""Time-align sampled blocked lanes with same-process native PC observations."""
import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import re
import subprocess
import tempfile
from analyze_frame_trace import analyze


def owner_mapping(progress,native,issuer_only=False):
    if issuer_only:
        # A publisher may update several lanes. Only the observed issuer of
        # each (row,lane) is required to be unambiguous; no one-SPU/one-lane
        # assumption. Decreases/resets are not completion evidence.
        owners=defaultdict(Counter);mapping={};native_counts=Counter(native.values())
        for w in progress['writes']:
            if 'increased_from_previous_spu_write_lanes' not in w:raise ValueError('Regenerate progress decode with lane-increase fields')
            for lane in w['increased_from_previous_spu_write_lanes']:
                if lane>1:owners[w['row'],lane][w['spu_id']]+=1
        for (row,lane),counts in owners.items():
            spu,n=counts.most_common(1)[0];fraction=n/sum(counts.values())
            if n<50 or fraction<.99 or spu not in native or native_counts[native[spu]]!=1:continue
            item=mapping.setdefault(native[spu],dict(spu_id=spu,rows={},evidence='unique observed issuer of lane increases; no job-completion proof'))
            item['rows'].setdefault(row,{})[str(lane)]=dict(evidence_count=n,observed_issuer_fraction=fraction)
        return mapping
    ownership=defaultdict(Counter);lane_owners=defaultdict(Counter)
    for w in progress['writes']:
        qualified=issuer_only or any('wwsjob_pm_' in n and '00003450' in n for n in w.get('native_app_stack',[]))
        if not qualified:continue
        for lane in w['changed_from_previous_spu_write_lanes']:
            if lane>1:ownership[w['spu_id']][lane]+=1;lane_owners[lane][w['spu_id']]+=1
    mapping={};minimum=50 if issuer_only else 5;fraction=.99 if issuer_only else .9
    native_counts=Counter(native.values())
    for spu,counts in ownership.items():
        lane,n=counts.most_common(1)[0];total=sum(counts.values());other=sum(lane_owners[lane].values())
        if n>=minimum and n/total>=fraction and spu in native and native_counts[native[spu]]==1:
            if issuer_only and n/other<fraction:continue
            mapping[native[spu]]=dict(spu_id=spu,lane=lane,evidence_count=n,observed_change_fraction=n/total,lane_issuer_fraction=n/other,evidence='successful issuer changes; no completion-stack proof' if issuer_only else 'observed WWS completion stack and lane changes')
    return mapping


def changed_after_snapshot(values,times,start,end,value):
    lo=bisect_right(times,start);hi=bisect_right(times,end)
    return any(v!=value for _,v in values[lo:hi])


def correlate(progress, trace, profile, binary,issuer_only=False,max_age_ms=5):
    summary, events = analyze(trace)
    meta=summary['metadata']
    with profile.open() as f:
        cpu_meta=json.loads(f.readline()[2:]);cpu=list(csv.DictReader(f))
    uuid=subprocess.check_output(['xcrun','dwarfdump','--uuid',str(binary)],text=True)
    if meta['uuid']!=cpu_meta['uuid'] or meta['uuid'].upper() not in uuid.upper():
        raise ValueError('Trace/profile/binary UUID differ')
    if (meta['app_base'],meta['app_end'])!=(cpu_meta['app_base'],cpu_meta['app_end']):
        raise ValueError('Different process image mappings')
    if cpu_meta['errors'] or cpu_meta['truncated'] or len(cpu)!=cpu_meta['rows']:
        raise ValueError('Incomplete CPU recording')
    candidates=defaultdict(set)
    for e in events:
        if e['kind']==18:candidates[e['who']&0x7fffffff].add(str(e['a']+(e['b']<<32)))
    native={k:next(iter(v)) for k,v in candidates.items() if len(v)==1}
    ambiguous_native={str(k):sorted(v) for k,v in candidates.items() if len(v)>1}
    if not 0<max_age_ms<=5:raise ValueError('snapshot age outside(0,5]ms')
    if not 0<=meta['clock_calibration_width_s']<=.0001:raise ValueError('trace clock calibration wider than100us')
    mapping=owner_mapping(progress,native,issuer_only)
    delta=meta['monotonic_minus_mach_s'];base,end=meta['app_base'],meta['app_end']
    selected=[r for r in cpu if r['thread_id'] in mapping and r['state']=='1' and
              meta['start']<=float(r['monotonic_s'])+delta<=meta['end']]
    offsets=sorted({int(pc,16)-base for r in selected for pc in r['pcs'].split(';') if base<=int(pc,16)<end})
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'addresses';path.write_text(''.join(hex(o)+'\n' for o in offsets))
        names=subprocess.check_output(['xcrun','atos','-arch','arm64','-o',str(binary),'--offset','-f',str(path)],text=True).splitlines() if offsets else []
    if len(offsets)!=len(names):raise ValueError('Symbol count differs')
    symbols={o:n.split(' (in ')[0] for o,n in zip(offsets,names)}
    snapshots=sorted(progress['snapshots'],key=lambda s:s['end']);times=[s['end'] for s in snapshots]
    writes=defaultdict(list)
    for w in progress['writes']:
        for lane,value in w['lane_values'].items():writes[(w['row'],int(lane))].append((w['end'],value))
    write_times={key:[w[0] for w in values] for key,values in writes.items()}
    matches=[];rejected=Counter()
    for sample in selected:
        t=float(sample['monotonic_s'])+delta;index=bisect_right(times,t)-1
        if index<0 or t-times[index]>max_age_ms/1000:rejected['snapshot too old']+=1;continue
        snap=snapshots[index];owner=mapping[sample['thread_id']]
        if issuer_only:
            candidates=[int(l) for l in owner['rows'].get(snap['row'],{}) if int(l) in snap['lagging_lanes']]
            if len(candidates)!=1:
                rejected['no unique owned lagging lane for this row']+=1;continue
            lane=candidates[0]
        else:lane=owner['lane']
        if lane not in snap['lagging_lanes']:rejected['owner lane not behind sampled target']+=1;continue
        key=(snap['row'],lane)
        if changed_after_snapshot(writes.get(key,[]),write_times.get(key,[]),snap['end'],t,snap['lanes'][lane-1]):
            rejected['lane changed after snapshot']+=1;continue
        stack=[symbols[int(pc,16)-base] for pc in sample['pcs'].split(';') if base<=int(pc,16)<end]
        modules=[re.split('_spu_func_',n)[0] for n in stack if n.startswith(('jobmod_','relocmod_','datamod_'))]
        matches.append(dict(time=t,spu_id=owner['spu_id'],lane=lane,row=snap['row'],target=snap['target'],
            sampled_value=snap['lanes'][lane-1],lagging_lanes=snap['lagging_lanes'],snapshot_age_ms=(t-snap['end'])*1000,
            module=modules[0] if modules else '<runtime/no job ancestor>',native_stack=stack))
    ranked=Counter(m['module'] for m in matches)
    sole=[m for m in matches if m['lagging_lanes']==[m['lane']]]
    sole_private=[m for m in matches if [x for x in m['lagging_lanes'] if x>1]==[m['lane']]]
    return dict(metadata=meta,cpu_metadata=cpu_meta,issuer_only=issuer_only,max_snapshot_age_ms=max_age_ms,ambiguous_native_mapping=ambiguous_native,native_mapping=mapping,cpu_samples_in_overlap=len(selected),
        matched_samples=len(matches),sole_lagging_samples=len(sole),sole_lagging_module_sample_counts=dict(Counter(m['module'] for m in sole).most_common()),sole_private_lane_samples=len(sole_private),sole_private_module_sample_counts=dict(Counter(m['module'] for m in sole_private).most_common()),rejected=dict(rejected),module_sample_counts=dict(ranked.most_common()),matches=matches,
        limitations=[f'Same UUID/PID image and calibrated clocks; snapshot age limited to{max_age_ms}ms.',
            'Rejects observed lane changes after the snapshot. Writes outside current watch coverage and non-atomic whole-row snapshots remain limitations.',
            'Clock offset is calibrated at trace export; drift across the15s window is not directly measured.',
            'Best-effort unsuspended native ancestry is contextual evidence, not exact function timing or a proven critical path.',
            'Sole-lagging cohort requires exactly one total lagging lane, not merely one private lane while shared lane1 is also behind.',
            'Shared lane1 is deliberately not attributed to one SPU; issuer-only mode requires >=50 increases and99% unique issuer per(row,lane). Multi-lane publishers are allowed; ambiguous simultaneous lagging lanes are excluded. No particular job completion is proven.',
            'Simultaneous instrumentation perturbs execution. Sample counts are not FPS or milliseconds saved.'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--issuer-only',action='store_true')
    p.add_argument('--maximum-snapshot-age-ms',type=float,default=5)
    for name in ('progress','trace','profile','binary','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();r=correlate(json.loads(a.progress.read_text()),a.trace,a.profile,a.binary,a.issuer_only,a.maximum_snapshot_age_ms)
    a.output.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:r[k] for k in ('native_mapping','cpu_samples_in_overlap','matched_samples','rejected','module_sample_counts')},indent=2))
