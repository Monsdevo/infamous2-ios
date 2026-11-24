#!/usr/bin/env python3
"""Compile every generated BCES SPU and firmware TU; no title PPU/game link.

One SDK per invocation, at most two compiler processes. The output is a local
static archive. Generated-function references are checked across all objects;
external runtime references deliberately remain for later executable linking.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", choices=("iphoneos", "macosx"), default="iphoneos")
    parser.add_argument("--resume", action="store_true", help="reuse unchanged successful objects recorded in the previous report")
    args = parser.parse_args()
    work = ROOT / "build/bces01229"
    prep = json.loads((ROOT / "out/bces-spu-preparation.json").read_text())
    if not prep["generated"]:
        raise SystemExit("Run prepare_bces_spu.py first")
    units = sorted((work / "spu").glob("*/spu_recomp.c"))
    units += sorted((work / "spu").glob("*_register.c"))
    units += [work / "spu/spu_workloads.c"]
    units += sorted((work / "lle").glob("*/*.cpp"))
    units += sorted((work / "lle_spu").glob("*/spu_recomp.c"))
    units += [work / "lle_spu/libsre_spu_register.c", work / "title/stubs.cpp"]
    if len(units) != 83:
        raise SystemExit(f"Expected 83 bounded support units, found {len(units)}; inspect generation inventory")
    port = ROOT / "upstream/infamous2-recomp"
    runtime = port / "ps3recomp-fork"
    env = dict(os.environ, DEVELOPER_DIR="/Applications/Xcode.app/Contents/Developer")
    sdk = subprocess.check_output(["xcrun", "--sdk", args.sdk, "--show-sdk-path"], env=env, text=True).strip()
    target = "arm64-apple-ios17.0" if args.sdk == "iphoneos" else "arm64-apple-macos14.0"
    platform = "IOS" if args.sdk == "iphoneos" else "MACOS"
    output = work / "support-compile" / args.sdk
    output.mkdir(parents=True, exist_ok=True)
    report_path = ROOT / f"out/bces-support-compile-{args.sdk}.json"
    header_hash = hashlib.sha256()
    headers = set(runtime.joinpath("include").rglob("*.h")) | set(runtime.joinpath("runtime").rglob("*.h"))
    headers |= set(work.joinpath("spu").rglob("*.h")) | set(work.joinpath("lle").rglob("*.h"))
    headers |= set(work.joinpath("lle_spu").rglob("*.h"))
    for header in sorted(headers):
        header_hash.update(str(header).encode())
        header_hash.update(header.read_bytes())
    header_hash.update((ROOT / "sources.lock.json").read_bytes())
    header_hash.update(subprocess.check_output(["xcrun", "--sdk", args.sdk, "clang", "--version"], env=env))
    cache_identity = header_hash.hexdigest()
    previous = {}
    if args.resume and report_path.exists():
        old_report = json.loads(report_path.read_text())
        if old_report.get("cache_identity") == cache_identity:
            previous = {r["source"]: r for r in old_report["units"]}

    def compile_one(pair):
        index, source = pair
        obj = output / f"{index:02}_{source.parent.name}_{source.stem}.o"
        log = obj.with_suffix(".log")
        cpp = source.suffix == ".cpp"
        cmd = ["xcrun", "--sdk", args.sdk, "clang++" if cpp else "clang", "-target", target,
               "-isysroot", sdk, "-std=c++20" if cpp else "-std=c17", "-O1", "-fno-strict-aliasing",
               "-fwrapv", "-ffp-contract=off", "-DSPU_USE_DISPATCH_MT", "-I" + str(runtime / "include"),
               "-I" + str(runtime / "runtime/spu"), "-I" + str(runtime / "runtime/ppu"),
               "-I" + str(runtime / "libs/video"), "-I" + str(port / "infamous2-lle"),
               "-c", str(source), "-o", str(obj)]
        if source.name.endswith("_module.cpp"):
            cmd += ["-I" + str(runtime / "runtime/prx")]
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        prior = previous.get(str(source), {})
        if (prior.get("returncode") == 0 and prior.get("sha256") == source_hash and prior.get("command") == cmd
                and obj.exists() and prior.get("object_sha256") == hashlib.sha256(obj.read_bytes()).hexdigest()):
            build = subprocess.check_output(["xcrun", "vtool", "-show-build", str(obj)], env=env, text=True)
            if f"platform {platform}\n" in build:
                return {**prior, "cached": True, "object_sha256": hashlib.sha256(obj.read_bytes()).hexdigest()}
        with log.open("w") as stream:
            rc = subprocess.run(cmd, env=env, stdout=stream, stderr=subprocess.STDOUT).returncode
        build = ""
        if rc == 0:
            build = subprocess.check_output(["xcrun", "vtool", "-show-build", str(obj)], env=env, text=True)
        print(f"{index + 1}/{len(units)} {source.parent.name}/{source.name}: {rc}", flush=True)
        return {"source": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "object": str(obj), "returncode": rc, "platform_verified": f"platform {platform}\n" in build,
                "object_sha256": hashlib.sha256(obj.read_bytes()).hexdigest() if rc == 0 else None,
                "log": str(log), "command": cmd}

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(compile_one, enumerate(units)))
    passed = all(r["returncode"] == 0 and r["platform_verified"] for r in results)
    missing = []
    archive = None
    if passed:
        defined, undefined = set(), set()
        symbols = subprocess.check_output(["xcrun", "nm", "-g", *[r["object"] for r in results]], env=env, text=True)
        for line in symbols.splitlines():
            parts = line.split()
            if len(parts) >= 2 and len(parts[-2]) == 1:
                (undefined if parts[-2] == "U" else defined).add(parts[-1])
        missing = sorted(s for s in undefined - defined if re.search(r"(?:spu_func_|_(?:ppu_)?func_)[0-9A-Fa-f]{8}", s))
        passed = not missing
        archive = output / "libbces_support.a"
        subprocess.run(["xcrun", "libtool", "-static", "-o", str(archive), *[r["object"] for r in results]],
                       env=env, check=True, stdout=subprocess.DEVNULL)
    summary = {"result": "PASS" if passed else "FAIL", "sdk": args.sdk, "compiler_jobs": 2,
               "cache_identity": cache_identity,
               "units": results, "missing_generated_functions": missing, "archive": str(archive) if archive else None,
               "title_PPU_compiled_here": False, "game_linked": False, "game_run": False, "game_frames": 0}
    report_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"result": summary["result"], "units": len(results),
                      "missing_generated_functions": missing, "game_run": False}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
