"""One shared shader transformation for the renderer and paired fixture replay."""
from pathlib import Path
import ast,json,re
ROOT=Path(__file__).resolve().parents[1]
def patch(shader):
    anchor='struct GLOut {'
    assert shader.count(anchor)==1
    index=shader.index(anchor)
    helper=(ROOT/'src/platform/LightingRZ.metal').read_text()
    runtime=(ROOT/'upstream/infamous2-recomp/ps3recomp-fork/runtime/spu/spu_helpers.h').read_text()
    tables=[]
    for old,new,size in [('spu_frest_fraction_lut','bces_frest',32),('spu_frsqest_fraction_lut','bces_frsqrt',64)]:
        body=re.search(r'static const uint32_t '+old+r'\['+str(size)+r'\] = (\{.*?\});',runtime,re.S).group(1)
        tables.append('constant uint '+new+'['+str(size)+']='+body+';\n')
    helper=helper.replace('BCES_RZ_LUTS',''.join(tables))
    shader=shader[:index]+helper+'\n'+(ROOT/'src/platform/LightingCulling.metal').read_text()+'\n'+shader[index:]
    old='constant GLParams& p [[buffer(0)]])'
    assert shader.count(old)==1
    shader=shader.replace(old,'constant GLParams& p [[buffer(0)]], device const uint* masks [[buffer(1)]])')
    old='if (z24 >= 0xFFFFFFu) return o;'
    assert shader.count(old)==1
    shader=shader.replace(old,'if (p.misc.y <= 0.0 || !masks[(uint(i.pos.y)/40u)*((nt.get_width()+31u)/32u)+uint(i.pos.x)/32u]) return o;')
    return shader

def patch_backend(source):
    start=source.index('"struct GLight {');end=source.index('/* inFAMOUS 2\'s SSAO job',start)
    raw=source[start:end]
    shader=''.join(ast.literal_eval(line.strip()) for line in raw.splitlines() if line.startswith('"'))
    shader=patch(shader)
    return source[:start]+''.join(json.dumps(line+'\n')+'\n' for line in shader.splitlines())+'\n'+source[end:]
