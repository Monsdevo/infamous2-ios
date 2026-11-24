#!/usr/bin/env python3
"""Decode sampled queue progress and actual successful SPU write provenance."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from analyze_frame_trace import analyze
from analyze_frame_dependencies import symbolize


def words(a, b):
    return a.to_bytes(4, 'big') + b.to_bytes(4, 'big')


def decode(events, metadata):
    groups = defaultdict(dict)
    for event in events:
        if not (300 <= event['kind'] <= 305 or 320 <= event['kind'] <= 328 or 352 <= event['kind'] <= 363):
            continue
        group = groups[event['who']]
        if event['kind'] in group:
            raise ValueError('Repeated progress tag/kind')
        group[event['kind']] = event
    snapshots, writes, incomplete = [], [], 0
    for tag, group in groups.items():
        is_snapshot = 300 in group
        required = range(300, 306) if is_snapshot else range(320, 327)
        if not all(kind in group for kind in required):
            incomplete += 1
            continue
        first = group[300 if is_snapshot else 320]
        row = first['a']
        if is_snapshot:
            data = words(group[303]['a'], group[303]['b']) + words(group[304]['a'], group[304]['b'])
            lanes = [int.from_bytes(data[i:i+2], 'big') for i in range(0, 16, 2)]
            target = group[302]['b']
            if target == 0xffffffff:
                target = None
            snapshots.append(dict(tag=tag, row=hex(row), start=first['t0'], end=first['t1'],
                object=hex(first['b']), slot=group[301]['a'], guest_lr=hex(group[301]['b']),
                list=hex(group[302]['a']), target=target, head=lanes[0], lanes=lanes[1:],
                minimum=min(lanes[1:]), lagging_lanes=[i for i in range(1, 8) if target is not None and lanes[i] < target],
                tid=group[305]['a'], scanned=group[305]['b']))
        else:
            data = words(group[325]['a'], group[325]['b']) + words(group[326]['a'], group[326]['b'])
            mask = group[324]['a']
            values = {str(i): int.from_bytes(data[i*2:i*2+2], 'big') for i in range(8)
                      if mask & (3 << (2*i)) == 3 << (2*i)}
            writes.append(dict(tag=tag, row=hex(row), ea=hex(first['b']), start=first['t0'], end=first['t1'],
                spu_id=group[321]['a'], image_id=group[321]['b'], guest_pc=hex(group[322]['a']), guest_lr=hex(group[322]['b']),
                lsa=hex(group[323]['a']), size=group[323]['b'], byte_mask=mask, command=hex(group[324]['b']),
                lane_values=values, job_words=[hex(group[k][field]) for k in (327, 328) if k in group for field in ('a', 'b')],
                native_pcs=[group[k]['a'] + (group[k]['b'] << 32) for k in sorted(group) if 352 <= k <= 363]))
    snapshots.sort(key=lambda item: item['start'])
    writes.sort(key=lambda item: item['end'])
    row_summary = {}
    for row in sorted({s['row'] for s in snapshots}):
        items = [s for s in snapshots if s['row'] == row]
        lagging = Counter(lane for s in items for lane in s['lagging_lanes'])
        row_summary[row] = dict(snapshots=len(items), unknown_target=sum(s['target'] is None for s in items),
            blocked_snapshots=sum(bool(s['lagging_lanes']) for s in items),
            lagging_lane_sample_counts=dict(lagging), head_range=[min(s['head'] for s in items), max(s['head'] for s in items)])
    # Compare consecutive SPU write observations. Full-vector writes may
    # repeat other lanes: only actual changes get counted as such. PPU writes
    # and unwatched periods are not covered, so this is provenance, not proof
    # of a complete dependency chain or of a job's own execution time.
    previous, changes, covered = {}, Counter(), Counter()
    for write in writes:
        changed = [];increased=[]
        for lane, value in write['lane_values'].items():
            if lane == '0':
                continue
            key = (write['row'], lane)
            covered[(write['row'], lane, write['spu_id'], write['image_id'])] += 1
            if key in previous and value != previous[key]:
                changed.append(int(lane))
                direction = 'increase' if value > previous[key] else 'decrease_or_reset'
                if direction=='increase':increased.append(int(lane))
                changes[(*key, write['spu_id'], write['image_id'], direction)] += 1
            previous[key] = value
        write['changed_from_previous_spu_write_lanes'] = changed
        write['increased_from_previous_spu_write_lanes'] = increased
    return dict(metadata=metadata, snapshots=snapshots, writes=writes, incomplete_groups=incomplete,
        rows=row_summary,
        writer_coverage=[dict(row=k[0], lane=int(k[1]), spu_id=k[2], image_id=k[3], observations=v) for k, v in covered.most_common()],
        observed_lane_changes=[dict(row=k[0], lane=int(k[1]), spu_id=k[2], image_id=k[3], direction=k[4], count=v) for k, v in changes.most_common()],
        limitations=['Snapshots are sampled at most once/ms/slot; lane loads are individually atomic, not one atomic 16-byte snapshot.',
            'Queue targets are bounded observations of up to64 nonzero command tags; unknown targets remain unknown.',
            'Only the latest watched row per slot is retained; PPU writes and unobserved periods are not covered.',
            'Successful ordinary PUT and PUTLLC/PUTLLUC commits are recorded after releasing locks; failed atomics are not writes.',
            'Issuer/native ancestry and job-header words identify publishers, not necessarily all upstream work.',
            'Lagging sample counts are not time spent per job. This recording is not an FPS benchmark.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    summary, events = analyze(args.trace)
    result = decode(events, summary['metadata'])
    if args.binary:
        symbolize(result, args.binary)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: result[k] for k in ('rows', 'incomplete_groups', 'observed_lane_changes')}, indent=2))
