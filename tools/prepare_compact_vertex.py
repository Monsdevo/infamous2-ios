"""Opt-in compact SNORM16x3 vertex transport for the derived iOS renderer."""
from prepare_job_flow import replace_once


def renderer(source):
    changes = [
        ('    const u8* fetched_verts;', '    u32 compact_mask;\n    const u8* fetched_verts;'),
        ('    dc.fetched_verts = NULL;', '    dc.fetched_verts = NULL;\n    dc.compact_mask = 0;'),
        ('rsx_be_format rt_fmt, u32 rt_count, int* out_fixed)',
         'rsx_be_format rt_fmt, u32 rt_count, int* out_fixed, u32 compact_mask)'),
        ('    const int fixed = !eng_guest_programs(&vp, &fp);',
         '    const int fixed = !eng_guest_programs(&vp, &fp);\n    if (fixed && compact_mask) return 0;'),
        ('        u32 shadow_mask, srgb_output, gamma_units, expand_units;',
         '        u32 shadow_mask, srgb_output, gamma_units, expand_units, compact_mask;'),
        ('        kmemo.layout_stride == layout->stride && kmemo.rt_count == rt_count &&',
         '        kmemo.compact_mask == compact_mask &&\n        kmemo.layout_stride == layout->stride && kmemo.rt_count == rt_count &&'),
        ('    key = eng_fnv1a(&layout->stride, sizeof layout->stride, key);',
         '    key = eng_fnv1a(&layout->stride, sizeof layout->stride, key);\n'
         '    if (compact_mask) key = eng_fnv1a(&compact_mask, sizeof compact_mask, key);'),
        ('    kmemo.layout_mask = layout->mask; kmemo.layout_stride = layout->stride;',
         '    kmemo.layout_mask = layout->mask; kmemo.layout_stride = layout->stride;\n'
         '    kmemo.compact_mask = compact_mask;'),
        ('''    if (vi > 0 && fi > 0)
        handle = g.be->pipeline_create(g.be->user, s_vs_hlsl, s_ps_hlsl, rs,
                                       layout, layout->stride, rt_fmt, rt_count);''',
         '''    if (vi > 0 && fi > 0) {
        if (compact_mask) {
            if (bces_compact_vertex_shader(s_vs_hlsl, sizeof s_vs_hlsl, compact_mask))
                handle = bces_metal_compact_pipeline_create(g.be->user, s_vs_hlsl, s_ps_hlsl, rs,
                                                           layout, layout->stride, rt_fmt, rt_count,
                                                           compact_mask);
        } else {
            handle = g.be->pipeline_create(g.be->user, s_vs_hlsl, s_ps_hlsl, rs,
                                           layout, layout->stride, rt_fmt, rt_count);
        }
    }'''),
        ('    if(bces_renderer_memo_mode(BCES_MEMO_VERTEX))\n        dc.fetched_verts',
         '''    if (consecutive && bces_compact_vertex_mode()) {
        dc.compact_mask = bces_compact_vertex_mask(&dc.fetch_plan, dc.refs, dc.n_refs);
        if (dc.compact_mask && !bces_compact_vertex_pack(&dc.fetch_plan, dc.refs, dc.n_refs,
                                                         dc.compact_mask, dc.verts))
            dc.compact_mask = 0;
    }
    if (dc.compact_mask)
        bces_fetch_ok = 1;
    else if(bces_renderer_memo_mode(BCES_MEMO_VERTEX))
        dc.fetched_verts'''),
        ('''    const u32 pipeline = eng_pipeline_get(&layout, &rs,
                                          eng_surface_format(sf.color_format),
                                          n_targets, &pipeline_is_fixed);''',
         '''    if (dc.compact_mask)
        layout.stride = bces_compact_vertex_stride(&layout, dc.compact_mask);
    u32 pipeline = eng_pipeline_get(&layout, &rs, eng_surface_format(sf.color_format),
                                   n_targets, &pipeline_is_fixed, dc.compact_mask);
    if (!pipeline && dc.compact_mask) {
        dc.compact_mask = 0;
        layout.stride = dc.fetch_plan.layout.stride;
        if (!rsx_vertex_fetch_all(&dc.fetch_plan, dc.refs, dc.n_refs, dc.verts)) {
            eng_drop("fetch", prim);
            return;
        }
        pipeline = eng_pipeline_get(&layout, &rs, eng_surface_format(sf.color_format),
                                    n_targets, &pipeline_is_fixed, 0);
    }'''),
        ('    DS_MARK(ns_draw);',
         '''    if (dc.compact_mask)
        bces_compact_vertex_draw(uploaded, dc.fetch_plan.layout.stride - layout.stride);
    DS_MARK(ns_draw);'''),
    ]
    for before, after in changes:
        source = replace_once(source, before, after)
    declaration = '''
extern u32 bces_metal_compact_pipeline_create(void*, const char*, const char*,
    const rsx_be_render_state*, const rsx_vertex_layout_plan*, u32, rsx_be_format, u32, u32);
'''
    return '#include "CompactVertex.h"\n' + replace_once(
        source, 'static u32 eng_pipeline_get(', declaration + '\nstatic u32 eng_pipeline_get(')


def metal(source):
    source = replace_once(source, '''static u32 eng_pipeline_create(void* user, const char* vs_hlsl, const char* ps_hlsl,
                               const rsx_be_render_state* rs,
                               const rsx_vertex_layout_plan* layout,
                               u32 vertex_stride, rsx_be_format rt_fmt,
                               u32 rt_count)''',
    '''u32 bces_metal_compact_pipeline_create(void* user, const char* vs_hlsl, const char* ps_hlsl,
                               const rsx_be_render_state* rs,
                               const rsx_vertex_layout_plan* layout,
                               u32 vertex_stride, rsx_be_format rt_fmt,
                               u32 rt_count, u32 compact_mask)''')
    source = replace_once(source, '''        vd.attributes[slot].format      = MTLVertexFormatFloat4;
        vd.attributes[slot].offset      = (NSUInteger)(slot * 16u);''',
        '''        const int compact = (compact_mask & (1u << layout->attrs[slot])) != 0;
        vd.attributes[slot].format      = compact ? MTLVertexFormatShort4 : MTLVertexFormatFloat4;
        vd.attributes[slot].offset      = bces_compact_vertex_offset(layout, compact_mask, slot);''')
    wrapper = '''static u32 eng_pipeline_create(void* user, const char* vs_hlsl, const char* ps_hlsl,
                               const rsx_be_render_state* rs,
                               const rsx_vertex_layout_plan* layout,
                               u32 vertex_stride, rsx_be_format rt_fmt, u32 rt_count)
{
    return bces_metal_compact_pipeline_create(user, vs_hlsl, ps_hlsl, rs, layout,
                                              vertex_stride, rt_fmt, rt_count, 0);
}

'''
    marker = 'static void eng_pipeline_release('
    return '#include "CompactVertex.h"\n' + replace_once(source, marker, wrapper + marker)


def prepare(overlay):
    video = overlay / 'libs/video'
    for name, transform in (('rsx_draw_engine.c', renderer), ('rsx_metal_backend.m', metal)):
        path = video / name
        path.write_text(transform(path.read_text()))
