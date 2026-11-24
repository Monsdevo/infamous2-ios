#pragma once
#include "spu_context.h"
#ifdef __cplusplus
extern "C" {
#endif
struct BCESGeometryExecution;
typedef int (*BCESGeometryBatch)(struct BCESGeometryExecution*,uint32_t*,u128*,uint8_t*);
typedef struct BCESGeometryExecution {
    uint8_t* backup; // Indexed undo storage; only first-written quads are copied.
    uint32_t* dirty;
    BCESGeometryBatch batch;
    void* opaque;
    uint64_t declined;
    unsigned kind;
} BCESGeometryExecution;
static inline void bces_geometry_write(uint8_t* ls,uint32_t address,u128 value,uint32_t* dirty,BCESGeometryExecution* execution){
    address&=0x3fff0;uint32_t mask=1u<<((address>>4)&31);unsigned word=address>>9;
    if(execution&&execution->backup&&!(dirty[word]&mask))memcpy(execution->backup+address,ls+address,16);
    dirty[word]|=mask;
    for(unsigned lane=0;lane<4;lane++){uint32_t x=__builtin_bswap32(value._u32[lane]);memcpy(ls+address+lane*4,&x,4);}
}
static inline void bces_geometry_rollback(uint8_t* ls,const BCESGeometryExecution* execution){
    for(unsigned word=0;word<512;word++){uint32_t bits=execution->dirty[word];while(bits){unsigned bit=__builtin_ctz(bits),a=(word*32+bit)*16;memcpy(ls+a,execution->backup+a,16);bits&=bits-1;}}
}
int bces_geometry_skin_execute(u128*,uint8_t*,uint32_t,uint32_t*,uint32_t*,BCESGeometryExecution*);
int bces_geometry_cull_execute(u128*,uint8_t*,uint32_t,uint32_t*,uint32_t*,BCESGeometryExecution*);
#ifdef __cplusplus
}
#endif
