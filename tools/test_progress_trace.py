#!/usr/bin/env python3
"""Run the actual read-only progress tracker under ASan/UBSan on the host."""
from pathlib import Path
import os
import subprocess
root=Path(__file__).resolve().parents[1]
sdk=root/'upstream/infamous2-recomp/ps3recomp-fork'
out=root/'build/bces01229/progress-test';out.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer')
subprocess.run(['xcrun','clang++','-std=c++20','-O1','-g','-fsanitize=address,undefined',
    '-fno-omit-frame-pointer','-I'+str(root/'src/platform'),
    '-I'+str(root/'build/bces01229/ios-prepared/trace-include'),
    '-I'+str(sdk/'include'),'-I'+str(sdk/'runtime/ppu'),'-I'+str(sdk/'runtime/memory'),
    str(root/'src/platform/ProgressTrace.cpp'),str(root/'tools/tests/progress_trace.cpp'),
    '-o',str(out/'progress-test')],env=env,check=True)
subprocess.run([str(out/'progress-test')],env=env,check=True)
