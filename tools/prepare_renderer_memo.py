#!/usr/bin/env python3
"""iOS-only exact-input memo experiment; keep the pinned reference functions."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write(path, text):
    if not path.exists() or path.read_text() != text:
        path.write_text(text)


def renderer_source(source):
    start = source.index('static u64 eng_texture_content_hash(')
    end = source.index('\nstatic int eng_staging_reserve(', start)
    old = source[start:end]
    body_start = old.index('    /* Eight independent FNV-style lanes:')
    tail = '    *readable = 1;\n    return hash;\n}'
    if old.count(tail) != 1:
        raise ValueError('Texture hash reference changed')
    # Keep its complete arithmetic unchanged. The experiment memoizes the
    # original value, and never substitutes a different hash algorithm.
    body = old[body_start:].replace(tail, '    return hash;\n}', 1)
    pure = 'static u64 bces_texture_hash_reference(const u8* src,u32 span)\n{\n' + body
    wrapped = '''static u64 eng_texture_content_hash(u32 location,u32 offset,u32 span,int* readable)
{
    const u8* src=span?eng_guest_ptr(NULL,location,offset,span):NULL;
    if(!src){*readable=0;return 0;}
    *readable=1;
    return bces_texture_hash_memo(src,span,bces_texture_hash_reference);
}
'''
    wrapped = wrapped.replace('static u64 eng_texture_content_hash(', 'static u64 bces_cached_texture_hash(')
    wrapped = wrapped.replace('    const u8* src=span?', '    if(!bces_renderer_memo_mode(BCES_MEMO_TEXTURE))return eng_texture_content_hash(location,offset,span,readable);\n    const u8* src=span?')
    rest = source[end:].replace('eng_texture_content_hash(', 'bces_cached_texture_hash(')
    source = '#include "TextureHashMemo.h"\n#include "VertexFetchMemo.h"\n#include "RendererMemo.h"\n' + source[:start] + old + '\n\n' + pure + '\n\n' + wrapped + rest
    changes = [
        ('    u8* verts;\n', '    u8* verts;\n    const u8* fetched_verts; // borrowed until the next batch; backend stages synchronously\n'),
        ('    dc.fetch_ok = 1;\n', '    dc.fetch_ok = 1;\n    dc.fetched_verts = NULL;\n'),
        ('''    if (!rsx_vertex_fetch_all(&dc.fetch_plan, dc.refs, dc.n_refs,
                              layout->stride ? dc.verts : NULL)) {''',
         '''    int bces_fetch_ok;
    if(bces_renderer_memo_mode(BCES_MEMO_VERTEX))
        dc.fetched_verts = bces_vertex_fetch_borrow(&dc.fetch_plan, dc.refs, dc.n_refs,
                              layout->stride ? dc.verts : NULL, &bces_fetch_ok);
    else
        bces_fetch_ok = rsx_vertex_fetch_all(&dc.fetch_plan, dc.refs, dc.n_refs,
                              layout->stride ? dc.verts : NULL);
    if (!bces_fetch_ok) {'''),
        ('    g.be->draw(g.be->user, topology, dc.verts, uploaded, layout.stride,',
         '    g.be->draw(g.be->user, topology, dc.fetched_verts ? dc.fetched_verts : dc.verts, uploaded, layout.stride,')]
    for before, after in changes:
        if source.count(before) != 1:
            raise ValueError('Borrowed vertex lifetime adaptation changed: ' + before[:50])
        source = source.replace(before, after, 1)
    return source


def prepare(output, sdk):
    lock = json.loads((ROOT / 'sources.lock.json').read_text())['ios_renderer_memo']
    original = sdk / lock['vertex_source']
    if hashlib.sha256(original.read_bytes()).hexdigest() != lock['vertex_sha256']:
        raise ValueError('Vertex reference changed: review memo input coverage')
    source = original.read_text()
    marker = 'int rsx_vertex_fetch_all('
    if source.count(marker) != 1:
        raise ValueError('Vertex reference symbol changed')
    # Retain the exact compiled compact object from the verified runtime archive.
    path = output / 'renderer-overlay/libs/video/rsx_draw_engine.c'
    write(path, renderer_source(path.read_text()))
    path = output / 'diagnostic_cellGcmSys.c'
    source = path.read_text()
    marker = '    bces_rsx_legacy_publish();'
    if source.count(marker) != 1:
        raise ValueError('Serialized renderer snapshot publication changed')
    write(path, '#include "RendererMemo.h"\n' + source.replace(marker, marker + '\n    bces_renderer_memo_publish();', 1))


if __name__ == '__main__':
    prepare(ROOT / 'build/bces01229/ios-prepared', ROOT / 'upstream/infamous2-recomp/ps3recomp-fork')
