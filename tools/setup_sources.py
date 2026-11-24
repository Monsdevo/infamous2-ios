#!/usr/bin/env python3
"""Fetch exact source revisions; never reset or overwrite local changes."""
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / "sources.lock.json").read_text())


def git(path, *args, capture=False):
    return subprocess.run(["git", "-C", str(path), *args], check=True,
                          text=True, capture_output=capture).stdout


def checkout(path, item):
    if not path.exists():
        path.mkdir(parents=True)
        git(path, "init", "--quiet")
        git(path, "remote", "add", "origin", item["url"])
    if git(path, "remote", "get-url", "origin", capture=True).strip() != item["url"]:
        raise SystemExit(f"Unexpected origin: {path}")
    head_check = subprocess.run(["git", "-C", str(path), "rev-parse", "--verify", "HEAD"],
                                capture_output=True, text=True)
    if head_check.returncode != 0:
        # Resume a failed initial network fetch only in an otherwise empty
        # repository. Never check out over user-owned files.
        if any(p.name != ".git" for p in path.iterdir()):
            raise SystemExit(f"Refusing to populate nonempty checkout without HEAD: {path}")
        git(path, "fetch", "--depth=1", "origin", item["commit"])
        git(path, "checkout", "--quiet", "--detach", "FETCH_HEAD")
    head = git(path, "rev-parse", "HEAD", capture=True).strip()
    if head != item["commit"]:
        raise SystemExit(f"Refusing to change existing checkout: {path}: {head}")


def main():
    port = ROOT / "upstream/infamous2-recomp"
    checkout(port, LOCK["port"])
    if git(port, "status", "--porcelain", "--untracked-files=no", capture=True).strip():
        raise SystemExit("Port has tracked local edits; review them before setup")
    runtime = port / "ps3recomp-fork"
    checkout(runtime, LOCK["runtime"])
    patch = port / LOCK["runtime"]["patch"]
    if hashlib.sha256(patch.read_bytes()).hexdigest() != LOCK["runtime"]["patch_sha256"]:
        raise SystemExit("Patch checksum mismatch")
    check = subprocess.run(["git", "-C", str(runtime), "apply", "--reverse", "--check", str(patch)],
                           capture_output=True)
    if check.returncode != 0:
        if git(runtime, "status", "--porcelain", "--untracked-files=no", capture=True).strip():
            raise SystemExit("Runtime has local changes; refusing to overwrite them")
        git(runtime, "apply", "--check", str(patch))
        git(runtime, "apply", str(patch))
    # Reconstruct HEAD + patch in a temporary index, without staging anything
    # in the user's checkout. Compare bytes, including added (untracked) files.
    with tempfile.TemporaryDirectory() as temp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(temp) / "index"))
        def index(*args):
            return subprocess.run(["git", "-C", str(runtime), *args], env=env,
                                  check=True, capture_output=True).stdout
        index("read-tree", "HEAD")
        index("apply", "--cached", str(patch))
        expected_paths = set(index("diff", "--cached", "--name-only").decode().splitlines())
        changed_paths = set(git(runtime, "diff", "HEAD", "--name-only", capture=True).splitlines())
        if changed_paths - expected_paths:
            raise SystemExit("Runtime has changes outside the expected patch")
        for name in expected_paths:
            if (runtime / name).read_bytes() != index("show", f":{name}"):
                raise SystemExit(f"Runtime content differs from pinned patch: {name}")
    print(f"Pinned source ready: {port}\nRuntime: {LOCK['runtime']['commit']} + verified patch")


if __name__ == "__main__":
    main()
