#!/usr/bin/env python3
"""Fetch locked shader compiler sources; do not change existing checkouts."""
from setup_sources import ROOT, LOCK, checkout, git
import sys

verify_only = sys.argv[1:] == ["--verify-only"]
if sys.argv[1:] and not verify_only:
    raise SystemExit("Usage: setup_shader_sources.py [--verify-only]")

for dependency in LOCK["shader_dependencies"]:
    path = ROOT / dependency["path"]
    if verify_only:
        if not (path / ".git").is_dir():
            raise SystemExit("Run python3 tools/setup_shader_sources.py first")
        if git(path, "rev-parse", "HEAD", capture=True).strip() != dependency["commit"]:
            raise SystemExit(f"Shader dependency revision mismatch: {path}")
        if git(path, "remote", "get-url", "origin", capture=True).strip() != dependency["url"]:
            raise SystemExit(f"Shader dependency origin mismatch: {path}")
    else:
        checkout(path, dependency)
    if git(path, "status", "--porcelain", "--untracked-files=no", capture=True).strip():
        raise SystemExit(f"Shader dependency has local changes: {path}")
    print(f"{dependency['name']}: {dependency['commit']}", flush=True)
