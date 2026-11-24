"""BCES iOS SSAO overlay; no pinned source/archive modifications."""
from pathlib import Path
import hashlib
from prepare_metal_lighting import replace,put
ROOT=Path(__file__).resolve().parents[1]
MODULES={'0087D500':'0081ED00','0087F880':'00821080','0087D880':'0081F080','0087E480':'0081FC80','0087EC80':'00820480'}
def depth_reference_source(output,report):
    unit=next(u for u in report['units'] if 'jobmod_e6fe749031f8_e2060/spu_recomp.c' in u['source'])
    source=Path(unit['source']).read_text()
    assert hashlib.sha256(source.encode()).hexdigest()==unit['sha256']
    start=source.index('void jobmod_e6fe749031f8_e2060_spu_func_00004AAC(spu_context* ctx) {')
    end=source.index('\nvoid ',start+1)
    body=source[start:end]
    marker='        ctx->gpr[25] = spu_ls_read128(ctx, ctx->gpr[27]._u32[0] + ctx->gpr[10]._u32[0]);'
    body=replace(body,marker,marker+'''
        // A non-depth pass is not claimed by the GPU route's depth-only call.
        // The ordinary 0xFFFE continuation restores IRQ state and both stacks.
        if(bces_ssao_depth_claim_guard(ctx)) {
            ctx->pc=0x4BF0;
            g_spu_trampoline_fn=jobmod_e6fe749031f8_e2060_spu_func_00004BF0;return;
        }''')
    source='#include "SSAODepthBoundary.h"\n'+source[:start]+body+source[end:]
    put(output/'ssao_spu_reference.c',source)
    return Path(unit['object']).name
