#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct BCESEdgeSpan {
    uint64_t start,cpu,epoch;
    uintptr_t context;
    uint32_t id,target,caller,spu,sampled,args[8];
} BCESEdgeSpan;
void bces_edge_flow_enable(int enabled);
BCESEdgeSpan bces_edge_span_begin(void* context,uint32_t caller,uint32_t target);
void bces_edge_span_end(BCESEdgeSpan span,void* context);
void bces_edge_job_begin(void* context);
void bces_edge_job_end(void* context);
void bces_edge_flow_dma(void* context,uint64_t ea,uint32_t lsa,uint32_t size,uint32_t cmd);
void bces_edge_flow_reader(const void* pointer,uint64_t bytes,uint32_t kind,uint32_t location,uint32_t offset);
#ifdef __cplusplus
}
#endif
