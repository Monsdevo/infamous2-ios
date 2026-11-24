#include "CriticalJobTrace.h"
#include "CriticalJobFlow.h"
#include "spu_context.h"
#include "ps3emu/ps3_ftrace.h"
#include <pthread.h>
#include <time.h>
unsigned bces_critical_job_enabled;
unsigned bces_critical_flow_enabled;
unsigned bces_critical_phases_enabled;
static uint32_t sequence;
static uint32_t flow_sequence;
static uint64_t watched_page_epoch[1u << 20];
static SPU_THREAD_LOCAL uint64_t sample_epoch;
static SPU_THREAD_LOCAL uint32_t child_sequence;
static SPU_THREAD_LOCAL BCESCriticalSpan logical_jobs[16];
void bces_critical_job_enable(int enabled) {
    __atomic_store_n(&bces_critical_job_enabled,!!enabled,__ATOMIC_RELEASE);
}
void bces_critical_flow_enable(int enabled) {
    __atomic_store_n(&bces_critical_flow_enabled, !!enabled, __ATOMIC_RELEASE);
}
void bces_critical_phases_enable(int enabled) {
    __atomic_store_n(&bces_critical_phases_enabled, !!enabled, __ATOMIC_RELEASE);
}

static int flow_target(uint32_t target) {
    if (__atomic_load_n(&bces_critical_phases_enabled, __ATOMIC_RELAXED))
        return target == 0xC0018F90u;
    return target == 0xC0018F90u || target == 0xC0006898u || target == 0xC0005390u;
}

static uint32_t flow_job(const spu_context* ctx) {
    const BCESCriticalSpan* span = &logical_jobs[ctx->spu_id & 15u];
    return span->epoch == g_ps3_ft.start && span->context == (uintptr_t)ctx &&
           flow_target(span->target) ? span->id : 0;
}

static int flow_watches(uint64_t address, uint32_t size) {
    if (!size || address > UINT32_MAX || size > 0x100000000ull - address) return 0;
    uint64_t epoch = g_ps3_ft.start;
    const uint32_t last = (uint32_t)((address + size - 1) >> 12);
    for (uint32_t page = (uint32_t)(address >> 12); page <= last; ++page) {
        if (__atomic_load_n(&watched_page_epoch[page], __ATOMIC_ACQUIRE) == epoch) return 1;
    }
    return 0;
}

int bces_critical_flow_transfer(void* context, uint64_t address, uint32_t size, int put) {
    if (!size || address > UINT32_MAX || size > 0x100000000ull - address) return 0;
    if (!put && __atomic_load_n(&bces_critical_phases_enabled, __ATOMIC_RELAXED)) return 0;
    if (!put || !flow_job(context)) return flow_watches(address, size);
    uint64_t epoch = g_ps3_ft.start;
    const uint32_t last = (uint32_t)((address + size - 1) >> 12);
    for (uint32_t page = (uint32_t)(address >> 12); page <= last; ++page) {
        __atomic_store_n(&watched_page_epoch[page], epoch, __ATOMIC_RELEASE);
    }
    return 1;
}

static uint32_t flow_be32(const uint8_t* p) {
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] << 8) | p[3];
}

void bces_critical_flow_dma(void* context, uint32_t address, uint32_t size,
                            uint32_t lsa, const uint8_t* put_source, uint64_t start, uint64_t end) {
    const spu_context* ctx = context;
    uint32_t tag = __atomic_add_fetch(&flow_sequence, 1, __ATOMIC_RELAXED);
    uint32_t job = flow_job(ctx);
    ps3_ft_span(put_source ? 420 : 423, tag, address, size, start, end);
    ps3_ft_span(421, tag, job, ctx->spu_id, start, end);
    ps3_ft_span(422, tag, lsa, ctx->image_id, start, end);
    ps3_ft_span(428, tag, ctx->pc, ctx->gpr[0]._u32[0], start, end);
    if (job && put_source && size >= 4) {
        ps3_ft_span(430, tag, flow_be32(put_source), size >= 8 ? flow_be32(put_source + 4) : 0, start, end);
    }
}

