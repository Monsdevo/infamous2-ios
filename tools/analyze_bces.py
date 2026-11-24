#!/usr/bin/env python3
"""Inventory the identified BCES input with pinned tools; never boot guest code.

Generated manifests and extracted game bytes stay under build/ or out/.
The profile records known inputs and unresolved mappings, not a playable target.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys

from check_inputs import elf_facts, parse_sfo

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def section_facts(data):
    offset = struct.unpack_from(">Q", data, 40)[0]
    stride, count = struct.unpack_from(">HH", data, 58)
    if stride < 64 or count > 4096 or offset + stride * count > len(data):
        raise ValueError("Invalid ELF section table")
    sections = []
    for i in range(count):
        _, kind, flags, va, file_offset, size, _, _, _, _ = struct.unpack_from(">II4QII2Q", data, offset + i * stride)
        if kind != 8 and file_offset + size > len(data):
            raise ValueError("Section exceeds input file")
        sections.append({"index": i, "type": kind, "flags": flags, "va": va,
                         "file_offset": file_offset, "bytes": size})
    return sections


def file_to_guest(offset, size, segments):
    mappings = [s["va"] + offset - s["file_offset"] for s in segments
                if s["file_offset"] <= offset and offset + size <= s["file_offset"] + s["file_bytes"]]
    if len(mappings) != 1:
        raise ValueError(f"Ambiguous/unmapped file range {offset:#x}+{size:#x}")
    return mappings[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--sfo", type=Path, required=True)
    parser.add_argument("--profile", type=Path, default=ROOT / "profiles/BCES01229-01.00.json")
    parser.add_argument("--work", type=Path, default=ROOT / "build/bces01229")
    parser.add_argument("--report", type=Path, default=ROOT / "out/bces-analysis.json")
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text())
    data = args.elf.read_bytes()
    elf = elf_facts(args.elf)
    sfo = parse_sfo(args.sfo.read_bytes())
    if elf["sha256"] != profile["elf_sha256"]:
        raise SystemExit("ELF identity mismatch; refusing to apply this BCES profile")
    if (sfo.get("TITLE_ID"), sfo.get("APP_VER")) != (profile["title_id"], profile["app_version"]):
        raise SystemExit("SFO identity mismatch")
    if hashlib.sha256(args.sfo.read_bytes()).hexdigest() != profile["sfo_sha256"]:
        raise SystemExit("SFO checksum mismatch")
    sections = section_facts(data)
    code_end = max(s["va"] + s["bytes"] for s in sections if s["flags"] & 6 == 6 and s["bytes"])
    if code_end != int(profile["code_end_exclusive"], 0):
        raise SystemExit("Executable section boundary mismatch")
    port = ROOT / "upstream/infamous2-recomp"
    toolkit = port / "ps3recomp-fork/tools"
    work = args.work.resolve()
    (work / "analysis").mkdir(parents=True, exist_ok=True)
    commands = [
        (toolkit / "ppu_loader.py", [str(args.elf.resolve()), "--output", str(work / "analysis")]),
        (toolkit / "extract_spu_images.py", [str(args.elf.resolve()), "-o", str(work / "spu/images")]),
        (port / "infamous2-lle/tools/extract_eboot_jobmods.py", [str(args.elf.resolve()), "--out", str(work / "spu/jobmods")]),
    ]
    for script, options in commands:
        with (work / "analysis" / (script.stem + ".log")).open("w") as log:
            subprocess.run([sys.executable, str(script), *options], check=True, stdout=log, stderr=subprocess.STDOUT)
    sys.path.insert(0, str(toolkit))
    job_tool = load_module("bces_job_tool", toolkit / "lift_jobmods.py")
    datamod = load_module("bces_datamod", port / "infamous2-lle/tools/lift_datamods.py")
    relocmod = load_module("bces_relocmod", port / "infamous2-lle/tools/lift_relocmods.py")
    jobs = []
    for i, path in enumerate(sorted((work / "spu/jobmods").glob("*.bin"))):
        raw = path.read_bytes()
        sha1 = hashlib.sha1(raw).hexdigest()
        if path.stem.split("_")[1] != sha1[:12]:
            raise ValueError("Extracted job filename/hash mismatch")
        file_offset = data.find(raw)
        if file_offset < 0:
            raise ValueError("Extracted job not found in original ELF")
        jobs.append({"module": path.stem, "image_id": job_tool.JOBMOD_IMAGE_BASE + i,
                     "bytes": len(raw), "sha1": sha1, "sha256": hashlib.sha256(raw).hexdigest(),
                     "file_offset": hex(file_offset), "guest_va": hex(file_to_guest(file_offset, len(raw), elf["load_segments"])),
                     "entry_lsa": hex(0x4000 + struct.unpack_from(">I", raw, 0x10)[0])})
    hooks = []
    for hook in profile["spu_hooks"]:
        found = next((j for j in jobs if j["module"] == hook["module"]), None)
        if found is None or found["image_id"] != hook["image_id"] or found["entry_lsa"] != hook["entry_lsa"]:
            raise ValueError("Critical job/profile mapping mismatch: " + hook["name"])
        hooks.append({**hook, "content_prefix_matches_reference_symbol": True,
                      "full_reference_bytes_available": False, "runtime_validated": False})
    datamods = []
    for offset, code_offset, size, code_end_offset in datamod.find_blobs(data):
        va = file_to_guest(offset, size, elf["load_segments"])
        datamods.append({"file_offset": hex(offset), "guest_va": hex(va), "bytes": size,
                         "code_offset": hex(code_offset), "code_end_offset": hex(code_end_offset),
                         "sha256": hashlib.sha256(data[offset:offset + size]).hexdigest()})
    relocs = [{"file_offset": hex(offset), "guest_va": hex(file_to_guest(offset, span, elf["load_segments"])),
               "bytes": span, "sha256": hashlib.sha256(data[offset:offset + span]).hexdigest()}
              for offset, span in relocmod.find_blobs(data)]
    prefix = args.elf.stem
    loader = json.loads((work / "analysis" / (prefix + ".loader.json")).read_text())
    imports = json.loads((work / "analysis" / (prefix + ".imports.json")).read_text())
    report = {"profile": profile["name"], "status": "analysis_pass", "game_boot_ready": False,
              "full_archive_integrity_verified": False, "ELF": elf, "loader": loader,
              "executable_section_end": hex(code_end), "sections": sections, "import_count": len(imports),
              "embedded_SPU_ELFs": [p.name for p in sorted((work / "spu/images").glob("spu_*.elf"))],
              "jobmods": jobs, "critical_hooks": hooks, "datamods": datamods, "relocmods": relocs,
              "unresolved": ["WWS runtime validation (static mapping in the SPU profile)", "firmware runtime compatibility",
                             "full SPU build/link", "full archive and asset integrity", "game runtime/boot validation"]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "profile": profile["name"],
                      "OPD_functions": loader["function_count"], "imports": len(imports), "code_end": hex(code_end),
                      "jobmods": len(jobs), "datamods": len(datamods), "relocmods": len(relocs),
                      "hooks": hooks, "game_boot_ready": False}, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
