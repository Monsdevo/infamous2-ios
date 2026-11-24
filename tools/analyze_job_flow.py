#!/usr/bin/env python3
"""Match SPU result writes to later memory access sites within one device trace."""
import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import json
from itertools import accumulate
from pathlib import Path
import subprocess
import tempfile

from analyze_critical_job import scopes
from analyze_frame_trace import analyze as load_trace, stats


TARGETS = {0x18F90: '1774dd', 0x6898: '867e', 0x5390: '43398b'}
RSX_SITES = {1: 'RSX vertex', 2: 'RSX index', 3: 'RSX texture/shader/inline', 4: 'RSX FIFO'}
FLOW_RECORDS = {420, 421, 422, 423, 425, 426, 427, 428, 430}


def ppu_symbols(pcs, meta, binary):
    if binary is None:
        return {}
    uuids = subprocess.check_output(['xcrun', 'dwarfdump', '--uuid', str(binary)], text=True)
    if meta['uuid'].lower() not in uuids.lower():
        raise ValueError('Trace and binary UUID differ')
    base = meta['app_base']
    pcs = sorted(pc for pc in pcs if base <= pc < meta['app_end'])
    if not pcs:
        return {}
    with tempfile.TemporaryDirectory() as directory:
        offsets = Path(directory) / 'offsets.txt'
        offsets.write_text(''.join(f'{pc - base:#x}\n' for pc in pcs))
        names = subprocess.check_output(['xcrun', 'atos', '-arch', 'arm64', '-o', str(binary),
                                         '--offset', '-f', str(offsets)], text=True).splitlines()
    if len(pcs) != len(names):
        raise ValueError('Could not pair PPU return addresses and symbols')
    return {pc: name.split(' (in ')[0] for pc, name in zip(pcs, names)}


def access_records(events, meta):
    groups = defaultdict(dict)
    reads, writes, boundary = [], [], 0
    for event in events:
        kind = event['kind']
        if kind == 424:
            reads.append(dict(event, site=RSX_SITES[event['who']]))
        elif kind in (429, 431):
            reads.append(dict(event, site='RSX FIFO', word=event['who'], header=kind == 429))
        elif kind in FLOW_RECORDS:
            group = groups[event['who']]
            if kind in group:
                raise ValueError('Duplicate data flow record')
            group[kind] = event
    for group in groups.values():
        primary = next((k for k in (420, 423, 425) if k in group), None)
        required = {425, 426, 427} if primary == 425 else {primary, 421, 422, 428}
        if primary == 420 and 421 in group and group[421]['a'] and group[420]['b'] >= 4:
            required.add(430)
        first = next(iter(group.values()))
        if set(group) != required:
            if first['t1'] >= meta['end'] - .01:
                boundary += 1
                continue
            raise ValueError(f'Incomplete data flow group {first["who"]}: {sorted(group)}')
        record = dict(group[primary])
        if primary == 425:
            record.update(site='PPU scalar', pc=group[426]['a'] + (group[426]['b'] << 32),
                          thread=group[427]['a'])
        else:
            record.update(site='SPU GET', job=group[421]['a'], spu=group[421]['b'],
                          lsa=group[422]['a'], image=group[422]['b'], pc=group[428]['a'],
                          lr=group[428]['b'])
            if 430 in group:
                record['first_word'] = group[430]['a']
        (writes if primary == 420 else reads).append(record)
    return reads, writes, boundary


def by_page(record):
    start = record['a']
    end = start + record['b']
    if not 0 <= start < end <= 1 << 32:
        raise ValueError('Invalid guest memory range')
    for page in range(start >> 12, ((end - 1) >> 12) + 1):
        yield page, max(start, page << 12), min(end, (page + 1) << 12)


