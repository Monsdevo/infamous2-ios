"""Conservative far-light rejection; retain tile mask, alpha packing and math."""
import ast,json
def fast_shader(shader,duplicate=True):
 start=shader.index('fragment GLOut eng_light_fs(')
 body=shader[start:]
 marker='        float3 Lv = L.pos_type.xyz - P; float d = length(Lv); float3 l = Lv / d;'
 assert body.count(marker)==1
 guard='''        float3 Lv = L.pos_type.xyz - P;
        // Skip only cases whose original attenuation and contribution are
        // certainly zero. 128 epsilon margin covers dot/sqrt rounding; small
        // magnitudes and non-finite/unusual inputs keep the original path.
        float farD2=dot(Lv,Lv),farR2=L.oacbn.x*L.oacbn.x;
        bool safeSpot=L.pos_type.w<=1.5f ||
            (all(isfinite(L.dir.xyz)) && all(abs(L.dir.xyz)<=65504.0f));
        if(all(isfinite(L.oacbn)) && safeSpot && L.oacbn.x>=0.0f && L.oacbn.x>L.col_inner.w &&
           farD2>=1.1754943508222875e-38f && farR2>=1.1754943508222875e-38f &&
           isfinite(farD2) && isfinite(farR2) &&
           farD2-farR2>1.52587890625e-5f*max(farD2,farR2))continue;
        float d = length(Lv); float3 l = Lv / d;'''
 body=body.replace(marker,guard)
 if duplicate:return shader+'\n'+body.replace('eng_light_fs(','eng_light_fs_far(',1)
 return shader[:start]+body
def patch_backend(source):
 start=source.index('"struct GLight {');end=source.index('/* inFAMOUS 2\'s SSAO job',start)
 shader=''.join(ast.literal_eval(line.strip()) for line in source[start:end].splitlines() if line.startswith('"'))
 shader=fast_shader(shader)
 source=source[:start]+''.join(json.dumps(line+'\n')+'\n' for line in shader.splitlines())+'\n'+source[end:]
 source='#include "LightingFarReject.h"\n'+source
 marker='static id<MTLBuffer> s_eng_light_param[8], bces_light_masks[8];';assert source.count(marker)==1
 source=source.replace(marker,marker+'\nstatic id<MTLRenderPipelineState> bces_light_far_pso;',1)
 marker='    if (!s_eng_light_out[0] || !s_eng_light_out[1] || s_eng_light_w != w || s_eng_light_h != h) {'
 assert source.count(marker)==1
 source=source.replace(marker,'''    if(!bces_light_far_pso) {
        MTLRenderPipelineDescriptor* pd=[MTLRenderPipelineDescriptor new];
        pd.vertexFunction=[s_eng_helper_lib newFunctionWithName:@"eng_fullscreen_vs"];
        pd.fragmentFunction=[s_eng_helper_lib newFunctionWithName:@"eng_light_fs_far"];
        pd.colorAttachments[0].pixelFormat=MTLPixelFormatRGBA8Unorm;
        pd.colorAttachments[1].pixelFormat=MTLPixelFormatRGBA8Unorm;
        NSError* error=nil;bces_light_far_pso=ios_profiled_pipeline(s_dev,pd,&error);
        if(!bces_light_far_pso){bces_light_far_fault();return 0;}
    }
'''+marker,1)
 marker='            [e setRenderPipelineState:s_eng_light_pso];';assert source.count(marker)==1
 source=source.replace(marker,'''            int far=bces_light_far_enabled();
            [e setRenderPipelineState:far?bces_light_far_pso:s_eng_light_pso];
            bces_light_far_pass(far);''',1)
 return source
def ensure_backend(source):
 if 'fragment GLOut eng_light_fs_far(' not in source:return patch_backend(source)
 # A Mac snapshot may already contain the shared iOS transformation. Verify
 # it rather than duplicating it or silently accepting a different shader.
 start=source.index('"struct GLight {');end=source.index('/* inFAMOUS 2\'s SSAO job',start)
 shader=''.join(ast.literal_eval(line.strip()) for line in source[start:end].splitlines() if line.startswith('"'))
 at=shader.index('fragment GLOut eng_light_fs_far(');reference=shader[:at].rstrip()+'\n'
 assert shader.split()==fast_shader(reference).split(),'Far shader differs from validated transformation'
 assert source.count('bces_light_far_pass(far);')==1
 return source
