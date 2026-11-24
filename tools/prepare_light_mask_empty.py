"""Exact empty-depth tile rejection before the original SPU arithmetic."""
import ast,json
from pathlib import Path
def shader_variant(msl,cooperative=False):
 a=msl.index('kernel void bces_light_tile_mask(');b=msl.index('\nstruct GLOut',a)
 kernel=msl[a:b]
 marker='    BGrid grid=bgrid(p,origin/uint2(32,40)+tile);'
 assert kernel.count(marker)==1
 prepass='''    // A tile whose every valid depth sample is background cannot set
    // original flags bit 0. Its result is zero regardless of light membership.
    uint geometry=0;
    for(uint j=tid;j<1280u;j+=64u){
        uint2 local=tile*uint2(32,40)+uint2(j%32u,j/32u);
        if(any(local>=extent))continue;
        uint z24=uint(clamp(zt.read(local).x,0.0,1.0)*16777215.0);
        if(z24!=0xFFFFFFu){geometry=1u;break;}
    }
    atomic_fetch_or_explicit(&flags,geometry,memory_order_relaxed);
    threadgroup_barrier(mem_flags::mem_threadgroup);
    if(atomic_load_explicit(&flags,memory_order_relaxed)==0u){
        if(tid==0)masks[tile.y*((extent.x+31u)/32u)+tile.x]=0u;
        return;
    }
'''
 # The existing geometry bit is now known set. All membership operations,
 # accumulation order and the accepted tile alpha decision stay original.
 kernel=kernel.replace('bces_light_tile_mask(','bces_light_tile_mask_empty(',1).replace(marker,prepass+marker,1)
 if cooperative:
  # Geometry has already been established for the whole group. Membership
  # is existential: the first true bmember decides the shared result. A
  # relaxed atomic read can only postpone early exit, never create a member.
  kernel=kernel.replace('    uint own=0;','    uint own=1;')
  needle='    for(uint i=tid;i<1280u;i+=64u) {';assert kernel.count(needle)==1
  kernel=kernel.replace(needle,needle+'\n        if(atomic_load_explicit(&flags,memory_order_relaxed)==3u)break;')
  needle='if(bmember(P,p.l[k])){own|=2u;break;}';assert kernel.count(needle)==1
  kernel=kernel.replace(needle,'if(bmember(P,p.l[k])){own|=2u;atomic_fetch_or_explicit(&flags,2u,memory_order_relaxed);break;}')
 return msl+'\n'+kernel
