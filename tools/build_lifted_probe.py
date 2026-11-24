#!/usr/bin/env python3
"""Build original PPC test instructions, then run the pinned offline loader/lifter.

No game data, assembler, downloaded packages or CPU JIT are involved. The ELF
contains a loop, an out-of-line call and big-endian memory accesses. Its output
must be compiled by the target SDK, not interpreted at runtime.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

def build_elf():
    text = bytearray(struct.pack(">I", 0x60000000) * (0x10C // 4))  # nop padding
    words = [
        0x7C0802A6,  # mflr r0
        0xF8010010,  # std r0,16(r1)
        0xF821FF81,  # stdu r1,-128(r1)
        0x3CC00006,  # lis r6,6 (results at 0x60040)
        0x38600000,  # li r3,0
        0x3880000A,  # li r4,10
        0x7C632214,  # add r3,r3,r4
        0x3884FFFF,  # addi r4,r4,-1
        0x2C040000,  # cmpwi r4,0
        0x4082FFF4,  # bne 0x50018
        0x90660040,  # stw r3,0x40(r6) -> sum = 55
        0x480000D5,  # bl 0x50100 (save/restore LR across the call)
        0x90660044,  # stw r3,0x44(r6) -> 3*55+7 = 172
        0x3CA01234,  # lis r5,0x1234
        0x60A55678,  # ori r5,r5,0x5678
        0x90A60048,  # stw r5,0x48(r6)
        0x80E60048,  # lwz r7,0x48(r6)
        0x90E6004C,  # stw r7,0x4c(r6)
        0x7C0004AC,  # sync (ARM memory barrier in generated code)
        0x38210080,  # addi r1,r1,128
        0xE8010010,  # ld r0,16(r1)
        0x7C0803A6,  # mtlr r0
        0x4E800020,  # blr
    ]
    for i, word in enumerate(words):
        struct.pack_into(">I", text, i * 4, word)
    struct.pack_into(">III", text, 0x100, 0x1C630003, 0x38630007, 0x4E800020)
    data = bytearray(0x100)
    struct.pack_into(">IIII", data, 0, 0x50000, 0x60080, 0x50100, 0x60080)
    # Two LOAD segments and one section for the OPD descriptors. The loader
    # discovers functions from this real section, without a handwritten list.
    result = bytearray(0x2180)
    result[:16] = b"\x7fELF\x02\x02\x01\0" + bytes(8)
    struct.pack_into(">HHIQQQIHHHHHH", result, 16, 2, 21, 1,
                     0x60000, 64, 0x2100, 0, 64, 56, 2, 64, 2, 0)
    for index, (offset, address, size, memory, flags) in enumerate([
        (0x1000, 0x50000, len(text), len(text), 5),
        (0x2000, 0x60000, len(data), 0x1000, 6),
    ]):
        struct.pack_into(">II6Q", result, 64 + index * 56,
                         1, flags, offset, address, address, size, memory, 0x1000)
    struct.pack_into(">II4QII2Q", result, 0x2140,
                     0, 1, 3, 0x60000, 0x2000, 16, 0, 0, 8, 0)
    result[0x1000:0x1000 + len(text)] = text
    result[0x2000:0x2100] = data
    return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    tools = args.source.resolve() / "tools"
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    elf = output / "lifted-probe.elf"
    elf.write_bytes(build_elf())
    subprocess.run([sys.executable, str(tools / "ppu_loader.py"), str(elf),
                    "--output", str(output)], check=True)
    functions = json.loads((output / "lifted-probe.functions.json").read_text())
    if [int(f["start"], 0) for f in functions] != [0x50000, 0x50100]:
        raise RuntimeError("Offline OPD discovery did not find the two test functions")
    subprocess.run([sys.executable, str(tools / "ppu_lifter.py"), str(elf),
                    "--functions", str(output / "lifted-probe.functions.json"),
                    "--hle-stubs", str(output / "lifted-probe.imports.json"),
                    "--symbol-prefix", "aot_", "--code-end", "0x5010c",
                    "--jobs", "1", "--single-file", "--header-name", "lifted_ppu.h",
                    "--source-name", "lifted_ppu.cpp", "--output", str(output)], check=True)
    manifest = {"synthetic": True, "game_data": False, "cpu_jit": False,
                "python": sys.version.split()[0], "functions_discovered": len(functions),
                "files": {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                          for name in ("lifted-probe.elf", "lifted_ppu.h", "lifted_ppu.cpp")}}
    (output / "lifted-probe.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
