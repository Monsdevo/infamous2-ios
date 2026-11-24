#include "spu_recomp.h"
#include "EdgeGeometry.h"
#include <assert.h>
#include <time.h>
#include <unistd.h>
int g_spu_ls_dbg=0,g_spu_ls_watch_n=0;
void spu_ls_watch_slow(const spu_context*c,uint32_t a,int w,const uint8_t*p,uint32_t pc,uint32_t lr){(void)c;(void)a;(void)w;(void)p;(void)pc;(void)lr;}
void jobmod_d0d15ec83992_ea2a0_spu_func_0000D698(spu_context*c){(void)c;}
void jobmod_d0d15ec83992_ea2a0_spu_func_0000D7F4(spu_context*c){(void)c;}
void jobmod_d0d15ec83992_ea2a0_spu_func_0000D9E8(spu_context*c){(void)c;}
static uint32_t seed=0xd808da28;
static uint32_t next(void){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
static double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
typedef void(*Kernel)(spu_context*);
static Kernel kernels[]={jobmod_d0d15ec83992_ea2a0_spu_func_0000D808,jobmod_d0d15ec83992_ea2a0_spu_func_0000D8A8,jobmod_d0d15ec83992_ea2a0_spu_func_0000DA28};
static const uint32_t edge[]={0,0x80000000,1,0x007fffff,0x00800000,0x00800001,0x3f000000,0x3f800000,0x3f800001,0xbf800000,0x7f7ffffe,0x7f7fffff,0x7f800000,0x7fffffff,0xff800000,0xffffffff};
static void initialize(spu_context*c,uint8_t*ls,unsigned test){
    memset(c,0,sizeof *c);c->ls=ls;
    for(unsigned r=0;r<128;++r)for(unsigned l=0;l<4;++l)c->gpr[r]._u32[l]=test%3==0?edge[next()%16]:next();
    for(unsigned p=0;p<SPU_LS_SIZE;p+=4){uint32_t x=test%3==0?edge[next()%16]:next();memcpy(ls+p,&x,4);}
    c->gpr[50]._u32[0]=4*(1+test%8); // DA28's original four-vertex loop.
    c->gpr[45]._u32[0]=test%2;
    c->gpr[86]._u32[0]=test%3?0:0x80; // All three D8A8 exits.
}
int main(void){
    spu_context*a=calloc(1,sizeof *a),*b=calloc(1,sizeof *b);
    uint8_t*als=malloc(SPU_LS_SIZE),*bls=malloc(SPU_LS_SIZE);assert(a&&b&&als&&bls);
    uint64_t initial;__asm__ volatile("mrs %0, fpcr":"=r"(initial));
    for(unsigned mode=0;mode<8;++mode){
        uint64_t configured=(initial&~((3ull<<22)|(1ull<<24)))|((uint64_t)(mode&3)<<22)|((uint64_t)(mode>>2)<<24);
        __asm__ volatile("msr fpcr, %0\n\tisb"::"r"(configured):"memory");
        for(unsigned k=0;k<3;++k)for(unsigned t=0;t<256;++t){
            initialize(a,als,t);
            if(t&1){memcpy(a->ls_store,als,SPU_LS_SIZE);a->ls=a->ls_store;}
            memcpy(b,a,sizeof *a);b->ls=(t&1)?b->ls_store:bls;memcpy(b->ls,a->ls,SPU_LS_SIZE);
            bces_edge_set_enabled(0);kernels[k](a);
            uint64_t before,after,fpcr;__asm__ volatile("mrs %0, fpsr":"=r"(before));
            bces_edge_set_enabled(1);kernels[k](b);
            __asm__ volatile("mrs %0, fpsr":"=r"(after));__asm__ volatile("mrs %0, fpcr":"=r"(fpcr));
            assert(fpcr==configured);if(!(mode&3))assert(before==after);
            int ls_equal=!memcmp(a->ls,b->ls,SPU_LS_SIZE);b->ls=a->ls;
            if(memcmp(a,b,sizeof *a)||!ls_equal){
                fprintf(stderr,"FAIL mode=%u kernel=%u case=%u pc=%x/%x\n",mode,k,t,a->pc,b->pc);return 1;
            }
        }
    }
    __asm__ volatile("msr fpcr, %0\n\tisb"::"r"(initial):"memory");
    assert(bces_edge_validations()==24 && bces_edge_mismatches()==0);
    puts("PASS: 6144 complete context/256 KiB LS comparisons; internal/external LS; RN fast path and other rounding-mode fallback; FZ off/on; FPCR preserved; accelerated FPSR preserved; three D8A8 exits; DA28 1..8 iterations");
    // Bounded normal-value microbenchmark; the same fixture is reset per call.
    // This does not predict iPhone frame rate or a complete Edge job's cost.
    for(unsigned k=0;k<3;++k){
        memset(a,0,sizeof *a);a->ls=als;
        for(unsigned p=0;p<SPU_LS_SIZE;p+=4){uint32_t x=0x3f000000+(next()&0x3fffff);memcpy(als+p,&x,4);}
        for(unsigned r=0;r<128;++r)for(unsigned l=0;l<4;++l)a->gpr[r]._u32[l]=0x3f000000+(next()&0x3fffff);
        double elapsed[2];
        for(unsigned mode=0;mode<2;++mode){
            bces_edge_set_enabled(mode);elapsed[mode]=0;
            for(unsigned i=0;i<10000;++i){memcpy(b,a,sizeof *a);memcpy(bls,als,SPU_LS_SIZE);b->ls=bls;b->gpr[50]._u32[0]=4;double start=now();kernels[k](b);elapsed[mode]+=now()-start;}
        }
        printf("HOST block=%u reference_ms=%.3f candidate_ms=%.3f ratio=%.3f (synthetic kernel with timer overhead, not iPhone FPS)\n",k,elapsed[0]*1000,elapsed[1]*1000,elapsed[0]/elapsed[1]);
    }
    char directory[]="/tmp/bces-edge-XXXXXX";assert(mkdtemp(directory));
    char path[256];snprintf(path,sizeof path,"%s/edge-control.txt",directory);
    bces_edge_control_configure(directory);
    FILE*f=fopen(path,"w");assert(f);fputs("off test1\n",f);fclose(f);
    bces_edge_control_poll();assert(!bces_edge_enabled());
    f=fopen(path,"w");assert(f);fputs("on test1\n",f);fclose(f);
    bces_edge_control_poll();assert(!bces_edge_enabled()); // Duplicate token.
    f=fopen(path,"w");assert(f);fputs("on test2\n",f);fclose(f);
    bces_edge_control_poll();assert(bces_edge_enabled());
    bces_edge_validation_result(0);assert(!bces_edge_enabled());
    f=fopen(path,"w");assert(f);fputs("on test3\n",f);fclose(f);
    bces_edge_control_poll();assert(!bces_edge_enabled()&&bces_edge_mismatches()==1);
    assert(!unlink(path));assert(!rmdir(directory));
    puts("PASS: on/off control, duplicate-token rejection and mismatch latch");
    free(a);free(b);free(als);free(bls);return 0;
}