def prepare(output,port):
    for name in ('ssao_gpu.h','ssao_gpu.c'):
        s=(port/'infamous2-lle'/name).read_text()
        if name.endswith('.h'):
            for a,b in MODULES.items():s=s.replace('0x'+a+'u','0x'+b+'u')
        put(output/name,s)
    p=output/'renderer-overlay/libs/video/rsx_metal_backend.m';s=p.read_text()
    start=s.index('    if (!s_eng_ssao_pso[0]) {',s.index('static u32 eng_ssao_pass('));end=s.index('    const u32 slot = s_eng_ssao_param_next++',start)
    resources=s[start:end].replace('if (!s_eng_ssao_pso[0]) {','if (!s_eng_ssao_pso[0] || !s_eng_ssao_pso[1] || !s_eng_ssao_pso[2] || !s_eng_ssao_pso[3] || !s_eng_ssao_pso[4]) {')
    helper='''int bces_metal_ssao_prepare(u32 fw,u32 fh,u32 hw,u32 hh,u32 bytes) {
    if(!s_dev || !s_eng_helper_lib || fw!=1280 || fh!=720 || hw!=640 || hh!=360 || bytes!=320)return 0;
'''+resources+'''
    for(unsigned i=0;i<8;i++) {
        if(!s_eng_ssao_param[i])s_eng_ssao_param[i]=[s_dev newBufferWithLength:bytes options:MTLResourceStorageModeShared];
        if(!s_eng_ssao_param[i])return 0;
    }
    return 1;
}
'''
    s=s[:start]+'    if(!bces_metal_ssao_prepare(fw,fh,hw,hh,const_bytes))return 0;\n'+s[end:]
    pos=s.index('static u32 eng_ssao_pass(');s=s[:pos]+helper+s[pos:];s='#include "MetalSSAO.h"\n'+s
    s=replace(s,'    memcpy([s_eng_ssao_param[slot] contents], consts, const_bytes);','    if(!s_eng_ssao_param[slot])return 0;\n    memcpy([s_eng_ssao_param[slot] contents], consts, const_bytes);')
    put(p,s)
    p=output/'renderer-overlay/libs/video/rsx_draw_engine.c';s=p.read_text();s='#include "MetalSSAO.h"\n'+s
    anchor='static uint32_t bces_light_input_epoch,bces_light_active_epoch;'
    s=replace(s,anchor,anchor+'\nstatic uint32_t bces_ssao_ready_epoch,bces_ssao_active_epoch;\nstatic uint64_t bces_ssao_pass_count,bces_ssao_binding_count,bces_ssao_fault_count;\nuint64_t bces_ssao_passes(void){return __atomic_load_n(&bces_ssao_pass_count,__ATOMIC_RELAXED);}\nuint64_t bces_ssao_bindings(void){return __atomic_load_n(&bces_ssao_binding_count,__ATOMIC_RELAXED);}\nuint64_t bces_ssao_faults(void){return __atomic_load_n(&bces_ssao_fault_count,__ATOMIC_RELAXED);}')
    marker='        __atomic_store_n(&bces_light_input_epoch,0,__ATOMIC_RELEASE);'
    # Reset belongs to the first normal-copy boundary only, not late light failure.
    pos=s.index(marker,s.index('    if (is_n && dst_offset == s_gl.diff_off) {'))
    s=s[:pos]+'        __atomic_store_n(&bces_ssao_ready_epoch,0,__ATOMIC_RELEASE);\n        __atomic_store_n(&bces_ssao_active_epoch,0,__ATOMIC_RELEASE);\n'+s[pos:]
    marker='        s_gl.have=0;s_gl.in_seq++;'
    s=replace(s,marker,marker+'''
        const char* ssao=getenv("PS3RECOMP_ENG_GPU_SSAO");
        if(ssao && *ssao && !__atomic_load_n(&bces_ssao_fault_count,__ATOMIC_RELAXED) &&
           bces_metal_ssao_prepare(s_gl.w,s_gl.h,s_gl.w/2,s_gl.h/2,320))
            __atomic_store_n(&bces_ssao_ready_epoch,s_gl.in_seq,__ATOMIC_RELEASE);''')
    s=replace(s,'      return ssao || (nowb && is_n); }','      (void)ssao;(void)nowb;return 0; } // iOS: retain both guest input writebacks, including SPU fallback')
    marker='static u32 eng_gpu_ssao_texture(const rsx_dsp_texture* t)'
    api='''int bces_ssao_publish(const void* constants,u32 bytes,u32 output_offset,u32 state,u32 half_depth) {
    const u32 epoch=__atomic_load_n(&bces_ssao_ready_epoch,__ATOMIC_ACQUIRE);
    if(!epoch || bytes!=320)return 0;
    pthread_mutex_lock(&s_gl_lock);
    if(epoch!=__atomic_load_n(&bces_ssao_ready_epoch,__ATOMIC_ACQUIRE)) {pthread_mutex_unlock(&s_gl_lock);return 0;}
    memcpy(s_gs.consts,constants,bytes);s_gs.bytes=bytes;
    s_gs.fw=1280;s_gs.fh=720;s_gs.hw=640;s_gs.hh=360;s_gs.have=1;s_gs.off=output_offset;
#if BCES_HALF_DEPTH_PROBE
    bces_half_depth_admit(epoch,state,half_depth);
#else
    (void)state;(void)half_depth;
#endif
    __atomic_store_n(&bces_ssao_active_epoch,epoch,__ATOMIC_RELEASE);
    pthread_mutex_unlock(&s_gl_lock);return 1;
}

'''
    s=replace(s,marker,api+marker)
    # Output address comes from the validated BCES pass table, never from an upstream VRAM guess.
    s=replace(s,'s_gs.off = (u32)strtoul(e, 0, 16);','/* output offset published from validated BCES pass table */')
    s=replace(s,'    if (!s_gs.on || t->location != RSX_LOCATION_LOCAL || t->offset != s_gs.off) return 0;',
      '    if (!s_gs.on || !__atomic_load_n(&bces_ssao_active_epoch,__ATOMIC_ACQUIRE) || t->location != RSX_LOCATION_LOCAL) return 0;\n    if(__atomic_load_n(&bces_ssao_active_epoch,__ATOMIC_ACQUIRE)!=s_gl.in_seq || t->offset!=s_gs.off)return 0;')
    s=replace(s,'        if (!out) return 0;','''        if (!out) {
            __atomic_add_fetch(&bces_ssao_fault_count,1,__ATOMIC_RELAXED);
            __atomic_store_n(&bces_ssao_ready_epoch,0,__ATOMIC_RELEASE);
            fprintf(stderr,"[bces SSAO] GPU output failed; current frame invalid, future jobs use SPU\\n");return 0;
        }''')
    s=replace(s,'        s_gs.out = out; s_gs.out_seq = s_gl.in_seq;','        s_gs.out = out; s_gs.out_seq = s_gl.in_seq;\n        __atomic_add_fetch(&bces_ssao_pass_count,1,__ATOMIC_RELAXED);')
    s=replace(s,'    return s_gs.out;','    __atomic_add_fetch(&bces_ssao_binding_count,1,__ATOMIC_RELAXED);\n    return s_gs.out;')
    put(p,s)
def hook(s):
    s='#include "MetalSSAO.h"\n#include "SSAODepthBoundary.h"\n'+s
    marker='void ssao_skip_4330(spu_context* ctx)\n{'
    s=replace(s,marker,'void jobmod_e6fe749031f8_e2060_spu_func_00004330(spu_context* ctx);\n'+marker+'''
    bces_ssao_depth_reset_scope(ctx);
    if(!bces_ssao_allow_job(ctx)) {jobmod_e6fe749031f8_e2060_spu_func_00004330(ctx);return;}
''')
    a=s.index('    ssao_tap_frame(ctx);',s.index('static uint32_t ssao_skip_step'))
    # Preserve actual half-depth output for any original CPU/RSX consumer.
    s=s[:a]+'''    if(ls16(ctx,0x6500)==0) {
        BCESSSAODepthScope previous=bces_ssao_depth_enter(ctx,param._u32[0]);
        ctx->gpr[3]=param;lcall(ctx,SJ(00005258),0x437C);
        bces_ssao_depth_leave(previous);return ctx->gpr[3]._u32[0];
    }
'''+s[a+len('    ssao_tap_frame(ctx);'):]
    s=replace(s,'void SJ(00004598)(spu_context*);','void SJ(00005258)(spu_context*);\nvoid SJ(00004598)(spu_context*);')
    s+='\nuint64_t bces_ssao_skipped_tiles(void){return __atomic_load_n(&g_ssaoskip_tiles,__ATOMIC_RELAXED);}\n'
    return s
