#!/usr/bin/env python3
"""Measure an A/B/A G-buffer fence comparison in a confirmed fixed scene."""
import argparse
import json
from pathlib import Path
import time

from geometry_device_control import command, report
from measure_geometry import measure
from rsx_measurement import validate_rsx


def compare(device, output, seconds):
    thermal = report(device, output / 'comparison-start.json')['performance']['thermal_state']

    def validate(current, initial):
        errors = validate_rsx(current, True, initial)
        counters = current.get('gbuffer_fence', {})
        if counters.get('mode') != mode:
            errors.append('unexpected G-buffer fence mode')
        if counters.get('mismatches'):
            errors.append('normal readback bytes differ')
        if mode and not counters.get('validated'):
            errors.append('missing same-frame byte validation')
        if current['performance'].get('metal_errors'):
            errors.append('Metal error')
        if initial and current.get('runtime_log_capped') != initial.get('runtime_log_capped'):
            errors.append('logging changed during window')
        return errors

    results = {}
    try:
        for name, mode in [('A', 0), ('B', 1), ('C', 0)]:
            command(device, {'gbuffer_fence': mode}, output / f'set-{name}')
            time.sleep(6)
            path = output / name
            result = measure(device, (0, 0), False, path, 'swamp-walkway-fixed-camera',
                             seconds, 100, seconds + 20, thermal, False, validate)
            samples = sorted(path.glob('[0-9][0-9][0-9].json'))
            if len(samples) >= 2:
                initial, final = [json.loads(p.read_text())['gbuffer_fence'] for p in (samples[0], samples[-1])]
                result['reused'] = final['reused'] - initial['reused']
                result['rejected'] = final['rejected'] - initial['rejected']
                if bool(result['reused']) != bool(mode):
                    result.update(valid=False, failure='measured mode did not match active readback path')
            results[name] = result
            if not result['valid']:
                break
    finally:
        command(device, {'gbuffer_fence': 0}, output / 'restore')
        (output / 'comparison.json').write_text(json.dumps(results, indent=2) + '\n')
    return len(results) == 3 and all(result['valid'] for result in results.values())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--seconds', type=int, default=18)
    args = parser.parse_args()
    raise SystemExit(0 if compare(args.device, args.output, args.seconds) else 1)
