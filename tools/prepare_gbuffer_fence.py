"""Reuse a completed depth fence for the immediately following normals readback."""
from prepare_job_flow import replace_once


def prepare(overlay):
    engine = overlay / 'libs/video/rsx_draw_engine.c'
    metal = overlay / 'libs/video/rsx_metal_backend.m'

    source = engine.read_text()
    marker = 'int rsx_draw_engine_write_back(int local, u32 offset, u32 pitch)'
    source = replace_once(source, marker, '''// Both surfaces still publish the original guest bytes at their original blits.
static unsigned bces_gbuffer_fence_enabled;
static uint64_t bces_gbuffer_reused_count, bces_gbuffer_rejected_count;
static uint64_t bces_gbuffer_validated_count, bces_gbuffer_mismatch_count;
static uint64_t bces_gbuffer_depth_ticket; // Owned by the serial RSX consumer.

void bces_gbuffer_fence_set(unsigned enabled) {
    __atomic_store_n(&bces_gbuffer_fence_enabled, !!enabled, __ATOMIC_RELEASE);
}
unsigned bces_gbuffer_fence_mode(void) {
    return __atomic_load_n(&bces_gbuffer_fence_enabled, __ATOMIC_ACQUIRE);
}
uint64_t bces_gbuffer_fence_reused(void) {
    return __atomic_load_n(&bces_gbuffer_reused_count, __ATOMIC_RELAXED);
}
uint64_t bces_gbuffer_fence_rejected(void) {
    return __atomic_load_n(&bces_gbuffer_rejected_count, __ATOMIC_RELAXED);
}

uint64_t bces_gbuffer_fence_validated(void) {
    return __atomic_load_n(&bces_gbuffer_validated_count, __ATOMIC_RELAXED);
}
uint64_t bces_gbuffer_fence_mismatches(void) {
    return __atomic_load_n(&bces_gbuffer_mismatch_count, __ATOMIC_RELAXED);
}

extern uint64_t bces_metal_gbuffer_ticket(void);
extern int bces_metal_gbuffer_reuse(uint64_t ticket, u32 surface, u32 w, u32 h);

''' + marker)
    marker = '    if (eng_gpu_light_blit(local ? RSX_LOCATION_LOCAL : RSX_LOCATION_MAIN, offset, pitch,'
    source = replace_once(source, marker, '''    const int gbuffer = local && dst_local == 0 && pitch == 5120u && eng_gpu_light_on();
    const int depth = gbuffer && dst_offset == s_gl.spec_off;
    const int normals = gbuffer && dst_offset == s_gl.diff_off;
    const uint64_t ticket = normals ? bces_gbuffer_depth_ticket : 0;
    if (depth || normals) bces_gbuffer_depth_ticket = 0;
''' + marker)
    marker = '''            g.be->submit_and_wait(g.be->user, RSX_BE_FLUSH_GUEST_REFERENCE);
            g.be->readback(g.be->user, sf->handle'''
    source = replace_once(source, marker, '''            static u32 checked_surface;
            static int checked_equal;
            int reuse = 0;
            u8* validation = NULL;
            if (normals && sf->w == 1280 && sf->h == 720 && bces_gbuffer_fence_mode()) {
                if (bces_metal_gbuffer_reuse(ticket, sf->handle, sf->w, sf->h)) {
                    if (checked_surface == sf->handle) {
                        reuse = checked_equal;
                    } else {
                        validation = malloc(sf->w * sf->h * 4u);
                        if (validation)
                            g.be->readback(g.be->user, sf->handle, 0, 0, sf->w, sf->h,
                                           validation, sf->w * 4u);
                    }
                }
                if (!validation)
                    __atomic_add_fetch(reuse ? &bces_gbuffer_reused_count : &bces_gbuffer_rejected_count,
                                       1, __ATOMIC_RELAXED);
            }
            if (!reuse) g.be->submit_and_wait(g.be->user, RSX_BE_FLUSH_GUEST_REFERENCE);
            g.be->readback(g.be->user, sf->handle''')
    marker = '            eng_rgba_to_guest_argb(dst, row, g.tex_staging, sf->w, sf->h);'
    source = replace_once(source, marker, '''            if (validation) {
                checked_surface = sf->handle;
                checked_equal = memcmp(validation, g.tex_staging, sf->w * sf->h * 4u) == 0;
                __atomic_add_fetch(checked_equal ? &bces_gbuffer_validated_count : &bces_gbuffer_mismatch_count,
                                   1, __ATOMIC_RELAXED);
                free(validation);
            }
''' + marker)
    marker = '        z->wb_stamp = z->stamp;\n        wrote = 1;'
    source = replace_once(source, marker, marker + '''
        if (depth && z->w == 1280 && z->h == 720 && bces_gbuffer_fence_mode())
            bces_gbuffer_depth_ticket = bces_metal_gbuffer_ticket();''')
    engine.write_text('#include "GBufferFence.h"\n' + source)

    source = metal.read_text()
    marker = 'static void diagnostic_commit(id<MTLCommandBuffer> buffer,uint32_t line)\n{'
    source = replace_once(source, marker, '''// Queue submission serial. The normal readback only borrows a fence
// when no intervening submission can have changed resource visibility.
static uint64_t bces_gbuffer_submit_serial;
static uint64_t bces_gbuffer_completed_flush;

''' + marker.replace('static void', 'static uint64_t') + '''
    const uint64_t submission = __atomic_add_fetch(&bces_gbuffer_submit_serial, 1, __ATOMIC_RELAXED);''')
    source = replace_once(source, '    [buffer commit];\n}', '    [buffer commit];\n    return submission;\n}')
    marker = '            diagnostic_commit(cb, __LINE__);\n            diagnostic_wait(cb, __LINE__);\n            if (ft_w0) {'
    source = replace_once(source, marker, '''            const uint64_t submission = diagnostic_commit(cb, __LINE__);
            diagnostic_wait(cb, __LINE__);
            bces_gbuffer_completed_flush = cb.status == MTLCommandBufferStatusCompleted
                ? submission : 0;
            if (ft_w0) {''')
    marker = 'static const rsx_draw_backend s_engine_backend = {'
    source = replace_once(source, marker, '''uint64_t bces_metal_gbuffer_ticket(void)
{
    const uint64_t submitted = __atomic_load_n(&bces_gbuffer_submit_serial, __ATOMIC_RELAXED);
    return bces_gbuffer_completed_flush == submitted ? submitted : 0;
}

int bces_metal_gbuffer_reuse(uint64_t ticket, u32 surface, u32 w, u32 h)
{
    if (!ticket || ticket != bces_metal_gbuffer_ticket() || s_eng_rec_count != 1) return 0;
    const EngRecord* copy = &s_eng_rec[0];
    if (copy->kind != ENG_REC_COLOR_COPY || copy->rt[0] != surface ||
        copy->resolve_dst == surface) return 0;
    id<MTLTexture> source = eng_obj(surface);
    return source && source.storageMode == MTLStorageModeShared &&
        source.width == w && source.height == h;
}

''' + marker)
    metal.write_text(source)
