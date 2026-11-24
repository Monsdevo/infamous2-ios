#!/usr/bin/env python3
"""Read-only inventory of user-owned inputs. No decryption or key handling."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUEST_VM_BYTES = 0xE0000000  # current launcher / iOS arena


def parse_sfo(data):
    if len(data) < 20 or data[:4] != b"\0PSF":
        raise ValueError("Invalid PARAM.SFO header")
    _, key_start, value_start, count = struct.unpack_from("<4I", data, 4)
    if count > (len(data) - 20) // 16:
        raise ValueError("Invalid SFO entry count")
    result = {}
    for i in range(count):
        key_offset, fmt, length, capacity, value_offset = struct.unpack_from("<HHIII", data, 20 + 16 * i)
        begin = key_start + key_offset
        end = data.find(b"\0", begin, value_start)
        start = value_start + value_offset
        if begin < key_start or end < begin or length > capacity or start + capacity > len(data):
            raise ValueError("SFO entry exceeds file bounds")
        key = data[begin:end].decode("utf-8")
        if fmt == 0x204:
            result[key] = data[start:start + length].rstrip(b"\0").decode("utf-8")
    return result


def elf_facts(path):
    with path.open("rb") as stream:
        total_size = path.stat().st_size
        header = stream.read(64)
        if len(header) < 64 or header[:7] != b"\x7fELF\x02\x02\x01":
            raise ValueError(f"Expected decrypted ELF64 big-endian: {path}")
        kind, machine = struct.unpack_from(">HH", header, 16)
        if machine != 21:
            raise ValueError(f"Expected EM_PPC64 (21), got {machine}: {path}")
        entry, phoff = struct.unpack_from(">QQ", header, 24)
        phsize, phcount = struct.unpack_from(">HH", header, 54)
        if phsize < 56 or phcount > 4096 or phoff + phsize * phcount > total_size:
            raise ValueError("Invalid ELF program-header table")
        segments = []
        for i in range(phcount):
            stream.seek(phoff + i * phsize)
            pt, flags, offset, va, _, file_size, memory_size, _ = struct.unpack(">II6Q", stream.read(56))
            if pt == 1:
                if offset + file_size > total_size:
                    raise ValueError("ELF load segment exceeds file")
                if file_size > memory_size:
                    raise ValueError("ELF load segment file size exceeds memory size")
                if va + memory_size > GUEST_VM_BYTES:
                    raise ValueError("ELF load segment exceeds current 3.5 GiB guest arena")
                segments.append({"va": va, "file_offset": offset, "flags": flags,
                                 "file_bytes": file_size, "memory_bytes": memory_size})
        if not segments:
            raise ValueError("ELF has no PT_LOAD segments")
        entry_opd = None
        if kind == 2:
            for segment in segments:
                if segment["va"] <= entry and entry + 8 <= segment["va"] + segment["file_bytes"]:
                    stream.seek(segment["file_offset"] + entry - segment["va"])
                    code, toc = struct.unpack(">II", stream.read(8))
                    executable = any(s["flags"] & 1 and s["va"] <= code and
                                     code + 4 <= s["va"] + s["file_bytes"] for s in segments)
                    if executable:
                        entry_opd = {"code": hex(code), "toc": hex(toc)}
                    break
            if not entry_opd:
                raise ValueError("EBOOT entry OPD does not resolve to file-backed executable code")
        stream.seek(0)
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"class": 64, "endian": "big", "machine": machine, "type": kind,
            "entry": hex(entry), "entry_opd": entry_opd, "sha256": digest, "load_segments": segments}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=ROOT / "profiles/BCES01229-01.00.json")
    parser.add_argument("--game-dir", type=Path)
    parser.add_argument("--eboot", type=Path, help="Separate decrypted EBOOT.elf, if outside USRDIR")
    parser.add_argument("--firmware-dir", type=Path, default=ROOT / "data/firmware/prx")
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text())
    args.game_dir = args.game_dir or ROOT / "data/game" / profile["title_id"]
    checks = []
    def inspect(label, path, reader):
        try:
            facts = reader(path)
            checks.append({"input": label, "path": str(path), "ok": True, "facts": facts})
            return facts
        except (OSError, ValueError, struct.error, UnicodeError) as error:
            checks.append({"input": label, "path": str(path), "ok": False, "error": str(error)})
            return None

    sfo = inspect("PARAM.SFO", args.game_dir / "PARAM.SFO", lambda p: parse_sfo(p.read_bytes()))
    if sfo:
        expected_version = profile.get("app_version")
        checks.append({"input": "target_metadata", "ok": sfo.get("TITLE_ID") == profile["title_id"] and
                       (expected_version is None or sfo.get("APP_VER") == expected_version),
                       "expected": {"TITLE_ID": profile["title_id"], "APP_VER": expected_version},
                       "observed_app_ver": sfo.get("APP_VER"),
                       "note": "Metadata identifies a candidate input, not runtime compatibility. NPUA upstream APP_VER documentation is inconsistent."})
    eboot = inspect("EBOOT.elf", args.eboot or args.game_dir / "USRDIR/EBOOT.elf", elf_facts)
    if eboot:
        segments = eboot["load_segments"]
        contains = lambda address, size: any(s["va"] <= address and address + size <= s["va"] + s["file_bytes"] for s in segments)
        ranges = profile["required_file_ranges"]
        checks.append({"input": "port_address_coverage", "ok": eboot["type"] == 2 and
                       all(contains(int(r["address"], 0), r["bytes"]) for r in ranges),
                       "note": "Profile-specific structural check only; guest code has not been run."})
        if profile.get("elf_sha256"):
            checks.append({"input": "profile_ELF_identity", "ok": eboot["sha256"] == profile["elf_sha256"],
                           "expected_sha256": profile["elf_sha256"]})
    for module in ("liblv2", "libsysmodule", "libsre"):
        inspect(module, args.firmware_dir / f"{module}.prx", elf_facts)
    archives = list((args.game_dir / "USRDIR").rglob("*.psarc")) if (args.game_dir / "USRDIR").is_dir() else []
    checks.append({"input": "game_archives", "ok": bool(archives), "count": len(archives),
                   "note": "Presence only; archive completeness and runtime decryption remain unverified."})
    good = all(c["ok"] for c in checks)
    print(json.dumps({"profile": profile["name"], "profile_game_boot_enabled": profile["game_boot_enabled"],
                      "inputs_ready_for_review": good, "binary_compatibility_verified": False,
                      "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())
