#!/usr/bin/env python3
"""iOS-only experimental light route, measured BCES bindings and SPU fallback.

Device replay found the upstream shader omits tile culling: a tile rejected by
all lights is alpha=0 on SPU but alpha=90 on upstream Metal, even with count>0.
The shared tile classifier now restores that distinction in the iOS overlay. Do not
replace this with a per-pixel acc==0 test: unlit pixels in an accepted tile
legitimately pack alpha=90. See docs/optimization-phase1-device-tests-tr.md.
"""
from pathlib import Path
from light_shader_culling import patch_backend

def replace(text,before,after):
    assert text.count(before)==1,before[:100]
    return text.replace(before,after,1)
def put(p,s):
    if not p.exists() or p.read_text()!=s:p.write_text(s)

def prepare_renderer(output):
    p=output/'renderer-overlay/libs/video/rsx_metal_backend.m';s=p.read_text()
    s=patch_backend(s)
    # Preflight pipeline and persistent buffers on the render thread BEFORE any SPU skip.
    start=s.index('    if (!s_eng_light_pso) {',s.index('static u32 eng_light_pass('));end=s.index('    const u32 slot = s_eng_light_param_next++',start)
    resources=s[start:end]
    resources=resources.replace('    if (!s_eng_light_out[0] ||','    if (!s_eng_light_out[0] || !s_eng_light_out[1] ||')
    helper='''int bces_metal_light_prepare(u32 w,u32 h)
{
    const u32 param_bytes=sizeof(rsx_gpu_light_params);
    if(!s_dev || !s_eng_helper_lib || !w || !h) return 0;
'''+resources+'''
    for(unsigned i=0;i<8;i++) {
        if(!s_eng_light_param[i]) s_eng_light_param[i]=[s_dev newBufferWithLength:param_bytes options:MTLResourceStorageModeShared];
        if(!s_eng_light_param[i]) return 0;
    }
    return 1;
}

'''
    s=s[:start]+'    if (!bces_metal_light_prepare(w,h)) return 0;\n'+s[end:]
    pos=s.index('static u32 eng_light_pass(');s=s[:pos]+helper+s[pos:]
    s='#include "MetalLighting.h"\n'+s
    # Match validation's non-fast math rather than changing CPU floating point semantics.
    s=replace(s,'s_eng_helper_lib = [s_dev newLibraryWithSource:kEngHelperMSL options:nil error:&err];',
      'MTLCompileOptions* light_options=[MTLCompileOptions new]; light_options.fastMathEnabled=NO;\n    s_eng_helper_lib = [s_dev newLibraryWithSource:kEngHelperMSL options:light_options error:&err];')
    s=replace(s,'static id<MTLBuffer> s_eng_light_param[8];','static id<MTLBuffer> s_eng_light_param[8], bces_light_masks[8];\nstatic id<MTLComputePipelineState> bces_light_mask_pso;')
    s=replace(s,'    for(unsigned i=0;i<8;i++) {','''    if(!bces_light_mask_pso) {
        NSError* error=nil;
        bces_light_mask_pso=[s_dev newComputePipelineStateWithFunction:[s_eng_helper_lib newFunctionWithName:@"bces_light_tile_mask"] error:&error];
        if(!bces_light_mask_pso){fprintf(stderr,"[gpu light] tile mask PSO failed: %s\\n",error.description.UTF8String);return 0;}
    }
    for(unsigned i=0;i<8;i++) {
        if(!bces_light_masks[i])bces_light_masks[i]=[s_dev newBufferWithLength:((w+31)/32)*((h+39)/40)*4 options:MTLResourceStorageModeShared];
        if(!bces_light_masks[i])return 0;''')
    marker='            MTLRenderPassDescriptor* rp = [MTLRenderPassDescriptor renderPassDescriptor];'
    pos=s.index(marker,s.index('        if (s_eng_rec[i].kind == ENG_REC_LIGHT)'))
    s=s[:pos]+'''            id<MTLBuffer> mask=bces_light_masks[r->clear_flags % 8u];
            if(!mask || !bces_light_mask_pso)continue;
            uint32_t origin[2]={0,0},extent[2]={(uint32_t)zt.width,(uint32_t)zt.height};
            id<MTLComputeCommandEncoder> c=[cb computeCommandEncoder];
            [c setComputePipelineState:bces_light_mask_pso];[c setTexture:zt atIndex:0];
            [c setBuffer:pb offset:0 atIndex:0];[c setBuffer:mask offset:0 atIndex:1];
            [c setBytes:origin length:sizeof origin atIndex:2];[c setBytes:extent length:sizeof extent atIndex:3];
            [c dispatchThreadgroups:MTLSizeMake((extent[0]+31)/32,(extent[1]+39)/40,1) threadsPerThreadgroup:MTLSizeMake(64,1,1)];
            [c endEncoding];
'''+s[pos:]
    start=s.index('        if (s_eng_rec[i].kind == ENG_REC_LIGHT)')
    marker='            [e setFragmentBuffer:pb offset:0 atIndex:0];'
    pos=s.index(marker,start)+len(marker);s=s[:pos]+'\n            [e setFragmentBuffer:mask offset:0 atIndex:1];'+s[pos:]
    put(p,s)
    p=output/'renderer-overlay/libs/video/rsx_draw_engine.c' ;s=p.read_text();s='#include "MetalLighting.h"\n#include "spu_context.h"\n'+s
    marker='static pthread_mutex_t s_gl_lock = PTHREAD_MUTEX_INITIALIZER;'
    s=replace(s,marker,marker+'''
static uint32_t bces_light_input_epoch,bces_light_active_epoch;
static uint64_t bces_light_pass_count,bces_light_binding_count,bces_light_fallback_count,bces_light_faults;
extern uint64_t g_lightskip_tiles;
uint64_t bces_light_fault_count(void) {return __atomic_load_n(&bces_light_faults,__ATOMIC_RELAXED);}
uint64_t bces_light_skipped_tiles(void) {return __atomic_load_n(&g_lightskip_tiles,__ATOMIC_RELAXED);}
uint64_t bces_light_fallback_jobs(void) {return __atomic_load_n(&bces_light_fallback_count,__ATOMIC_RELAXED);}
uint64_t bces_light_rendered_passes(void) {return __atomic_load_n(&bces_light_pass_count,__ATOMIC_RELAXED);}
uint64_t bces_light_bindings(void) {return __atomic_load_n(&bces_light_binding_count,__ATOMIC_RELAXED);}
static u32 bces_ls_word(const uint8_t* p) {return (u32)p[0]<<24|(u32)p[1]<<16|(u32)p[2]<<8|p[3];}
int bces_light_allow_job(void* opaque) {
    const spu_context* c=(const spu_context*)opaque;
    const u32 epoch=__atomic_load_n(&bces_light_input_epoch,__ATOMIC_ACQUIRE);
    // Main's current frame header points at the shared pass iterator.
    const u32 fb=c->gpr[84]._u32[0];
    if(!epoch || !vm_base || fb>0x3ff00u)goto fallback;
    const u32 frame=bces_ls_word(c->ls+0x9c80),lights=bces_ls_word(c->ls+0x9cb0);
    if(frame>0x3ff00u)goto fallback;
    const u32 count=bces_ls_word(c->ls+frame+0x90);
    if(count>128 || lights>0x40000u || (uint64_t)lights+48ull*count>0x40000u)goto fallback;
    for(u32 i=0;i<count;i++) {u32 type=bces_ls_word(c->ls+lights+48u*i+0x14);if(type!=1 && type!=2)goto fallback;}
    const u32 state=bces_ls_word(c->ls+fb);
    if(state<0x10000u || state>0x0fffff80u)goto fallback;
    const uint8_t* header=vm_base+state;
    const u32 pass=(u32)header[0]<<8|header[1];
    const u32 table=bces_ls_word(header+12);
    if(pass>8 || table<0x10000u || table>0x0ffff000u)goto fallback;
    const uint8_t* desc=vm_base+table+128u*pass;
    if(desc[0]!=40 || desc[1]!=18 ||
       bces_ls_word(desc+0x48)!=0x00200028u || bces_ls_word(desc+0x58)!=0x00200028u ||
       bces_ls_word(desc+0x68)!=0x00200028u || bces_ls_word(desc+0x78)!=0x00200028u ||
       bces_ls_word(desc+0x4c)!=0x406u || bces_ls_word(desc+0x5c)!=0x405u ||
       bces_ls_word(desc+0x6c)!=0x405u || bces_ls_word(desc+0x7c)!=0x406u || bces_ls_word(desc+0x44)!=0x1400u ||
       bces_ls_word(desc+0x54)!=0x1400u || bces_ls_word(desc+0x64)!=0x1400u ||
       bces_ls_word(desc+0x74)!=0x1400u ||
       bces_ls_word(desc+0x40)!=bces_gcm_io_ea(0x06ff3b80u) ||
       bces_ls_word(desc+0x50)!=bces_gcm_io_ea(0x06ff3b80u) ||
       bces_ls_word(desc+0x60)!=bces_gcm_io_ea(0x07377b80u) ||
       bces_ls_word(desc+0x70)!=bces_gcm_io_ea(0x07377b80u))goto fallback;
    // Current source images and persistent GPU resources are now available.
    __atomic_store_n(&bces_light_active_epoch,epoch,__ATOMIC_RELEASE);return 1;
fallback:
    __atomic_add_fetch(&bces_light_fallback_count,1,__ATOMIC_RELAXED);return 0;
}
''')
    marker='    if (is_n && dst_offset == s_gl.diff_off) {'
    s=replace(s,marker,marker+'''
        __atomic_store_n(&bces_light_input_epoch,0,__ATOMIC_RELEASE);
        __atomic_store_n(&bces_light_active_epoch,0,__ATOMIC_RELEASE);''')
    marker='    if (s_gl.have == 3u) { s_gl.have = 0; s_gl.in_seq++; }'
    s=replace(s,marker,'''    if (s_gl.have == 3u) {
        s_gl.have=0;s_gl.in_seq++;
        if(!__atomic_load_n(&bces_light_faults,__ATOMIC_RELAXED) && s_gl.w==1280 && s_gl.h==720 && bces_metal_light_prepare(s_gl.w,s_gl.h))
            __atomic_store_n(&bces_light_input_epoch,s_gl.in_seq,__ATOMIC_RELEASE);
    }''')
    marker='    if (!s_gl.in_seq || !s_gl.n_tex || !s_gl.z_tex) return 0;'
    s=replace(s,marker,marker+'\n    if(__atomic_load_n(&bces_light_active_epoch,__ATOMIC_ACQUIRE)!=s_gl.in_seq) return 0;')
    s=replace(s,'        if (!diff || !spec) return 0;','''        if (!diff || !spec) {
            __atomic_add_fetch(&bces_light_faults,1,__ATOMIC_RELAXED);
            __atomic_store_n(&bces_light_input_epoch,0,__ATOMIC_RELEASE);
            __atomic_store_n(&bces_light_active_epoch,0,__ATOMIC_RELEASE);
            fprintf(stderr,"[gpu light] output failure; frame invalid; SPU restored for future frames\\n");return 0;
        }''')
    marker='        s_gl.out_diff = diff; s_gl.out_spec = spec; s_gl.out_seq = s_gl.in_seq;'
    s=replace(s,marker,marker+'\n        __atomic_add_fetch(&bces_light_pass_count,1,__ATOMIC_RELAXED);')
    marker='    return view ? view : tex;'
    s=replace(s,marker,'    __atomic_add_fetch(&bces_light_binding_count,1,__ATOMIC_RELAXED);\n'+marker)
    put(p,s)
    p=output/'diagnostic_cellGcmSys.c';s=p.read_text();s+='\nuint32_t bces_gcm_io_ea(uint32_t io) { return gcm_io2ea(io); }\n';put(p,s)

