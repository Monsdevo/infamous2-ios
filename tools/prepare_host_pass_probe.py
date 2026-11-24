"""Mac research-only hardware timestamp hooks; keep shared/iOS source intact."""
def patch(source):
 s='#include "MetalPassProbe.h"\n'+source
 marker='    [buffer commit];';assert s.count(marker)==1;s=s.replace(marker,'    bces_pass_probe_commit(buffer);\n'+marker,1)
 marker='static void eng_present(void* user, u32 surface)\n{';assert s.count(marker)==1
 s=s.replace(marker,marker+'\n    bces_pass_probe_present_begin();',1)
 marker='    if (s_dumptex) { eng_dumptex_write(s_dumptex, s_dumptex_path); s_dumptex = nil; }'
 assert s.count(marker)==1;s=s.replace(marker,marker+'\n    bces_pass_probe_boundary(s_dev);',1)
 marker='[cb renderCommandEncoderWithDescriptor:rp]';assert s.count(marker)==7
 s=s.replace(marker,'bces_pass_probe_encoder(cb,rp,__func__,__LINE__)')
 # Distinguish the five SSAO stages and lighting from guest geometry.
 a=s.index('if (s_eng_rec[i].kind == ENG_REC_SSAO)');b=s.index('if (s_eng_rec[i].kind == ENG_REC_LIGHT)',a)
 body=s[a:b];assert body.count('bces_pass_probe_encoder(cb,rp,__func__,__LINE__)')==1
 s=s[:a]+body.replace('bces_pass_probe_encoder(cb,rp,__func__,__LINE__)','bces_pass_probe_encoder(cb,rp,"SSAO",k)')+s[b:]
 a=s.index('if (s_eng_rec[i].kind == ENG_REC_LIGHT)');b=s.index('if (s_eng_rec[i].kind == ENG_REC_DEPTH_RESOLVE)',a)
 body=s[a:b];assert body.count('bces_pass_probe_encoder(cb,rp,__func__,__LINE__)')==1
 s=s[:a]+body.replace('bces_pass_probe_encoder(cb,rp,__func__,__LINE__)','bces_pass_probe_encoder(cb,rp,"LIGHTING",0)')+s[b:]
 marker='id<MTLComputeCommandEncoder> c=[cb computeCommandEncoder];'
 assert s.count(marker)==1
 s=s.replace(marker,'id<MTLComputeCommandEncoder> c=bces_pass_probe_compute(cb,"LIGHT_TILE_MASK");')
 # Count recorded guest draws only while one frame is armed; off-path is a
 # single relaxed flag read. No new render-pass split or GPU fence.
 a=s.index('static void eng_encode_draw(');b=s.index('{',a)+1
 s=s[:b]+'''\n    if(__atomic_load_n(&bces_pass_probe_draw_recording,__ATOMIC_RELAXED))
        bces_pass_probe_draw(r->pipeline,r->vertex_count,r->index_count);
'''+s[b:]
 return s
