#!/usr/bin/env python3
"""Isolated, bounded native replay of the original pure skinning call graph."""
from pathlib import Path
import re,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
MODULE='jobmod_d0d15ec83992_ea2a0'

def prepare():
    source=ROOT/'build/bces01229/spu'/MODULE/'spu_recomp.c'
    report=json.loads((ROOT/'out/bces-support-compile-iphoneos-spu-O2-copy.json').read_text())
    unit,=[u for u in report['units'] if Path(u['source'])==source]
    raw=source.read_bytes();assert hashlib.sha256(raw).hexdigest()==unit['sha256']
    text=raw.decode();bodies=dict(re.findall(r'void '+MODULE+r'_spu_func_0000([0-9A-F]{4})\(spu_context\* ctx\) \{(.*?)(?=\nvoid |\Z)',text,re.S))
    seen=set();todo=['D0A8','A798']
    while todo:
        pc=todo.pop()
        if pc in seen or pc=='E6C0':continue
        seen.add(pc);todo+=re.findall(MODULE+r'_spu_func_0000([0-9A-F]{4})',bodies[pc])
    assert len(seen)>=48
    out=ROOT/'build/bces01229/skinning';out.mkdir(exist_ok=True)
    pieces=['#include "spu_recomp.h"\n#include "spu_helpers.h"\n#include "SkinningReplay.h"\n']
    for pc in sorted(seen):
        body=bodies[pc].replace('spu_ls_read128(', 'skin_read(').replace('spu_ls_write128(','skin_write(')
        pieces.append(f'void {MODULE}_spu_func_0000{pc}(spu_context* ctx) {{\n skin_visit(ctx,0x{pc});'+body)
    pieces.append(f'void {MODULE}_spu_func_0000E6C0(spu_context* ctx) {{ skin_assert(ctx); }}\n')
    pieces.append('void skin_dispatch(spu_context* ctx) {switch(ctx->pc) {\n')
    for pc in sorted(seen|{'E6C0'}):pieces.append(f'case 0x{pc}: {MODULE}_spu_func_0000{pc}(ctx); return;\n')
    pieces.append('default: fprintf(stderr,"unexpected pure skin pc %x\\n",ctx->pc);abort();}}\n')
    (out/'reference.c').write_text(''.join(pieces))
    (out/'reference-source.json').write_text(json.dumps({'sha256':unit['sha256'],'blocks':sorted(seen)},indent=2)+'\n')
    return out
if __name__=='__main__':print(prepare())
