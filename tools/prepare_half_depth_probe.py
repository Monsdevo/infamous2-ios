"""Compare the original guest half-depth with the same Metal SSAO generation."""
import re
from prepare_job_flow import replace_once

INCLUDES = '#include "HalfDepthProbe.h"\n#include "ps3emu/ps3_ftrace.h"\n'


def loader(source):
    for width in (1, 2, 4, 8):
        pattern = rf'(uint{width * 8}_t\s+vm_read{width * 8}\s*\(uint64_t a\) \{{ if \(vm_oob\(\(uint32_t\)a,{width}\)\) return 0;)'
        line = f'''
    if (PS3_FT_ON() && g_active_ctx)
        bces_half_depth_read(a, {width}, 473, (uint32_t)g_active_ctx->thread_id,
                             (uint32_t)(uintptr_t)__builtin_return_address(0));'''
        source, count = re.subn(pattern, lambda match: match[0] + line, source)
        if count != 1:
            raise ValueError(f'Unexpected vm_read{width * 8} implementation')
    return INCLUDES + source


def prepare(output, overlay):
    dma = output / 'diagnostic_spu_dma.h'
    marker = '        gm_copy_from(ls_ptr, (const uint8_t*)ea_ptr, size);'
    dma.write_text(INCLUDES + replace_once(dma.read_text(), marker, '''
        if (PS3_FT_ON())
            bces_half_depth_read(ea, size, 472, (uint32_t)spu->resident_ovl, spu->pc);
''' + marker))
    engine = overlay / 'libs/video/rsx_draw_engine.c'
    source = engine.read_text()
    marker = '        const u32 out = g.be->ssao_pass(g.be->user, s_gl.z_tex, s_gl.n_tex, c, bytes, fw, fh, hw, hh);'
    source = replace_once(source, marker, '''        bces_half_depth_select(s_gl.in_seq);
''' + marker + '''
        bces_half_depth_select(0);''')
    marker = 'static const u8* eng_edge_vertex_ptr('
    helper = '''static const u8* eng_half_depth_read_ptr(void* user, u32 location, u32 offset, u32 bytes) {
    const u8* p = eng_guest_ptr(user, location, offset, bytes);
    if (PS3_FT_ON() && p && vm_base && (uintptr_t)p >= (uintptr_t)vm_base)
        bces_half_depth_read((uintptr_t)p - (uintptr_t)vm_base, bytes, 474, location, offset);
    return p;
}

'''
    source, count = re.subn(r'(const u8\* (?:p|src|uc|fp_uc|q)\s*=\s*[^;\n]*)\beng_guest_ptr\(',
                            r'\1eng_half_depth_read_ptr(', source)
    if count < 10:
        raise ValueError('Expected renderer read paths were not found')
    source = replace_once(source, 'if (size) uc = eng_guest_ptr(', 'if (size) uc = eng_half_depth_read_ptr(')
    engine.write_text(INCLUDES + replace_once(source, marker, helper + marker))

    metal = overlay / 'libs/video/rsx_metal_backend.m'
    source = metal.read_text()
    marker = '} EngRecord;'
    source = replace_once(source, marker, '    u32 half_depth_probe_frame;\n' + marker)
    marker = '    r->kind = ENG_REC_SSAO;'
    source = replace_once(source, marker, marker + '\n    r->half_depth_probe_frame = bces_half_depth_claim();')
    start = source.index('        if (s_eng_rec[i].kind == ENG_REC_SSAO)')
    end = source.index('        if (s_eng_rec[i].kind == ENG_REC_LIGHT)', start)
    section = source[start:end]
    marker = '            if (!zt || !nt || !hd || !a || !b || !out || !pb) continue;'
    section = replace_once(section, marker, '''            if (!zt || !nt || !hd || !a || !b || !out || !pb) {
                bces_half_depth_complete(r->half_depth_probe_frame, NULL);
                continue;
            }
            int encoded_depth = 0;''')
    section = replace_once(section, '                [e endEncoding];', '''                [e endEncoding];
                if (k == 0) encoded_depth = 1;''')
    marker = '            continue;\n        }'
    section = replace_once(section, marker, '''            const u32 probe = r->half_depth_probe_frame;
            if (probe) {
                id<MTLBuffer> buffer = nil;
                if (encoded_depth && hd.width == 640 && hd.height == 360 && hd.pixelFormat == MTLPixelFormatR32Float)
                    buffer = [s_dev newBufferWithLength:BCES_HALF_DEPTH_BYTES options:MTLResourceStorageModeShared];
                id<MTLBlitCommandEncoder> copy = buffer ? [cb blitCommandEncoder] : nil;
                if (copy) {
                    [copy copyFromTexture:hd sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0,0,0)
                              sourceSize:MTLSizeMake(640,360,1) toBuffer:buffer destinationOffset:0
                   destinationBytesPerRow:2560 destinationBytesPerImage:BCES_HALF_DEPTH_BYTES];
                    [copy endEncoding];
                    [cb addCompletedHandler:^(id<MTLCommandBuffer> completed) {
                        bces_half_depth_complete(probe, completed.status == MTLCommandBufferStatusCompleted ? buffer.contents : NULL);
                    }];
                } else {
                    bces_half_depth_complete(probe, NULL);
                }
            }
''' + marker)
    metal.write_text(INCLUDES + source[:start] + section + source[end:])
