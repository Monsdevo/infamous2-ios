#!/usr/bin/env python3
"""Replay a private Edge snapshot; never distribute captured game data."""
import argparse
import json
import subprocess
from prepare_edge_geometry import ROOT,MODULE,prepare
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('fixture',type=__import__('pathlib').Path)
args=parser.parse_args()
work=ROOT/'build/bces01229/edge-test'
prepare(work,json.loads((ROOT/'out/bces-support-compile-iphoneos-spu-O2-copy.json').read_text()))
sdk=ROOT/'upstream/infamous2-recomp/ps3recomp-fork/runtime/spu'
binary=work/'replay'
subprocess.run(['clang','-std=gnu17','-O2','-fwrapv','-fno-strict-aliasing','-ffp-contract=off','-DSPU_USE_DISPATCH_MT',
    '-fsanitize=address,undefined','-I'+str(ROOT/'src/platform'),'-I'+str(ROOT/'src/game'),'-I'+str(ROOT/'build/bces01229/spu'/MODULE),'-I'+str(sdk),
    str(work/'edge_kernels.c'),str(ROOT/'src/platform/EdgeGeometry.c'),str(ROOT/'tools/tests/edge_replay.c'),'-o',str(binary)],check=True)
subprocess.run([str(binary),str(args.fixture.resolve())],check=True)