void bces_critical_flow_fifo(uint32_t address, uint32_t word, int header) {
    if (__atomic_load_n(&bces_critical_phases_enabled, __ATOMIC_RELAXED)) return;
    // Record exactly the observed dword at each 32-byte aligned address.
    if ((address & 31u) || !flow_watches(address, 4)) return;
    uint64_t now = ps3_ft_now();
    ps3_ft_span(header ? 429 : 431, word, address, 4, now, now);
}

void bces_critical_flow_rsx(uint32_t address, uint32_t size, uint32_t source) {
    if (__atomic_load_n(&bces_critical_phases_enabled, __ATOMIC_RELAXED)) return;
    if (!flow_watches(address, size)) return;
    uint64_t now = ps3_ft_now();
    ps3_ft_span(424, source, address, size, now, now);
}

void bces_critical_flow_ppu(uint32_t address, uint32_t size, uintptr_t caller, uint32_t thread) {
    if (__atomic_load_n(&bces_critical_phases_enabled, __ATOMIC_RELAXED)) return;
    if (!flow_watches(address, size)) return;
    uint64_t now = ps3_ft_now();
    uint32_t tag = __atomic_add_fetch(&flow_sequence, 1, __ATOMIC_RELAXED);
    uint64_t pc = caller & 0x0000ffffffffffffull;
    ps3_ft_span(425, tag, address, size, now, now);
    ps3_ft_span(426, tag, (uint32_t)pc, (uint32_t)(pc >> 32), now, now);
    ps3_ft_span(427, tag, thread, 0, now, now);
}
static uint64_t cpu_now(void) {
    struct timespec t;
    if(clock_gettime(CLOCK_THREAD_CPUTIME_ID,&t))return UINT64_MAX;
    return (uint64_t)t.tv_sec*1000000000ull+t.tv_nsec;
}
typedef struct {
    uint64_t start, cpu;
    uint32_t job, tag;
} PhaseSpan;

static SPU_THREAD_LOCAL PhaseSpan phases[16][8];

