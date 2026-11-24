#!/usr/bin/env python3
"""Compile selected real BCES units for iPhoneOS; this is NOT a game link/boot.

Also prepare separate light/SSAO source overlays with profile-specific image IDs.
The pinned NPUA sources remain intact. At most two compiler processes run.
"""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    profile = json.loads((ROOT / "profiles/BCES01229-01.00.json").read_text())
    report = json.loads((ROOT / "out/bces-analysis.json").read_text())
    if report["profile"] != profile["name"] or report["ELF"]["sha256"] != profile["elf_sha256"]:
        raise SystemExit("Run analyze_bces.py on the identified input first")
    port = ROOT / "upstream/infamous2-recomp"
    runtime = port / "ps3recomp-fork"
    lock = json.loads((ROOT / "sources.lock.json").read_text())
    commit = subprocess.check_output(["git", "-C", str(port), "rev-parse", "HEAD"], text=True).strip()
    if commit != lock["port"]["commit"]:
        raise SystemExit("Port revision differs from sources.lock.json")
    work = ROOT / "build/bces01229"
    output = work / "compile-checks/iphoneos"
    output.mkdir(parents=True, exist_ok=True)
    overlays = []
    for hook in profile["spu_hooks"]:
        source = port / ("infamous2-lle/gpu_" + hook["name"] + ".c")
        original = subprocess.check_output(["git", "-C", str(port), "show", "HEAD:" + str(source.relative_to(port))])
        if original != source.read_bytes():
            raise SystemExit("Pinned title hook has local edits; refusing to derive overlay")
        macro = hook["name"].upper() + "_JOB_IMAGE"
        old = f'#define {macro} {hook["reference_image_id"]}'
        new = f'#define {macro} {hook["image_id"]}'
        text = original.decode()
        if text.count(old) != 1:
            raise SystemExit("Expected image binding not found: " + macro)
        destination = output / source.name
        destination.write_text(text.replace(old, new, 1))
        overlays.append({"source": str(source), "overlay": str(destination), "macro": macro,
                         "reference_image": hook["reference_image_id"], "BCES_image": hook["image_id"]})
    env = dict(os.environ)
    env.setdefault("DEVELOPER_DIR", "/Applications/Xcode.app/Contents/Developer")
    sdk = subprocess.check_output(["xcrun", "--sdk", "iphoneos", "--show-sdk-path"], env=env, text=True).strip()
    generated = sorted((work / "recompiled").glob("ppu_recomp_*.cpp"))
    if not generated or not (work / "recompiled/ppu_recomp.h").exists():
        raise SystemExit("Generate the full BCES PPU source set first")
    units = [generated[0], generated[-1]]
    units += [work / "spu" / h["module"] / "spu_recomp.c" for h in profile["spu_hooks"]]
    units += [Path(o["overlay"]) for o in overlays]

    def compile_one(index, source):
        obj = output / f'{index:02}_{source.stem}.o'
        log = output / f'{index:02}_{source.stem}.log'
        cpp = source.suffix == ".cpp"
        command = ["xcrun", "--sdk", "iphoneos", "clang++" if cpp else "clang",
                   "-target", "arm64-apple-ios17.0", "-isysroot", sdk,
                   "-std=c++20" if cpp else "-std=c17", "-O1", "-fno-strict-aliasing",
                   "-fwrapv", "-ffp-contract=off", "-DSPU_USE_DISPATCH_MT",
                   "-I" + str(runtime / "include"), "-I" + str(runtime / "runtime/spu"),
                   "-I" + str(runtime / "runtime/ppu"), "-I" + str(port / "infamous2-lle"),
                   "-I" + str(runtime / "libs/video"), "-c", str(source), "-o", str(obj)]
        with log.open("w") as stream:
            rc = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT).returncode
        platform = ""
        if rc == 0:
            platform = subprocess.check_output(["xcrun", "vtool", "-show-build", str(obj)], env=env, text=True)
        return {"source": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "object": str(obj), "log": str(log), "returncode": rc,
                "platform_IOS": "platform IOS\n" in platform,
                "command": command}

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda pair: compile_one(*pair), enumerate(units)))
    passed = all(r["returncode"] == 0 and r["platform_IOS"] for r in results)
    summary = {"result": "PASS" if passed else "FAIL", "profile": profile["name"],
               "compiler_jobs": 2, "PPU_source_chunks_generated": len(generated),
               "PPU_chunks_compiled": sum(r["returncode"] == 0 for r in results[:2]),
               "SPU_jobs_compiled": sum(r["returncode"] == 0 for r in results[2:4]),
               "hook_sources_compiled": sum(r["returncode"] == 0 for r in results[4:]),
               "game_linked": False, "game_run": False, "overlays": overlays, "units": results}
    (ROOT / "out/bces-ios-compile-checks.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"result": summary["result"], "units": [{"source": r["source"], "returncode": r["returncode"],
                      "platform_IOS": r["platform_IOS"], "log": r["log"]} for r in results],
                      "game_linked": False, "game_run": False}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
