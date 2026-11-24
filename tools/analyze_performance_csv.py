#!/usr/bin/env python3
"""Summarize explicit CSV windows without inferring a game stage from FPS."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics


def summarize(path, label, last_seconds=None):
    with path.open() as source:
        rows = list(csv.DictReader(source))
    if not rows:
        raise ValueError("CSV has no measurement rows")
    if last_seconds is not None:
        if last_seconds <= 0:
            raise ValueError("Window must be positive")
        start = float(rows[-1]["monotonic_s"]) - last_seconds
        rows = [r for r in rows if float(r["monotonic_s"]) >= start]
    metrics = {}
    for key, validity in (("fps", None), ("frame_mean_ms", "frame_samples"),
            ("frame_p95_ms", "frame_samples"), ("cpu_percent", "cpu_valid"),
            ("gpu_mean_ms", "gpu_samples"), ("render_mean_ms", "render_samples"),
            ("footprint_bytes", "memory_valid"), ("peak_sampled_bytes", "memory_valid"),
            ("available_process_memory_bytes", None), ("memory_warning_count", None), ("thermal", None)):
        values = []
        for row in rows:
            if key not in row or not row[key]:
                continue
            if validity and not float(row.get(validity) or 0):
                continue
            value = float(row[key])
            if math.isfinite(value):
                values.append(value)
        if values:
            metrics[key] = {"samples": len(values), "median": statistics.median(values),
                            "min": min(values), "max": max(values)}
    return {"source": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "label": label, "rows": len(rows), "start_monotonic_s": float(rows[0]["monotonic_s"]),
            "end_monotonic_s": float(rows[-1]["monotonic_s"]), "metrics": metrics,
            "interpretation": "Medians/min/max of sampled windows; rolling p95 values are not a whole-run frame p95. GPU covers presentation command buffers only. Label supplied by operator."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--last-seconds", type=float)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = json.dumps(summarize(args.csv, args.label, args.last_seconds), indent=2) + "\n"
    if args.output:
        args.output.write_text(result)
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
