#!/usr/bin/env python3
"""Paired tile capture around the existing fully-drained call, never replace its result."""
import ast,hashlib,json
from light_shader_culling import patch as patch_light_shader
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def put(p,s):
    if not p.exists() or p.read_text()!=s:p.write_text(s)
def prepare(output,report,sdk):
    unit=next(u for u in report['units'] if 'jobmod_c6e7383dc013_e5400/spu_recomp.c' in u['source'])
    source=Path(unit['source']).read_text()
    assert hashlib.sha256(source.encode()).hexdigest()==unit['sha256']
    call='        { uint32_t _tg = ctx->gpr[98]._u32[0]; ctx->gpr[0] = spu_link(0x6730); int32_t _si = (int32_t)ctx->image_id; ctx->pc = _tg; ctx->host_depth++; spu_indirect_branch(ctx); spu_drain_call(ctx, 0x6730); ctx->host_depth--; spu_img_restore(ctx, _si); }'
    assert source.count(call)==1
    source='#include "LightingValidation.h"\n#include "MetalLighting.h"\n'+source.replace(call,
        '        bces_light_reference_tap(ctx,ctx->gpr[98]._u32[0]);\n        unsigned capture_token=bces_light_validation_begin(ctx,ctx->gpr[98]._u32[0]);\n'+call+'\n        if(capture_token) bces_light_validation_end(ctx,capture_token);')
    assert source.count('ctx->gpr[2] = spu_ila(0x4578);')==1 # original indirect dispatch reaches registry hook
    put(output/'lighting_spu_reference.c',source)
    backend=(sdk/'libs/video/rsx_metal_backend.m').read_text()
    expected=json.loads((ROOT/'sources.lock.json').read_text())['ios_renderer_overlay']['source_sha256']['libs/video/rsx_metal_backend.m']
    assert hashlib.sha256(backend.encode()).hexdigest()==expected
    section=backend[backend.index('"struct GLight {'):backend.index('/* inFAMOUS 2\'s SSAO job')]
    shader=''.join(ast.literal_eval(line.strip()) for line in section.splitlines() if line.startswith('"'))
    shader=patch_light_shader(shader)
    shader=shader.replace('device const uint* masks [[buffer(1)]])','device const uint* masks [[buffer(1)]], constant uint2& origin [[buffer(2)]])')
    assert shader.count('uint2 px = uint2(i.pos.xy);')==1
    shader=shader.replace('uint2 px = uint2(i.pos.xy);','uint2 local = uint2(i.pos.xy); uint2 px = local + origin;')
    shader=shader.replace('nt.read(px)','nt.read(local)').replace('zt.read(px)','zt.read(local)')
    prefix='#include <metal_stdlib>\nusing namespace metal;\nstruct BOut { float4 pos [[position]]; };\nvertex BOut capture_vs(uint id [[vertex_id]]) { float2 a[3]={float2(-1,-1),float2(3,-1),float2(-1,3)}; BOut o; o.pos=float4(a[id],0,1); return o; }\n'
    put(output/'lighting_validation_msl.inc','static const char* lighting_validation_msl=R"LIGHT_MSL('+prefix+shader+')LIGHT_MSL";\n')
    return Path(unit['object']).name
