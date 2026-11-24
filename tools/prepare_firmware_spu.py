#!/usr/bin/env python3
"""Validate this firmware's relocated SPU bodies, then invoke the pinned lift.

PPU pointer/size slots and code/data bounds are tied to the exact image hash.
This establishes static mappings, not firmware/game execution compatibility.
"""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    profile = json.loads((ROOT / "profiles/firmware-4.93.json").read_text())
    directory = ROOT / "build/bces01229/lle/libsre"
    image = (directory / "meta/libsre_image.bin").read_bytes()
    if hashlib.sha256(image).hexdigest() != profile["libsre_image_sha256"]:
        raise SystemExit("Unexpected relocated libsre image")
    toolkit = ROOT / "upstream/infamous2-recomp/ps3recomp-fork/tools"
    sys.path.insert(0, str(toolkit))
    from spu_disasm import spu_decode
    from find_spu_functions import collect_branch_targets
    from lift_firmware_spu import spu_elfs
    base = int(next(m["base"] for m in profile["modules"] if m["name"] == "libsre"), 0)
    args = []
    bodies = []
    for body in profile["spu_bodies"]:
        off, size, code = (int(body[k], 0) for k in ("offset", "bytes", "code_bytes"))
        raw = image[off:off + size]
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != body["sha256"]:
            raise SystemExit("Firmware body hash/size mismatch")
        if struct.unpack_from(">I", image, int(body["pointer_slot"], 0))[0] != base + off:
            raise SystemExit("Firmware body pointer mismatch")
        if struct.unpack_from(">I", image, int(body["size_slot"], 0))[0] != size:
            raise SystemExit("Firmware body length mismatch")
        insns = [spu_decode(struct.unpack_from(">I", raw, k)[0], 0xa00 + k) for k in range(0x10, code, 4)]
        if any(0xa00 + code <= t < 0xa00 + size for t in collect_branch_targets(insns)):
            raise SystemExit("Firmware branch targets proposed data tail")
        args += ["--body", f"{off:x}:{size:x}:A00:A00:{code:x}"]
        bodies.append({**body, "direct_targets_into_tail": [],
                       "last_instructions": [str(i) for i in insns[-8:]],
                       "data_preserved": True, "indirect_targets_exhaustively_proven": False})
    output = ROOT / "build/bces01229/lle_spu"
    output.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(toolkit / "lift_firmware_spu.py"), "--module-dir", str(directory),
               "--base", hex(base), "--name", "libsre", "--first-image-id", "100", *args, "--out", str(output)]
    with (output / "generation.log").open("w") as log:
        subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
    report = {"firmware": profile["version"], "embedded_spu_elfs": spu_elfs(image), "bodies": bodies,
              "command": command, "runtime_validated": False}
    (ROOT / "out/firmware-spu-generation.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Generated libsre SPU sources; not runtime validated.")


if __name__ == "__main__":
    main()
