#!/usr/bin/env python3
"""Expose known pinned-fork test mismatches and reject any new failure."""
import subprocess
import sys

EXPECTED = [
    "[FAIL] a size change reallocates and releases the old target",
    "[FAIL] a different offset is a different surface",
    "[FAIL] the same offset in another context DMA is another surface",
    "[FAIL] a triangle list of distinct vertices is not indexed (3 verts, 3 indices)",
]
def main():
    results = []
    for label, executable in zip(("unpatched baseline", "platform overlay"), sys.argv[1:], strict=True):
        run = subprocess.run([executable], capture_output=True, text=True)
        failures = [line.split("   (")[0] for line in run.stdout.splitlines() if line.startswith("[FAIL]")]
        print(f"{label}: exit={run.returncode}, {len(failures)} failing checks")
        for line in failures:
            print(line)
        results.append((run.returncode, failures))
    if results == [(0, []), (0, [])]:
        print("All upstream checks passed on both sources")
    elif results == [(1, EXPECTED), (1, EXPECTED)]:
        print("PASS: no new failures; four existing pinned-fork mismatches remain (not fixed or hidden)")
    else:
        raise SystemExit("FAIL: unexpected upstream failure or platform regression")


if __name__ == "__main__":
    main()
