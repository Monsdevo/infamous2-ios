"""Mac-only opt-in normals omission; depth and original default stay intact."""
def patch(engine,light,ssao):
 marker='    if (is_n && dst_offset == s_gl.diff_off) {'
 assert engine.count(marker)==1
 engine=engine.replace(marker,marker+'\n        bces_host_normals_begin();')
 marker='      (void)ssao;(void)nowb;return 0; } // iOS: retain both guest input writebacks, including SPU fallback'
 assert engine.count(marker)==1
 engine=engine.replace(marker,'''      (void)ssao;(void)nowb;
      if(is_n && bces_host_normals_skip(s_gl.n_tex && s_gl.w==1280 && s_gl.h==720 &&
         !__atomic_load_n(&bces_light_faults,__ATOMIC_RELAXED) &&
         !__atomic_load_n(&bces_ssao_fault_count,__ATOMIC_RELAXED) &&
         bces_metal_light_prepare(s_gl.w,s_gl.h) &&
         bces_metal_ssao_prepare(s_gl.w,s_gl.h,s_gl.w/2,s_gl.h/2,320)))return 1;
      return 0; } // Depth writeback remains mandatory for the original depth job.''')
 marker='if(!bces_light_allow_job(ctx)) {'
 assert light.count(marker)==1
 light=light.replace(marker,marker+' bces_host_normals_require();')
 marker='if(!bces_ssao_allow_job(ctx)) {'
 assert ssao.count(marker)==1
 ssao=ssao.replace(marker,marker+' bces_host_normals_require();')
 return tuple('#include "HostNormalsWriteback.h"\n'+s for s in (engine,light,ssao))
