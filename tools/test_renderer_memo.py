#!/usr/bin/env python3
"""Run the real pinned decoder against the memo under address/UB sanitizers."""
from pathlib import Path
import os
import subprocess

ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'build/bces01229/renderer-memo-test'
out.mkdir(parents=True,exist_ok=True)
sdk=ROOT/'upstream/infamous2-recomp/ps3recomp-fork'
original=(sdk/'libs/video/rsx_vertex_compact.c').read_text()
assert original.count('int rsx_vertex_fetch_all(')==1
source=out/'reference.c'
source.write_text(original)
env=dict(os.environ,DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer')
command=['xcrun','clang','-O1','-g','-fno-omit-frame-pointer','-fsanitize=address,undefined',
         '-Wl,-dead_strip','-I'+str(sdk/'libs/video'),'-I'+str(sdk/'include'),
         '-I'+str(ROOT/'src/platform'),str(source),str(ROOT/'src/platform/RendererMemo.c'),
         str(ROOT/'src/platform/TextureHashMemo.c'),str(ROOT/'src/platform/VertexFetchMemo.c'),
         str(ROOT/'tools/tests/renderer_memo.c'),'-o',str(out/'test')]
subprocess.run(command,env=env,check=True)
subprocess.run([str(out/'test')],env=env,check=True)
