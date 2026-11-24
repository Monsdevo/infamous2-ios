#!/usr/bin/env python3
"""Apply our platform patch in a build overlay; keep the pinned checkout intact."""
import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ("libs/video/rsx_metal_backend.m", "libs/video/rsx_draw_engine.c", "libs/video/rsx_shader_msl.cpp")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    lock = json.loads((ROOT / "sources.lock.json").read_text())["ios_renderer_overlay"]
    patch = ROOT / lock["patch"]
    if hashlib.sha256(patch.read_bytes()).hexdigest() != lock["patch_sha256"]:
        raise SystemExit("iOS renderer patch checksum mismatch")
    for name in FILES:
        if hashlib.sha256((args.source / name).read_bytes()).hexdigest() != lock["source_sha256"][name]:
            raise SystemExit(f"Renderer source changed; refusing an unverified overlay: {name}")
    with tempfile.TemporaryDirectory(prefix="infamous2-renderer-") as tmp:
        stage = Path(tmp)
        for name in FILES:
            dest = stage / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args.source / name, dest)
        subprocess.run(["/usr/bin/patch", "--batch", "--forward", "-p1", "-i",
                        str(patch)], cwd=stage, check=True)
        for name in FILES:
            contents = (stage / name).read_bytes()
            dest = args.output / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists() or dest.read_bytes() != contents:
                dest.write_bytes(contents)


if __name__ == "__main__":
    main()
