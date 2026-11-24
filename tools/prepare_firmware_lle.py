#!/usr/bin/env python3
"""Generate local firmware LLE sources with the pinned tools, one worker.

Does not download/install firmware, alter the toolkit, link or boot a title.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def bounded_lifter(toolkit):
    """Local raw-PRX boundary repair; preserve the pinned shared runtime."""
    source = toolkit / "ppu_lifter.py"
    profile = json.loads((ROOT / "profiles/firmware-4.93.json").read_text())
    if hashlib.sha256(source.read_bytes()).hexdigest() != profile["ppu_lifter_source_sha256"]:
        raise ValueError("Pinned PPU lifter checksum differs")
    text = source.read_text()
    lower = "    lifter.code_hi = args.code_end\n"
    gap = "        for target in sorted(all_refs):\n"
    if text.count(lower) != 1 or text.count(gap) != 1:
        raise ValueError("Pinned lifter layout differs; review boundary repair")
    text = text.replace(lower, "    if args.raw:\n        lifter.code_lo = base_addr\n" + lower, 1)
    text = text.replace(gap, gap + "            if self._outside_code(target):\n                continue\n", 1)
    out = ROOT / "build/bces01229/toolkit/ppu_lifter_bounded.py"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    return out


def main():
    profile = json.loads((ROOT / "profiles/firmware-4.93.json").read_text())
    toolkit = ROOT / "upstream/infamous2-recomp/ps3recomp-fork/tools"
    sys.path.insert(0, str(toolkit))
    from lift_prx import Prx
    lifter = bounded_lifter(toolkit)
    env = dict(os.environ, PYTHONPATH=str(toolkit))
    results = []
    for module in profile["modules"]:
        stem, base = module["name"], int(module["base"], 0)
        source = ROOT / "data/firmware/prx" / (stem + ".prx")
        if hashlib.sha256(source.read_bytes()).hexdigest() != module["sha256"]:
            raise SystemExit("Firmware identity mismatch: " + stem)
        out = ROOT / "build/bces01229/lle" / stem
        meta = out / "meta"
        meta.mkdir(parents=True, exist_ok=True)

        def run(name, arguments):
            cmd = [sys.executable, str(lifter if name == "ppu_lifter.py" else toolkit / name), *map(str, arguments)]
            log = out / (name + ".log")
            print("Generating", stem, name, flush=True)
            with log.open("w") as stream:
                subprocess.run(cmd, check=True, env=env, stdout=stream, stderr=subprocess.STDOUT)
            return {"command": cmd, "log": str(log)}

        commands = [run("lift_prx.py", [source, "--base", hex(base), "--output", meta])]
        exports = json.loads((meta / (stem + "_exports.json")).read_text())
        imports = json.loads((meta / (stem + "_imports.json")).read_text())
        va, size = Prx(str(source)).text_extent()
        args = [meta / (stem + "_image.bin"), "--raw", "--base", hex(base),
                "--toc", exports["toc"], "--code-end", hex(base + va + size),
                "--functions", meta / (stem + "_functions.json"),
                "--symbol-prefix", stem + "_", "--header-name", stem + "_recomp.h",
                "--source-name", stem + "_recomp.c", "--max-chunk-lines", "30000",
                "--jobs", "1", "-o", out]
        stubs = [{"library": lib, "nid": nid, "stub": slot}
                 for lib, entries in imports.items() for nid, slot in entries.items()]
        if stubs:
            path = meta / (stem + "_hle_stubs.json")
            path.write_text(json.dumps(stubs, indent=2) + "\n")
            args += ["--hle-stubs", path]
        commands.append(run("ppu_lifter.py", args))
        commands.append(run("gen_prx_module.py", [meta, "--stem", stem, "--file", stem + ".sprx",
                                                "--prefix", stem + "_", "--out", out / (stem + "_module.cpp")]))
        results.append({**module, "code_end_exclusive": hex(base + va + size), "commands": commands,
                        "sources": [{"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                                    for p in sorted(out.glob("*.cpp"))]})
    report = {"result": "GENERATED", "firmware": profile["version"], "worker_jobs": 1,
              "lifter_overlay": str(lifter), "lifter_overlay_sha256": hashlib.sha256(lifter.read_bytes()).hexdigest(),
              "modules": results, "linked": False, "runtime_validated": False}
    (ROOT / "out/firmware-lle-generation.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Generated three PPU firmware modules; not linked or booted.")


if __name__ == "__main__":
    main()
