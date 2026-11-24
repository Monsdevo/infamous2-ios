"""Instrument access sites in the derived iPhone build for SPU result tracing."""
import re


GUARD = '(__atomic_load_n(&bces_critical_flow_enabled, __ATOMIC_RELAXED) && PS3_FT_ON())'
INCLUDES = '#include "CriticalJobFlow.h"\n#include "ps3emu/ps3_ftrace.h"\n'


def replace_once(source, marker, replacement):
    if source.count(marker) != 1:
        raise ValueError(f'Unexpected job flow source marker: {marker}')
    return source.replace(marker, replacement, 1)


def spu_phases(source):
    prefix = 'jobmod_1774dd41c4e8_e14f90_spu_func_'

    def insert(pc, phase, entering, after_retry=False, before_return=False):
        nonlocal source
        signature = f'void {prefix}{pc:08X}(spu_context* ctx) {{\n'
        start = source.index(signature) + len(signature)
        end = source.index('\n}\n', start)
        body = source[start:end]
        position = 0
        if after_retry:
            position = body.index('\n', body.index('return; }')) + 1
        if before_return:
            position = body.rindex('        SPU_RET(ctx);')
        probe = f'        if (__atomic_load_n(&bces_critical_phases_enabled, __ATOMIC_RELAXED)) bces_critical_phase(ctx, {phase}, {entering});\n'
        source = source[:start] + body[:position] + probe + body[position:] + source[end:]

    insert(0x12C50, 0, 1)
    pattern = r'(        ctx->gpr\[0\] = spu_link\(0x13F9C\); [^\n]+\n)'
    source, count = re.subn(pattern, r'\1        if (__atomic_load_n(&bces_critical_phases_enabled, __ATOMIC_RELAXED)) bces_critical_phase(ctx, 0, 0);\n', source)
    if count != 1:
        raise ValueError('Unexpected command builder return')
    insert(0x43D0, 1, 1, after_retry=True)
    insert(0x4460, 1, 0, after_retry=True)
    insert(0x13030, 2, 1)
    insert(0x130C8, 2, 0, after_retry=True)
    insert(0x13BC8, 3, 1)
    insert(0x13C00, 3, 0)
    insert(0x14160, 4, 1)
    insert(0x142B8, 4, 0, before_return=True)
    return '#include "CriticalJobFlow.h"\n' + source


def dma(source):
    get_copy = '        gm_copy_from(ls_ptr, (const uint8_t*)ea_ptr, size);'
    source = replace_once(source, get_copy, f'''        const int flow_read = {GUARD} &&
            bces_critical_flow_transfer(spu, ea, size, 0);
        const uint64_t flow_start = flow_read ? ps3_ft_now() : 0;
{get_copy}
        if (flow_read) bces_critical_flow_dma(spu, (uint32_t)ea, size, lsa, NULL, flow_start, ps3_ft_now());''')
    marker = '        const int diagnostic_watch=diagnostic_label || diagnostic_progress;'
    source = replace_once(source, marker, f'''        const int flow_write = {GUARD} &&
            bces_critical_flow_transfer(spu, ea, size, 1);
        const int diagnostic_watch=diagnostic_label || diagnostic_progress || flow_write;''')
    marker = '        /* Tell whoever is listening where this PUT landed.'
    return INCLUDES + replace_once(source, marker, '''        if (diagnostic_t0 && flow_write) bces_critical_flow_dma(spu, (uint32_t)ea,
            size, lsa, ls_ptr, diagnostic_t0, diagnostic_t1);
''' + marker)


def loader(source):
    for width in (1, 2, 4, 8):
        pattern = rf'(uint{width * 8}_t\s+vm_read{width * 8}\s*\(uint64_t a\) \{{ if \(vm_oob\(\(uint32_t\)a,{width}\)\) return 0;)'
        probe = f'''\n    if ({GUARD} && g_active_ctx)
        bces_critical_flow_ppu((uint32_t)a, {width}, (uintptr_t)__builtin_return_address(0),
                               (uint32_t)g_active_ctx->thread_id);'''
        source, count = re.subn(pattern, lambda match: match[0] + probe, source)
        if count != 1:
            raise ValueError(f'Unexpected vm_read{width * 8} implementation')
    return INCLUDES + source


