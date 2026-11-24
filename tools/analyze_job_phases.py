#!/usr/bin/env python3
"""Disaggregate the 1774dd builder and match completed FIFO parks to observed PUTs."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from analyze_critical_job import scopes
from analyze_frame_trace import analyze as load_trace, stats, union_seconds
from analyze_job_flow import access_records, version_matches


PHASES = ('builder_12c50', 'input_43d0', 'input_13030',
          'publish_13bc8', 'reserve_publish_14160')


def analyze(path, progress=None):
    trace, events = load_trace(path)
    meta = trace['metadata']
    calls, missing = scopes(events, meta)
    if any(not row.get('cancelled') and row['start'] < meta['end'] - .25 for row in missing):
        raise ValueError('Incomplete interior job scope')
    jobs = {row['id']: row for row in calls if row['whole_job'] and not row['boundary'] and row['entry'] == 0x18f90}
    if not jobs:
        raise ValueError('No complete 1774dd jobs')
    groups = defaultdict(dict)
    for row in events:
        if row['kind'] in (440, 441, 442, 443):
            group = groups[row['who']]
            if row['kind'] in group:
                raise ValueError('Duplicate phase event')
            group[row['kind']] = row
    rejected, by_job, summary = Counter(), defaultdict(list), defaultdict(list)
    bad_jobs = set()
    for group in groups.values():
        owner = next((group[k]['a'] for k in (440, 441, 443) if k in group), None)
        if owner not in jobs:
            rejected['boundary_or_unmeasured_job'] += 1
            continue
        if set(group) != {440, 441, 442}:
            rejected['missing_or_reentered_phase'] += 1
            bad_jobs.add(owner)
            continue
        start, end, clock = (group[k] for k in (440, 441, 442))
        cpu = (clock['a'] + (clock['b'] << 32)) / 1e6
        wall = (end['t1'] - end['t0']) * 1000
        job = jobs[owner]
        if ((start['a'], start['b'], start['t0']) != (end['a'], end['b'], end['t0'])
                or not job['start'] <= end['t0'] <= end['t1'] <= job['end']
                or cpu > wall + .02):
            rejected['invalid_phase_bounds_or_clock'] += 1
            bad_jobs.add(owner)
            continue
        by_job[owner].append(dict(phase=end['b'], cpu_ms=cpu, wall_ms=wall,
                                  t0=end['t0'], t1=end['t1']))

    complete_builders = set()
    for owner, rows in by_job.items():
        if owner in bad_jobs:
            continue
        parents = [row for row in rows if row['phase'] == 0]
        if len(parents) != 1:
            rejected['missing_or_multiple_builder'] += 1
            continue
        parent = parents[0]
        children = sorted((row for row in rows if row is not parent), key=lambda row: row['t0'])
        previous = parent['t0']
        for child in children:
            if child['t0'] < previous or child['t1'] > parent['t1']:
                break
            previous = child['t1']
        else:
            complete_builders.add(owner)
            for row in rows:
                summary[PHASES[row['phase']]].append(row)
            summary['builder_remainder'].append({
                metric: parent[metric] - sum(row[metric] for row in children)
                for metric in ('cpu_ms', 'wall_ms')
            })
            continue
        rejected['overlap_or_outside_builder'] += 1

    duration = meta['end'] - meta['start']
    phase_stats = {
        name: dict(count=len(rows), cpu_ms=stats([row['cpu_ms'] for row in rows]),
                   wall_ms=stats([row['wall_ms'] for row in rows]),
                   cpu_ms_per_capture_second=sum(row['cpu_ms'] for row in rows) / duration)
        for name, rows in summary.items()
    }
    if not phase_stats:
        raise ValueError('No validated builder partitions')
    _, writes, boundary = access_records(events, meta)
    writes_by_tag = {row['who']: row for row in writes}
    starts = [row for row in events if row['kind'] == 445]
    parks = [row for row in events if row['kind'] == 444 and row['t1'] <= meta['end']]
    abandoned = [row for row in events if row['kind'] == 446 and row['t1'] <= meta['end']]
    start_keys = {(row['a'], row['t0']) for row in starts}
    if any((row['a'], row['t0']) not in start_keys for row in parks + abandoned):
        raise ValueError('Missing FIFO park start')
    reads = [dict(park, b=4, t0=park['t1'], wait_start=park['t0']) for park in parks]
    linked = []
    for read, tag, size in version_matches(reads, writes, jobs):
        write = writes_by_tag[tag]
        if (size == 4 and read['a'] == write['a'] and write.get('first_word') == read['who']
                and write['t1'] >= read['wait_start']):
            linked.append(dict(ea=hex(read['a']), job=write['job'], lr=hex(write['lr']),
                               park_ms=(read['t1'] - read['wait_start']) * 1000,
                               park_before_put_end_ms=max(0, write['t1'] - read['wait_start']) * 1000,
                               put_end_to_resume_ms=(read['t1'] - write['t1']) * 1000))
    frame_parks = [union_seconds([(row['t0'], row['t1']) for row in parks], window['start'], window['end']) * 1000
                   for window in trace['frame_windows']]
    phase_poll = defaultdict(list)
    if progress is not None:
        if progress['metadata'] != meta:
            raise ValueError('Progress analysis belongs to a different recording')
        for poll in progress['qualified_job_poll_spans']:
            if poll['job'] not in complete_builders:
                continue
            spans = by_job[poll['job']]
            parent = next(row for row in spans if row['phase'] == 0)
            children = sorted((row for row in spans if row is not parent), key=lambda row: row['t0'])

            def overlap(name, a, b):
                start, end = max(a, poll['start']), min(b, poll['end'])
                if end > start:
                    phase_poll[name].append((start, end))

            previous = parent['t0']
            for child in children:
                overlap('builder_remainder', previous, child['t0'])
                overlap(PHASES[child['phase']], child['t0'], child['t1'])
                previous = child['t1']
            overlap('builder_remainder', previous, parent['t1'])
    return dict(metadata=meta, target_jobs=len(jobs), validated_builders=len(complete_builders),
                jobs_without_phase_records=len(jobs.keys() - by_job.keys()), rejected=dict(rejected),
                phases=phase_stats, dma_groups_at_boundary=boundary, put_count=len(writes),
                park_starts=len(starts), park_resolved=len(parks), park_abandoned=len(abandoned),
                park_open=len(starts) - len(parks) - len(abandoned),
                resolved_park_wall_ms=stats([(row['t1'] - row['t0']) * 1000 for row in parks]),
                resolved_park_wall_per_frame_ms=stats(frame_parks), park_exact_put_links=linked,
                qualified_poll_overlap_by_phase_ms={name: union_seconds(spans, meta['start'], meta['end']) * 1000
                                                     for name, spans in phase_poll.items()},
                frame_metrics=trace['frame_metrics'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--progress', type=Path)
    args = parser.parse_args()
    result = analyze(args.trace, json.loads(args.progress.read_text()) if args.progress else None)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
