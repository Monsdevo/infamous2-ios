#!/usr/bin/env python3
"""Symbolicate an Apple cpu_resource report using only a UUID-matched Mach-O.

Tree weights are inclusive. Exclusive weights subtract direct children, never
sum recursive inclusive frames. These sparse samples are not a Time Profiler
trace or a gameplay benchmark; the operator must supply the scene label.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


def verify_uuid(report, dwarf_output):
    expected = json.loads(report.splitlines()[0])["slice_uuid"].upper()
    matches = re.findall(r"UUID: ([0-9A-Fa-f-]+) \(arm64\)", dwarf_output)
    if expected not in [value.upper() for value in matches]:
        raise ValueError(f"Report UUID {expected} does not match arm64 binary")
    return expected


def analyze_tree(report, app):
    sections = report.split("Powerstats for:")
    sections = [s for s in sections[1:] if s.splitlines()[0].strip().startswith(app + " ")]
    if len(sections) != 1:
        raise ValueError("Expected one target Powerstats section")
    section = sections[0].split("Binary Images:")[0]
    nodes, stack = [], []
    for line in section.splitlines():
        match = re.match(r"^( +)(\d+) +(.+?) \[0x[0-9a-fA-F]+\]", line)
        if not match:
            continue  # <e-core> / <Kernel mode> annotate a sample, not a frame.
        indent, weight, name = len(match[1]), int(match[2]), match[3]
        while stack and stack[-1]["indent"] >= indent:
            stack.pop()
        parent = stack[-1] if stack else None
        role = parent["role"] if parent else "other"
        if "spu_exec_thread_proc " in name:
            role = "SPU"
        elif "gameWorker(" in name or "ppu_host_thread_proc " in name:
            role = "PPU"
        elif "frame_clock(" in name:
            role = "renderer"
        node = {"indent": indent, "weight": weight, "children": 0,
                "name": name, "role": role, "root": parent is None}
        if parent:
            parent["children"] += weight
        nodes.append(node)
        stack.append(node)
    roles, exclusive = Counter(), Counter()
    for node in nodes:
        count = node["weight"] - node["children"]
        if count < 0:
            raise ValueError("Inconsistent tree: child weights exceed parent")
        roles[node["role"]] += count
        # Combine PC offsets within a function, leaving system library offsets.
        name = re.sub(r" \(in " + re.escape(app) + r"\) \+ \d+$", "", node["name"])
        exclusive[name] += count
    total = sum(n["weight"] for n in nodes if n["root"])
    if not total or sum(roles.values()) != total:
        raise ValueError("Empty or inconsistent sample tree")
    return {"total_samples": total, "disjoint_role_samples": dict(roles),
            "exclusive_functions": [{"function": name, "samples": count}
                                    for name, count in exclusive.most_common() if count]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--app", default="Infamous2Game")
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.report.read_text()
    uuid = verify_uuid(raw, subprocess.check_output(
        ["xcrun", "dwarfdump", "--uuid", str(args.binary)], text=True))
    pattern = r"\?\?\? \(" + re.escape(args.app) + r" \+ (\d+)\)"
    offsets = sorted(set(re.findall(pattern, raw)), key=int)
    if not offsets:
        raise ValueError("No unresolved application offsets")
    with tempfile.TemporaryDirectory() as temp:
        addresses = Path(temp) / "offsets.txt"
        addresses.write_text("".join(hex(int(x)) + "\n" for x in offsets))
        symbols = subprocess.check_output(["xcrun", "atos", "-arch", "arm64", "-o",
            str(args.binary), "--offset", "-f", str(addresses)], text=True).splitlines()
    if len(symbols) != len(offsets):
        raise ValueError("atos returned a different number of symbols")
    mapping = dict(zip(offsets, symbols))
    annotated = re.sub(pattern, lambda m: mapping[m[1]], raw)
    output = analyze_tree(annotated, args.app)
    output.update({"label": args.label, "uuid": uuid,
        "report": str(args.report.resolve()),
        "report_sha256": hashlib.sha256(args.report.read_bytes()).hexdigest(),
        "binary": str(args.binary.resolve()),
        "binary_sha256": hashlib.sha256(args.binary.read_bytes()).hexdigest(),
        "symbolicated_offsets": len(offsets),
        "interpretation": "Sparse OS samples, including kernel frames; role counts are disjoint. Exclusive function weights exclude descendants. Scene supplied by operator; not a Time Profiler trace."})
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    args.output.with_suffix(".symbolicated.txt").write_text(annotated)
    print(json.dumps({key: output[key] for key in ("uuid", "total_samples", "disjoint_role_samples")}))


if __name__ == "__main__":
    main()
