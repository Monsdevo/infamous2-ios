#!/usr/bin/env python3
"""UUID-checked own-process PC samples; CPU-time weighting per thread.

FP ancestry is best-effort and unsuspended: use exclusive PCs for ranking,
ancestry for attribution only. Profiling windows are not FPS benchmarks.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


def summarize(path, binary, label):
    with path.open() as f:
        meta = json.loads(f.readline().removeprefix('# '))
        rows = list(csv.DictReader(f))
    uuids = re.findall(r'UUID: ([0-9A-Fa-f-]+) \(arm64\)', subprocess.check_output(
        ['xcrun', 'dwarfdump', '--uuid', str(binary)], text=True))
    if meta['uuid'].upper() not in [u.upper() for u in uuids]:
        raise ValueError('Profile and executable UUID differ')
    if len(rows) != meta['rows'] or not rows or meta['end'] <= meta['start']:
        raise ValueError('Empty/inconsistent native profile')
    base, end = meta['app_base'], meta['app_end']
    offsets = sorted({int(pc, 16)-base for row in rows for pc in row['pcs'].split(';')
                      if base <= int(pc, 16) < end})
    with tempfile.TemporaryDirectory() as directory:
        addresses = Path(directory)/'offsets.txt'
        addresses.write_text(''.join(hex(pc)+'\n' for pc in offsets))
        names = subprocess.check_output(['xcrun', 'atos', '-arch', 'arm64', '-o', str(binary),
             '--offset', '-f', str(addresses)], text=True).splitlines()
    if len(names) != len(offsets):
        raise ValueError('Symbol count differs')
    symbols = {pc: name.split(' (in ')[0] for pc, name in zip(offsets, names)}
    threads = defaultdict(list)
    for row in rows:
        threads[row['thread_id']].append(row)
    exclusive, inclusive, roles = Counter(), Counter(), Counter()
    work_groups = Counter()
    module_ancestry = Counter()
    thread_summary = []
    for tid, samples in threads.items():
        cpu_delta = max(0, int(samples[-1]['cpu_us'])-int(samples[0]['cpu_us']))/1e6
        running = [s for s in samples if int(s.get('state', 1))==1]
        census = Counter(int(s['state']) for s in samples if int(s.get('census', 0)))
        weight = cpu_delta/len(running) if running else 0
        waiting = Counter()
        for sample in samples:
            if int(sample.get('state', 1))!=1:
                pcs = [int(pc,16) for pc in sample['pcs'].split(';')]
                app = [symbols[pc-base] for pc in pcs if base<=pc<end]
                waiting[app[0] if app else '<system/unresolved>']+=1
        thread_summary.append({'tid': tid, 'samples': len(samples), 'running_pc_samples':len(running),
            'observed_cpu_seconds': cpu_delta, 'periodic_state_observations':dict(census),
            'waiting_app_callers':waiting.most_common(5)})
        if not running:
            exclusive['<no-running-PC-sample>']+=cpu_delta;roles['other/unresolved']+=cpu_delta
            work_groups['no running PC']+=cpu_delta
        for sample in running:
            pcs = [int(pc, 16) for pc in sample['pcs'].split(';')]
            stack = [symbols[pc-base] for pc in pcs if base <= pc < end]
            leaf = symbols.get(pcs[0]-base, '<system/unresolved>')
            exclusive[leaf] += weight
            for name in set(stack):
                inclusive[name] += weight
            # Different modules may appear in one stack: these values overlap.
            observed_modules = {match.group(1) for name in stack
                if (match := re.match(r'^((?:jobmod|datamod|relocmod)_[0-9a-f]+(?:_e[0-9a-f]+)?)_spu_func_', name))}
            for module in observed_modules:
                module_ancestry[module] += weight
            # A partition of observed ancestry, not job-boundary timing. A
            # datamod without its caller stays unassigned rather than guessed.
            if any(name.startswith('jobmod_c6e7383dc013_') for name in stack):
                work_groups['lighting job ancestry']+=weight
            elif any(name.startswith('jobmod_e6fe749031f8_') for name in stack):
                work_groups['SSAO tiled pipeline job ancestry']+=weight
            elif any(name.startswith('datamod_') for name in stack):
                work_groups['datamod without observed job ancestor']+=weight
            else:
                work_groups['other ancestry']+=weight
            if any(name.startswith(('spu_', 'jobmod_')) or 'spu_exec_thread_proc' in name for name in stack):
                role = 'SPU'
            elif any('frame_clock' in name or 'eng_' in name or 'rsx_' in name for name in stack):
                role = 'renderer'
            elif any('ppu_' in name or 'gameWorker' in name or name.startswith('func_') for name in stack):
                role = 'PPU'
            else:
                role = 'other/unresolved'
            roles[role] += weight
    total = sum(exclusive.values())
    exclusive_modules = Counter()
    for name, value in exclusive.items():
        match = re.match(r'^((?:jobmod|datamod|relocmod)_[0-9a-f]+(?:_e[0-9a-f]+)?)_spu_func_', name)
        exclusive_modules[match.group(1) if match else '<other functions>'] += value
    def ranking(counter):
        return [{'function': name, 'estimated_cpu_seconds': value,
                 'percent_of_observed_cpu': 100*value/total if total else 0}
                for name, value in counter.most_common(60)]
    return {'label': label, 'metadata': meta, 'profile': str(path.resolve()),
            'profile_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'binary': str(binary.resolve()), 'symbolicated_offsets': len(offsets),
            'observed_cpu_seconds': total, 'disjoint_roles_cpu_seconds': dict(roles),
            'observed_ancestry_groups_cpu_seconds_not_job_timings': dict(work_groups),
            'exclusive': ranking(exclusive), 'inclusive_do_not_sum': ranking(inclusive),
            'exclusive_modules': ranking(exclusive_modules),
            'module_ancestry_do_not_sum': ranking(module_ancestry),
            'threads': sorted(thread_summary, key=lambda t: -t['observed_cpu_seconds']),
            'interpretation': 'Running-state PC samples weighted by each thread observed CPU delta. Not exact function timings; unsuspended FP ancestry can be incomplete/inconsistent. Sampler thread excluded; kernel execution cannot be unwound. Scene label supplied by operator.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('profile', type=Path)
    p.add_argument('--binary', required=True, type=Path)
    p.add_argument('--label', required=True)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    result = summarize(args.profile, args.binary, args.label)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'roles': result['disjoint_roles_cpu_seconds'], 'top': result['exclusive'][:12]}, indent=2))


if __name__ == '__main__':
    main()
