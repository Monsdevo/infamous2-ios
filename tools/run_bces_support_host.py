#!/usr/bin/env python3
"""Compile/link only the host diagnostic using existing, tested dependencies.

Configure bces_support_host with CMake first. This deliberately does not rebuild
dependencies: their existing objects/archives must already be valid for the
configured host toolchain. Use cmake --build for a cold/changed dependency tree.
All commands come from that target's Ninja rules and are executed as argv,
without evaluating shell text. No title boot or graphics initialization occurs.
"""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    build = ROOT / "build/host"
    commands = subprocess.check_output(["ninja", "-t", "commands", "bces_support_host"],
                                       cwd=build, text=True).splitlines()
    compile_cmd = shlex.split(commands[-2])
    link_cmd = shlex.split(commands[-1])
    source = ROOT / "src/host/bces_support_main.cpp"
    if str(source) not in compile_cmd or "-c" not in compile_cmd:
        raise SystemExit("Unexpected diagnostic compile rule")
    if link_cmd[:2] != [":", "&&"] or link_cmd[-2:] != ["&&", ":"]:
        raise SystemExit("Unexpected diagnostic link rule")
    link_cmd = link_cmd[2:-2]
    if link_cmd[link_cmd.index("-o") + 1] != "bces_support_host" or any(t in link_cmd for t in ("&&", ";", "|")):
        raise SystemExit("Refusing unexpected link command")
    inputs = []
    for token in link_cmd:
        if token.endswith((".a", ".o")) and "bces_support_main.cpp.o" not in token:
            path = Path(token)
            if not path.is_absolute():
                path = build / path
            inputs.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    report = {"dependencies_rebuilt": False, "inputs": inputs,
              "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "compile": compile_cmd, "link": link_cmd, "game_started": False}
    with (ROOT / "out/step10-support-host-direct-build.log").open("w") as log:
        for command in (compile_cmd, link_cmd):
            result = subprocess.run(command, cwd=build, stdout=log, stderr=subprocess.STDOUT)
            if result.returncode:
                raise SystemExit(f"Diagnostic compile/link failed: {result.returncode}; see build log")
    with (ROOT / "out/step10-support-host.log").open("w") as log:
        result = subprocess.run([str(build / "bces_support_host")], cwd=ROOT,
                                stdout=log, stderr=subprocess.STDOUT)
    report.update(returncode=result.returncode, executable_sha256=hashlib.sha256((build / "bces_support_host").read_bytes()).hexdigest())
    (ROOT / "out/bces-support-host-build.json").write_text(json.dumps(report, indent=2) + "\n")
    print((ROOT / "out/step10-support-host.log").read_text())
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
