#!/usr/bin/env python3
"""Build an isolated O2 variant of the 70 generated SPU units, one job at a time.

Reuse the other 13 baseline objects byte for byte. Preserve O1 objects/report/
archive. No fast-math, altered arithmetic flags, runtime edits or PPU rebuild.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def variant_command(command, obj):
    if command.count("-O1") != 1 or any(x.startswith("-O") and x != "-O1" for x in command):
        raise ValueError("Expected one baseline -O1 option")
    if command.count("-o") != 1:
        raise ValueError("Expected one object output")
    result = ["-O2" if item == "-O1" else item for item in command]
    result[result.index("-o") + 1] = str(obj)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--sdk", choices=("iphoneos", "macosx"), default="iphoneos")
    args = parser.parse_args()
    env = dict(os.environ, DEVELOPER_DIR="/Applications/Xcode.app/Contents/Developer",
               TMPDIR=str(ROOT / "build/tmp"))
    baseline_path = ROOT / f"out/bces-support-compile-{args.sdk}.json"
    baseline = json.loads(baseline_path.read_text())
    units = baseline["units"]
    if baseline["result"] != "PASS" or baseline["sdk"] != args.sdk or len(units) != 83:
        raise SystemExit("Expected verified 83-unit SDK-matching O1 baseline")
    selected = [u for u in units if Path(u["source"]).name == "spu_recomp.c"]
    if len(selected) != 70:
        raise SystemExit("Expected 70 generated SPU units; inspect inventory")
    # Validate the actual baseline archive, not just loose objects.
    members = subprocess.check_output(["ar", "-t", baseline["archive"]], text=True).splitlines()
    if sorted(m for m in members if not m.startswith("__.SYMDEF")) != sorted(Path(u["object"]).name for u in units):
        raise SystemExit("Baseline archive inventory mismatch")
    for unit in units:
        if (not unit["platform_verified"] or sha(unit["source"]) != unit["sha256"]
                or sha(unit["object"]) != unit["object_sha256"]):
            raise SystemExit("Baseline input changed: " + unit["source"])
        member = subprocess.check_output(["ar", "-p", baseline["archive"], Path(unit["object"]).name])
        if hashlib.sha256(member).hexdigest() != unit["object_sha256"]:
            raise SystemExit("Baseline archive member mismatch")
    output = ROOT / f"build/bces01229/support-compile/{args.sdk}-spu-O2"
    output.mkdir(parents=True, exist_ok=True)
    report_path = ROOT / f"out/bces-support-compile-{args.sdk}-spu-O2.json"
    runtime = ROOT / "upstream/infamous2-recomp/ps3recomp-fork"
    identity = hashlib.sha256()
    for header in sorted(set(runtime.rglob("*.h")) | set((ROOT / "build/bces01229/spu").rglob("*.h"))
                         | set((ROOT / "build/bces01229/lle_spu").rglob("*.h"))):
        identity.update(str(header).encode())
        identity.update(header.read_bytes())
    identity.update(baseline_path.read_bytes())
    identity.update(Path(__file__).read_bytes())
    identity.update(subprocess.check_output(["xcrun", "--sdk", args.sdk, "clang", "--version"], env=env))
    cache_identity = identity.hexdigest()
    prior = {}
    if args.resume and report_path.exists():
        old = json.loads(report_path.read_text())
        if old.get("cache_identity") == cache_identity:
            prior = {u["source"]: u for u in old["units"]}
    report = {"result": "BUILDING", "sdk": args.sdk, "variant": "spu-O2",
              "compiler_jobs": 1, "cache_identity": cache_identity,
              "baseline_report_sha256": sha(baseline_path), "baseline_archive_sha256": sha(baseline["archive"]),
              "optimized_SPU_units": 70, "unchanged_baseline_units": 13,
              "units": [], "archive": None, "game_run": False}
    def save():
        temp = report_path.with_suffix(".tmp")
        temp.write_text(json.dumps(report, indent=2) + "\n")
        temp.replace(report_path)
    save()
    for index, unit in enumerate(units):
        if Path(unit["source"]).name != "spu_recomp.c":
            report["units"].append({**unit, "baseline_reused": True})
            save()
            continue
        obj = output / Path(unit["object"]).name
        log = obj.with_suffix(".log")
        command = variant_command(unit["command"], obj)
        previous = prior.get(unit["source"], {})
        cached = (previous.get("returncode") == 0 and previous.get("command") == command
                  and obj.exists() and sha(obj) == previous.get("object_sha256"))
        if cached:
            item = {**previous, "cached": True}
        else:
            with log.open("w") as stream:
                rc = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT).returncode
            build = subprocess.check_output(["xcrun", "vtool", "-show-build", str(obj)], env=env, text=True) if rc == 0 else ""
            item = {**unit, "object": str(obj), "log": str(log), "command": command,
                    "returncode": rc, "platform_verified": ("platform "+("IOS" if args.sdk=="iphoneos" else "MACOS")+"\n") in build,
                    "object_sha256": sha(obj) if rc == 0 else None, "cached": False}
        report["units"].append(item)
        save()
        print(f"{index+1}/83 {Path(unit['source']).parent.name}: {'cached' if cached else item['returncode']}", flush=True)
        if item["returncode"] or not item["platform_verified"]:
            report["result"] = "FAIL"
            save()
            return 1
    defined, undefined = set(), set()
    symbols = subprocess.check_output(["xcrun", "nm", "-g", *[u["object"] for u in report["units"]]], env=env, text=True)
    import re
    for line in symbols.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[-2]) == 1:
            (undefined if parts[-2] == "U" else defined).add(parts[-1])
    missing = sorted(s for s in undefined - defined if re.search(r"(?:spu_func_|_(?:ppu_)?func_)[0-9A-Fa-f]{8}", s))
    report["missing_generated_functions"] = missing
    if missing:
        report["result"] = "FAIL"
        save()
        return 1
    archive = output / "libbces_support.a"
    subprocess.run(["xcrun", "libtool", "-static", "-o", str(archive), *[u["object"] for u in report["units"]]], env=env, check=True)
    report.update(result="PASS", archive=str(archive), archive_sha256=sha(archive))
    save()
    print("PASS: 70 SPU units O2; 13 baseline objects unchanged; O1 preserved", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
