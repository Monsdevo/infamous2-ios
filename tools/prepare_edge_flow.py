#!/usr/bin/env python3
"""Add opt-in coarse Edge call spans and renderer buffer-range provenance."""
import re
from pathlib import Path

TARGETS={'5740','D0A8','A798','6E08','7860','7570','76C0','7B70','6A40','83C8','AD48'}
def instrument(source):
    prefix='jobmod_d0d15ec83992_ea2a0_spu_func_0000'
    entry=f'void {prefix}E2A0(spu_context* ctx) {{'
    assert source.count(entry)==1
    source=source.replace(entry,entry+'\n    bces_edge_job_begin(ctx);')
    exit='        ctx->int_enable = 0; SPU_RET(ctx);'
    a=source.index(f'void {prefix}E364(');b=source.index('\n}\n',a)
    chunk=source[a:b];assert chunk.count(exit)==1
    source=source[:a]+chunk.replace(exit,'        bces_edge_job_end(ctx);\n'+exit)+source[b:]
    pattern=r'ctx->gpr\[0\] = spu_link\((0x[0-9A-F]+)\); \{ int32_t _si = \(int32_t\)ctx->image_id; ctx->host_depth\+\+; '+prefix+r'([0-9A-F]{4})\(ctx\); spu_drain_call\(ctx, \1\); ctx->host_depth--; spu_img_restore\(ctx, _si\); \}'
    count=0
    def replace(m):
        nonlocal count
        lr,target=m.groups()
        if target not in TARGETS:return m.group()
        count+=1
        s=m.group().replace('int32_t _si =','BCESEdgeSpan _edge_span=bces_edge_span_begin(ctx,'+lr+',0x'+target+'); int32_t _si =',1)
        return s.replace('ctx->host_depth--;','bces_edge_span_end(_edge_span,ctx); ctx->host_depth--;',1)
    source=re.sub(pattern,replace,source)
    assert count==16,count
    return '#include "EdgeFlow.h"\n'+source

def renderer(path):
    s=Path(path).read_text()
    marker='static u64 eng_fnv1a(const void* data, u32 n, u64 hash)\n{'
    assert s.count(marker)==1
    helpers='''static const u8* eng_edge_vertex_ptr(void* user,u32 location,u32 offset,u32 bytes) {
    const u8* p=eng_guest_ptr(user,location,offset,bytes);
    if(PS3_FT_ON())bces_edge_flow_reader(p,bytes,1,location,offset);
    return p;
}
static const u8* eng_edge_index_ptr(void* user,u32 location,u32 offset,u32 bytes) {
    const u8* p=eng_guest_ptr(user,location,offset,bytes);
    if(PS3_FT_ON())bces_edge_flow_reader(p,bytes,2,location,offset);
    return p;
}
'''
    s=s.replace(marker,helpers+marker)
    before='rsx_vertex_fetch_plan_init(&dc.fetch_plan, &g.rsx, layout, eng_guest_ptr, NULL);'
    assert s.count(before)==1;s=s.replace(before,before.replace('eng_guest_ptr','eng_edge_vertex_ptr'))
    for before in ('eng_guest_ptr(NULL, ia_loc, (u32)start, (u32)bytes)', 'eng_guest_ptr(NULL, ia_loc, ia.offset + (first + i) * esz, esz)'):
        assert s.count(before)==1;s=s.replace(before,before.replace('eng_guest_ptr','eng_edge_index_ptr'))
    Path(path).write_text('#include "EdgeFlow.h"\n#include "ps3emu/ps3_ftrace.h"\n'+s)
