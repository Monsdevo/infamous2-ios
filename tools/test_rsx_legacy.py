#!/usr/bin/env python3
"""Actual pinned legacy processor vs iOS adapter; no phone or benchmark."""
from pathlib import Path
import subprocess
from prepare_rsx_legacy import ROOT,instrument

sdk=ROOT/'upstream/infamous2-recomp/ps3recomp-fork'
original=(sdk/'libs/video/cellGcmSys.c').read_text();patched=instrument(original,sdk)
restored=patched.removeprefix('#include "RSXLegacyFastPath.h"\n').replace('                int bces_dispatch_active;\n','').replace('                  bces_dispatch_active=eng;\n','').replace('bces_rsx_legacy_method(&s_state, m, dw, bces_dispatch_active);','rsx_process_method(&s_state, m, dw);').replace('    bces_rsx_legacy_publish();\n','')
assert restored==original
print('PASS exact GCM roundtrip: dispatch/2D/user-command/flip/reference/report/semaphore/FIFO control unchanged',flush=True)
work=ROOT/'build/bces01229/rsx-test';work.mkdir(parents=True,exist_ok=True)
includes=['-I'+str(p) for p in (ROOT/'src/platform',sdk/'include',sdk/'libs/video')]
common=['-std=gnu17','-O2','-fno-strict-aliasing','-fsanitize=address,undefined',*includes]
obj=work/'rsx_commands.o'
subprocess.run(['clang',*common,'-DNDEBUG','-c',str(sdk/'libs/video/rsx_commands.c'),'-o',str(obj)],check=True)
binary=work/'legacy-check'
subprocess.run(['clang',*common,str(ROOT/'src/platform/RSXLegacyFastPath.c'),str(ROOT/'tools/tests/rsx_legacy_fastpath.c'),str(obj),'-o',str(binary)],check=True)
for case in [(1,1,0,0),(0,1,0,0),(1,0,0,0),(1,1,1,0),(1,1,0,1),(0,0,1,0)]:
 r=subprocess.run([str(binary),*map(str,case)],capture_output=True,text=True)
 if r.returncode:
  print(r.stdout[-3000:]);print(r.stderr[-5000:]);raise SystemExit(r.returncode)
 print(r.stdout.strip(),flush=True)
print('PASS all adapter checks; no performance claim',flush=True)
