#!/usr/bin/env python3
"""Derive the phase archive from Build 59 by recompiling just 1774dd."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from prepare_job_flow import spu_phases


root = Path(__file__).resolve().parents[1]
baseline_path = root / 'out/bces-support-critical59.json'
baseline = json.loads(baseline_path.read_text())
out = root / 'build/bces01229/support-compile/iphoneos-critical62'
out.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer',
           TMPDIR=str(root / 'build/tmp'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


if baseline['result'] != 'PASS' or not baseline['critical_job_logical_jobs'] or sha(baseline['archive']) != baseline['archive_sha256']:
    raise SystemExit('Invalid Build 59 archive')
units = []
for unit in baseline['units']:
    original = Path(unit['source'])
    if original.parent.name != 'jobmod_1774dd41c4e8_e14f90':
        units.append(unit)
        continue
    if sha(original) != unit['sha256']:
        raise SystemExit('Source hash differs')
    source = out / 'spu_recomp.c'
    source.write_text(spu_phases(original.read_text()))
    shutil.copy2(original.with_suffix('.h'), out / 'spu_recomp.h')
    obj = out / Path(unit['object']).name
    command = [{unit['source']: str(source), unit['object']: str(obj)}.get(arg, arg)
               for arg in unit['command']]
    subprocess.run(command, env=env, check=True)
    platform = subprocess.check_output(['xcrun', 'vtool', '-show-build', str(obj)], env=env, text=True)
    if 'platform IOS\n' not in platform:
        raise SystemExit('Expected iPhoneOS object')
    units.append(dict(unit, source=str(source), sha256=sha(source), object=str(obj),
                      object_sha256=sha(obj), command=command))

if len(units) != 83 or sum(Path(unit['object']).parent == out for unit in units) != 1:
    raise SystemExit('Expected exactly one replacement')
archive = out / 'libbces_support.a'
subprocess.run(['xcrun', 'libtool', '-static', '-o', str(archive),
                *(unit['object'] for unit in units)], env=env, check=True)
report = dict(baseline, units=units, archive=str(archive), archive_sha256=sha(archive),
              critical_job_phases=True, parent_report_sha256=sha(baseline_path))
(root / 'out/bces-support-critical62.json').write_text(json.dumps(report, indent=2) + '\n')
