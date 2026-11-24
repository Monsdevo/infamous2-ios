#!/usr/bin/env python3
"""Derive one SPU TU from verified O2, retaining original bodies for native hooks.

Only two definition names change. All original calls and registration entries
still refer to the public names supplied by BCESSpuCopy.c, including direct
trampoline transfers that a registry-only hook would miss.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TARGET = "spu_0001_at_0085E400"
NAMES = {"000011C8": "bces_reference_copy_11c8", "00000F94": "bces_reference_copy_0f94"}


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def derive(original):
    result = original
    references = '#include "spu_recomp.h"\n#include "spu_helpers.h"\n'
    for address, reference in NAMES.items():
        signature = f"void {TARGET}_spu_func_{address}(spu_context* ctx) {{"
        if result.count(signature) != 1:
            raise ValueError("Generated definition identity changed: " + address)
        start = original.index(signature)
        end = original.index("\n}\n", start) + 3
        body = original[start:end].replace(signature, f"void {reference}(spu_context* ctx) {{", 1)
        references += body + "\n"
        result = result.replace(signature, f"void {reference}(spu_context* ctx) {{", 1)
    return result, references


def main():
    env = dict(os.environ, DEVELOPER_DIR="/Applications/Xcode.app/Contents/Developer",
               TMPDIR=str(ROOT / "build/tmp"))
    baseline_path = ROOT / "out/bces-support-compile-iphoneos-spu-O2.json"
    baseline = json.loads(baseline_path.read_text())
    if baseline["result"] != "PASS" or baseline["sdk"] != "iphoneos" or len(baseline["units"]) != 83:
        raise SystemExit("Expected verified iPhoneOS O2 archive")
    if sha(baseline["archive"]) != baseline["archive_sha256"]:
        raise SystemExit("O2 archive changed")
    for unit in baseline["units"]:
        if sha(unit["source"]) != unit["sha256"] or sha(unit["object"]) != unit["object_sha256"]:
            raise SystemExit("O2 input changed: " + unit["source"])
    target, = [u for u in baseline["units"] if Path(u["source"]).parent.name == TARGET]
    output = ROOT / "build/bces01229/support-compile/iphoneos-spu-O2-copy"
    output.mkdir(exist_ok=True, parents=True)
    generated, references = derive(Path(target["source"]).read_text())
    source = output / "spu_recomp.c"
    source.write_text(generated)
    (output / "spu_recomp.h").write_bytes(Path(target["source"]).with_suffix(".h").read_bytes())
    (output / "test_reference.c").write_text(references)
    obj = output / Path(target["object"]).name
    cmd = [str(source) if s == target["source"] else str(obj) if s == target["object"] else s for s in target["command"]]
    assert cmd.count("-O2") == 1
    with (output / "compile.log").open("w") as log:
        subprocess.run(cmd, env=env, check=True, stdout=log, stderr=subprocess.STDOUT)
    platform = subprocess.check_output(["xcrun", "vtool", "-show-build", str(obj)], env=env, text=True)
    if "platform IOS\n" not in platform:
        raise SystemExit("Wrong SDK platform")
    units = [{**u, "source": str(source), "sha256": sha(source), "object": str(obj),
              "object_sha256": sha(obj), "command": cmd, "log": str(output / "compile.log")}
             if u is target else u for u in baseline["units"]]
    archive = output / "libbces_support.a"
    subprocess.run(["xcrun", "libtool", "-static", "-o", str(archive), *[u["object"] for u in units]], env=env, check=True)
    report = {"result": "PASS", "sdk": "iphoneos", "variant": "spu-O2-copy", "compiler_jobs": 1,
              "units": units, "archive": str(archive), "archive_sha256": sha(archive),
              "baseline_report_sha256": sha(baseline_path), "original_source": target["source"],
              "original_source_sha256": target["sha256"], "renamed_definitions": NAMES,
              "native_override": str(ROOT / "src/game/BCESSpuCopy.c"),
              "native_override_sha256": sha(ROOT / "src/game/BCESSpuCopy.c"),
              "native_header_sha256": sha(ROOT / "src/game/BCESSpuCopy.h"),
              "unchanged_objects": 82, "game_run": False}
    (ROOT / "out/bces-support-compile-iphoneos-spu-O2-copy.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: one derived SPU object, two reference names; 82 O2 objects unchanged")


if __name__ == "__main__":
    main()
