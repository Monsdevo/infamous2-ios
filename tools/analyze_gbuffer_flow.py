#!/usr/bin/env python3
"""Associate observed G-buffer publications with sampled first SPU DMA reads."""
import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path

SURFACES = {1: ('normals', 0x06FF3B80), 2: ('depth', 0x07377B80)}
REJECTIONS = {
    1: 'input_epoch_or_context', 2: 'frame_header', 3: 'light_count_or_range',
    4: 'light_type', 5: 'iterator_state', 6: 'pass_or_table', 7: 'stream_descriptor',
}


def analyze(path):
    with path.open() as source:
        meta = json.loads(source.readline().removeprefix('# '))
        rows = list(csv.DictReader(source))
    if meta['dropped'] or len(rows) != meta['rows']:
        raise ValueError('Incomplete frame trace')

    blits = defaultdict(list)
    reads = defaultdict(dict)
    rejections = Counter()
    for row in rows:
        kind, who, a, b = (int(row[key]) for key in ('kind', 'who', 'a', 'b'))
        start, end = float(row['start_s']), float(row['end_s'])
        if kind == 460:
            if not b:
                raise ValueError(f'Unresolved or discontinuous guest mapping for {a:#x}')
            blits[who].append((start, end, a, b))
        elif 461 <= kind <= 464:
            if kind in reads[who]:
                raise ValueError(f'Duplicate DMA event field for {who}')
            reads[who][kind] = (a, b, start)
        elif kind == 465:
            rejections[REJECTIONS[a]] += 1

    consumers = defaultdict(list)
    for fields in reads.values():
        if fields.keys() != {461, 462, 463, 464}:
            raise ValueError('Incomplete DMA event')
        address, size, time = fields[461]
        image, overlay, _ = fields[462]
        pc, lr, _ = fields[463]
        spu, mask, _ = fields[464]
        consumers[mask & 0xff].append(dict(
            time=time, address=hex(address), size=size, image=image, overlay=overlay,
            pc=hex(pc), lr=hex(lr), spu=spu, ssao_pass0=bool(mask >> 8)))

    result = {}
    for surface, (name, base) in SURFACES.items():
        writes = sorted(blits[surface])
        ordered = sorted(consumers[surface], key=lambda read: read['time'])
        frames = []
        for index, (first, second, following) in enumerate(zip(writes, writes[1:], writes[2:])):
            if [first[2], second[2], following[2]] != [base, base + 4096, base]:
                continue
            if second[3] != first[3] + 4096 or following[3] != first[3]:
                raise ValueError('Unexpected mapping change within a publication window')
            if not meta['start'] <= first[0] <= first[1] <= second[0] <= second[1] <= following[0] <= meta['end']:
                continue
            observed = [r for r in ordered if first[0] <= r['time'] < following[0]]
            after = [r for r in observed if r['time'] >= second[1]]
            other = [r for r in after if not r['ssao_pass0']]
            depth_pass = [r for r in after if r['ssao_pass0']]
            frames.append(dict(
                publication=index, guest_base=hex(first[3]), ready_s=second[1],
                during_publication=sum(r['time'] < second[1] for r in observed),
                first_after=after[0] if after else None,
                first_other_after=other[0] if other else None,
                first_pass0_after=depth_pass[0] if depth_pass else None,
                first_after_ms=(after[0]['time'] - second[1]) * 1000 if after else None,
                observed_dma_sites=sorted({(r['image'], r['overlay'], r['lr'], r['ssao_pass0']) for r in observed})))
        result[name] = frames
    if not result['depth'] or not result['normals'] or not reads:
        raise ValueError('No complete publication windows or DMA samples')
    return dict(metadata=meta, light_rejections=rejections, surfaces=result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(analyze(args.trace), indent=2) + '\n')
