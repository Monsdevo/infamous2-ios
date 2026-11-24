#!/usr/bin/env python3
"""Verify this diagnostic VFS's installed copies against the original disc.

Reads only; never edits installs or creates completion markers. Generated
files without a disc counterpart are reported separately, not called verified.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    source_root = ROOT / "data/game/BCES01229/USRDIR"
    installed = ROOT / "data/vfs/BCES01229/dev_hdd0/game/BCES01143_INSTALL/USRDIR"
    if not (installed / "ne.bv").is_file():
        raise SystemExit("The real installer has not created its completion file")
    results, generated = [], []
    for target in sorted(installed.rglob("*")):
        if not target.is_file():
            continue
        rel = target.relative_to(installed)
        source = source_root / rel
        if not source.is_file():
            generated.append({"path": str(rel), "bytes": target.stat().st_size})
            continue
        before = (source.stat(), target.stat())
        if before[0].st_size != before[1].st_size:
            raise SystemExit("Installed size differs: " + str(rel))
        digest = hashlib.sha256()
        with source.open("rb") as a, target.open("rb") as b:
            while block := a.read(4 * 1024**2):
                if block != b.read(len(block)):
                    raise SystemExit("Installed bytes differ: " + str(rel))
                digest.update(block)
        after = (source.stat(), target.stat())
        if any((a.st_size, a.st_mtime_ns) != (b.st_size, b.st_mtime_ns) for a, b in zip(before, after)):
            raise SystemExit("File changed during comparison: " + str(rel))
        results.append({"path": str(rel), "bytes": before[0].st_size, "sha256": digest.hexdigest()})
        print("Verified", rel, flush=True)
    if not results:
        raise SystemExit("No installed disc copies found")
    report = {"result": "PASS", "installed_root": str(installed), "verified_copies": len(results),
              "verified_copy_bytes": sum(r["bytes"] for r in results), "copies": results,
              "generated_or_without_disc_counterpart": generated,
              "installer_completion_marker_exists": True, "gameplay_verified": False}
    (ROOT / "out/step11-installed-copy-check.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "copies"}, indent=2))


if __name__ == "__main__":
    main()
