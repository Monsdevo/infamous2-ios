#!/usr/bin/env python3
"""Locate main-PPU short-sleep intervals inside/outside FIFO drain intervals."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from analyze_frame_trace import analyze, stats


def merged(items, lo, hi):
    result = []
    for a, b in sorted((max(lo, a), min(hi, b)) for a, b in items if b > lo and a < hi):
        if b <= a:
            continue
        if result and a <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], b))
        else:
            result.append((a, b))
    return result


def length(items):
    return sum(b - a for a, b in items)


def overlap(left, right):
    # Inputs are disjoint unions; intersections are therefore disjoint too.
    return sum(max(0, min(b, d) - max(a, c)) for a, b in left for c, d in right)


def progress_overlap(path, main_ppu=1):
    summary, events = analyze(path)
    drains = [(e['t0'], e['t1']) for e in events if e['kind'] == 7]
    polls = [e for e in events if e['kind'] == 2 and e['who'] == main_ppu]
    frames, sites = [], defaultdict(float)
    for window in summary['frame_windows']:
        lo, hi = window['start'], window['end']
        drain = merged(drains, lo, hi)
        poll = merged([(e['t0'], e['t1']) for e in polls], lo, hi)
        both = overlap(drain, poll)
        frames.append(dict(interval_ms=(hi-lo)*1000, drain_ms=length(drain)*1000,
            main_poll_ms=length(poll)*1000, main_poll_inside_drain_ms=both*1000,
            main_poll_outside_drain_ms=max(0, length(poll)-both)*1000))
        for event in polls:
            if event['t1'] <= lo or event['t0'] >= hi:
                continue
            item = merged([(event['t0'], event['t1'])], lo, hi)
            sites[hex(event['b'])] += max(0, length(item)-overlap(drain, item))*1000
    return dict(method='Per-frame clipped unions/intersections in the same trace clock; no subtraction of independent medians.',
        metadata=summary['metadata'], main_ppu=main_ppu,
        metrics={key: stats([f[key] for f in frames]) for key in frames[0]} if frames else {},
        outside_drain_poll_sites_ms=dict(sorted(sites.items(), key=lambda item: -item[1])), frames=frames,
        limitations=['Drain includes mutex/GPU waits/scheduling, not exclusive CPU.',
            'Usleep brackets can include scheduling. Outside-drain polling does not identify its producer or prove avoidable delay.',
            'Only kind2 short sleeps are counted; no overlapping syscall wall spans are added.',
            'Instrumented windows are not an uninstrumented FPS benchmark.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--main-ppu', type=int, default=1)
    args = parser.parse_args()
    result = progress_overlap(args.trace, args.main_ppu)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result['metrics'], indent=2))
