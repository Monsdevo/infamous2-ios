#!/usr/bin/env python3
"""Compare a paired R32Float/guest snapshot and list observed guest readers."""
import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path
import struct

WIDTH, HEIGHT = 640, 360
BYTES = WIDTH * HEIGHT * 4
KINDS = {472: 'SPU DMA', 473: 'PPU helper', 474: 'RSX buffer request'}


def ordered_float(bits):
    return 0x80000000 - (bits & 0x7fffffff) if bits >> 31 else 0x80000000 + bits


def analyze(trace, sample):
    with trace.open() as source:
        metadata = json.loads(source.readline().removeprefix('# '))
        rows = list(csv.DictReader(source))
    if metadata['dropped'] or len(rows) != metadata['rows']:
        raise ValueError('Incomplete trace')
    data = sample.read_bytes()
    if len(data) != 24 + 2 * BYTES:
        raise ValueError('Unexpected paired snapshot size')
    trace_ns, frame, address = struct.unpack_from('<QQQ', data)
    if abs(trace_ns / 1e9 - metadata['start']) > 1e-6:
        raise ValueError('Snapshot belongs to a different trace')
    events = sorted(((float(row['start_s']), int(row['kind']), int(row['who']),
                      int(row['a']), int(row['b'])) for row in rows
                     if 470 <= int(row['kind']) <= 474))
    reference = [event for event in events if event[1:4] == (471, frame, address)]
    if len(reference) != 1:
        raise ValueError('Expected one completed SPU publication for the paired frame')

    guest = memoryview(data)[24:24 + BYTES]
    metal = memoryview(data)[24 + BYTES:]
    exact = 0
    abs_error = []
    ulp = []
    nonfinite = 0
    for offset in range(0, BYTES, 4):
        original, = struct.unpack_from('>I', guest, offset)
        candidate, = struct.unpack_from('<I', metal, offset)
        exact += original == candidate
        a, = struct.unpack_from('>f', guest, offset)
        b, = struct.unpack_from('<f', metal, offset)
        if math.isfinite(a) and math.isfinite(b):
            abs_error.append(abs(a - b))
            ulp.append(abs(ordered_float(original) - ordered_float(candidate)))
        else:
            nonfinite += 1

    admissions = [event for event in events if event[1] == 470]
    reads = [event for event in events if event[1] in KINDS]
    readers = Counter(KINDS[event[1]] for event in reads)
    next_admission = next((event[0] for event in admissions if event[0] > reference[0][0] and
                           event[2] != frame), metadata['end'])
    paired_reads = [event for event in reads if reference[0][0] <= event[0] < next_admission]
    first = None
    if paired_reads:
        time, kind, actor, ea, site = paired_reads[0]
        first = dict(kind=KINDS[kind], actor=actor, address=hex(ea), site=hex(site),
                     after_reference_ms=(time - reference[0][0]) * 1000)
    return dict(frame=frame, guest_address=hex(address), pixels=WIDTH * HEIGHT,
                exact_pixels=exact, nonfinite_pairs=nonfinite,
                max_absolute_error=max(abs_error, default=None),
                mean_absolute_error=sum(abs_error) / len(abs_error) if abs_error else None,
                max_ulp=max(ulp, default=None), within_one_ulp=sum(value <= 1 for value in ulp),
                admissions=len(admissions), reader_counts=dict(readers),
                first_paired_frame_reader=first, trace_rows=len(rows))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    parser.add_argument('sample', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.trace, args.sample)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
