#include "EdgeFlow.h"
#include "spu_context.h"
#include "ps3emu/ps3_ftrace.h"
#include <time.h>
#include <pthread.h>
extern uint8_t* vm_base;
static int enabled;
static uint32_t sequence,descriptors,root_sequence,reader_sequence;
static SPU_THREAD_LOCAL BCESEdgeSpan job;
static uint32_t mix(uint32_t x){x^=x>>16;x*=0x7feb352du;x^=x>>15;x*=0x846ca68bu;return x^(x>>16);}
void bces_edge_flow_enable(int value){__atomic_store_n(&enabled,!!value,__ATOMIC_RELAXED);}
static int active(void){return __atomic_load_n(&enabled,__ATOMIC_RELAXED)&&PS3_FT_ON();}
static uint64_t cpu_now(void){struct timespec t;if(clock_gettime(CLOCK_THREAD_CPUTIME_ID,&t))return UINT64_MAX;return (uint64_t)t.tv_sec*1000000000u+t.tv_nsec;}
BCESEdgeSpan bces_edge_span_begin(void* opaque,uint32_t caller,uint32_t target){
    BCESEdgeSpan s={0};if(!active())return s;
    spu_context*c=opaque;
    if(target!=0xE2A0 && (!job.id||!job.sampled||job.context!=(uintptr_t)c||job.epoch!=g_ps3_ft.start))return s;
    s.epoch=g_ps3_ft.start;s.start=ps3_ft_now();
    if(s.start<s.epoch||s.start>g_ps3_ft.end)return (BCESEdgeSpan){0};
    s.cpu=cpu_now();s.context=(uintptr_t)c;s.id=__atomic_add_fetch(&sequence,1,__ATOMIC_RELAXED);
    s.target=target;s.caller=caller;s.spu=c->spu_id;
    uint32_t root=target==0xE2A0?__atomic_add_fetch(&root_sequence,1,__ATOMIC_RELAXED):0;
    s.sampled=target==0xE2A0?(root<=8 || !(mix(root)&15u)):1;
    for(unsigned i=0;i<8;++i)s.args[i]=c->gpr[3+i]._u32[0];
    // 5740 reads descriptor fields through r7 (+44/+48 in the lifted code).
    // Capture only eight raw 128-byte windows; this is not a decoded schema.
    if(target==0x5740 && __atomic_fetch_add(&descriptors,1,__ATOMIC_RELAXED)<8){
        uint32_t base=s.args[4]&SPU_LS_MASK;
        for(uint32_t o=0;o<128;o+=4){
            uint32_t word=0;for(unsigned b=0;b<4;++b)word=(word<<8)|c->ls[(base+o+b)&SPU_LS_MASK];
            ps3_ft_span(209,s.id,o,word,s.start,s.start);
        }
    }
    return s;
}
void bces_edge_span_end(BCESEdgeSpan s,void* opaque){
    if(!s.id||!active()||s.epoch!=g_ps3_ft.start||s.context!=(uintptr_t)opaque)return;
    spu_context*c=opaque;uint64_t end=ps3_ft_now(),cpu=cpu_now();
    uint64_t delta=s.cpu==UINT64_MAX||cpu==UINT64_MAX||cpu<s.cpu?UINT64_MAX:cpu-s.cpu;
    uint64_t native=0;pthread_threadid_np(NULL,&native);
    ps3_ft_span(200,s.id,s.target,s.spu,s.start,end);
    ps3_ft_span(201,s.id,(uint32_t)delta,(uint32_t)(delta>>32),s.start,end);
    ps3_ft_span(202,s.id,s.caller,(uint32_t)c->host_depth|(s.sampled?0x80000000u:0),s.start,end);
    ps3_ft_span(203,s.id,(uint32_t)native,(uint32_t)(native>>32),s.start,end);
    for(unsigned i=0;i<4;++i)ps3_ft_span(204+i,s.id,s.args[2*i],s.args[2*i+1],s.start,end);
    ps3_ft_span(208,s.id,c->gpr[3]._u32[0],c->gpr[4]._u32[0],s.start,end);
}
void bces_edge_job_begin(void* opaque){
    job=bces_edge_span_begin(opaque,0,0xE2A0);
}
void bces_edge_job_end(void* opaque){BCESEdgeSpan previous=job;job=(BCESEdgeSpan){0};bces_edge_span_end(previous,opaque);}
void bces_edge_flow_dma(void* opaque,uint64_t ea,uint32_t lsa,uint32_t size,uint32_t cmd){
    if(!active()||job.context!=(uintptr_t)opaque||!job.id||!job.sampled||job.epoch!=g_ps3_ft.start)return;
    spu_context*c=opaque;uint64_t t=ps3_ft_now();uint32_t tag=__atomic_add_fetch(&sequence,1,__ATOMIC_RELAXED);
    ps3_ft_span(211,tag,(uint32_t)ea,size,t,t);
    ps3_ft_span(212,tag,lsa,cmd,t,t);
    ps3_ft_span(213,tag,job.id,c->spu_id,t,t);
    ps3_ft_span(214,tag,(uint32_t)c->pc,c->gpr[0]._u32[0],t,t);
    ps3_ft_span(215,tag,(uint32_t)(ea>>32),c->image_id,t,t);
}
void bces_edge_flow_reader(const void* pointer,uint64_t bytes,uint32_t kind,uint32_t location,uint32_t offset){
    if(!pointer||!bytes||bytes>UINT32_MAX||!active()||!vm_base)return;
    uintptr_t p=(uintptr_t)pointer,base=(uintptr_t)vm_base;
    if(p<base||p-base>UINT32_MAX||bytes>0x100000000ull-(p-base))return;
    uint32_t reader=__atomic_add_fetch(&reader_sequence,1,__ATOMIC_RELAXED);
    if(reader>8 && (mix(reader)&63u))return;
    uint64_t t=ps3_ft_now();uint32_t tag=__atomic_add_fetch(&sequence,1,__ATOMIC_RELAXED);
    ps3_ft_span(220,tag,(uint32_t)(p-base),(uint32_t)bytes,t,t);
    ps3_ft_span(221,tag,kind,location,t,t);
    ps3_ft_span(222,tag,offset,reader<=8?1:64,t,t);
}
