#!/usr/bin/env python3
"""Extract only identified BCES analysis inputs from a bounded ISO prefix.

The original archive is never modified. This intentionally DOES NOT validate
the entire 7z/ISO CRC or extract assets. Known hashes validate selected files.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ROOT / "data/incoming/inFamous 2 (Turkey).7z")
    parser.add_argument("--output", type=Path, default=ROOT / "data/inspection/bces01229")
    args = parser.parse_args()
    profile = json.loads((ROOT / "profiles/BCES01229-01.00.json").read_text())
    selected = args.output / "selected"
    required = [("PS3_GAME/PARAM.SFO", 1040, profile["sfo_sha256"]),
                ("PS3_GAME/USRDIR/EBOOT.BIN", 10162208, profile["self_sha256"])]

    def verify_selected():
        for name, size, sha in required:
            path = selected / name
            if not path.exists():
                return False
            if path.stat().st_size != size or hashlib.sha256(path.read_bytes()).hexdigest() != sha:
                raise SystemExit("Existing selected input differs from profile; preserved: " + str(path))
        return True

    args.output.mkdir(parents=True, exist_ok=True)
    reused = verify_selected()
    prefix = args.output / "disc-prefix-128MiB.partial"
    if not reused:
        if not prefix.exists():
            with prefix.open("xb") as output, (args.output / "prefix-decode.log").open("wb") as log:
                proc = subprocess.Popen(["7zz", "x", "-so", "-mmt=2", str(args.archive.resolve()),
                                         "inFamous 2 (Turkey).iso"], stdout=subprocess.PIPE, stderr=log)
                try:
                    remaining = 128 * 1024 * 1024
                    while remaining:
                        chunk = proc.stdout.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise RuntimeError("ISO stream ended before the analysis prefix")
                        output.write(chunk)
                        remaining -= len(chunk)
                finally:
                    proc.terminate()
                    proc.stdout.close()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
        if prefix.stat().st_size != 128 * 1024 * 1024:
            raise SystemExit("Incomplete existing prefix preserved; inspect before retry")
        with (args.output / "selected-extract.log").open("w") as log:
            rc = subprocess.run(["7zz", "x", "-mmt=2", "-aos", "-o" + str(selected.resolve()), str(prefix.resolve()),
                                 "PS3_GAME/PARAM.SFO", "PS3_DISC.SFB", "PS3_GAME/USRDIR/EBOOT.BIN"],
                                stdout=log, stderr=subprocess.STDOUT).returncode
        if rc not in (0, 2) or not verify_selected():
            raise SystemExit("Selected-file extraction failed or hashes did not match; no game data accepted")
    report = {"profile": profile["name"], "reused_verified_files": reused,
              "selected_hashes_verified": True, "full_archive_integrity_verified": False,
              "source_archive_modified": False, "prefix_only": True, "game_boot_attempted": False}
    (args.output / "selected-inputs.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
