#include "RSXLegacyFastPath.h"
#include "rsx_commands.h"
#include <stdatomic.h>
#include <stdlib.h>

// The audited implementation is pinned by prepare_rsx_legacy.py. Only the
// unused legacy state's writes are skipped. Unknowns and all functional
// side effects retain the original processor, including its semaphore state.
static int state_only(uint32_t m) {
    if (m&3u) return 0;
    if ((m>=0x900u&&m<=0x97Cu)||(m>=0xA20u&&m<=0xA3Cu)||
        (m>=NV4097_SET_TRANSFORM_PROGRAM&&m<NV4097_SET_TRANSFORM_PROGRAM+32u*4u)||
        (m>=0x1680u&&m<=0x16BCu)||(m>=0x1740u&&m<=0x177Cu)||
        (m>=NV4097_SET_TEXTURE_CONTROL3&&m<NV4097_SET_TEXTURE_CONTROL3+RSX_MAX_TEXTURES*4u)||
        (m>=0x1A00u&&m<0x1A00u+RSX_MAX_TEXTURES*0x20u)||
        (m>=0x1C00u&&m<0x1C00u+RSX_MAX_VERTEX_ATTRIBS*16u)||
        (m>=NV4097_SET_TRANSFORM_CONSTANT&&m<NV4097_SET_TRANSFORM_CONSTANT+NV4097_SET_TRANSFORM_CONSTANT_DWORDS*4u)) return 1;
    switch(m) {
        case NV4097_SET_SURFACE_FORMAT: case NV4097_SET_SURFACE_CLIP_HORIZONTAL:
        case NV4097_SET_SURFACE_CLIP_VERTICAL: case NV4097_SET_SURFACE_COLOR_AOFFSET:
        case NV4097_SET_SURFACE_COLOR_BOFFSET: case NV4097_SET_SURFACE_COLOR_COFFSET:
        case NV4097_SET_SURFACE_COLOR_DOFFSET: case NV4097_SET_SURFACE_ZETA_OFFSET:
        case NV4097_SET_SURFACE_COLOR_TARGET: case NV4097_SET_SURFACE_PITCH_A:
        case NV4097_SET_SURFACE_PITCH_B: case NV4097_SET_SURFACE_PITCH_C:
        case NV4097_SET_SURFACE_PITCH_D: case NV4097_SET_SURFACE_PITCH_Z:
        case NV4097_SET_VIEWPORT_HORIZONTAL: case NV4097_SET_VIEWPORT_VERTICAL:
        case NV4097_SET_SCISSOR_HORIZONTAL: case NV4097_SET_SCISSOR_VERTICAL:
        case NV4097_SET_COLOR_MASK: case NV4097_SET_ALPHA_TEST_ENABLE:
        case NV4097_SET_ALPHA_FUNC: case NV4097_SET_ALPHA_REF:
        case NV4097_SET_BLEND_ENABLE: case NV4097_SET_BLEND_FUNC_SFACTOR:
        case NV4097_SET_BLEND_FUNC_DFACTOR: case NV4097_SET_BLEND_EQUATION:
        case NV4097_SET_DEPTH_TEST_ENABLE: case NV4097_SET_DEPTH_FUNC:
        case NV4097_SET_DEPTH_MASK: case NV4097_SET_STENCIL_TEST_ENABLE:
        case NV4097_SET_STENCIL_FUNC: case NV4097_SET_STENCIL_FUNC_REF:
        case NV4097_SET_STENCIL_FUNC_MASK: case NV4097_SET_STENCIL_OP_FAIL:
        case NV4097_SET_STENCIL_OP_ZFAIL: case NV4097_SET_STENCIL_OP_ZPASS:
        case NV4097_SET_CULL_FACE_ENABLE: case NV4097_SET_CULL_FACE:
        case NV4097_SET_FRONT_FACE: case NV4097_SET_SHADER_PROGRAM:
        case NV4097_SET_SHADER_CONTROL: case NV4097_SET_TRANSFORM_PROGRAM_LOAD:
        case NV4097_SET_TRANSFORM_PROGRAM_START: case NV4097_SET_VERTEX_ATTRIB_OUTPUT_MASK:
        case NV4097_SET_TRANSFORM_CONSTANT_LOAD: case NV4097_SET_VERTEX_ATTRIB_INPUT_MASK:
        case NV4097_SET_TRANSFORM_BRANCH_BITS: case 0x1FC0u:
            return 1;
        default: return 0;
    }
}

