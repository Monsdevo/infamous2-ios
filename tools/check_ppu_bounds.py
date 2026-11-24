#!/usr/bin/env python3
"""Reproduce raw PRX lower-bound failure with original, tiny PPC test bytes."""
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

from prepare_firmware_lle import ROOT, bounded_lifter


def main():
    toolkit = ROOT / "upstream/infamous2-recomp/ps3recomp-fork/tools"
    overlay = bounded_lifter(toolkit)
    work = ROOT / "build/bces01229/bounds-test"
    work.mkdir(parents=True, exist_ok=True)
    base = 0x30000000
    raw = work / "original-test.bin"
    # b base-0x1000; blr. The target is not in this synthetic image.
    raw.write_bytes(struct.pack(">II", 0x4bfff000, 0x4e800020))
    functions = work / "functions.json"
    functions.write_text(json.dumps([{"start": hex(base), "end": hex(base + 8)}]))
    reports = []
    for name, tool in (("pinned", toolkit / "ppu_lifter.py"), ("bounded", overlay)):
        out = work / name
        cmd = [sys.executable, str(tool), str(raw), "--raw", "--base", hex(base),
               "--code-end", hex(base + 8), "--functions", str(functions), "--jobs", "1", "-o", str(out)]
        with (work / (name + ".log")).open("w") as log:
            subprocess.run(cmd, check=True, env=dict(os.environ, PYTHONPATH=str(toolkit)),
                           stdout=log, stderr=subprocess.STDOUT)
        addresses = []
        for source in sorted(out.glob("*.cpp")) + sorted(out.glob("*.c")):
            addresses += [int(a, 16) for a in re.findall(r'\{ 0x([0-9A-F]+)ULL, func_', source.read_text())]
        bad = [hex(a) for a in addresses if not base <= a < base + 8]
        reports.append({"tool": name, "table_entries": len(addresses), "out_of_image": bad})
    if not reports[0]["out_of_image"] or reports[1]["out_of_image"] or reports[1]["table_entries"] != 1:
        raise AssertionError("Boundary repair regression")
    profile = json.loads((ROOT / "profiles/firmware-4.93.json").read_text())
    firmware = []
    for module in profile["modules"]:
        name, start = module["name"], int(module["base"], 0)
        directory = ROOT / "build/bces01229/lle" / name
        size = len((directory / "meta" / (name + "_image.bin")).read_bytes())
        entries = []
        for source in directory.glob("*_recomp_*.cpp"):
            entries += [int(a, 16) for a in re.findall(r'\{ 0x([0-9A-F]+)ULL, '+name+r'_func_', source.read_text())]
        if not entries or any(not start <= a < start + size for a in entries):
            raise AssertionError("Firmware still registers an out-of-image function: " + name)
        firmware.append({"module": name, "entries": len(entries), "out_of_image": 0})
    report = {"result": "PASS", "regression": reports, "firmware_tables": firmware,
              "pinned_tool_modified": False, "overlay_sha256": hashlib.sha256(overlay.read_bytes()).hexdigest()}
    (ROOT / "out/ppu-bounds-validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
