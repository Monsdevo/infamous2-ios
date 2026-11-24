#include "ProgressTrace.h"
#include "ps3emu/ps3_ftrace.h"
#include "ppu_context.h"
#include "guest_mem_atomic.h"
#include <atomic>
#include <execinfo.h>
#include <algorithm>
#include <iterator>
#include <pthread.h>

extern "C" {
extern PPU_THREAD_LOCAL ppu_context* g_active_ctx;
extern uint8_t* vm_base;
extern uint32_t ppu_vm_size;
}
namespace {
std::atomic<uint64_t> epoch{0};
std::atomic<int> compact_mode{0};
std::atomic<uint32_t> rows[8]{};
std::atomic<uint32_t> sequence{0};
uint64_t sampled[8]{}; // main PPU only
bool range(uint64_t address,uint64_t size) {
    return vm_base && ppu_vm_size && address>=0x10000 && address<ppu_vm_size && size<=ppu_vm_size-address;
}
uint32_t be32(const uint8_t* p) {
    return uint32_t(p[0])<<24|uint32_t(p[1])<<16|uint32_t(p[2])<<8|p[3];
}
uint32_t read32(uint32_t a){return __builtin_bswap32(gm_load32(vm_base+a));}
uint16_t read16(uint32_t a){return __builtin_bswap16(gm_load16(vm_base+a));}
}
extern "C" void bces_progress_trace_set_compact(int value){compact_mode.store(value>=0&&value<=2?value:0,std::memory_order_relaxed);}
extern "C" int bces_progress_trace_compact(void){return compact_mode.load(std::memory_order_relaxed);}
extern "C" int bces_progress_trace_watched(uint64_t ea,uint32_t size) {
    if(!size || ea>UINT32_MAX || size>0x100000000ull-ea ||
       epoch.load(std::memory_order_acquire)!=g_ps3_ft.start)return 0;
    for(auto& item:rows){uint32_t row=item.load(std::memory_order_relaxed);
        if(row && ea<uint64_t(row)+16 && uint64_t(row)<ea+uint64_t(size))return 1;}
    return 0;
}
extern "C" void bces_progress_trace_ppu(uint32_t tid,uint32_t lr,uint64_t begin,uint64_t end) {
    if(tid!=1 || end<g_ps3_ft.start || end>g_ps3_ft.end)return;
    bool direct=lr==0x3710e0 || lr==0x37110c || lr==0x371138;
    bool queue=lr==0x370654 || lr==0x370694 || lr==0x3706bc;
    if(!direct && !queue)return;
    auto* ctx=g_active_ctx;
    if(!ctx || ctx->thread_id!=tid)return;
    uint32_t object=(uint32_t)ctx->gpr[direct?28:31];
    uint64_t slot=ctx->gpr[direct?27:29];
    if(slot>=8 || !range(object,12))return;
    uint32_t base=read32(object);
    uint64_t row_address=uint64_t(base)+0x40+slot*16;
    if(!range(row_address,16) || !range(uint64_t(base)+0x30+slot*4,4))return;
    if(epoch.load(std::memory_order_relaxed)!=g_ps3_ft.start){
        for(auto& item:rows)item.store(0,std::memory_order_relaxed);
        std::fill(std::begin(sampled),std::end(sampled),0);
        epoch.store(g_ps3_ft.start,std::memory_order_release);
    }
    rows[slot].store((uint32_t)row_address,std::memory_order_release);
    // At most one snapshot/ms/slot, preserving the ordinary short-sleep trace.
    const bool every_poll=compact_mode.load(std::memory_order_relaxed)==2;
    if(!every_poll && end-sampled[slot]<1000000)return;
    const uint64_t snapshot_begin=ps3_ft_now();
    uint8_t data[16];gm_copy_from(data,vm_base+row_address,16);
    uint32_t list=read32(base+0x30+(uint32_t)slot*4);
    uint32_t target=direct?(uint16_t)ctx->gpr[29]:UINT32_MAX;
    unsigned scanned=0;
    if(queue){
        uint32_t head=(uint32_t(data[0])<<8)|data[1];
        // Original005054F0 skips nonzero +2 command tags to a zero terminator.
        // Bound diagnostic reads independently of the game's unbounded scan.
        for(;scanned<64;scanned++){
            uint64_t entry=uint64_t(list)+(uint64_t(head)+scanned)*8;
            if(!range(entry,8))break;
            if(!read16((uint32_t)entry+2)){target=head+scanned;break;}
        }
    }
    const uint64_t snapshot_end=ps3_ft_now();
    if(every_poll){
        // Exact usleep bracket with an explicitly POST-poll queue snapshot.
        // The analysis rejects observed changes during the poll/read interval.
        uint32_t poll_tag=++sequence;
        ps3_ft_span(310,poll_tag,(uint32_t)row_address,target,begin,end);
        ps3_ft_span(311,poll_tag,be32(data),be32(data+4),begin,end);
        ps3_ft_span(312,poll_tag,be32(data+8),be32(data+12),begin,end);
        ps3_ft_span(313,poll_tag,lr,(uint32_t)slot,snapshot_begin,snapshot_end);
    }
    if(end-sampled[slot]<1000000)return;
    sampled[slot]=end;
    uint32_t tag=++sequence;
    ps3_ft_span(300,tag,(uint32_t)row_address,object,snapshot_begin,snapshot_end);
    ps3_ft_span(301,tag,(uint32_t)slot,lr,snapshot_begin,snapshot_end);
    ps3_ft_span(302,tag,list,target,snapshot_begin,snapshot_end);
    ps3_ft_span(303,tag,be32(data),be32(data+4),snapshot_begin,snapshot_end);
    ps3_ft_span(304,tag,be32(data+8),be32(data+12),snapshot_begin,snapshot_end);
    ps3_ft_span(305,tag,tid,scanned,snapshot_begin,snapshot_end);
}
extern "C" void bces_progress_trace_dma(uint32_t spu,int image,uint32_t pc,uint32_t lr,
    uint64_t ea,uint32_t lsa,uint32_t size,const uint8_t* source,const uint8_t* ls,
    uint32_t command,uint64_t begin,uint64_t end) {
    if(!source || !size || !PS3_FT_ON() || begin>g_ps3_ft.end || end<g_ps3_ft.start ||
       epoch.load(std::memory_order_acquire)!=g_ps3_ft.start)return;
    const bool compact=bces_progress_trace_compact();
    void* stack[12];int depth=0;
    for(auto& item:rows){
        uint32_t row=item.load(std::memory_order_acquire);
        if(!row || ea>=uint64_t(row)+16 || uint64_t(row)>=ea+uint64_t(size))continue;
        uint8_t data[16]={};uint32_t mask=0;
        for(unsigned i=0;i<16;i++)if(uint64_t(row)+i>=ea && uint64_t(row)+i-ea<size){
            data[i]=source[uint64_t(row)+i-ea];mask|=1u<<i;}
        // Called after all coherence/lock-line locks have been released.
        if(compact){
            static thread_local uint64_t mapped_epoch=0;
            static thread_local uint32_t mapped_spu=UINT32_MAX;
            if(mapped_epoch!=g_ps3_ft.start||mapped_spu!=spu){
                uint64_t native=0;pthread_threadid_np(nullptr,&native);
                ps3_ft_span(18,spu|0x80000000u,uint32_t(native),uint32_t(native>>32),begin,end);
                mapped_epoch=g_ps3_ft.start;mapped_spu=spu;
            }
        }else if(!depth)depth=backtrace(stack,12);
        uint32_t tag=++sequence;
        ps3_ft_span(320,tag,row,(uint32_t)ea,begin,end);
        ps3_ft_span(321,tag,spu,(uint32_t)image,begin,end);
        ps3_ft_span(322,tag,pc,lr,begin,end);
        ps3_ft_span(323,tag,lsa,size,begin,end);
        ps3_ft_span(324,tag,mask,command,begin,end);
        ps3_ft_span(325,tag,be32(data),be32(data+4),begin,end);
        ps3_ft_span(326,tag,be32(data+8),be32(data+12),begin,end);
        if(ls&&!compact){
            ps3_ft_span(327,tag,be32(ls+0x4010),be32(ls+0x4014),begin,end);
            ps3_ft_span(328,tag,be32(ls+0x4018),be32(ls+0x4020),begin,end);
        }
        for(int i=0;i<depth;i++){
            uintptr_t address=(uintptr_t)stack[i]&0x0000ffffffffffffull;
            ps3_ft_span(352+i,tag,(uint32_t)address,(uint32_t)(address>>32),begin,end);
        }
    }
}
