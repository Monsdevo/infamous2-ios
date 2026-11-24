#!/usr/bin/env python3
"""Fetch/verify the locked Boost.Context assembly source checkout."""
from setup_sources import ROOT, LOCK, checkout, git
import sys

verify_only = sys.argv[1:] == ["--verify-only"]
if sys.argv[1:] and not verify_only:
    raise SystemExit("Usage: setup_context_sources.py [--verify-only]")
dependency = LOCK["context_dependency"]
path = ROOT / dependency["path"]
if verify_only:
    if not (path / ".git").is_dir():
        raise SystemExit("Run python3 tools/setup_context_sources.py first")
    if git(path, "rev-parse", "HEAD", capture=True).strip() != dependency["commit"]:
        raise SystemExit("Boost.Context revision mismatch")
    if git(path, "remote", "get-url", "origin", capture=True).strip() != dependency["url"]:
        raise SystemExit("Boost.Context origin mismatch")
else:
    checkout(path, dependency)
if git(path, "status", "--porcelain", "--untracked-files=no", capture=True).strip():
    raise SystemExit("Boost.Context source has local changes")
print(f"Boost.Context: {dependency['commit']}")
