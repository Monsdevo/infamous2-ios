#!/usr/bin/env python3
"""Fetch/verify the locked SDL2 source checkout."""
from setup_sources import ROOT, LOCK, checkout, git
import sys

verify_only = sys.argv[1:] == ["--verify-only"]
if sys.argv[1:] and not verify_only:
    raise SystemExit("Usage: setup_sdl_sources.py [--verify-only]")
dependency = LOCK["sdl_dependency"]
path = ROOT / dependency["path"]
if verify_only:
    if not (path / ".git").is_dir():
        raise SystemExit("Run python3 tools/setup_sdl_sources.py first")
    if git(path, "rev-parse", "HEAD", capture=True).strip() != dependency["commit"]:
        raise SystemExit("SDL2 revision mismatch")
    if git(path, "remote", "get-url", "origin", capture=True).strip() != dependency["url"]:
        raise SystemExit("SDL2 origin mismatch")
else:
    checkout(path, dependency)
if git(path, "status", "--porcelain", "--untracked-files=no", capture=True).strip():
    raise SystemExit("SDL2 source has local changes")
print(f"SDL2: {dependency['commit']}")
