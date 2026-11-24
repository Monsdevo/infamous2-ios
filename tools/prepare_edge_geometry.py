#!/usr/bin/env python3
"""Derive three measured Edge arithmetic blocks without altering dispatch/DMA.
The verified baseline remains intact; only the derived iOS archive is replaced.
"""
import hashlib
import json
import re
from pathlib import Path
from prepare_edge_flow import instrument
from prepare_skinning import patch as patch_skinning

ROOT=Path(__file__).resolve().parents[1]
MODULE='jobmod_d0d15ec83992_ea2a0'
BLOCKS=('D808','D8A8','DA28')

def derive(source):
    pieces=[]
    for index,pc in enumerate(BLOCKS):
        name=f'{MODULE}_spu_func_0000{pc}'
        signature=f'void {name}(spu_context* ctx) {{'
        assert source.count(signature)==1
        start=source.index(signature);end=source.index('\n}\n',start)+3
        original=source[start:end]
        # No calls, channels, DMA, yields or indirect dispatch inside this scope.
        # Integer CUFLT uses spu__sf_pack (not host float conversion).
        helpers=set(re.findall(r'\b(spu_\w+)\(',original))
        allowed={'spu_ai','spu_a','spu_fm','spu_fma','spu_fms','spu_shufb',
                 'spu_ls_read128','spu_ls_write128','spu_ori','spu_selb',
                 'spu_cuflt','spu_shli','spu_shlqbyi','spu_roti','spu_xsbh','spu_andhi'}
        assert helpers<=allowed,helpers-allowed
        assert not re.search(r'SPU_|spu_(?:call|stop|channel|dma)',original)
        ref=original.replace('void '+name+'(', 'static void '+name+'_reference(',1)
        fast=original.replace('void '+name+'(', 'static void '+name+'_arm64(',1)
        for op in ('fm','fma','fms'):
            fast=fast.replace('spu_'+op+'(', 'bces_rz_'+op+'(')
        fast=fast.replace('{\n','{\n    uint64_t edge_fpsr; __asm__ volatile("mrs %0, fpsr":"=r"(edge_fpsr));\n    uint64_t edge_fpcr=bces_rz_begin();\n',1)
        # Restore both control and exception state at every original exit.
        fast=fast.replace('return;', 'bces_rz_end(edge_fpcr); __asm__ volatile("msr fpsr, %0"::"r"(edge_fpsr):"memory"); return;')
        wrapper=f'''void {name}(spu_context* ctx) {{
    if (!bces_edge_enabled()) {{ {name}_reference(ctx); return; }}
    uint64_t control; __asm__ volatile("mrs %0, fpcr":"=r"(control));
    /* The pinned runtime's double/TwoSum helpers assume round-to-nearest.
       Preserve their existing behavior if a caller selects another mode. */
    if (control & (3ull<<22)) {{ {name}_reference(ctx); return; }}
    if (bces_edge_validate_next({index})) {{
        spu_context* reference=malloc(sizeof *reference);
        uint8_t* local_store=malloc(SPU_LS_SIZE);
        if (!reference || !local_store) {{ free(reference); free(local_store); {name}_reference(ctx); return; }}
        memcpy(reference,ctx,sizeof *reference); memcpy(local_store,ctx->ls,SPU_LS_SIZE);
        void* snapshot=bces_edge_snapshot_input(ctx,{index});
        reference->ls=local_store;
        {name}_reference(reference);
        {name}_arm64(ctx);
        reference->ls=ctx->ls;
        /* Only this block's architectural outputs: ls_store aliases ctx->ls
           in production, and reservation/mailbox fields can change externally. */
        int equal=!memcmp(reference->gpr,ctx->gpr,sizeof ctx->gpr)
            && reference->pc==ctx->pc && reference->tramp_fn==ctx->tramp_fn
            && !memcmp(local_store,ctx->ls,SPU_LS_SIZE);
        bces_edge_snapshot_finish(snapshot,reference,ctx,local_store,equal);
        if (!equal) {{
            /* Reservation/mailbox fields may change asynchronously: never
               restore the entire host context from a stale shadow copy. */
            memcpy(ctx->ls,local_store,SPU_LS_SIZE);
            memcpy(ctx->gpr,reference->gpr,sizeof ctx->gpr);
            ctx->pc=reference->pc; ctx->tramp_fn=reference->tramp_fn;
        }}
        free(local_store); free(reference);
        bces_edge_validation_result(equal);
        return;
    }}
    bces_edge_note_call({index});
    {name}_arm64(ctx);
}}
'''
        replacement=ref+'\n'+fast+'\n'+wrapper
        source=source[:start]+replacement+source[end:]
        pieces.append(replacement)
    prefix='#include "spu_recomp.h"\n#include "BCESSpuRZ.h"\n#include "EdgeGeometry.h"\n'
    return prefix+source,prefix+'\n'.join(pieces)

def prepare(output,report):
    unit,=[u for u in report['units'] if Path(u['source']).parent.name==MODULE]
    raw=Path(unit['source']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==unit['sha256']
    full,kernels=derive(raw.decode())
    full=patch_skinning(instrument(full))
    output.mkdir(parents=True,exist_ok=True)
    for name,text in [('edge_geometry.c',full),('edge_kernels.c',kernels)]:
        p=output/name
        if not p.exists() or p.read_text()!=text:p.write_text(text)
    (output/'edge-source.json').write_text(json.dumps({'source':unit['source'],'sha256':unit['sha256'],'blocks':BLOCKS,'default_enabled':False},indent=2)+'\n')
    return Path(unit['object']).name

if __name__=='__main__':
    report=json.loads((ROOT/'out/bces-support-compile-iphoneos-spu-O2-copy.json').read_text())
    prepare(ROOT/'build/bces01229/edge-test',report)
