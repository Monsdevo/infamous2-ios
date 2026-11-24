#define main edge_synthetic_test_main
#include "edge_geometry.c"
#undef main
#include "EdgeGeometrySnapshot.h"
#include <stddef.h>
int main(int argc,char**argv){
    assert(argc==2);FILE*f=fopen(argv[1],"rb");assert(f);
    EdgeSnapshot*s=malloc(sizeof *s);assert(s&&fread(s,sizeof *s,1,f)==1);fclose(f);
    assert(s->magic==0x45444745&&s->context_size==sizeof(spu_context)&&s->ls_size==SPU_LS_SIZE&&s->block<3);
    printf("fixture block=%u fpcr=%llx context_size=%u\n",s->block,(unsigned long long)s->fpcr,s->context_size);
    unsigned n=0,outside=0;for(unsigned i=0;i<sizeof(spu_context);++i)if(((uint8_t*)&s->reference)[i]!=((uint8_t*)&s->actual)[i]){
        if(i<offsetof(spu_context,ls_store)||i>=offsetof(spu_context,ls_store)+SPU_LS_SIZE)outside++;
        if(n++<20)printf("recorded_context_diff byte=%u ref=%02x actual=%02x\n",i,((uint8_t*)&s->reference)[i],((uint8_t*)&s->actual)[i]);
    }
    printf("recorded_context_diff_bytes=%u resv_word_offset=%zu gpr_offset=%zu pc_offset=%zu\n",n,offsetof(spu_context,resv_word),offsetof(spu_context,gpr),offsetof(spu_context,pc));
    printf("recorded_outside_ls_store_diff_bytes=%u\n",outside);
    n=0;for(unsigned i=0;i<SPU_LS_SIZE;++i)if(s->reference_ls[i]!=s->actual_ls[i]){if(n++<20)printf("recorded_ls_diff byte=%u ref=%02x actual=%02x\n",i,s->reference_ls[i],s->actual_ls[i]);}
    printf("recorded_ls_diff_bytes=%u\n",n);
    spu_context*a=malloc(sizeof *a),*b=malloc(sizeof *b);assert(a&&b);
    uint8_t*als=malloc(SPU_LS_SIZE),*bls=malloc(SPU_LS_SIZE);assert(als&&bls);
    memcpy(a,&s->input,sizeof *a);memcpy(b,a,sizeof *a);a->ls=a->ls_store;b->ls=b->ls_store;
    memcpy(a->ls,s->input_ls,SPU_LS_SIZE);memcpy(b->ls,s->input_ls,SPU_LS_SIZE);
    __asm__ volatile("msr fpcr, %0\n\tisb"::"r"(s->fpcr):"memory");
    bces_edge_set_enabled(0);kernels[s->block](a);
    bces_edge_set_enabled(1);kernels[s->block](b);int ls_equal=!memcmp(a->ls,b->ls,SPU_LS_SIZE);b->ls=a->ls;
    int equal=!memcmp(a,b,sizeof *a)&&ls_equal&&!bces_edge_mismatches();
    printf("host_replay_full_context_ls_equal=%d\n",equal);
    free(a);free(b);free(als);free(bls);free(s);return equal?0:1;
}
