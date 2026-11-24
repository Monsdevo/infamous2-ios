"""Trace the serial renderer stages in an iPhone diagnostic build."""
import re

from prepare_job_flow import replace_once


def instrument(path, scopes):
    source = path.read_text()
    for function, declaration in scopes.items():
        pattern = rf'(^[^\n;]*\b{function}\([^;{{}}]*?\)\n\{{\n)'
        source, count = re.subn(pattern, lambda match: match[0] + declaration + '\n', source, flags=re.M)
        if count != 1:
            raise ValueError(f'Unexpected renderer definition: {function}')
    return '#include "RendererStageTrace.h"\n' + source


def prepare(output, overlay):
    gcm = output / 'diagnostic_cellGcmSys.c'
    renderer = overlay / 'libs/video/rsx_draw_engine.c'
    metal = overlay / 'libs/video/rsx_metal_backend.m'
    gcm.write_text(instrument(gcm, {
        'gcm_rsx_process_fifo_unlocked': '    BCES_RENDERER_STAGE(trace, 1, 0);',
        'nv3089_blit': '    BCES_RENDERER_STAGE(trace, 8, s_gcm2d.dst_offset);',
    }))
    source = instrument(renderer, {
        'sink_end': '    BCES_RENDERER_STAGE(trace, 2, 0);',
        'dc_fetch': '    BCES_RENDERER_STAGE(trace, 3, 0);',
        'bces_cached_texture_hash': '    BCES_RENDERER_STAGE(trace, 5, span);',
        'rsx_draw_engine_write_back_to': '    BCES_RENDERER_STAGE(trace, 9, dst_offset);',
        'eng_rgba_to_guest_argb': '    BCES_RENDERER_STAGE(trace, 10, w * h * 4u);',
    })
    fetch = '''    else
        bces_fetch_ok = rsx_vertex_fetch_all(&dc.fetch_plan, dc.refs, dc.n_refs,
                              layout->stride ? dc.verts : NULL);'''
    source = replace_once(source, fetch, fetch.replace('    else\n', '''    else {
        BCES_RENDERER_STAGE(trace, 4, dc.n_refs * layout->count);
''') + '\n    }')
    renderer.write_text(source)
    metal.write_text(instrument(metal, {
        'eng_draw': '    BCES_RENDERER_STAGE(trace, 6, 0);',
        'eng_submit_and_wait': '    BCES_RENDERER_STAGE(trace, 7, reason);',
    }))