def version_matches(reads, writes, jobs):
    """Resolve byte ranges against the latest observed DMA; censor concurrent PUTs."""
    pages = defaultdict(list)
    for write in sorted(writes, key=lambda record: record['t0']):
        for page, lo, hi in by_page(write):
            pages[page].append((lo, hi, write))
    starts = {page: [write['t0'] for _, _, write in entries] for page, entries in pages.items()}
    latest_ends = {page: list(accumulate((write['t1'] for _, _, write in entries), max))
                   for page, entries in pages.items()}
    for read in reads:
        found = defaultdict(int)
        for page, lo, hi in by_page(read):
            entries = pages.get(page)
            if not entries:
                continue
            remaining = [(lo, hi)]
            count = bisect_right(starts[page], read['t1'])
            for index in range(count - 1, -1, -1):
                a, b, write = entries[index]
                pieces = []
                for left, right in remaining:
                    x, y = max(a, left), min(b, right)
                    if x >= y:
                        pieces.append((left, right))
                        continue
                    if left < x:
                        pieces.append((left, x))
                    if y < right:
                        pieces.append((y, right))
                    # A later or in-flight competing DMA masks this range even
                    # when it has no complete measured producer job.
                    job = jobs.get(write['job'])
                    if not job or write['t1'] >= read['t0'] or read.get('job') == write['job']:
                        continue
                    first_possible_overlap = bisect_right(latest_ends[page], write['t0'], hi=index)
                    concurrent = any(older['t1'] > write['t0'] and c < y and d > x
                                     for c, d, older in entries[first_possible_overlap:index])
                    if not concurrent:
                        found[write['who']] += y - x
                remaining = pieces
                if not remaining:
                    break
        for tag, bytes_read in found.items():
            yield read, tag, bytes_read


def fifo_header(word):
    if word >> 16 == 0xFEAD:
        return 'flip'
    if word >> 29 == 1:
        return 'jump'
    if word & 3 == 2:
        return 'call'
    if word == 0x20000:
        return 'return'
    if word >> 29 in (0, 2) and (word >> 18) & 0x7ff:
        return f'method {word & 0x1ffc:#06x}'
    return 'other'


