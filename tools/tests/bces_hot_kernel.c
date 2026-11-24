#include "spu_context.h"
#include <assert.h>
#include <time.h>
void bces_hot_reference_234(spu_context*);
void bces_hot_cached_234(spu_context*);
void bces_hot_rz_234(spu_context*);
void spu_indirect_branch(spu_context* ctx){(void)ctx;}
int g_spu_ls_dbg=0,g_spu_ls_watch_n=0;
void spu_ls_watch_slow(const spu_context* c,uint32_t a,int w,const uint8_t* p,uint32_t pc,uint32_t lr){(void)c;(void)a;(void)w;(void)p;(void)pc;(void)lr;}
static uint32_t rng=0x2347320;
static uint32_t next(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
int main(void) {
    spu_context *a=calloc(1,sizeof *a),*b=calloc(1,sizeof *b);assert(a&&b);
    uint8_t *als=malloc(SPU_LS_SIZE),*bls=malloc(SPU_LS_SIZE);assert(als&&bls);
    for(unsigned test=0;test<1000;++test) {
        memset(a,0,sizeof *a);a->ls=als;a->image_id=234;a->host_depth=test&1;
        for(unsigned r=0;r<128;++r)for(unsigned lane=0;lane<4;++lane)a->gpr[r]._u32[lane]=next();
        for(unsigned p=0;p<SPU_LS_SIZE;p+=4){uint32_t v=next();memcpy(als+p,&v,4);}
        a->gpr[6]._u32[0]=4*(1+test%8);
        memcpy(b,a,sizeof *a);b->ls=bls;memcpy(bls,als,SPU_LS_SIZE);
        bces_hot_reference_234(a);
        uint64_t old_fpcr,after_fpcr;__asm__ volatile("mrs %0, fpcr":"=r"(old_fpcr));
        bces_hot_rz_234(b);
        __asm__ volatile("mrs %0, fpcr":"=r"(after_fpcr));assert(after_fpcr==old_fpcr);
        b->ls=als;
        if(memcmp(a,b,sizeof *a)||memcmp(als,bls,SPU_LS_SIZE)){fprintf(stderr,"FAIL full context/LS case=%u\n",test);return 1;}
        b->ls=bls;
    }
    puts("PASS: 1000 full-context + complete LS comparisons; random bit patterns, 1..8 loop iterations, both return modes");
    for(unsigned iterations=1;iterations<=64;iterations*=8) {
        double elapsed[2];
        // Normal finite inputs exercise the guarded floating-point fast path.
        for(unsigned p=0;p<SPU_LS_SIZE;++p)als[p]=0;
        for(unsigned mode=0;mode<2;++mode) {
            double start=now();
            for(unsigned run=0;run<2000;++run) {
                memset(a,0,sizeof *a);a->ls=als;a->host_depth=1;
                for(unsigned r=0;r<128;++r)for(unsigned lane=0;lane<4;++lane)a->gpr[r]._u32[lane]=0x3f000000+(next()&0x3fffff);
                a->gpr[6]._u32[0]=4*iterations;
                (mode?bces_hot_rz_234:bces_hot_reference_234)(a);
            }
            elapsed[mode]=now()-start;
        }
        printf("HOST iterations=%u reference_ms=%.3f rz_candidate_ms=%.3f speedup=%.3f; not iPhone FPS\n",iterations,elapsed[0]*1000,elapsed[1]*1000,elapsed[0]/elapsed[1]);
    }
    free(a);free(b);free(als);free(bls);
}
