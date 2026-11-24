#!/usr/bin/env python3
"""Measure work on the serial FIFO consumer between matched Metal submissions."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from analyze_frame_trace import analyze as load_trace, stats, union_seconds


STAGES = {
    1: 'fifo_body', 2: 'draw_prepare', 3: 'vertex_prepare', 4: 'vertex_decode',
    5: 'texture_hash', 6: 'metal_staging', 7: 'sync_submit',
    8: 'image_blit', 9: 'guest_writeback', 10: 'rgba_to_argb',
}


def analyze(path):
    trace, events = load_trace(path)
    meta = trace['metadata']
    kinds = defaultdict(list)
    for event in events:
        kinds[event['kind']].append(event)

    def key(event):
        return event['who'], event['t0'], event['t1']

    clocks = defaultdict(list)
    for event in kinds[451]:
        clocks[key(event)].append((event['a'] + (event['b'] << 32)) / 1e6)
    spans = []
    duplicates = Counter(key(event) for event in kinds[450])
    rejected = Counter()
    for event in kinds[450]:
        if duplicates[key(event)] != 1 or len(clocks[key(event)]) != 1:
            rejected[STAGES[event['a']]] += 1
            continue
        cpu = clocks[key(event)][0]
        if cpu > (event['t1'] - event['t0']) * 1000 + .01:
            rejected[STAGES[event['a']]] += 1
            continue
        spans.append(dict(event, cpu=cpu))

    commits = sorted(kinds[16], key=lambda event: event['t0'])
    executions = {event['who']: event for event in kinds[15]}
    # In each eng_encode_and_commit call, the encode marker is immediately
    # before the commit. Also require the enclosing present call to agree.
    present_commits = []
    for encode in kinds[11]:
        if encode['a'] != 1:
            continue
        near = [event for event in commits if 0 <= event['t0'] - encode['t1'] < .003]
        if near and any(p['t0'] <= encode['t0'] <= near[0]['t0'] <= p['t1'] for p in kinds[10]):
            present_commits.append(near[0])
    present_commits.sort(key=lambda event: event['t0'])
    if len({event['who'] for event in present_commits}) != len(present_commits):
        raise ValueError('A present commit matched more than once')

    gpu = [(event['t0'], event['t1']) for event in kinds[15]]
    waits = [(event['t0'], event['t1']) for event in kinds[12]]
    wait_gpu_overlap = [(max(a, c), min(b, d)) for a, b in waits for c, d in gpu
                        if max(a, c) < min(b, d)]
    bodies = [span for span in spans if span['a'] == 1]
    frames = []
    active_serial_spans = defaultdict(int)
    for previous, final in zip(present_commits, present_commits[1:]):
        lo, hi = previous['t0'], final['t0']
        if lo < meta['start'] + .2 or hi > meta['end'] - .2:
            continue
        batch = [event for event in commits if lo <= event['t0'] <= hi]
        if not all(event['who'] in executions for event in batch):
            continue
        contained = [body for body in bodies if lo <= body['t0'] <= body['t1'] <= hi]
        if not contained:
            continue
        # The frame clock presents after the FIFO drain returns.
        scope = max(contained, key=lambda body: body['t1'] - body['t0'])
        serial_bodies = [body for body in contained if body['who'] == scope['who']]
        prior_end = executions[previous['who']]['t1']
        first = batch[1]['t0']
        quiet_lo = max(lo, prior_end)
        # Older submitted work must also be finished before counting this gap.
        earlier = [event for event in commits if event['t0'] < lo and event['who'] in executions]
        if earlier:
            quiet_lo = max(quiet_lo, max(executions[event['who']]['t1'] for event in earlier))
        gaps = []
        finished_through = quiet_lo
        for current, following in zip(batch, batch[1:]):
            finished_through = max(finished_through, executions[current['who']]['t1'])
            if following['t0'] > finished_through:
                gaps.append((finished_through, following['t0']))
        # Synchronous waits may be logged twice by the nested wrappers.
        wait_ms = union_seconds(waits, lo, hi) * 1000
        wait_busy_ms = union_seconds(wait_gpu_overlap, lo, hi) * 1000
        frame = dict(start=lo, end=hi, frame_ms=(hi - lo) * 1000,
                     serial_thread=scope['who'], submissions=len(batch) - 1,
                     first_gpu_submission_gap_ms=max(0, first - quiet_lo) * 1000,
                     gpu_queue_empty_ms=union_seconds(gaps, lo, hi) * 1000,
                     gpu_busy_ms=union_seconds(gpu, lo, hi) * 1000,
                     sync_wait_ms=wait_ms, sync_wait_gpu_busy_ms=wait_busy_ms,
                     sync_wait_outside_gpu_busy_ms=max(0, wait_ms - wait_busy_ms),
                     readback_calls=sum(lo <= row['t0'] <= row['t1'] <= hi for row in kinds[13]),
                     readback_ms=union_seconds([(r['t0'], r['t1']) for r in kinds[13]], lo, hi) * 1000)
        for stage, name in STAGES.items():
            selected = [span for span in spans if span['a'] == stage and span['who'] == scope['who']
                        and any(body['t0'] <= span['t0'] <= span['t1'] <= body['t1'] for body in serial_bodies)]
            intervals = [(span['t0'], span['t1']) for span in selected]
            if stage != 1:
                frame[name + '_cpu_ms'] = sum(span['cpu'] for span in selected)
            frame[name + '_wall_ms'] = union_seconds(intervals, lo, hi) * 1000
            frame[name + '_before_first_submit_ms'] = union_seconds(intervals, quiet_lo, first) * 1000
            frame[name + '_queue_empty_ms'] = sum(union_seconds(intervals, a, b) for a, b in gaps) * 1000
            active_serial_spans[name] += len(selected)
        frame['fifo_body_cpu_ms'] = sum(body['cpu'] for body in serial_bodies)
        frames.append(frame)
    if not frames:
        raise ValueError('No full renderer windows with matched GPU records and serial FIFO scope')
    metrics = {name: stats([frame[name] for frame in frames])
               for name in frames[0] if name not in ('start', 'end', 'serial_thread')}
    return dict(metadata=meta, matched_present_commits=len(present_commits), frames=frames, metrics=metrics,
                stage_counts=dict(active_serial_spans), unresolved_stage_clock=dict(rejected),
                guest_writeback_calls_by_destination=dict(Counter(hex(s['b']) for s in spans if s['a'] == 9)),
                limitations=[
                    'Nested stage times overlap. CPU draw preparation includes vertex preparation and texture hashing.',
                    'Per-stage CPU includes clock overhead. CPU is attributed only to fully contained spans.',
                    'The pre-submit gap starts after the previous GPU work observed in the trace. External GPU work is outside coverage.',
                    'End-to-end savings require a controlled implementation comparison.',
                ])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(analyze(args.trace), indent=2) + '\n')
