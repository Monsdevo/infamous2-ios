#include "ProgressTrace.h"
#include "ps3emu/ps3_ftrace.h"
#include "ppu_context.h"
#include <cassert>
#include <vector>
#include <cstdio>
extern "C" {
PPU_THREAD_LOCAL ppu_context* g_active_ctx=nullptr;
uint8_t* vm_base=nullptr;
uint32_t ppu_vm_size=0x30000;
ps3_ft_state g_ps3_ft={};
}
static void put16(unsigned a,unsigned v){vm_base[a]=v>>8;vm_base[a+1]=v;}
static void put32(unsigned a,unsigned v){put16(a,v>>16);put16(a+2,v);}
static const ps3_ft_rec& event(unsigned kind){
    for(unsigned i=g_ps3_ft.n;i--;)if(g_ps3_ft.buf[i].kind==kind)return g_ps3_ft.buf[i];
    assert(false);return g_ps3_ft.buf[0];
}
int main(){
    std::vector<uint8_t> memory(ppu_vm_size);vm_base=memory.data();
    std::vector<ps3_ft_rec> records(1024);g_ps3_ft.buf=records.data();g_ps3_ft.cap=records.size();
    uint64_t t=ps3_ft_now();g_ps3_ft.start=t-1000000;g_ps3_ft.end=t+1000000000;g_ps3_ft.on=2;
    ppu_context ctx={};ctx.thread_id=1;ctx.gpr[31]=0x11000;ctx.gpr[29]=0;g_active_ctx=&ctx;
    put32(0x11000,0x12000);put32(0x12030,0x13000);
    for(unsigned i=0;i<8;i++)put16(0x12040+i*2,i?5:4);
    put16(0x13000+4*8+2,7);put16(0x13000+5*8+2,2); // zero terminator at6
    auto before=memory;auto saved=ctx;
    bces_progress_trace_ppu(1,0x370694,t,t);
    assert(memory==before && !memcmp(&ctx,&saved,sizeof ctx));
    assert(event(300).a==0x12040 && event(302).b==6 && event(305).b==2);
    assert(bces_progress_trace_watched(0x12040,16));
    assert(!bces_progress_trace_watched(0x1203f,1));
    assert(bces_progress_trace_watched(0x1204f,1));
    assert(!bces_progress_trace_watched(0x12050,1));
    assert(!bces_progress_trace_watched(UINT64_MAX-1,4));
    assert(!bces_progress_trace_watched(UINT32_MAX,2));
    uint8_t partial[]={0x01,0x23};
    bces_progress_trace_dma(8192,234,0x1234,0x4321,0x12046,0,2,partial,nullptr,0x20,t,t+1);
    assert(event(324).a==0xc0 && event(325).b==0x123);
    unsigned n=g_ps3_ft.n;
    bces_progress_trace_ppu(2,0x370694,t,t+2000000);assert(g_ps3_ft.n==n);
    ctx.gpr[29]=8;bces_progress_trace_ppu(1,0x370694,t,t+2000000);assert(g_ps3_ft.n==n);
    ctx=saved;ctx.gpr[28]=0x11000;ctx.gpr[27]=0;ctx.gpr[29]=17;
    bces_progress_trace_ppu(1,0x37110c,t,t+2000000);assert(event(302).b==17);
    g_ps3_ft.start++;assert(!bces_progress_trace_watched(0x12040,16));
    ctx=saved;for(unsigned i=0;i<64;i++)put16(0x13000+(4+i)*8+2,1);
    before=memory;bces_progress_trace_ppu(1,0x370694,t,t+4000000);
    assert(event(302).b==UINT32_MAX && event(305).b==64);
    assert(memory==before && !memcmp(&ctx,&saved,sizeof ctx));
    g_active_ctx=nullptr;n=g_ps3_ft.n;bces_progress_trace_ppu(1,0x370694,t,t+6000000);assert(g_ps3_ft.n==n);
    // Compact mode keeps the exact seven successful-write core events. Native
    // identity is emitted once/window/issuer without waiting for an SPU wait.
    bces_progress_trace_set_compact(1);assert(bces_progress_trace_compact());
    n=g_ps3_ft.n;
    bces_progress_trace_dma(8192,234,0x1234,0x4321,0x12046,0,2,partial,nullptr,0x20,t,t+1);
    assert(g_ps3_ft.n==n+8&&event(18).who==(8192u|0x80000000u));
    for(unsigned i=n;i<g_ps3_ft.n;i++)assert(g_ps3_ft.buf[i].kind==18||(g_ps3_ft.buf[i].kind>=320&&g_ps3_ft.buf[i].kind<=326));
    n=g_ps3_ft.n;bces_progress_trace_dma(8192,234,0x1234,0x4321,0x12046,0,2,partial,nullptr,0x20,t,t+1);assert(g_ps3_ft.n==n+7);
    n=g_ps3_ft.n;bces_progress_trace_dma(8193,234,0x1234,0x4321,0x12046,0,2,partial,nullptr,0x20,t,t+1);assert(g_ps3_ft.n==n+8&&event(18).who==(8193u|0x80000000u));
    assert(memory==before);
    // Focused mode records the real poll bracket and a separately timed
    // POST-poll snapshot, even when the ordinary 1ms sampler is throttled.
    bces_progress_trace_set_compact(2);assert(bces_progress_trace_compact()==2);
    ctx=saved;g_active_ctx=&ctx;uint64_t q=ps3_ft_now();g_ps3_ft.start=q-1000;
    bces_progress_trace_ppu(1,0x370694,q-50000,q);
    assert(event(310).a==0x12040 && event(310).t0==q-50000 && event(310).t1==q);
    assert(event(313).a==0x370694 && event(313).t0>=q);
    n=g_ps3_ft.n;q=ps3_ft_now();bces_progress_trace_ppu(1,0x370694,q-50000,q);
    assert(g_ps3_ft.n>=n+4);assert(memory==before && !memcmp(&ctx,&saved,sizeof ctx));
    bces_progress_trace_set_compact(0);
    puts("PASS: queue/direct targets, bounded scan, read-only context/memory, partial DMA masks, window isolation and address bounds");
}
