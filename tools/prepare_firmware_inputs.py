#!/usr/bin/env python3
"""Check/copy three local firmware inputs; decrypt missing PRXs with RPCS3.

Never installs firmware or changes a user installation. Existing differing
project files are refused. The host decrypt tool can write its own user config
and cache directories; it is never packaged with the iOS application.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from check_inputs import elf_facts

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed-flash", type=Path, required=True)
    args = parser.parse_args()
    profile = json.loads((ROOT / "profiles/firmware-4.93.json").read_text())
    pup = ROOT / "data/incoming/PS3UPDAT.PUP"
    if hashlib.sha256(pup.read_bytes()).hexdigest() != profile["pup_sha256"]:
        raise SystemExit("Unexpected PUP input")
    version = (args.installed_flash / "vsh/etc/version.txt").read_text()
    if not version.startswith("release:04.9300:"):
        raise SystemExit("Extracted firmware version mismatch")
    output = ROOT / "data/firmware/prx"
    output.mkdir(parents=True, exist_ok=True)
    encrypted, facts = [], []
    for module in profile["modules"]:
        name = module["name"]
        raw = (args.installed_flash / "sys/external" / (name + ".sprx")).read_bytes()
        if hashlib.sha256(raw).hexdigest() != module["sprx_sha256"]:
            raise SystemExit("Extracted firmware identity mismatch: " + name)
        target = output / (name + ".sprx")
        if target.exists() and target.read_bytes() != raw:
            raise SystemExit("Refusing to overwrite differing input: " + str(target))
        if not target.exists():
            target.write_bytes(raw)
        prx = output / (name + ".prx")
        if not prx.exists():
            encrypted.append(target)
        elif hashlib.sha256(prx.read_bytes()).hexdigest() != module["sha256"]:
            raise SystemExit("Existing decrypted PRX mismatch: " + str(prx))
    if encrypted:
        rpcs3 = ROOT / "upstream/host-tools/rpcs3-arm64/RPCS3.app/Contents/MacOS/rpcs3"
        cmd = [str(rpcs3)]
        # RPCS3 consumes one filename for each --decrypt occurrence.
        for path in encrypted:
            cmd += ["--decrypt", str(path)]
        with (ROOT / "out/firmware-prx-decrypt.log").open("w") as log:
            subprocess.run(cmd, check=True, stdout=log, stderr=subprocess.STDOUT)
    for module in profile["modules"]:
        path = output / (module["name"] + ".prx")
        found = elf_facts(path)
        if found["sha256"] != module["sha256"] or found["type"] != 0xffa4:
            raise SystemExit("Decrypted PRX validation failed: " + str(path))
        facts.append({"module": module["name"], "path": str(path), "facts": found})
    report = {"version": version, "PUP_sha256": profile["pup_sha256"],
              "flash_source": str(args.installed_flash.resolve()), "modules": facts,
              "runtime_validated": False}
    (ROOT / "out/firmware-input-validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS: firmware 4.93, three encrypted/decrypted module identities and PRX headers")


if __name__ == "__main__":
    main()
