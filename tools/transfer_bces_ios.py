#!/usr/bin/env python3
"""Copy existing assets to the development app; publish readiness only last.

Copies packed PSARC files and the byte-verified Mac install, not Mac saves.
No existing app data is removed. Run after installation and device link check.
"""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = "dev.infamous2.iosprobe"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True)
    parser.add_argument("--resume", action="store_true", help="Copy only missing/size-mismatched inventory entries; requires a fresh in-app validation report")
    args = parser.parse_args()
    env = dict(os.environ, DEVELOPER_DIR="/Applications/Xcode.app/Contents/Developer", TMPDIR=str(ROOT / "build/tmp"))
    out = ROOT / "out/step12-asset-transfer"
    out.mkdir(exist_ok=True)
    device_report = out / "before-report.json"
    base = ["xcrun", "devicectl", "device"]
    with (out / "before-report-copy.log").open("w") as log:
        subprocess.run([*base, "copy", "from", "--device", args.device,
                        "--domain-type", "appDataContainer", "--domain-identifier", BUNDLE,
                        "--source", "Documents/bces-device-report.json", "--destination", str(device_report)],
                       env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    report = json.loads(device_report.read_text())
    manifest_path = ROOT / "build/bces01229/ios-prepared/resources/bces-inputs.json"
    manifest = json.loads(manifest_path.read_text())
    if not report["link_validation_passed"] or not report["bundled_ELF_verified"]:
        raise SystemExit("Device link/input check must pass before transfer")
    # The app must be relaunched/refreshed before invoking this tool: the report's
    # available capacity is measured by checkInputs(), not by every HUD tick.
    available = report["available_capacity_bytes"]
    selected = manifest["entries"]
    retained_bytes = 0
    staging = ROOT / "build/bces01229/transfer-resume"
    if args.resume:
        listing = out / "resume-before-files.json"
        with (out / "resume-before-files.log").open("w") as log:
            subprocess.run([*base, "info", "files", "--device", args.device,
                            "--domain-type", "appDataContainer", "--domain-identifier", BUNDLE,
                            "--subdirectory", "Documents/BCES01229", "--timeout", "60",
                            "--json-output", str(listing)], env=env, stdout=log,
                           stderr=subprocess.STDOUT, check=True)
        remote = {f["relativePath"]: f["metadata"]["size"]
                  for f in json.loads(listing.read_text())["result"]["files"]
                  if not f["resources"]["isDirectory"]}
        selected = [e for e in manifest["entries"] if remote.get(e["path"]) != e["bytes"]]
        retained_bytes = manifest["total_bytes"] - sum(e["bytes"] for e in selected)
        # Private staging contains only hard links to immutable inputs. Do not
        # touch mtimes through them; do not remove any device-side directories.
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        roots = {"PS3_GAME": ROOT / "data/game/BCES01229",
                 "dev_flash": ROOT / "data/firmware/dev_flash",
                 "dev_hdd0": ROOT / "data/vfs/BCES01229/dev_hdd0"}
        for entry in selected:
            rel = Path(entry["path"])
            if rel.is_absolute() or ".." in rel.parts or rel.parts[0] not in roots:
                raise SystemExit("Unsafe input inventory path: " + str(rel))
            source = roots[rel.parts[0]].joinpath(*rel.parts[1:])
            if source.stat().st_size != entry["bytes"]:
                raise SystemExit("Source changed: " + str(source))
            target = staging / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            os.link(source, target)
    required = sum(e["bytes"] for e in selected)
    # Conservative: require space for all selected bytes plus reserve, without
    # assuming that overwriting partial files immediately reclaims their space.
    if available < required + 1024**3:
        raise SystemExit(f"Not enough measured device headroom: available={available}, remaining={required}")
    previous = out / "state.json"
    if previous.exists():
        shutil.copyfile(previous, out / ("state-before-" + str(time.time_ns()) + ".json"))
    state = {"complete": False, "total_asset_bytes": manifest["total_bytes"],
             "available_before": available, "phases": [], "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
             "resume": args.resume, "retained_size_matching_bytes": retained_bytes,
             "selected_bytes": required, "selected_files": len(selected)}

    def save():
        (out / "state.json").write_text(json.dumps(state, indent=2) + "\n")

    save()
    for label, source in (("PS3_GAME", ROOT / "data/game/BCES01229"),
                          ("dev_flash", ROOT / "data/firmware/dev_flash"),
                          ("dev_hdd0", ROOT / "data/vfs/BCES01229/dev_hdd0")):
        if args.resume:
            source = staging / label
            if not source.exists():
                continue
        phase = {"label": label, "source": str(source), "complete": False}
        state["phases"].append(phase); save()
        print("Transfer starting:", label, flush=True)
        start = time.monotonic()
        with (out / (label + ".log")).open("w") as log:
            result = subprocess.run([*base, "copy", "to", "--device", args.device,
                "--domain-type", "appDataContainer", "--domain-identifier", BUNDLE,
                "--source", str(source), "--destination", "Documents/BCES01229/" + label,
                "--timeout", "7200", "--json-output", str(out / (label + ".json"))],
                env=env, stdout=log, stderr=subprocess.STDOUT)
        phase.update(returncode=result.returncode, elapsed_seconds=time.monotonic() - start,
                     complete=result.returncode == 0); save()
        if result.returncode:
            raise SystemExit("Transfer did not finish: " + label + "; no readiness token published")
        print("Transfer finished:", label, flush=True)
    # A successful command alone is insufficient: check every required file's
    # size before publishing readiness. The app additionally hashes critical
    # files and verifies the token's manifest digest before admitting boot.
    final_listing = out / "after-files.json"
    with (out / "after-files.log").open("w") as log:
        subprocess.run([*base, "info", "files", "--device", args.device,
                        "--domain-type", "appDataContainer", "--domain-identifier", BUNDLE,
                        "--subdirectory", "Documents/BCES01229", "--timeout", "60",
                        "--json-output", str(final_listing)], env=env, stdout=log,
                       stderr=subprocess.STDOUT, check=True)
    final_files = {f["relativePath"]: f["metadata"]["size"]
                   for f in json.loads(final_listing.read_text())["result"]["files"]
                   if not f["resources"]["isDirectory"]}
    bad = [e["path"] for e in manifest["entries"] if final_files.get(e["path"]) != e["bytes"]]
    state["final_inventory_size_mismatches"] = bad
    save()
    if bad:
        raise SystemExit(f"{len(bad)} files still missing or size-mismatched; no readiness token published")
    token = out / "transfer-complete.json"
    token.write_text(json.dumps({"manifest_sha256": state["manifest_sha256"], "profile": manifest["profile"],
                                 "asset_bytes": manifest["total_bytes"]}, indent=2) + "\n")
    with (out / "completion-copy.log").open("w") as log:
        subprocess.run([*base, "copy", "to", "--device", args.device,
                        "--domain-type", "appDataContainer", "--domain-identifier", BUNDLE,
                        "--source", str(token), "--destination", "Documents/BCES01229/transfer-complete.json"],
                       env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    state["complete"] = True; save()
    print("All assets copied; device must still validate inventory before boot.", flush=True)


if __name__ == "__main__":
    main()
