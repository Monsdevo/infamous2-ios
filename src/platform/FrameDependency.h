#pragma once
#include <stdint.h>

/* Only full writes of lighting and SSAO label words. No memory reads here. */
static inline int bces_trace_covers_word(uint64_t ea, uint32_t size, uint32_t word) {
    return ea <= word && ea + (uint64_t)size >= (uint64_t)word + 4;
}
static inline int bces_trace_label_range(uint64_t ea, uint32_t size, uint32_t base) {
    return bces_trace_covers_word(ea,size,base+0x870u) ||
           bces_trace_covers_word(ea,size,base+0x880u) ||
           bces_trace_covers_word(ea,size,base+0x890u);
}
static inline uint32_t bces_trace_be_word(const uint8_t* p) {
    return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
}
#ifdef __cplusplus
extern "C" {
#endif
void bces_frame_trace_dma(uint32_t spu_id, int image, uint32_t pc, uint32_t lr,
    uint64_t ea, uint32_t lsa, uint32_t size, const uint8_t* source,
    uint32_t label_base, uint64_t begin, uint64_t end);
#ifdef __cplusplus
}
#endif
