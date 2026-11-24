#!/usr/bin/env python3
"""Extract the already-local BCES archive, entirely on the project volume.

The ISO stream is CRC/SHA checked while writing. A partial ISO is replayed
and byte-compared before appending, so interruption does not trust partial
data. Game extraction skips existing files (-aos) in a private staging
directory; sizes and critical input hashes are checked before acceptance.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import zlib

from check_inputs import parse_sfo

ROOT = Path(__file__).resolve().parents[1]
ISO_SIZE = 15327297536
ISO_CRC = "245D231E"


def main():
    archive = ROOT / "data/incoming/inFamous 2 (Turkey).7z"
    profile = json.loads((ROOT / "profiles/BCES01229-01.00.json").read_text())
    proof = json.loads((ROOT / "out/bces-archive-validation.json").read_text())
    if archive.stat().st_size != proof["bytes"] or not proof["archive_crc_pass"]:
        raise SystemExit("Archive does not match the inspected input size/proof")
    images = ROOT / "data/images"
    images.mkdir(parents=True, exist_ok=True)
    iso = images / "BCES01229.iso"
    partial = iso.with_suffix(".iso.partial")
    state = images / "BCES01229-iso.json"
    staging = ROOT / "data/staging/BCES01229-disc"
    game = ROOT / "data/game/BCES01229"
    before = archive.stat()
    identity = {"archive_size": before.st_size, "archive_mtime_ns": before.st_mtime_ns,
                "archive_recorded_sha256": proof["sha256"]}
    env = dict(os.environ, TMPDIR=str(ROOT / "build/tmp"))
    Path(env["TMPDIR"]).mkdir(parents=True, exist_ok=True)
    if os.stat(ROOT).st_dev != os.stat("/Volumes/monssd").st_dev:
        raise SystemExit("Project is not on monssd")
    if iso.exists():
        record = json.loads(state.read_text())
        if record.get("identity") != identity or iso.stat().st_size != ISO_SIZE or record.get("complete") is not True:
            raise SystemExit("Existing ISO has no matching completed extraction proof; preserved")
    else:
        if shutil.disk_usage(ROOT).free < 2 * ISO_SIZE + 3 * 1024**3:
            raise SystemExit("Need space for the ISO, extracted game and build reserve on monssd")
        if partial.exists() and (not state.exists() or json.loads(state.read_text()).get("identity") != identity):
            raise SystemExit("Existing partial ISO has different provenance; preserved")
        state.write_text(json.dumps({"identity": identity, "complete": False}, indent=2) + "\n")
        existing = partial.stat().st_size if partial.exists() else 0
        if existing > ISO_SIZE:
            raise SystemExit("Partial ISO is too large; preserved")
        digest, crc, total = hashlib.sha256(), 0, 0
        with partial.open("r+b" if partial.exists() else "w+b") as output, (images / "decode.log").open("wb") as log:
            proc = subprocess.Popen(["7zz", "x", "-so", "-mmt=1", str(archive), "inFamous 2 (Turkey).iso"],
                                    stdout=subprocess.PIPE, stderr=log, env=env)
            try:
                while block := proc.stdout.read(1024 * 1024):
                    if total + len(block) > ISO_SIZE:
                        raise ValueError("Decoded ISO exceeds expected size")
                    verify = min(len(block), max(0, existing - total))
                    if verify and output.read(verify) != block[:verify]:
                        raise ValueError("Existing ISO prefix differs from the decoded stream")
                    output.write(block[verify:])
                    digest.update(block)
                    crc = zlib.crc32(block, crc)
                    total += len(block)
                    if total % (256 * 1024**2) == 0:
                        print(f"ISO {total}/{ISO_SIZE} bytes", flush=True)
                rc = proc.wait()
            except BaseException:
                proc.terminate()
                proc.wait()
                raise
        if rc or total != ISO_SIZE or f"{crc:08X}" != ISO_CRC:
            raise SystemExit(f"ISO verification failed: rc={rc}, bytes={total}, CRC={crc:08X}")
        if (archive.stat().st_size, archive.stat().st_mtime_ns) != (before.st_size, before.st_mtime_ns):
            raise SystemExit("Archive changed during extraction")
        os.replace(partial, iso)
        state.write_text(json.dumps({"identity": identity, "complete": True, "bytes": total,
                                    "crc32": f"{crc:08X}", "sha256": digest.hexdigest()}, indent=2) + "\n")
    # This hybrid disc's UDF view reports a headers error in 7-Zip. Its
    # ISO9660 view lists cleanly and spans the verified complete ISO size.
    # Select that filesystem explicitly rather than accepting UDF errors.
    listing = subprocess.check_output(["7zz", "l", "-tiso", "-slt", str(iso)], env=env, text=True)
    (images / "BCES01229-files.txt").write_text(listing)
    expected = {}
    for record in listing.split("\n\n"):
        fields = dict(line.split(" = ", 1) for line in record.splitlines() if " = " in line)
        name = fields.get("Path", "")
        if name.startswith("PS3_GAME/") and "Size" in fields and fields.get("Folder") != "+" and "D" not in fields.get("Attributes", ""):
            rel = PurePosixPath(name)
            if rel.is_absolute() or ".." in rel.parts:
                raise SystemExit("Unsafe ISO path")
            expected[str(rel.relative_to("PS3_GAME"))] = int(fields["Size"])
    if not expected or "PARAM.SFO" not in expected or "USRDIR/EBOOT.BIN" not in expected:
        raise SystemExit("Unexpected game layout")
    staged_game = staging / "PS3_GAME"
    # The existing scaffold may contain empty USRDIR directories. Keep them,
    # and only populate from staging after all file sizes and identity pass.
    complete = all((game / rel).is_file() and (game / rel).stat().st_size == size for rel, size in expected.items())
    if not complete:
        staging.mkdir(parents=True, exist_ok=True)
        with (images / "extract-game.log").open("w") as log:
            subprocess.run(["7zz", "x", "-tiso", "-mmt=1", "-aos", "-o" + str(staging), str(iso), "PS3_GAME/*"],
                           env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        for rel, size in expected.items():
            path = staged_game / rel
            if not path.is_file() or path.stat().st_size != size:
                raise SystemExit("Extracted file missing/size mismatch: " + rel)
        for rel, key in (("PARAM.SFO", "sfo_sha256"), ("USRDIR/EBOOT.BIN", "self_sha256")):
            if hashlib.sha256((staged_game / rel).read_bytes()).hexdigest() != profile[key]:
                raise SystemExit("Full game identity mismatch: " + rel)
        # Refuse to replace any preexisting user file, including different data.
        for source in sorted(staged_game.rglob("*")):
            if not source.is_file():
                continue
            target = game / source.relative_to(staged_game)
            if target.exists():
                raise SystemExit("Existing game file preserved; resolve before merging: " + str(target))
        game.mkdir(parents=True, exist_ok=True)
        for source in sorted(staged_game.rglob("*")):
            if source.is_file():
                target = game / source.relative_to(staged_game)
                target.parent.mkdir(parents=True, exist_ok=True)
                source.rename(target)
    for rel, key in (("PARAM.SFO", "sfo_sha256"), ("USRDIR/EBOOT.BIN", "self_sha256")):
        if hashlib.sha256((game / rel).read_bytes()).hexdigest() != profile[key]:
            raise SystemExit("Existing/finished game identity mismatch: " + rel)
    sfo = parse_sfo((game / "PARAM.SFO").read_bytes())
    report = {"title_id": sfo["TITLE_ID"], "app_version": sfo["APP_VER"], "game_dir": str(game),
              "iso": str(iso), "files": len(expected), "game_file_bytes": sum(expected.values()),
              "PSARC_files": len(list(game.rglob("*.psarc"))), "sizes_verified_against_ISO": True,
              "PSARC_internal_integrity_verified": False, "game_booted": False,
              "monssd_free_bytes": shutil.disk_usage(ROOT).free}
    (ROOT / "out/bces-game-extraction.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