def analyze(path, binary=None):
    timeline, events = load_trace(path)
    meta = timeline['metadata']
    calls, missing = scopes(events, meta)
    if any(not m.get('cancelled') and m['start'] < meta['end'] - .25 for m in missing):
        raise ValueError('Missing interior logical job return')
    jobs = {call['id']: dict(call, module=TARGETS[call['entry']]) for call in calls
            if call['whole_job'] and not call['boundary'] and call['entry'] in TARGETS}
    if not jobs:
        raise ValueError('No complete target job scopes')
    reads, writes, boundary = access_records(events, meta)
    writes_by_tag = {write['who']: write for write in writes}
    puts = defaultdict(list)
    for write in writes:
        job = jobs.get(write['job'])
        if job:
            if not job['start'] <= write['t0'] <= write['t1'] <= job['end'] or write['spu'] != job['spu']:
                raise ValueError('DMA outside its producer job')
            puts[job['module']].append(write)
    matches = []
    word_mismatches = Counter()
    for read, tag, bytes_read in version_matches(reads, writes, jobs):
        write = writes_by_tag[tag]
        job = jobs[write['job']]
        consumer = jobs.get(read.get('job'))
        word_verified = ('word' in read and 'first_word' in write and
                         read['a'] == write['a'] and bytes_read == 4)
        if word_verified and read['word'] != write['first_word']:
            word_mismatches[job['module']] += 1
            continue
        matches.append(dict(module=job['module'], job=job['id'], put=tag,
                            put_address=write['a'], put_size=write['b'], put_pc=write['pc'],
                            put_lr=write['lr'], put_lsa=write['lsa'], put_image=write['image'],
                            site=read['site'], consumer_module=consumer['module'] if consumer else None,
                            consumer_job=consumer['id'] if consumer else None,
                            consumer_started_before_put_end=bool(consumer and consumer['start'] < write['t1']),
                            reader_pc=read.get('pc'), reader_lr=read.get('lr'), reader_image=read.get('image'),
                            reader_thread=read.get('thread'), reader_address=read['a'],
                            reader_size=read['b'], bytes=bytes_read,
                            lag_ms=1000 * (read['t0'] - write['t1']), word_verified=word_verified,
                            fifo_word=read.get('word'),
                            fifo_header=fifo_header(read['word']) if read.get('header') else None,
                            job_wall_ms=job['wall_ms'], job_cpu_ms=job['cpu_ms'],
                            reader_before_job_end=read['t0'] < job['end']))
    symbols = ppu_symbols({m['reader_pc'] for m in matches if m['site'] == 'PPU scalar'}, meta, binary)
    for match in matches:
        if match['site'] == 'PPU scalar':
            match['reader_symbol'] = symbols.get(match['reader_pc'], hex(match['reader_pc']))
    verified_fifo_jobs = {m['job'] for m in matches if m['word_verified']}
    modules = {}
    for module in TARGETS.values():
        observations = [m for m in matches if m['module'] == module]
        measured = [job for job in jobs.values() if job['module'] == module]
        verified = [m for m in observations if m['word_verified']]
        first_verified = {}
        for match in sorted(verified, key=lambda match: match['lag_ms']):
            first_verified.setdefault(match['put'], match)
        first_spu_reads = {}
        for match in sorted((m for m in observations if m['site'] == 'SPU GET'), key=lambda m: m['lag_ms']):
            first_spu_reads.setdefault((match['put'], match['consumer_module']), match)
        linked_jobs = {m['consumer_job'] for m in observations if m['consumer_job'] in verified_fifo_jobs}
        modules[module] = dict(
            jobs=len(measured), job_cpu_ms=stats([j['cpu_ms'] for j in measured]),
            job_wall_ms=stats([j['wall_ms'] for j in measured]),
            puts=len(puts[module]), put_bytes=sum(w['b'] for w in puts[module]),
            put_sites=Counter(f'{w["image"]}:{w["lr"]:#x}/{w["b"]}' for w in puts[module]).most_common(20),
            matched_puts=len({m['put'] for m in observations}),
            matching_accesses=dict(Counter(m['site'] for m in observations)),
            fifo_verified_reads=len(verified), fifo_verified_puts=len(first_verified),
            fifo_verified_jobs=len({m['job'] for m in verified}),
            fifo_word_mismatches_excluded=word_mismatches[module],
            downstream_jobs_with_verified_fifo_output=len(linked_jobs),
            puts_read_by_downstream_jobs_with_verified_fifo_output=len({m['put'] for m in observations
                                                                       if m['consumer_job'] in linked_jobs}),
            puts_first_observed_read_by_already_running_job=len({m['put'] for m in first_spu_reads.values()
                                                                 if m['consumer_started_before_put_end']}),
            verified_first_word_lag_ms=stats([m['lag_ms'] for m in first_verified.values()]),
            verified_fifo_headers=Counter(m['fifo_header'] for m in verified if m['fifo_header']).most_common(20),
            spu_consumer_modules=dict(Counter(m['consumer_module'] or 'outside selected scopes'
                                              for m in first_spu_reads.values())),
            spu_first_observed_read_ms={consumer: stats([m['lag_ms'] for m in first_spu_reads.values()
                                                        if (m['consumer_module'] or 'outside selected scopes') == consumer])
                                        for consumer in {m['consumer_module'] or 'outside selected scopes'
                                                         for m in first_spu_reads.values()}},
            evidence_examples=verified[:3] + list(first_spu_reads.values())[:3],
            ppu_callers=Counter(m['reader_symbol'] for m in observations if m['site'] == 'PPU scalar').most_common(20),
            spu_read_sites=Counter(f'{m["reader_image"]}:{m["reader_lr"]:#x}' for m in observations
                                   if m['site'] == 'SPU GET').most_common(20),
            publication_to_access_ms={site: stats([m['lag_ms'] for m in observations if m['site'] == site])
                                      for site in sorted({m['site'] for m in observations})},
        )
    report = dict(metadata=meta, modules=modules, dropped_boundary_groups=boundary,
                  access_counts=dict(Counter(read['site'] for read in reads)), recorded_puts=len(writes),
                  scope_cancellations=sum(bool(m.get('cancelled')) for m in missing),
                  frame_metrics=timeline['frame_metrics'], limitations=[
                      'Observed byte-range provenance, not content identity or evidence of a stall.',
                      'FIFO dword reads are sampled at 32-byte aligned addresses. A verified word equals the producer PUT prefix; this does not verify the whole buffer.',
                      'PUT and GET timestamps bracket the guest memory copy. Renderer ranges are pointer requests or FIFO reads.',
                      'PPU scalar records mark entry to a read helper. Some reads can come from runtime code called with an active PPU context.',
                      'Plain DMA writes to watched pages are recorded. PPU stores, atomic writes, GPU writes and uninstrumented reads can escape coverage.',
                      'Pages are armed by the first measured producer PUT. Earlier accesses and results emitted after logical job return are not attributed.',
                  ])
    return report, dict(matches=matches, producer_puts=dict(puts))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--details', action='store_true', help='Also export all byte-range matches')
    args = parser.parse_args()
    result, details = analyze(args.trace, args.binary)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    if args.details:
        args.output.with_suffix('.details.json').write_text(json.dumps(details, indent=2) + '\n')
    print(json.dumps(result['modules'], indent=2))
