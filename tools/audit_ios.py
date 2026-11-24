#!/usr/bin/env python3
"""Reproduce SDK-level compatibility findings, preserving compiler diagnostics."""
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "upstream/infamous2-recomp/ps3recomp-fork"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)
env = dict(os.environ)
env.setdefault("DEVELOPER_DIR", "/Applications/Xcode.app/Contents/Developer")
base = ["xcrun", "--sdk", "iphoneos", "clang", "-target", "arm64-apple-ios17.0", f"-I{SDK / 'include'}"]
checks = {
    "metal-ios-syntax": [*base, "-fobjc-arc", "-fsyntax-only", str(SDK / "libs/video/rsx_metal_backend.m")],
    "win32-compat-ios-syntax": [*base, "-fsyntax-only", str(SDK / "runtime/platform/win32_compat.c")],
    "fiber-ios-syntax": [*base, "-fsyntax-only", str(SDK / "libs/spurs/cellFiber.c")],
}
ucontext = OUT / "ucontext-check.c"
ucontext.write_text("#define _XOPEN_SOURCE 600\n#include <ucontext.h>\nint main(void) { ucontext_t c; return getcontext(&c); }\n")
checks["ucontext-device-link"] = [*base, str(ucontext), "-o", str(OUT / "ucontext-check")]
results = {}
for name, command in checks.items():
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    (OUT / f"{name}.log").write_text(result.stdout + result.stderr)
    results[name] = {"exit_code": result.returncode, "command": command,
                     "scope": "compile/link only; not a device execution"}
(OUT / "ios-audit.json").write_text(json.dumps(results, indent=2))
print(json.dumps({name: value["exit_code"] for name, value in results.items()}, indent=2))