def prepare_hook(text):
    text='#include "MetalLighting.h"\n'+text
    start=text.index('void infamous2_gpu_light_install(void)')
    text=text[:start]+'''// Only the whole tile walk is replaced. Reference tiles remain callable for fallback.
void infamous2_gpu_light_install(void) {
    const char* e=getenv("PS3RECOMP_ENG_GPU_LIGHT");if(!e || !*e)return;
    const spu_fn old=spu_replace_function(LIGHT_JOB_IMAGE,0x4578u,light_skip_4578);
    if(old!=jobmod_c6e7383dc013_e5400_spu_func_00004578) {
        if(old)spu_replace_function(LIGHT_JOB_IMAGE,0x4578u,old);
        fprintf(stderr,"[gpu light] BCES walk guard failed; reference kept\\n");return;
    }
    fprintf(stderr,"[gpu light] BCES conditional Metal walk installed; SSAO remains SPU\\n");
}
void bces_light_reference_tap(void* opaque,uint32_t target) {
    spu_context* c=(spu_context*)opaque;
    if(target!=0x4ac8 || !getenv("PS3RECOMP_ENG_GPU_LIGHT") || !*getenv("PS3RECOMP_ENG_GPU_LIGHT"))return;
    u32 p=c->gpr[3]._u32[0];
    if(p<=0x3ffe4u && ls_u32(c,p+4)==0 && ls_u32(c,p+8)==0)light_tap_constants(c);
}
'''
    marker='void light_skip_4578(spu_context* ctx)\n{'
    text=replace(text,marker,marker+'''
    if(!bces_light_allow_job(ctx)) {
        jobmod_c6e7383dc013_e5400_spu_func_00004578(ctx);return;
    }''')
    return text
