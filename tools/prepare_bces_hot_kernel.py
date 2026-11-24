#!/usr/bin/env python3
"""Derive a bounded experiment from the measured BCES image 234 hot function.
No generated baseline or upstream file is modified.
"""
from pathlib import Path
import hashlib
import json
import re

ROOT=Path(__file__).resolve().parents[1]
MODULE='datamod_00821080'
NAME=MODULE+'_spu_func_00007320'


def derive(source):
    signature=f'void {NAME}(spu_context* ctx) {{'
    assert source.count(signature)==1
    start=source.index(signature);end=source.index('\n}\n',start)+3
    original=source[start:end]
    assert original.count('SPU_RET(ctx);')==1
    assert not re.search(r'\breturn\b|SPU_CALL|SPU_DRAIN|SPU_BRANCH|SPU_RET_REG',original)
    # Only local register values change location; original LS helpers, arithmetic,
    # loop order, full final register file and SPU_RET remain unchanged.
    fast=original.replace(NAME,'bces_hot_cached_234',1)
    fast=fast.replace('ctx->gpr[','registers[')
    fast=fast.replace('{\n','{\n    u128 registers[128]; memcpy(registers,ctx->gpr,sizeof registers);\n',1)
    fast=fast.replace('SPU_RET(ctx);','memcpy(ctx->gpr,registers,sizeof registers);\n        SPU_RET(ctx);')
    reference=original.replace(NAME,'bces_hot_reference_234',1)
    rz=original.replace(NAME,'bces_hot_rz_234',1)
    for name in ('fa','fs','fm','fma'):
        rz=rz.replace('spu_'+name+'(', 'bces_rz_'+name+'(')
    rz=rz.replace('{\n','{\n    uint64_t previous_fpcr=bces_rz_begin();\n',1)
    rz=rz.replace('SPU_RET(ctx);','bces_rz_end(previous_fpcr);\n        SPU_RET(ctx);')
    return reference,fast,rz


def main():
    report=json.loads((ROOT/'out/bces-support-compile-iphoneos-spu-O2-copy.json').read_text())
    unit,=[u for u in report['units'] if Path(u['source']).parent.name==MODULE]
    source=Path(unit['source']);raw=source.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==unit['sha256']
    ref,fast,rz=derive(raw.decode())
    out=ROOT/'build/bces01229/hot-kernel';out.mkdir(parents=True,exist_ok=True)
    (out/'kernels.c').write_text('#include "spu_context.h"\n#include "BCESSpuRZ.h"\n'+ref+'\n'+fast+'\n'+rz)
    (out/'source.json').write_text(json.dumps({'source':str(source),'sha256':unit['sha256'],'function':NAME,'image_id':234},indent=2)+'\n')
    print(out)


if __name__=='__main__':main()
