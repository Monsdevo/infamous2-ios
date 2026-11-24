#!/usr/bin/env python3
"""Bounded opt-in timeline capture in an already running diagnostic process."""
import argparse
import csv
import json
from pathlib import Path
import time
import uuid

from geometry_device_control import BUNDLE, call, report


def capture(device, output, seconds):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    before = report(device, output / 'before.json')
    token = 'critical' + uuid.uuid4().hex

    def write(text):
        control = output / 'control.txt'
        control.write_text(text)
        call(['device', 'copy', 'to', '--device', device,
              '--domain-type', 'appDataContainer', '--domain-identifier', BUNDLE,
              '--source', str(control.resolve()),
              '--destination', 'Documents/frame-trace-control.txt'])

    try:
        write(f'start {token} {seconds}\n')
        seen = False
        for index in range(30):
            time.sleep(2)
            current = report(device, output / f'{index:02}.json')
            if (current['pid'] != before['pid'] or
                    current.get('geometry_control_session') != before.get('geometry_control_session')):
                raise RuntimeError('Game process changed during timeline capture')
            state = current.get('frame_trace_state', 0)
            if state < 0:
                raise RuntimeError('Frame tracer reported an error')
            seen |= state in (1, 2)
            if seen and state == 3:
                break
        else:
            raise RuntimeError('Frame capture did not complete; process needs --diagnose-frame')
        for name in ['frame-trace.csv', 'frame-thread-map.csv']:
            call(['device', 'copy', 'from', '--device', device,
                  '--domain-type', 'appDataContainer', '--domain-identifier', BUNDLE,
                  '--source', 'Documents/' + name,
                  '--destination', str((output / name).resolve())])
        with (output / 'frame-trace.csv').open() as source:
            metadata = json.loads(source.readline().removeprefix('# '))
            rows = sum(1 for _ in csv.DictReader(source))
        if metadata['token'] != token or metadata['dropped'] or rows != metadata['rows']:
            raise RuntimeError('Trace token mismatch, dropped events or incomplete file')
        result = dict(valid=True, pid=before['pid'], metadata=metadata,
                      thermal_states=sorted({json.loads(p.read_text())['performance']['thermal_state']
                                             for p in output.glob('[0-9][0-9].json')}),
                      limitation='Instrumented timeline; not an uninstrumented FPS benchmark.')
        (output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2), flush=True)
    finally:
        write('idle\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--seconds', type=int, choices=range(1, 31), default=10)
    args = parser.parse_args()
    capture(args.device, args.output, args.seconds)
