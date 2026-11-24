#!/usr/bin/env python3
"""Validate BCES-specific mappings, generate SPU sources without editing pins.

Bounds only limit instruction generation; wrapped ELFs retain all data bytes.
Static checks cannot prove all dynamic branch targets or runtime correctness.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

from check_inputs import elf_facts

ROOT = Path(__file__).resolve().parents[1]


def checked_elf(path, profile):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != profile["elf_sha256"]:
        raise ValueError("BCES ELF identity mismatch")
    segments = elf_facts(path)["load_segments"]

    def at(va, size):
        for s in segments:
            offset = va - s["va"]
            if 0 <= offset and offset + size <= s["file_bytes"]:
                return data[s["file_offset"] + offset:s["file_offset"] + offset + size]
        raise ValueError(f"Unmapped guest range {va:#x}+{size:#x}")
    return data, at


def validate_wws(at, wws, imports):
    def word(va):
        return struct.unpack(">I", at(va, 4))[0]
    address = int(wws["guest_va"], 0)
    if word(int(wws["pointer_slot"], 0)) != address or word(int(wws["size_slot"], 0)) != wws["raw_bytes"]:
        raise ValueError("WWS TOC pointer/size mismatch")
    # Getter opcodes include TOC-relative loads and align-up to 128 bytes.
    expected = {0x505fe8: 0x80628854, 0x505fec: 0x4e800020,
                0x505ff0: 0x80628858, 0x505ff4: 0x3863007f,
                0x505ff8: 0x54630030, 0x505ffc: 0x4e800020,
                0x504ff8: 0x7c791b78, 0x50502c: 0x78670020, 0x505034: 0x7b260020}
    calls = {0x504ff0: 0x505fe8, 0x504ffc: 0x505ff0, 0x505050: 0x6e95b0}
    for va, opcode in expected.items():
        if word(va) != opcode:
            raise ValueError(f"WWS calling convention changed at {va:#x}")
    for va, target in calls.items():
        opcode = word(va)
        delta = opcode & 0x03fffffc
        if delta & 0x02000000:
            delta -= 0x04000000
        if opcode & 0xfc000003 != 0x48000001 or va + delta != target:
            raise ValueError(f"WWS call target mismatch at {va:#x}")
    nid = int(wws["spurs_initialize_nid"], 0)
    stub = int(wws["spurs_initialize_stub"], 0)
    match = [i for i in imports if int(str(i["nid"]), 0) == nid and int(str(i["stub"]), 0) == stub]
    if len(match) != 1:
        raise ValueError("WWS destination is not the expected SPURS import")
    if (wws["raw_bytes"] + 127) & ~127 != wws["dma_bytes"]:
        raise ValueError("WWS padded span mismatch")
    raw = at(address, wws["dma_bytes"])
    if any(struct.unpack_from(">I", raw, k)[0] >> 25 != 0x21 for k in range(0, 16, 4)):
        raise ValueError("WWS four-ILA signature missing")
    return raw, {"TOC_pointer_size": True, "getters_and_call_arguments": True,
                 "SPURS_import": match[0], "sha256": hashlib.sha256(raw).hexdigest(),
                 "runtime_validated": False}


def validate_boundary(raw, item, toolkit):
    from spu_disasm import spu_decode
    from find_spu_functions import collect_branch_targets
    import lift_jobmods as lj
    if hashlib.sha256(raw).hexdigest() != item["sha256"]:
        raise ValueError("Job identity mismatch: " + item["module"])
    end = int(item["code_end"], 0)
    limit = end - lj.BASE
    if limit <= 0x30 or limit % 4 or limit >= len(raw):
        raise ValueError("Invalid code/data boundary")
    if raw[limit:limit + 16].hex() != item["tail_prefix"]:
        raise ValueError("Code/data tail signature mismatch")
    instructions = [spu_decode(struct.unpack_from(">I", raw, k)[0], lj.BASE + k) for k in range(0x30, limit, 4)]
    targets = collect_branch_targets(instructions)
    # Tables may be stored in rodata after the code boundary. Keep the full
    # raw image available to the manual-link/switch-table recognizers.
    manual = lj.manual_link_targets(raw)
    switches = lj.switch_table_targets(raw)
    tail_targets = sorted(t for t in targets | set(manual) | set(switches) if end <= t < lj.BASE + len(raw))
    if tail_targets:
        raise ValueError("Code targets proposed data tail: " + repr(tail_targets))
    return {**item, "direct_targets_into_tail": [], "manual_targets_into_tail": [],
            "external_direct_targets": [hex(t) for t in sorted(targets) if not lj.BASE <= t < end],
            "last_instructions": [str(i) for i in instructions[-8:]],
            "data_preserved": True, "indirect_targets_exhaustively_proven": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    profile = json.loads((ROOT / "profiles/BCES01229-01.00.json").read_text())
    spu = json.loads((ROOT / "profiles/BCES01229-spu.json").read_text())
    toolkit = ROOT / "upstream/infamous2-recomp/ps3recomp-fork/tools"
    sys.path.insert(0, str(toolkit))
    work = ROOT / "build/bces01229"
    eboot = ROOT / "data/inspection/bces01229/selected/PS3_GAME/USRDIR/EBOOT.elf"
    data, at = checked_elf(eboot, profile)
    imports = json.loads((work / "analysis/EBOOT.imports.json").read_text())
    raw, evidence = validate_wws(at, spu["wws"], imports)
    checks = [validate_boundary((work / "spu/jobmods" / (b["module"] + ".bin")).read_bytes(), b, toolkit)
              for b in spu["code_boundaries"]]
    # The title extractors use a constant VA offset. Check every actual range
    # against PT_LOAD before allowing that convention for this exact ELF.
    analysis = json.loads((ROOT / "out/bces-analysis.json").read_text())
    for blob in analysis["datamods"] + analysis["relocmods"]:
        off, va = int(blob["file_offset"], 0), int(blob["guest_va"], 0)
        if va != off + 0x10000 or at(va, blob["bytes"]) != data[off:off + blob["bytes"]]:
            raise ValueError("SPU blob file/guest mapping mismatch")
    report = {"profile": profile["name"], "wws": {**spu["wws"], **evidence}, "boundaries": checks,
              "generated": False, "game_boot_ready": False}
    if not args.validate_only:
        def run(script, arguments, label):
            print("Generating", label, flush=True)
            with (work / "analysis" / (label + ".log")).open("w") as log:
                subprocess.run([sys.executable, str(script), *map(str, arguments)], check=True,
                               stdout=log, stderr=subprocess.STDOUT)

        from wrap_spu_elf import wrap
        name = "wwsjob_pm_at_00887100"
        images = work / "spu/images"
        (images / (name + ".elf")).write_bytes(wrap(raw, base=0xa00, entry=0xa00))
        run(toolkit / "build_spu_workloads.py", ["--images", images, "--lifted", work / "spu",
            "--out", work / "spu/spu_workloads.c", "--register-fn", "infamous2_spu_register_all",
            "--constructor", "--relift", "--title", "infamous2", "--eboot", eboot,
            "--extra-funcs", name + "=0xA2C"], "spu-workloads")
        # Local configuration of the pinned generator; never alter its file.
        import lift_jobmods as lj
        lj.CODE_END.update({b["module"]: int(b["code_end"], 0) for b in checks})
        old_argv = sys.argv
        sys.argv = [str(toolkit / "lift_jobmods.py"), "--jobmods", str(work / "spu/jobmods"),
                    "--out", str(work / "spu"), "--register", str(work / "spu/jobmods_register.c"),
                    "--symbol-prefix", "infamous2"]
        try:
            lj.main()
        finally:
            sys.argv = old_argv
        manifest = json.loads((work / "spu/jobmods_manifest.json").read_text())
        if len(manifest) != len(analysis["jobmods"]) or sum(m["unsupported"] for m in manifest):
            raise ValueError("Incomplete/unsupported job generation")
        for boundary in checks:
            text = (work / "spu" / boundary["module"] / "spu_recomp.c").read_text()
            address = int(boundary["retained_tail_entry"], 0)
            if f"0x{address:X}" not in text and f"{address:08X}" not in text:
                raise ValueError("Real code before the boundary was lost")
        for tool in ("lift_datamods.py", "lift_relocmods.py"):
            run(ROOT / "upstream/infamous2-recomp/infamous2-lle/tools" / tool,
                [eboot, "--out", work / "spu", "--va-offset", "0x10000"], tool[:-3])
        # Make jobmod includes independent of the generated directory's depth.
        for path in (work / "spu").glob("jobmod_*/spu_recomp.*"):
            path.write_text(re.sub(r'#include "(?:\.\./)+runtime/spu/', '#include "', path.read_text()))
        source = ROOT / "upstream/infamous2-recomp/infamous2-lle/stubs.cpp"
        pinned = subprocess.check_output(["git", "-C", str(source.parents[1]), "show", "HEAD:infamous2-lle/stubs.cpp"])
        if source.read_bytes() != pinned:
            raise ValueError("Pinned stubs have local edits")
        old = "#define WWSJOB_PM_EA    0x008E5B00u"
        text = pinned.decode()
        if text.count(old) != 1:
            raise ValueError("Expected WWS binding missing")
        overlay = work / "title/stubs.cpp"
        overlay.parent.mkdir(exist_ok=True)
        text = text.replace("0x008E5B00", "0x00887100").replace("wwsjob_pm_at_008E5B00", name)
        overlay.write_text(text)
        report.update(generated=True, jobmods=len(manifest), jobmods_unsupported=0,
                      datamods=len(analysis["datamods"]), relocmods=len(analysis["relocmods"]),
                      stubs_overlay=str(overlay))
    if report["generated"]:
        report["remaining_unsupported"] = []
        for source in sorted((work / "spu").glob("*/spu_recomp.c")):
            text = source.read_text()
            entries = re.findall(r'spu_unsupported\(0x([0-9A-F]+), "([^"]+)"\)', text)
            if entries:
                report["remaining_unsupported"].append({"module": source.parent.name,
                    "count": len(entries), "entries": [{"lsa": "0x" + a.lower(), "instruction": i} for a, i in entries],
                    "classified_safe": False})
        report["remaining_unsupported_count"] = sum(m["count"] for m in report["remaining_unsupported"])
    report_name = "bces-spu-validation.json" if args.validate_only else "bces-spu-preparation.json"
    (ROOT / "out" / report_name).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("profile", "generated", "game_boot_ready")}))


if __name__ == "__main__":
    main()