def fifo(source):
    for marker, address, word, header in (
        ('        u32 w = vm_read32(ea);\n        /* Only remember', 'ea', 'w', 1),
        ('                    u32 v = vm_read32(dea);', 'dea', 'v', 0),
        ('                const u32 dw = vm_read32(dea);', 'dea', 'dw', 0),
    ):
        first, *rest = marker.split('\n', 1)
        indent = first[:len(first) - len(first.lstrip())]
        probe = f'{indent}if ({GUARD}) bces_critical_flow_fifo({address}, {word}, {header});'
        source = replace_once(source, marker, '\n'.join((first, probe, *rest)))
    marker = '        /* Only remember offsets BELOW put'
    source = replace_once(source, marker, '''        // The drain owns this state under the FIFO lock.
        static uint64_t phase_epoch, phase_park_start;
        static u32 phase_park_ea, phase_park_word;
        if (__atomic_load_n(&bces_critical_phases_enabled, __ATOMIC_RELAXED) && PS3_FT_ON()) {
            const uint64_t now = ps3_ft_now();
            if (phase_epoch != g_ps3_ft.start) {
                phase_epoch = g_ps3_ft.start;
                phase_park_start = 0;
            }
            if (phase_park_start && (ea != phase_park_ea || w != phase_park_word)) {
                if (ea == phase_park_ea) {
                    ps3_ft_span(444, w, ea, s_fifo_getoff, phase_park_start, now);
                } else {
                    ps3_ft_span(446, 0, phase_park_ea, ea, phase_park_start, now);
                }
                phase_park_start = 0;
            }
            if (!phase_park_start && (w >> 29) == 1 &&
                (w & 0x1FFFFFFCu) == s_fifo_getoff && put != s_fifo_getoff) {
                phase_park_start = now;
                phase_park_ea = ea;
                phase_park_word = w;
                ps3_ft_span(445, w, ea, s_fifo_getoff, now, now);
            }
        }
''' + marker)
    return INCLUDES + source


def renderer(source):
    marker = 'static const u8* eng_edge_vertex_ptr('
    helper = f'''static void eng_job_flow_read(const u8* p, u32 bytes, u32 kind) {{
    if ({GUARD} && vm_base && p && (uintptr_t)p >= (uintptr_t)vm_base &&
        (uintptr_t)p - (uintptr_t)vm_base <= UINT32_MAX)
        bces_critical_flow_rsx((u32)((uintptr_t)p - (uintptr_t)vm_base), bytes, kind);
}}

static const u8* eng_job_flow_ptr(void* user, u32 location, u32 offset, u32 bytes) {{
    const u8* p = eng_guest_ptr(user, location, offset, bytes);
    eng_job_flow_read(p, bytes, 3);
    return p;
}}

'''
    source = replace_once(source, marker, helper + marker)
    for kind in (1, 2):
        marker = f'    if(PS3_FT_ON())bces_edge_flow_reader(p,bytes,{kind},location,offset);'
        source = replace_once(source, marker, f'    eng_job_flow_read(p, bytes, {kind});\n' + marker)
    # The const pointer requests below serve read paths. Writable readback
    # destinations go through the unchanged eng_guest_ptr entry point.
    source, count = re.subn(r'(const u8\* (?:src|uc|fp_uc|q)\s*=\s*[^;\n]*)\beng_guest_ptr\(',
                            r'\1eng_job_flow_ptr(', source)
    if count < 8:
        raise ValueError('Expected renderer read paths were not found')
    # Fragment microcode fetch can request a larger second range.
    source = replace_once(source, 'if (size) uc = eng_guest_ptr(', 'if (size) uc = eng_job_flow_ptr(')
    return INCLUDES + source
