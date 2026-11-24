#!/usr/bin/env python3
"""Match the serial depth and normal writeback fences to Metal submissions."""
import argparse
import csv
import json
from pathlib import Path
from statistics import median

DEPTH = 0x07377B80
NORMALS = 0x06FF3B80


def analyze(trace_path, stages_path):
    stages = json.loads(stages_path.read_text())
    rows = []
    with trace_path.open() as source:
        metadata = json.loads(source.readline().removeprefix('# '))
        if metadata['dropped'] or metadata['token'] != stages['metadata']['token']:
            raise ValueError('Incomplete or mismatched renderer trace')
        row_count = 0
        for row in csv.DictReader(source):
            row_count += 1
            kind, who, a, b = (int(row[name]) for name in ('kind', 'who', 'a', 'b'))
            if kind in (11, 12, 15, 16) or (kind == 450 and a == 9 and b in (DEPTH, NORMALS)):
                start, end = (float(row[name]) for name in ('start_s', 'end_s'))
                rows.append((kind, who, a, b, start, end))

        if row_count != metadata['rows']:
            raise ValueError('Truncated renderer trace')

    executions = {row[1]: row for row in rows if row[0] == 15}
    samples = []
    for frame in stages['frames']:
        lo, hi = frame['start'], frame['end']
        match = {}
        for surface in (DEPTH, NORMALS):
            spans = [row for row in rows if row[:4] == (450, frame['serial_thread'], 9, surface)
                     and lo <= row[4] <= row[5] <= hi]
            if len(spans) != 1:
                raise ValueError('Expected one writeback scope per full surface and frame')
            start, end = spans[0][4:]
            local = [row for row in rows if start <= row[4] <= row[5] <= end]
            commits = [row for row in local if row[0] == 16]
            waits = [row for row in local if row[0] == 12 and row[2] == 0]
            encodes = [row for row in local if row[0] == 11 and row[2] == 0]
            if len(commits) != 1 or len(waits) != 1 or len(encodes) != 1:
                raise ValueError('Expected a single Metal flush in each writeback')
            commit, wait, encode = commits[0], waits[0], encodes[0]
            gpu = executions[commit[1]]
            if not encode[5] <= commit[4] <= gpu[4] <= gpu[5] <= wait[5]:
                raise ValueError('Submission timing did not match its GPU execution')
            match[surface] = (commit, wait, encode, gpu)

        depth, normal = match[DEPTH], match[NORMALS]
        if not depth[1][5] <= normal[0][4] or depth[0][1] >= normal[0][1]:
            raise ValueError('Unexpected depth/normal fence order')
        # Keep the original GPU timing and move all intervening host work
        # ahead of the first wait, even the copies a prototype might remove.
        # This is an illustrative same-queue overlap model, not a benchmark.
        gap = normal[0][4] - depth[1][5]
        earlier_normal_commit = depth[0][4] + gap
        samples.append(dict(
            depth_commit=depth[0][1], normal_commit=normal[0][1],
            depth_records=depth[2][3], normal_records=normal[2][3],
            depth_wait_ms=(depth[1][5] - depth[1][4]) * 1000,
            normal_wait_ms=(normal[1][5] - normal[1][4]) * 1000,
            between_wait_and_normal_commit_ms=gap * 1000,
            earlier_gpu_work_remaining_ms=max(0, depth[3][5] - earlier_normal_commit) * 1000))
    if not samples:
        raise ValueError('No complete fence pairs')
    return dict(trace_token=metadata['token'], frames=samples, medians={
        key: median(row[key] for row in samples)
        for key in samples[0] if not key.endswith('_commit')
    })


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    parser.add_argument('stages', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(analyze(args.trace, args.stages), indent=2) + '\n')
