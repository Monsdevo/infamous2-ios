#!/usr/bin/env python3
"""Bounded real BCES boot, with game/saves/logs/temp all on monssd.

The VFS disc is an APFS COW clone, not a second physical game download.
No user save or RPCS3 install is used. A guest present call is NOT by itself
proof of a visible game frame. The saved frame must be inspected separately.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

from check_inputs import parse_sfo

ROOT = Path(__file__).resolve().parents[1]


def writable_usage(vfs):
    """Logical bytes in this diagnostic's own writable mounts, not the disc."""
    result = {}
    for mount in ("dev_hdd0", "gamedata"):
        files = [p for p in (vfs / mount).rglob("*") if p.is_file()]
        result[mount] = {"files": len(files), "logical_bytes": sum(p.stat().st_size for p in files)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=20)
    parser.add_argument("--label", default="first")
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument("--physical-limit-mib", type=int, default=2048,
                        help="Stop this diagnostic if its measured footprint exceeds this value")
    args = parser.parse_args()
    if not 1 <= args.seconds <= 300 or not re.fullmatch(r"[a-z0-9-]{1,48}", args.label):
        raise SystemExit("Invalid diagnostic duration/label")
    if not 256 <= args.physical_limit_mib <= 4096:
        raise SystemExit("Physical diagnostic limit must be 256..4096 MiB")
    profile = json.loads((ROOT / "profiles/BCES01229-01.00.json").read_text())
    game = ROOT / "data/game/BCES01229"
    if hashlib.sha256((game / "PARAM.SFO").read_bytes()).hexdigest() != profile["sfo_sha256"]:
        raise SystemExit("Game metadata identity mismatch")
    if parse_sfo((game / "PARAM.SFO").read_bytes())["TITLE_ID"] != profile["title_id"]:
        raise SystemExit("Wrong game title")
    extraction = json.loads((ROOT / "out/bces-game-extraction.json").read_text())
    if not extraction["sizes_verified_against_ISO"]:
        raise SystemExit("Full extraction must complete first")
    elf = ROOT / "data/inspection/bces01229/selected/PS3_GAME/USRDIR/EBOOT.elf"
    if hashlib.sha256(elf.read_bytes()).hexdigest() != profile["elf_sha256"]:
        raise SystemExit("ELF identity mismatch")
    vfs = ROOT / "data/vfs/BCES01229"
    vfs.mkdir(parents=True, exist_ok=True)
    disc = vfs / "PS3_GAME"
    if not disc.exists():
        temporary = vfs / "PS3_GAME.cloning"
        if temporary.exists():
            raise SystemExit("Partial VFS clone preserved; inspect before retry")
        subprocess.run(["cp", "-cR", str(game), str(temporary)], check=True)
        temporary.rename(disc)
    if (disc / "PARAM.SFO").read_bytes() != (game / "PARAM.SFO").read_bytes():
        raise SystemExit("Existing disc clone does not match profile")
    run = ROOT / "out" / ("step11-boot-" + args.label)
    run.mkdir(parents=True, exist_ok=True)
    log_path = run / "boot.log"
    if log_path.exists():
        raise SystemExit("Existing run log preserved; select a new --label")
    for path in (vfs / "dev_hdd0", vfs / "gamedata", ROOT / "build/tmp"):
        path.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, DEVELOPER_DIR="/Applications/Xcode.app/Contents/Developer",
        TMPDIR=str(ROOT / "build/tmp"), PS3_VFS_ROOT=str(vfs), PS3_HDD0_ROOT=str(vfs / "dev_hdd0"),
        PS3_DEV_FLASH=str(ROOT / "data/firmware/dev_flash"), PS3_GAMEDATA_ROOT=str(vfs / "gamedata"),
        PS3_TITLE="inFAMOUS 2 BCES01229 diagnostic", PS3_LANG="en",
        PS3_BOOT_PATH="/dev_bdvd/PS3_GAME/USRDIR/EBOOT.BIN",
        GCM_SEMA_ACQUIRE="1", GCM_SEMA_ACQUIRE_MS="200", GCM_PARK_GRACE_MS="1000",
        BCES_BOOT_SECONDS=str(args.seconds), BCES_BOOT_PHYSICAL_LIMIT_MIB=str(args.physical_limit_mib),
        PS3RECOMP_ENG_GPU_LIGHT="", PS3RECOMP_ENG_GPU_SSAO="", PS3RECOMP_ENG_SKIP_FP="",
        PS3_CALLTRACE="8", PS3_CALLTRACE_TO="10230",
        PS3RECOMP_METAL_FRAME_DUMP=str(run / "frame.ppm"))
    if not args.windowed:
        env.update(HEADLESS="1", PS3RECOMP_METAL_HEADLESS="1")
    else:
        env.pop("HEADLESS", None)
        env.pop("PS3RECOMP_METAL_HEADLESS", None)
    executable = ROOT / "build/bces01229/host/Infamous2BCES"
    command = [str(executable), str(elf)]
    usage_before = writable_usage(vfs)
    free_before = shutil.disk_usage(ROOT).free
    start = time.monotonic()
    reason = None
    with log_path.open("wb") as log:
        proc = subprocess.Popen(command, cwd=run, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        while proc.poll() is None:
            if log_path.stat().st_size > 16 * 1024**2:
                reason = "log_limit"
            elif time.monotonic() - start > args.seconds + 15:
                reason = "external_deadline"
            if reason:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                break
            time.sleep(0.5)
        rc = proc.wait()
    text = log_path.read_text(errors="replace")
    if reason is None:
        if "STOP physical footprint limit exceeded" in text:
            reason = "diagnostic_physical_limit"
        elif "STOP bounded boot deadline reached" in text:
            reason = "diagnostic_time_limit"
    memory = [{"virtual_bytes": int(a), "physical_footprint": int(b), "resident_bytes": int(c),
               "guest_present_calls": int(d)} for a, b, c, d in re.findall(
        r"virtual_bytes=(\d+) physical_footprint=(\d+) resident_bytes=(\d+) guest_present_calls=(\d+)", text)]
    report = {"title_id": profile["title_id"], "command": command,
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "returncode": rc, "termination_reason": reason, "elapsed_seconds": time.monotonic() - start,
        "log": str(log_path), "environment": {k: v for k, v in env.items() if k.startswith(("PS3", "GCM_", "BCES_")) or k == "TMPDIR"},
        "loader_dispatch_message": "dispatching entry OPD" in text,
        "observed_entry_call_trace": "[CALL] -> 0x00010230" in text,
        "memory_samples": memory, "peak_measured_physical_bytes": max((x["physical_footprint"] for x in memory), default=0),
        "maximum_guest_present_calls": max((x["guest_present_calls"] for x in memory), default=0),
        "frame_capture_exists": (run / "frame.ppm").exists(), "visible_game_frame_verified": False,
        "native_game_boot_attempted": True, "device_test": False, "disc_clone": str(disc)}
    report.update(writable_mounts_before=usage_before, writable_mounts_after=writable_usage(vfs),
                  monssd_free_before=free_before, monssd_free_after=shutil.disk_usage(ROOT).free)
    (run / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("environment", "memory_samples")}, indent=2))
    # This command records an attempted boot, not a PASS even when guest exits 0.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