void bces_critical_phase(void* context, unsigned phase, int entering) {
    if (!__atomic_load_n(&bces_critical_phases_enabled, __ATOMIC_RELAXED) ||
        __atomic_load_n(&g_ps3_ft.on, __ATOMIC_ACQUIRE) != 2 || phase >= 8) return;
    const spu_context* ctx = context;
    uint32_t job = flow_job(ctx);
    if (!job) return;
    PhaseSpan* span = &phases[ctx->spu_id & 15u][phase];
    uint64_t now = ps3_ft_now();
    if (entering) {
        if (span->job == job)
            ps3_ft_span(443, span->tag, job, phase, span->start, now);
        *span = (PhaseSpan){now, cpu_now(), job, __atomic_add_fetch(&flow_sequence, 1, __ATOMIC_RELAXED)};
        ps3_ft_span(440, span->tag, job, phase, now, now);
    } else if (span->job == job) {
        uint64_t cpu = cpu_now();
        uint64_t delta = cpu != UINT64_MAX && cpu >= span->cpu ? cpu - span->cpu : UINT64_MAX;
        ps3_ft_span(441, span->tag, job, phase, span->start, now);
        ps3_ft_span(442, span->tag, (uint32_t)delta, (uint32_t)(delta >> 32), span->start, now);
        *span = (PhaseSpan){0};
    }
}
BCESCriticalSpan bces_critical_begin(void* opaque,uint32_t target,uint32_t return_pc) {
    BCESCriticalSpan s={0};
    if(!__atomic_load_n(&bces_critical_job_enabled,__ATOMIC_RELAXED)||
       __atomic_load_n(&g_ps3_ft.on,__ATOMIC_ACQUIRE)!=2)return s;
    if (__atomic_load_n(&bces_critical_flow_enabled, __ATOMIC_RELAXED) && !flow_target(target)) return s;
    s.epoch=g_ps3_ft.start;s.start=ps3_ft_now();
    if(s.start<s.epoch||s.start>g_ps3_ft.end)return (BCESCriticalSpan){0};
    if(sample_epoch!=s.epoch){sample_epoch=s.epoch;child_sequence=0;}
    s.weight=target==0x5A98?16:1;
    if(s.weight==16 && ((child_sequence++)&15u))return (BCESCriticalSpan){0};
    spu_context* c=opaque;
    s.id=__atomic_add_fetch(&sequence,1,__ATOMIC_RELAXED);
    s.context=(uintptr_t)c;s.target=target;s.return_pc=return_pc;
    s.depth=c->host_depth;s.spu=c->spu_id;s.r3=c->gpr[3]._u32[0];s.r4=c->gpr[4]._u32[0];
    s.ovl=c->resident_ovl;s.image=c->image_id;s.task=c->resident_task;
    pthread_threadid_np(NULL,&s.native);s.cpu=cpu_now();
    ps3_ft_span(400,s.id,target,s.spu,s.start,s.start);
    return s;
}
static void finish(BCESCriticalSpan s,void* opaque,uint32_t return_pc) {
    if(!s.id)return;
    uint64_t cpu=cpu_now(),end=ps3_ft_now(),native=0;
    pthread_threadid_np(NULL,&native);
    if(__atomic_load_n(&g_ps3_ft.on,__ATOMIC_ACQUIRE)!=2||
       s.epoch!=g_ps3_ft.start||s.context!=(uintptr_t)opaque)return;
    spu_context* c=opaque;
    const int valid_cpu=native==s.native && cpu!=UINT64_MAX && s.cpu!=UINT64_MAX && cpu>=s.cpu;
    uint64_t delta=valid_cpu?cpu-s.cpu:UINT64_MAX;
    ps3_ft_span(401,s.id,s.target,s.spu,s.start,end);
    ps3_ft_span(402,s.id,(uint32_t)delta,(uint32_t)(delta>>32),s.start,end);
    ps3_ft_span(403,s.id,(uint32_t)native,(uint32_t)(native>>32),s.start,end);
    ps3_ft_span(404,s.id,s.return_pc,return_pc,s.start,end);
    ps3_ft_span(405,s.id,s.r3,s.r4,s.start,end);
    ps3_ft_span(406,s.id,s.depth,(uint32_t)c->host_depth,s.start,end);
    ps3_ft_span(407,s.id,(uint32_t)s.context,(uint32_t)(s.context>>32),s.start,end);
    ps3_ft_span(408,s.id,s.weight,valid_cpu,s.start,end);
    ps3_ft_span(409,s.id,c->resident_ovl,(uint32_t)c->image_id,s.start,end);
    ps3_ft_span(410,s.id,s.ovl,c->resident_ovl,s.start,end);
    ps3_ft_span(411,s.id,s.task,c->resident_task,s.start,end);
    ps3_ft_span(412,s.id,s.image,(uint32_t)c->image_id,s.start,end);
}
void bces_critical_end(BCESCriticalSpan s,void* opaque) {
    spu_context* c=opaque;finish(s,opaque,c->pc&SPU_LS_MASK);
}
void bces_critical_logical_begin(void* opaque,uint32_t entry) {
    spu_context* c=opaque;
    if((c->gpr[0]._u32[0]&SPU_LS_MASK)!=0x3218)return;
    BCESCriticalSpan next=bces_critical_begin(c,0xC0000000u|entry,0x3218);
    if(!next.id)return;
    BCESCriticalSpan* previous=&logical_jobs[c->spu_id&15u];
    if(previous->id && previous->epoch==next.epoch)
        ps3_ft_span(418,previous->id,1,next.target,previous->start,next.start);
    *previous=next;
}
void bces_critical_logical_end(void* opaque) {
    spu_context* c=opaque;BCESCriticalSpan* slot=&logical_jobs[c->spu_id&15u];
    if((c->gpr[0]._u32[0]&SPU_LS_MASK)!=0x3218)return;
    if(slot->context!=(uintptr_t)c||!slot->id)return;
    BCESCriticalSpan s=*slot;*slot=(BCESCriticalSpan){0};
    finish(s,c,c->gpr[0]._u32[0]&SPU_LS_MASK);
}
