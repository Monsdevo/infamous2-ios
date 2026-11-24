"""Research-only depth/stencil PSO alternative, with original draw path intact."""
def patch(source):
 s='#include "HostDepthOnly.h"\n'+source
 marker='    id<MTLRenderPipelineState> pso;\n    id<MTLDepthStencilState>   ds;'
 assert s.count(marker)==1
 s=s.replace(marker,'    id<MTLRenderPipelineState> pso, depth_only_pso;\n    id<MTLDepthStencilState>   ds;')
 marker='    s_eng_pipe[slot].pso = pso;'
 assert s.count(marker)==1
 s=s.replace(marker,marker+'''
    s_eng_pipe[slot].depth_only_pso=nil;
    unsigned color_write=0;
    for(unsigned i=0;i<rt_count;i++)color_write|=(unsigned)pd.colorAttachments[i].writeMask;
    // eng_function receives the fully generated HLSL, including alpha
    // discard. This Metal path has no separate fixed-function alpha test
    // or alpha-to-coverage stage. Judge the executed shader, not a stale
    // guest enable bit; any discard/clip/depth/coverage syntax still rejects.
    int depth_only=bces_depth_only_eligible(ps_hlsl,color_write,0);
    if(depth_only) {
        pd.fragmentFunction=nil;
        NSError* depth_error=nil;
        s_eng_pipe[slot].depth_only_pso=ios_profiled_pipeline(s_dev,pd,&depth_error);
        if(s_eng_pipe[slot].depth_only_pso)bces_depth_only_pipeline();
        else bces_depth_only_fault();
    }
    const char* research=getenv("BCES_RESEARCH_DIR");
    if(research){char path[1024];snprintf(path,sizeof path,"%s/pipeline-state.jsonl",research);
        FILE* f=fopen(path,"a");if(f){
          fprintf(f,"{\\"pipeline\\":%u,\\"color_write\\":%u,\\"alpha_func\\":%u,\\"depth_test\\":%u,\\"depth_func\\":%u,\\"depth_write\\":%u,\\"stencil\\":%u,\\"stencil_write_mask\\":%u,\\"stencil_fail\\":%u,\\"stencil_zfail\\":%u,\\"stencil_zpass\\":%u,\\"depth_only_eligible\\":%d}\\n",slot+1,color_write,rs->alpha_func,rs->depth_test,rs->depth_func,rs->depth_write,rs->stencil_enable,rs->s_write_mask,rs->s_fail,rs->s_zfail,rs->s_zpass,depth_only);fclose(f);
        }
    }
''',1)
 marker='    if (b->pso != ENG_PTR(p->pso)) { [enc setRenderPipelineState:p->pso]; b->pso = ENG_PTR(p->pso); }'
 assert s.count(marker)==1
 s=s.replace(marker,'''    id<MTLRenderPipelineState> selected=p->pso;
    if(p->depth_only_pso){int fast=bces_depth_only_enabled();
        if(fast)selected=p->depth_only_pso;
        bces_depth_only_draw(fast);
    }
    if (b->pso != ENG_PTR(selected)) { [enc setRenderPipelineState:selected]; b->pso = ENG_PTR(selected); }''',1)
 for marker in ('s_eng_pipe[i].pso = nil;','s_eng_pipe[pipeline - 1].pso = nil;'):
  assert s.count(marker)==1
  s=s.replace(marker,marker+'\n'+marker.replace('.pso = nil;','.depth_only_pso = nil;'))
 return s
