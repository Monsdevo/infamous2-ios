#include "BCESSpuRZ.h"
#include <assert.h>
static uint32_t rng=0x7320234;
static uint32_t next(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
int main(void) {
    uint64_t initial_fpcr;__asm__ volatile("mrs %0, fpcr":"=r"(initial_fpcr));
    const uint32_t edge[]={0,0x80000000,1,0x007fffff,0x00800000,0x00800001,0x3f000000,0x3f800000,0x3f800001,0xbf800000,0x7f7ffffe,0x7f7fffff,0x7f800000,0x7fffffff,0xff800000,0xffffffff};
    for(unsigned flush=0;flush<2;++flush) {
    uint64_t configured=(initial_fpcr&~(1ull<<24))|((uint64_t)flush<<24);
    bces_rz_end(configured);
    for(unsigned i=0;i<200000;++i) {
        u128 a,b,c,ref[6],got[6];
        for(unsigned lane=0;lane<4;++lane) {
            a._u32[lane]=i<4096?edge[(i+lane)%16]:next();
            b._u32[lane]=i<4096?edge[(i/16+lane)%16]:next();
            c._u32[lane]=i<4096?edge[(i/256+lane)%16]:next();
        }
        ref[0]=spu_fa_ref(a,b);ref[1]=spu_fs_ref(a,b);ref[2]=spu_fm_ref(a,b);ref[3]=spu_fma_ref(a,b,c);ref[4]=spu_fms_ref(a,b,c);ref[5]=spu_fnms_ref(a,b,c);
        uint64_t old=bces_rz_begin();
        got[0]=bces_rz_fa(a,b);got[1]=bces_rz_fs(a,b);got[2]=bces_rz_fm(a,b);got[3]=bces_rz_fma(a,b,c);got[4]=bces_rz_fms(a,b,c);got[5]=bces_rz_fnms(a,b,c);
        bces_rz_end(old);
        uint64_t restored;__asm__ volatile("mrs %0, fpcr":"=r"(restored));assert(restored==old);
        for(unsigned op=0;op<6;++op)if(memcmp(&ref[op],&got[op],16)) {
            for(unsigned lane=0;lane<4;++lane)if(ref[op]._u32[lane]!=got[op]._u32[lane])fprintf(stderr,"FAIL i=%u op=%u lane=%u a=%08x b=%08x c=%08x ref=%08x got=%08x\n",i,op,lane,a._u32[lane],b._u32[lane],c._u32[lane],ref[op]._u32[lane],got[op]._u32[lane]);
            return 1;
        }
    }
    }
    bces_rz_end(initial_fpcr);
    puts("PASS: 9.6 million lane/op comparisons against exact integer SPU reference; flush-to-zero OFF/ON; FPCR restored");
}
