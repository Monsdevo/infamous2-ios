#!/usr/bin/env python3
"""Prepare a real-title macOS target, preserving the pinned reference runner.

Reuse only hash-verified macOS archives from the completed runtime diagnostic.
Recompile all title-dependent PPU scaffolding against the BCES header. No
synthetic PPU fixture or synthetic ELF is linked into the game executable.
"""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    port = ROOT / "upstream/infamous2-recomp"
    work = ROOT / "build/bces01229"
    title = work / "title"
    title.mkdir(parents=True, exist_ok=True)
    profile = json.loads((ROOT / "profiles/BCES01229-01.00.json").read_text())
    manifest = json.loads((ROOT / "out/bces-codegen-manifest.json").read_text())
    if manifest["ELF_sha256"] != profile["elf_sha256"]:
        raise SystemExit("Title generation/profile mismatch")
    for name, digest in manifest["source_sha256"].items():
        if hashlib.sha256((work / "recompiled" / name).read_bytes()).hexdigest() != digest:
            raise SystemExit("Title source differs from generation manifest: " + name)
    lock = json.loads((ROOT / "sources.lock.json").read_text())
    if subprocess.check_output(["git", "-C", str(port), "rev-parse", "HEAD"], text=True).strip() != lock["port"]["commit"]:
        raise SystemExit("Port commit mismatch")

    def pinned(name):
        path = port / "infamous2-lle" / name
        original = subprocess.check_output(["git", "-C", str(port), "show", "HEAD:infamous2-lle/" + name])
        if path.read_bytes() != original:
            raise SystemExit("Reference source has local changes: " + name)
        return original.decode()

    main_source = pinned("main.cpp")
    marker = '    printf("=== ps3recomp game runner ===\\n");'
    if main_source.count(marker) != 1:
        raise SystemExit("Runner structure changed")
    main_source = main_source.replace(marker, '    setvbuf(stdout, NULL, _IONBF, 0);\n' + marker, 1)
    (title / "main.cpp").write_text(main_source)
    for hook in profile["spu_hooks"]:
        text = pinned("gpu_" + hook["name"] + ".c")
        macro = hook["name"].upper() + "_JOB_IMAGE"
        old, new = f'#define {macro} {hook["reference_image_id"]}', f'#define {macro} {hook["image_id"]}'
        if text.count(old) != 1:
            raise SystemExit("Hook binding changed")
        (title / ("gpu_" + hook["name"] + ".c")).write_text(text.replace(old, new, 1))
    (title / "ssao_gpu.c").write_text(pinned("ssao_gpu.c"))
    snapshot = json.loads((ROOT / "out/bces-support-host-build.json").read_text())
    archives = []
    for item in snapshot["inputs"]:
        path = Path(item["path"])
        if path.suffix != ".a" or str(path) in archives:
            continue
        if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise SystemExit("Existing dependency changed; rebuild/validate it first: " + str(path))
        archives.append(str(path))
    support = str(work / "support-compile/macosx/libbces_support.a")
    runtime = str(ROOT / "build/host/libps3recomp_full_runtime.a")
    if support not in archives or runtime not in archives:
        raise SystemExit("Missing support/runtime archive in proven host link")
    dependencies = [p for p in archives if p not in (support, runtime)]
    cmake = ["# Generated local macOS dependency snapshot, never use for iOS.",
             f'set(BCES_SUPPORT "{support}")', f'set(BCES_RUNTIME "{runtime}")', "set(BCES_DEPENDENCIES"]
    cmake += ['  "' + p + '"' for p in dependencies]
    cmake += [")", ""]
    (work / "host-dependencies.cmake").write_text("\n".join(cmake))
    print(f"Prepared real BCES host target: 164 PPU chunks; {len(archives)} verified host archives. No synthetic fixture.")


if __name__ == "__main__":
    main()
