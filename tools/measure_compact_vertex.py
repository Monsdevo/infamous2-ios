#!/usr/bin/env python3
"""Measure one warmed compact-vertex window with raw presentation timestamps."""
import argparse
import json
from pathlib import Path

from measure_geometry import measure
from rsx_measurement import validate_rsx


def capture(device, mode, output, thermal, seconds):
    def validate(current, initial):
        errors = validate_rsx(current, True, initial)
        if current.get('compact_vertex', {}).get('mode') != mode:
            errors.append('compact vertex mode differs')
        if current['performance'].get('metal_errors', 0):
            errors.append('Metal errors reported')
        if initial and current['performance'].get('pipeline_failed', 0) != initial['performance'].get('pipeline_failed', 0):
            errors.append('renderer pipeline failed during measurement')
        return errors

    result = measure(device, (0, 0), False, output, 'swamp-walkway-fixed-camera',
                     seconds, 100, seconds + 20, thermal, False, validate)
    reports = sorted(output.glob('[0-9][0-9][0-9].json'))
    if len(reports) >= 2:
        first, last = [json.loads(p.read_text())['compact_vertex'] for p in (reports[0], reports[-1])]
        result['compact_draws'] = last['draws'] - first['draws']
        result['compact_bytes_saved'] = last['bytes_saved'] - first['bytes_saved']
        if bool(result['compact_draws']) != bool(mode):
            result.update(valid=False, failure='measured mode does not match actual compact draws')
    result['compact_mode'] = mode
    (output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result.get(key) for key in
                      ('valid', 'failure', 'compact_mode', 'compact_draws', 'compact_bytes_saved', 'raw_frame_stats')}),
          flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', required=True)
    parser.add_argument('--mode', required=True, type=int, choices=(0, 1))
    parser.add_argument('--thermal-state', required=True, type=int, choices=(0, 1, 2, 3))
    parser.add_argument('--seconds', type=int, default=20)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = capture(args.device, args.mode, args.output, args.thermal_state, args.seconds)
    raise SystemExit(0 if result['valid'] else 1)
