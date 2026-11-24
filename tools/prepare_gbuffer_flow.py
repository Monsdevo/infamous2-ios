"""Add bounded, read-only G-buffer DMA and blit probes to the derived build."""
from prepare_job_flow import replace_once


def prepare(output, overlay):
    gcm = output / 'diagnostic_cellGcmSys.c'
    dma = output / 'diagnostic_spu_dma.h'
    engine = overlay / 'libs/video/rsx_draw_engine.c'

    marker = 'static void nv3089_blit(void)\n{'
    source = replace_once(gcm.read_text(), marker, '''// Packed low/high guest EA boundaries, published by the FIFO thread.
uint64_t bces_gbuffer_ranges[2];
uint64_t bces_gbuffer_blit_sequence;
uint32_t bces_gbuffer_event_sequence;

static void bces_gbuffer_publish_range(unsigned surface, u32 io)
{
    const u32 size = 1280u * 720u * 4u;
    const u32 ea = gcm_io2ea(io);
    uint64_t range = 0;
    if (ea && ea <= UINT32_MAX - size && gcm_io2ea(io + size - 1) == ea + size - 1) {
        range = ((uint64_t)(ea + size) << 32) | ea;
        for (u32 page = (io | 0xfffffu) + 1; page < io + size; page += 0x100000u)
            if (gcm_io2ea(page) != ea + (page - io)) { range = 0; break; }
    }
    __atomic_store_n(&bces_gbuffer_ranges[surface], range, __ATOMIC_RELEASE);
}

''' + marker)
    marker = '    /* The source may be a target the register-file engine drew,'
    source = replace_once(source, marker, '''    const u32 trace_io = s_gcm2d.dst_offset + out_y * dst_pitch + out_x * 4u;
    unsigned trace_surface = 0;
    uint64_t trace_blit_start = 0;
    if (PS3_FT_ON() && s_gcm2d.dst_dma == 0xFEED0001u && dst_pitch == 5120u) {
        if (trace_io == 0x06ff3b80u || trace_io == 0x06ff4b80u) trace_surface = 1;
        if (trace_io == 0x07377b80u || trace_io == 0x07378b80u) trace_surface = 2;
        if (trace_surface) {
            bces_gbuffer_publish_range(trace_surface - 1, trace_surface == 1 ? 0x06ff3b80u : 0x07377b80u);
            __atomic_add_fetch(&bces_gbuffer_blit_sequence, 1, __ATOMIC_RELEASE);
            trace_blit_start = ps3_ft_now();
        }
    }
''' + marker)
    source = replace_once(source, 'blit_done:\n', '''blit_done:
    if (trace_blit_start) {
        const uint64_t now = ps3_ft_now();
        const u32 ea = gcm_io2ea(trace_io);
        const uint64_t range = __atomic_load_n(&bces_gbuffer_ranges[trace_surface - 1], __ATOMIC_ACQUIRE);
        ps3_ft_span(460, trace_surface, trace_io, range ? ea : 0, trace_blit_start, now);
        __atomic_add_fetch(&bces_gbuffer_blit_sequence, 1, __ATOMIC_RELEASE);
    }
''')
    gcm.write_text('#include "ps3emu/ps3_ftrace.h"\n' + source)

    marker = '        gm_copy_from(ls_ptr, (const uint8_t*)ea_ptr, size);'
    source = replace_once(dma.read_text(), marker, '''        // Normal GETs and each GETL element use this same copy site.
        if (PS3_FT_ON() && size && ea <= UINT32_MAX && size <= 0x100000000ull - ea) {
            for (unsigned surface = 0; surface < 2; surface++) {
                const uint64_t range = __atomic_load_n(&bces_gbuffer_ranges[surface], __ATOMIC_ACQUIRE);
                if (!range || ea >= (range >> 32) || ea + size <= (uint32_t)range) continue;
                // Preserve the first hit of each role per SPU context and blit boundary.
                static SPU_THREAD_LOCAL struct {
                    uint64_t epoch, boundary;
                    const spu_context* context;
                } seen[16][2][2];
                const unsigned role = bces_ssao_depth_trace_active(spu);
                const uint64_t epoch = g_ps3_ft.start;
                const uint64_t boundary = __atomic_load_n(&bces_gbuffer_blit_sequence, __ATOMIC_ACQUIRE);
                const unsigned lane = spu->spu_id & 15u;
                if (seen[lane][surface][role].epoch == epoch &&
                    seen[lane][surface][role].boundary == boundary &&
                    seen[lane][surface][role].context == spu) continue;
                seen[lane][surface][role].epoch = epoch;
                seen[lane][surface][role].boundary = boundary;
                seen[lane][surface][role].context = spu;
                const uint64_t now = ps3_ft_now();
                const uint32_t tag = __atomic_add_fetch(&bces_gbuffer_event_sequence, 1, __ATOMIC_RELAXED);
                ps3_ft_span(461, tag, (uint32_t)ea, size, now, now);
                ps3_ft_span(462, tag, spu->image_id, spu->resident_ovl, now, now);
                ps3_ft_span(463, tag, spu->pc, spu->gpr[0]._u32[0], now, now);
                ps3_ft_span(464, tag, spu->spu_id, (surface + 1) | (role << 8), now, now);
            }
        }
''' + marker)
    dma.write_text('''#include "ps3emu/ps3_ftrace.h"
#include "SSAODepthBoundary.h"
extern uint64_t bces_gbuffer_ranges[2];
extern uint64_t bces_gbuffer_blit_sequence;
extern uint32_t bces_gbuffer_event_sequence;
''' + source)

    source = engine.read_text()
    start = source.index('int bces_light_allow_job(void* opaque) {')
    end = source.index('\n}\n', start)
    guard = source[start:end]
    anchors = (
        ('    if(!epoch', 1), ('    if(frame>', 2), ('    if(count>', 3),
        ('    for(u32 i=0;i<count', 4), ('    if(state<', 5),
        ('    if(pass>', 6), ('    if(desc[0]', 7),
    )
    for anchor, reason in anchors:
        if guard.count(anchor) != 1:
            raise ValueError(f'Unexpected Metal light guard {anchor}')
        assignment = '    unsigned reason' if reason == 1 else '    reason'
        guard = guard.replace(anchor, f'{assignment}={reason};\n' + anchor, 1)
    guard = replace_once(guard, 'fallback:\n', '''fallback:
    if (PS3_FT_ON()) {
        const uint64_t now = ps3_ft_now();
        ps3_ft_span(465, c->spu_id, reason, epoch, now, now);
    }
''')
    engine.write_text('#include "ps3emu/ps3_ftrace.h"\n' + source[:start] + guard + source[end:])
