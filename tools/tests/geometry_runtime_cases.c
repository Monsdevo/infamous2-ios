#define main skinning_replay_main
#include "skinning_replay.c"
#undef main
#include "GeometryKernels.h"
#include <time.h>
int bces_geometry_test_fault=0;
static void skin(spu_context*c){c->pc=0xD0A8;skin_dispatch(c);}
static void cull(spu_context*c){c->pc=0xA798;skin_dispatch(c);}
static void reset(spu_context*c,SkinningSnapshot*s){memcpy(c,&s->input,sizeof *c);c->ls=c->ls_store;memcpy(c->ls,s->input_ls,SPU_LS_SIZE);c->host_depth=1;c->int_enable=0;c->stop_request=0;c->tramp_fn=NULL;}
static void check(spu_context*c,SkinningSnapshot*s){assert(!memcmp(c->gpr,s->output.gpr,2048));assert(!memcmp(c->ls,s->output_ls,SPU_LS_SIZE));assert(c->pc==s->output.pc);assert(c->host_depth==1);assert(c->tramp_fn==NULL);}
int main(int argc,char**argv){
 assert(argc>=3);spu_context*c=malloc(sizeof *c);assert(c);
 for(int arg=1;arg<argc;arg++){
  FILE*f=fopen(argv[arg],"rb");assert(f);SkinningSnapshot*s=malloc(sizeof *s);assert(s&&fread(s,sizeof *s,1,f)==1);fclose(f);unsigned kind=s->version==2;BCESGeometryReference fn=kind?cull:skin;uint32_t ret=kind?0x59F0:0x5980;
  for(unsigned route=0;route<=2;route++){
   bces_geometry_set_route(kind,route);bces_geometry_set_validation(0);
   if(route==2){for(unsigned wait=0;bces_geometry_metal_state()==1&&wait<3000;wait++){struct timespec t={0,100000000};nanosleep(&t,NULL);}assert(bces_geometry_metal_state()==2);}BCESGeometryStats before=bces_geometry_stats(kind);
   struct timespec start,end;clock_gettime(CLOCK_MONOTONIC,&start);
   // At least eight obligatory comparisons, then direct transactional commits.
   for(unsigned repeat=0;repeat<10;repeat++){reset(c,s);bces_geometry_execute(c,kind,fn,ret);check(c,s);}
   clock_gettime(CLOCK_MONOTONIC,&end);double ms=1000*(end.tv_sec-start.tv_sec)+(end.tv_nsec-start.tv_nsec)/1e6;
   BCESGeometryStats after=bces_geometry_stats(kind);
   assert(after.entries[route]-before.entries[route]==10&&after.total_ns[route]>before.total_ns[route]);
   assert(after.total_ns[route]-before.total_ns[route]>=after.trial_ns-before.trial_ns);
   if(route==0)assert(after.total_ns[route]-before.total_ns[route]>=after.reference_ns-before.reference_ns);
   assert(!after.mismatches&&!after.failures&&!after.fallbacks);
   if(route){assert(after.calls[route]-before.calls[route]==10);assert(after.validations-before.validations==8);}
   printf("PASS runtime %s kind=%u route=%u 10 full-output checks; wall total %.3f ms (Mac, includes first-use/validation)\n",argv[arg],kind,route,ms);
  }
  bces_geometry_set_route(kind,1);bces_geometry_set_validation(1);BCESGeometryStats before=bces_geometry_stats(kind);reset(c,s);bces_geometry_execute(c,kind,fn,ret);check(c,s);assert(bces_geometry_stats(kind).validations==before.validations+1);
  // Separate LS (raw/shared model) must stay on the original path.
  uint8_t*shared=malloc(SPU_LS_SIZE);assert(shared);reset(c,s);memcpy(shared,s->input_ls,SPU_LS_SIZE);c->ls=shared;before=bces_geometry_stats(kind);bces_geometry_execute(c,kind,fn,ret);check(c,s);assert(bces_geometry_stats(kind).fallbacks==before.fallbacks+1);free(shared);
  printf("PASS forced validation and shared-LS fallback\n");free(s);
 }
 // Test real producer/consumer order on the SAME architectural context:
 // skinning output feeds culling input, rather than two unrelated replays.
 FILE*skin_file=fopen(argv[1],"rb"),*cull_file=fopen(argv[2],"rb");assert(skin_file&&cull_file);
 SkinningSnapshot*skin_fixture=malloc(sizeof *skin_fixture),*cull_fixture=malloc(sizeof *cull_fixture);assert(skin_fixture&&cull_fixture);
 assert(fread(skin_fixture,sizeof *skin_fixture,1,skin_file)==1&&fread(cull_fixture,sizeof *cull_fixture,1,cull_file)==1);fclose(skin_file);fclose(cull_file);
 assert(skin_fixture->version==1&&cull_fixture->version==2);
 const unsigned pairs[][2]={{1,2},{2,1},{1,1},{2,2},{0,0}};
 for(unsigned validation=0;validation<2;validation++){
  bces_geometry_set_validation(validation);
  for(unsigned pair=0;pair<5;pair++){
   unsigned skin_route=pairs[pair][0],cull_route=pairs[pair][1];
   bces_geometry_set_route(0,skin_route);bces_geometry_set_route(1,cull_route);
   for(unsigned repeat=0;repeat<3;repeat++){
    assert(bces_geometry_route(0)==skin_route&&bces_geometry_route(1)==cull_route);
    reset(c,skin_fixture);BCESGeometryStats before_skin=bces_geometry_stats(0),before_cull=bces_geometry_stats(1);
    bces_geometry_execute(c,0,skin,0x5980);check(c,skin_fixture);
    assert(bces_geometry_route(1)==cull_route); // Skin selection cannot change culling.
    for(unsigned argument=0;argument<4;argument++){unsigned reg=(unsigned[]){0,3,4,5}[argument];c->gpr[reg]=cull_fixture->input.gpr[reg];}
    assert(!memcmp(c->gpr,cull_fixture->input.gpr,2048)&&!memcmp(c->ls,cull_fixture->input_ls,SPU_LS_SIZE));
    bces_geometry_execute(c,1,cull,0x59F0);check(c,cull_fixture);
    BCESGeometryStats after_skin=bces_geometry_stats(0),after_cull=bces_geometry_stats(1);
    assert(after_skin.calls[skin_route]==before_skin.calls[skin_route]+1&&after_cull.calls[cull_route]==before_cull.calls[cull_route]+1);
    assert(after_skin.fallbacks==before_skin.fallbacks&&after_cull.fallbacks==before_cull.fallbacks);
    assert(!after_skin.mismatches&&!after_cull.mismatches);
    if(validation){if(skin_route)assert(after_skin.validations==before_skin.validations+1);if(cull_route)assert(after_cull.validations==before_cull.validations+1);}
   }
   printf("PASS same-context skinning/culling pair=%u/%u validation=%u: 3 sequential full-output runs, independent selection, no fallback\n",skin_route,cull_route,validation);
  }
 }
 free(skin_fixture);free(cull_fixture);
 // The production adapter must discard a bad trial, preserve the live
 // reference output and latch only that route off until process restart.
 FILE*f=fopen(argv[1],"rb");assert(f);SkinningSnapshot*s=malloc(sizeof *s);assert(s&&fread(s,sizeof *s,1,f)==1);fclose(f);assert(s->version==1);
 bces_geometry_set_route(0,1);bces_geometry_set_validation(1);BCESGeometryStats before=bces_geometry_stats(0);bces_geometry_test_fault=1;
 reset(c,s);bces_geometry_execute(c,0,skin,0x5980);check(c,s);BCESGeometryStats after=bces_geometry_stats(0);assert(after.mismatches==before.mismatches+1&&(after.blocked_mask&2));
 bces_geometry_test_fault=0;reset(c,s);bces_geometry_execute(c,0,skin,0x5980);check(c,s);assert(bces_geometry_stats(0).fallbacks==after.fallbacks+1);
 puts("PASS injected mismatch: original output retained, route latched off, subsequent call falls back");free(s);
 puts("PASS complete call timers include reference/recovery and commit; actual GPU coverage is separate from requested route");
 for(unsigned i=0;i<65536;i++)free(first[i]);free(c);return 0;
}
