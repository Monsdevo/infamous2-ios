#!/usr/bin/env python3
"""Adversarial checks for BCES address and code/data boundary guards."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys

from prepare_bces_spu import ROOT, checked_elf, validate_boundary, validate_wws


def main():
    toolkit = ROOT / "upstream/infamous2-recomp/ps3recomp-fork/tools"
    sys.path.insert(0, str(toolkit))
    profile = json.loads((ROOT / "profiles/BCES01229-01.00.json").read_text())
    spu = json.loads((ROOT / "profiles/BCES01229-spu.json").read_text())
    _, at = checked_elf(ROOT / "data/inspection/bces01229/selected/PS3_GAME/USRDIR/EBOOT.elf", profile)
    imports = json.loads((ROOT / "build/bces01229/analysis/EBOOT.imports.json").read_text())
    results = []

    def rejects(name, fn):
        try:
            fn()
        except ValueError as error:
            results.append({"check": name, "result": "PASS", "rejection": str(error)})
        else:
            raise AssertionError("Unsafe input accepted: " + name)

    validate_wws(at, spu["wws"], imports)
    results.append({"check": "actual WWS mapping", "result": "PASS"})
    old = copy.deepcopy(spu["wws"])
    old["guest_va"] = "0x8e5b00"
    rejects("NPUA policy address on BCES", lambda: validate_wws(at, old, imports))
    wrong = copy.deepcopy(imports)
    for record in wrong:
        if int(str(record["nid"]), 0) == 0xefeb2679:
            record["nid"] = "0x12345678"
    rejects("wrong SPURS import at same stub", lambda: validate_wws(at, spu["wws"], wrong))

    def bad_call(va, size):
        if va == 0x505050 and size == 4:
            return struct.pack(">I", 0x48000001 | ((0x6e9530 - va) & 0x03fffffc))
        return at(va, size)
    rejects("call redirected to other SPURS function", lambda: validate_wws(bad_call, spu["wws"], imports))
    rejects("unmapped policy range", lambda: at(0xe0000000, 11904))
    for item in spu["code_boundaries"]:
        raw = (ROOT / "build/bces01229/spu/jobmods" / (item["module"] + ".bin")).read_bytes()
        validate_boundary(raw, item, toolkit)
        results.append({"check": item["module"] + " actual boundary", "result": "PASS"})
        altered = bytearray(raw)
        # Synthesize a real direct call into the proposed data tail, and update
        # its checksum so this exercises the flow guard, not just identity.
        start, target = 0x4030, int(item["code_end"], 0)
        struct.pack_into(">I", altered, 0x30, 0x33000000 | (((target - start) // 4 & 0xffff) << 7))
        changed = {**item, "sha256": hashlib.sha256(altered).hexdigest()}
        rejects(item["module"] + " call into data", lambda: validate_boundary(altered, changed, toolkit))
    item = copy.deepcopy(spu["code_boundaries"][0])
    raw = (ROOT / "build/bces01229/spu/jobmods" / (item["module"] + ".bin")).read_bytes()
    item.update(code_end="0xdb80", tail_prefix=raw[0x9b80:0x9b90].hex())
    rejects("truncation after earlier return loses real helpers", lambda: validate_boundary(raw, item, toolkit))
    report = {"result": "PASS", "checks": results, "game_run": False}
    (ROOT / "out/bces-static-validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS: {len(results)} checks, including bad address/import/call and data-tail branches")


if __name__ == "__main__":
    main()
