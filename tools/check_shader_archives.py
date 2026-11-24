#!/usr/bin/env python3
"""Check every object in shader archives for the requested Apple platform."""
import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--build", type=Path, required=True)
parser.add_argument("--platform", choices=("MACOS", "IOS", "IOSSIMULATOR"), required=True)
parser.add_argument("--include-runtime", action="store_true", help="Also check platform/fiber diagnostic libraries")
parser.add_argument("--include-full-runtime", action="store_true", help="Also check complete runtime and SDL2 libraries")
args = parser.parse_args()
expected = {"MACOS": 1, "IOS": 2, "IOSSIMULATOR": 7}[args.platform]
env = dict(os.environ)
env.setdefault("DEVELOPER_DIR", "/Applications/Xcode.app/Contents/Developer")
names = ("glslang", "glslang-default-resource-limits", "SPIRV", "SPIRV-Tools", "SPIRV-Tools-opt",
         "spirv-cross-core", "spirv-cross-glsl", "spirv-cross-msl", "spirv-cross-c")
if args.include_runtime:
    names += ("runtime_platform", "runtime_probe_fixture", "ios_fiber_context")
if args.include_full_runtime:
    names += ("ps3recomp_full_runtime", "SDL2")
results = []
for name in names:
    paths = list(args.build.rglob(f"lib{name}.a"))
    if len(paths) != 1:
        raise SystemExit(f"Expected exactly one built archive for {name}, found {paths}")
    archive = paths[0]
    members = subprocess.check_output(["/usr/bin/ar", "-t", str(archive)], text=True).splitlines()
    objects = [m for m in members if not m.startswith("__.SYMDEF")]
    commands = subprocess.check_output(["xcrun", "otool", "-l", str(archive)], env=env, text=True)
    platforms = [int(x) for x in re.findall(r"^\s*platform\s+(\d+)\s*$", commands, re.MULTILINE)]
    if not objects or len(platforms) != len(objects) or set(platforms) != {expected}:
        raise SystemExit(f"Wrong/incomplete build platforms in {archive}: {set(platforms)}, "
                         f"{len(platforms)} LC_BUILD_VERSION records / {len(objects)} members")
    results.append({"archive": str(archive), "objects_checked": len(objects), "platform": args.platform,
                    "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()})
print(json.dumps({"result": "PASS", "archives": results}, indent=2))
