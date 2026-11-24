#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Read-only, bounded diagnostic hooks; callers admit them only during a trace. */
void bces_progress_trace_set_compact(int enabled);
int bces_progress_trace_compact(void);
void bces_progress_trace_ppu(uint32_t tid,uint32_t lr,uint64_t begin,uint64_t end);
int bces_progress_trace_watched(uint64_t ea,uint32_t size);
void bces_progress_trace_dma(uint32_t spu,int image,uint32_t pc,uint32_t lr,
    uint64_t ea,uint32_t lsa,uint32_t size,const uint8_t* source,const uint8_t* ls,
    uint32_t command,uint64_t begin,uint64_t end);
#ifdef __cplusplus
}
#endif