// 0 unconfigured, 1 explicitly off, 2 requested on, 3 diagnostic full path.
static _Atomic unsigned mode;
static uint64_t methods,skipped,forwarded,syncs,draws;
static _Atomic uint64_t published[5];
static _Atomic unsigned sequence;

void bces_rsx_legacy_configure(int enabled) {
    unsigned selected=enabled?2u:1u;
    if(enabled) {
        // A legacy state-dependent debug dump needs all shadow state. The
        // original code treats presence (including "0") as enabled for many.
        const char* keys[]={"RSX_TRACE","SURFDBG","RTT_DUMP","VDATA_DBG",
            "LOAD_DBG","TCONST_DBG","TCONST_MAX","TCONST_ALL","TCONST_SLOT",
            "TCONST_AFTER","SEQ_DBG","MVPDBG","RSX_LABELSTAT","GCM_SEMA_TRACE"};
        for(unsigned i=0;i<sizeof keys/sizeof keys[0];i++)
            if(getenv(keys[i])) { selected=3;break; }
    }
    unsigned expected=0;
    atomic_compare_exchange_strong_explicit(&mode,&expected,selected,
                                          memory_order_release,memory_order_relaxed);
}

void bces_rsx_legacy_method(rsx_state* state,uint32_t method,uint32_t data,
                            int dispatch_active) {
    methods++;
    if(atomic_load_explicit(&mode,memory_order_relaxed)==2u && dispatch_active &&
       state_only(method) && rsx_get_backend()==NULL) {
        skipped++;return;
    }
    forwarded++;
    if(method==0x1D6Cu||method==0x1D70u||method==0x1D74u||method==0x50u)syncs++;
    if(method==NV4097_DRAW_ARRAYS||method==NV4097_DRAW_INDEX_ARRAY)draws++;
    // Retain BEGIN_END, clear values, index state and draws too. This keeps
    // milestones/first-draw logs and potential legacy callbacks in one place.
    (void)rsx_process_method(state,method,data);
}

void bces_rsx_legacy_publish(void) {
    atomic_fetch_add_explicit(&sequence,1,memory_order_acq_rel);
    const uint64_t values[]={methods,skipped,forwarded,syncs,draws};
    for(unsigned i=0;i<5;i++)atomic_store_explicit(published+i,values[i],memory_order_relaxed);
    atomic_fetch_add_explicit(&sequence,1,memory_order_release);
}

BCESRSXLegacyStats bces_rsx_legacy_stats(void) {
    BCESRSXLegacyStats s={0};unsigned m=atomic_load_explicit(&mode,memory_order_acquire);
    s.configured=m!=0;s.requested=m==2||m==3;s.enabled=m==2;s.debug_fallback=m==3;
    for(;;) {
        unsigned a=atomic_load_explicit(&sequence,memory_order_acquire);if(a&1u)continue;
        s.methods=atomic_load_explicit(published,memory_order_relaxed);
        s.state_skipped=atomic_load_explicit(published+1,memory_order_relaxed);
        s.legacy_forwarded=atomic_load_explicit(published+2,memory_order_relaxed);
        s.sync_forwarded=atomic_load_explicit(published+3,memory_order_relaxed);
        s.draw_forwarded=atomic_load_explicit(published+4,memory_order_relaxed);
        if(a==atomic_load_explicit(&sequence,memory_order_acquire))return s;
    }
}