def patch(source,capture_inputs=True):
 if 'static id<MTLComputePipelineState> bces_light_mask_empty_pso,' in source:
  if capture_inputs and 'bces_mask_capture(cb,zt,pb);' not in source:
   source='#include "HostMaskCapture.h"\n'+source
   marker='id<MTLComputeCommandEncoder> c=bces_pass_probe_compute(cb,"LIGHT_TILE_MASK");'
   assert source.count(marker)==1
   source=source.replace(marker,'bces_mask_capture(cb,zt,pb);\n            '+marker,1)
  return source
 s='#include "HostLightMask.h"\n'+('#include "HostMaskCapture.h"\n' if capture_inputs else '')+source
 a=s.index('"struct GLight {');b=s.index('/* inFAMOUS 2\'s SSAO job',a)
 m=''.join(ast.literal_eval(q.strip()) for q in s[a:b].splitlines() if q.startswith('"'))
 variant=m+'\n'+(Path(__file__).resolve().parents[1]/'src/host/LightMaskInterval.metal').read_text()+'''
kernel void bces_mask_compare(device const uint* reference [[buffer(0)]],
 device const uint* candidate [[buffer(1)]],device atomic_uint* stats [[buffer(2)]],
 constant uint& count [[buffer(3)]],uint id [[thread_position_in_grid]]){
 if(id>=count)return;
 if(reference[id]!=candidate[id])atomic_fetch_add_explicit(&stats[0],1u,memory_order_relaxed);
 atomic_fetch_add_explicit(&stats[1],1u,memory_order_relaxed);
}
'''
 s=s[:a]+''.join(json.dumps(q+'\n')+'\n' for q in variant.splitlines())+'\n'+s[b:]
 marker='static id<MTLComputePipelineState> bces_light_mask_pso;';assert s.count(marker)==1
 s=s.replace(marker,marker+'\nstatic id<MTLComputePipelineState> bces_light_mask_empty_pso,bces_light_mask_compare_pso;',1)
 marker='    for(unsigned i=0;i<8;i++) {'
 start=s.index('    if(!bces_light_mask_pso) {');at=s.index(marker,start)
 s=s[:at]+'''    if(!bces_light_mask_empty_pso){
        NSError* error=nil;
        bces_light_mask_empty_pso=[s_dev newComputePipelineStateWithFunction:[s_eng_helper_lib newFunctionWithName:@"bces_light_tile_mask_empty"] error:&error];
        bces_light_mask_compare_pso=[s_dev newComputePipelineStateWithFunction:[s_eng_helper_lib newFunctionWithName:@"bces_mask_compare"] error:&error];
        if(!bces_light_mask_empty_pso || !bces_light_mask_compare_pso)bces_mask_fault();
    }
'''+s[at:]
 marker='id<MTLComputeCommandEncoder> c=bces_pass_probe_compute(cb,"LIGHT_TILE_MASK");'
 if marker not in s:marker='id<MTLComputeCommandEncoder> c=[cb computeCommandEncoder];'
 assert s.count(marker)==1
 if capture_inputs:s=s.replace(marker,'bces_mask_capture(cb,zt,pb);\n            '+marker,1)
 marker='            [c setComputePipelineState:bces_light_mask_pso];[c setTexture:zt atIndex:0];';assert s.count(marker)==1
 s=s.replace(marker,'''            unsigned mask_mode=bces_mask_enabled();
            int empty_mask=mask_mode==1 && bces_light_mask_empty_pso!=nil;
            [c setComputePipelineState:empty_mask?bces_light_mask_empty_pso:bces_light_mask_pso];[c setTexture:zt atIndex:0];
            bces_mask_pass(empty_mask);''',1)
 a=s.index('            unsigned mask_mode=bces_mask_enabled();');marker='            [c endEncoding];';at=s.index(marker,a)+len(marker)
 s=s[:at]+'''
            if(mask_mode==2 && bces_light_mask_empty_pso && bces_light_mask_compare_pso){
                id<MTLBuffer> candidate=[s_dev newBufferWithLength:mask.length options:MTLResourceStorageModeShared];
                id<MTLBuffer> results=[s_dev newBufferWithLength:8 options:MTLResourceStorageModeShared];
                if(!candidate || !results)bces_mask_fault();
                else {
                    memset(results.contents,0,8);
                    id<MTLComputeCommandEncoder> ve=[cb computeCommandEncoder];
                    [ve setComputePipelineState:bces_light_mask_empty_pso];[ve setTexture:zt atIndex:0];
                    [ve setBuffer:pb offset:0 atIndex:0];[ve setBuffer:candidate offset:0 atIndex:1];
                    [ve setBytes:origin length:sizeof origin atIndex:2];[ve setBytes:extent length:sizeof extent atIndex:3];
                    [ve dispatchThreadgroups:MTLSizeMake((extent[0]+31)/32,(extent[1]+39)/40,1) threadsPerThreadgroup:MTLSizeMake(64,1,1)];[ve endEncoding];bces_mask_pass(1);
                    uint32_t count=((extent[0]+31)/32)*((extent[1]+39)/40);
                    ve=[cb computeCommandEncoder];[ve setComputePipelineState:bces_light_mask_compare_pso];
                    [ve setBuffer:mask offset:0 atIndex:0];[ve setBuffer:candidate offset:0 atIndex:1];[ve setBuffer:results offset:0 atIndex:2];[ve setBytes:&count length:sizeof count atIndex:3];
                    [ve dispatchThreads:MTLSizeMake(count,1,1) threadsPerThreadgroup:MTLSizeMake(64,1,1)];[ve endEncoding];
                    [cb addCompletedHandler:^(id<MTLCommandBuffer> done){
                        const uint32_t* values=results.contents;
                        if(done.status!=MTLCommandBufferStatusCompleted || values[1]!=count)bces_mask_fault();
                        else bces_mask_validation(values[0],values[1]);
                    }];
                }
                // The game always consumes the reference mask in mode 2.
            }
'''+s[at:]
 return s
