#!/usr/bin/env python3
"""Compare actual lifted Edge blocks and derived ARM64 blocks, no game assets."""
import json
import subprocess
from prepare_edge_geometry import ROOT, MODULE, prepare
work=ROOT/'build/bces01229/edge-test'
prepare(work,json.loads((ROOT/'out/bces-support-compile-iphoneos-spu-O2-copy.json').read_text()))
sdk=ROOT/'upstream/infamous2-recomp/ps3recomp-fork/runtime/spu'
base=['clang','-std=gnu17','-O2','-fwrapv','-fno-strict-aliasing','-ffp-contract=off','-DSPU_USE_DISPATCH_MT',
      '-I'+str(ROOT/'src/platform'),'-I'+str(ROOT/'src/game'),'-I'+str(ROOT/'build/bces01229/spu'/MODULE),'-I'+str(sdk),
      str(work/'edge_kernels.c'),str(ROOT/'src/platform/EdgeGeometry.c'),str(ROOT/'tools/tests/edge_geometry.c')]
for sanitized in (True,False):
    binary=work/('test-sanitized' if sanitized else 'test-release')
    subprocess.run(base+(['-fsanitize=address,undefined'] if sanitized else [])+['-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
