#include "BCESSpuCopy.h"
#include "spu_context.h"
#include "spu_helpers.h"
#include <assert.h>
#include <time.h>

void bces_reference_copy_11c8(spu_context*);
void bces_reference_copy_0f94(spu_context*);
void spu_0001_at_0085E400_spu_func_000011C8(spu_context*);
void spu_0001_at_0085E400_spu_func_00000F94(spu_context*);
/* Reference tails only schedule these symbols. Do not execute their bodies. */
void spu_0001_at_0085E400_spu_func_0000151C(spu_context* c) { (void)c; }
void spu_0001_at_0085E400_spu_func_00001214(spu_context* c) { (void)c; }
void spu_0001_at_0085E400_spu_func_00001570(spu_context* c) { (void)c; }
void spu_0001_at_0085E400_spu_func_00000FB4(spu_context* c) { (void)c; }
int g_spu_ls_dbg=0, g_spu_ls_watch_n=0;
void spu_ls_watch_slow(const spu_context* c, uint32_t a, int w, const uint8_t* p, uint32_t pc, uint32_t lr) {
    (void)c;(void)a;(void)w;(void)p;(void)pc;(void)lr;
}
static uint32_t rng=0xc0611239;
static uint32_t next(void) { rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng; }
static void setup(spu_context* c, uint32_t src, uint32_t dst, uint32_t n, uint32_t offset) {
    c->image_id=2; c->host_depth=1; c->policy_mode=0;
    c->gpr[3]._u32[0]=offset;c->gpr[14]._u32[0]=offset+n;
    c->gpr[12]._u32[0]=src-offset;c->gpr[82]._u32[0]=dst-offset;
    c->gpr[4]._u32[0]=n;c->gpr[6]._u32[0]=src;c->gpr[7]._u32[0]=dst;
    c->gpr[83]._u32[0]=0x30000;c->tramp_fn=NULL;
}
static double now(void) { struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9; }
int main(void) {
    assert(bces_spu_copy_selftest()==0);
    spu_context* a=calloc(1,sizeof(*a));spu_context* b=calloc(1,sizeof(*b));assert(a&&b);
    uint8_t* als=malloc(SPU_LS_SIZE);uint8_t* bls=malloc(SPU_LS_SIZE);assert(als&&bls);
    uint64_t fast=0,fallback=0;
    for (unsigned kind=0;kind<2;++kind) for(unsigned i=0;i<1100;++i) {
        memset(a,0,sizeof(*a));a->ls=als;
        for(unsigned j=0;j<128;++j)for(unsigned lane=0;lane<4;++lane)a->gpr[j]._u32[lane]=next();
        for(unsigned j=0;j<SPU_LS_SIZE;j+=4) { uint32_t v=next();memcpy(a->ls+j,&v,4); }
        uint32_t n=128+(next()%8000),src=0x8000+(next()%64)*16,dst=0x18000+(next()%64)*16;
        unsigned scenario=i%11;
        if(scenario==1)n=16+next()%112;
        if(scenario==2)dst=src+16;
        if(scenario==3)dst=src-16;
        if(scenario==4)dst=src;
        if(scenario==5)++src;
        if(scenario==6)src=SPU_LS_SIZE-32;
        setup(a,src,dst,n,16*(next()%8));
        if(scenario==7)a->image_id=3;
        if(scenario==8)a->policy_mode=1;
        g_spu_ls_dbg=scenario==9;
        bces_spu_copy_set_enabled(scenario!=10);
        memcpy(b,a,sizeof(*a));b->ls=bls;memcpy(bls,als,SPU_LS_SIZE);
        BCESSpuCopyStats before=bces_spu_copy_stats();
        (kind?bces_reference_copy_0f94:bces_reference_copy_11c8)(a);
        (kind?spu_0001_at_0085E400_spu_func_00000F94:spu_0001_at_0085E400_spu_func_000011C8)(b);
        b->ls=als;
        if(memcmp(a,b,sizeof(*a)) || memcmp(als,bls,SPU_LS_SIZE)) { fprintf(stderr,"FAIL kind=%u scenario=%u n=%u\n",kind,scenario,n);return 1; }
        b->ls=bls;
        BCESSpuCopyStats after=bces_spu_copy_stats();
        if(scenario==0)assert(after.fast_calls==before.fast_calls+1);
        else assert(after.fallback_calls==before.fallback_calls+1);
        fast+=after.fast_calls-before.fast_calls;fallback+=after.fallback_calls-before.fallback_calls;
    }
    printf("PASS: 2200 full-context differential cases, fast=%llu fallback=%llu; overlap/alignment/wrap/debug/disabled preserved\n",(unsigned long long)fast,(unsigned long long)fallback);
    g_spu_ls_dbg=0;bces_spu_copy_set_enabled(1);
    for(unsigned kind=0;kind<2;++kind) {
      const uint32_t sizes[]={128,256,512,1024,4096,32768};
      for(unsigned size=0;size<sizeof(sizes)/sizeof(sizes[0]);++size) {
        double elapsed[2];
        for(unsigned mode=0;mode<2;++mode) {
            double start=now();
            for(unsigned i=0;i<20000;++i) {
                setup(a,0x8000,0x18000,sizes[size],16);
                if(mode) (kind?spu_0001_at_0085E400_spu_func_00000F94:spu_0001_at_0085E400_spu_func_000011C8)(a);
                else (kind?bces_reference_copy_0f94:bces_reference_copy_11c8)(a);
            }
            elapsed[mode]=now()-start;
        }
        printf("HOST microbenchmark kind=%u bytes=%u reference_ms=%.3f native_ms=%.3f ratio=%.2f; not device FPS\n",kind,sizes[size],elapsed[0]*1000,elapsed[1]*1000,elapsed[0]/elapsed[1]);
      }
    }
    free(a);free(b);free(als);free(bls);
}
