#include "FrameTrace.h"
#include "FrameDependency.h"
#include "ProgressTrace.h"
#include <TargetConditionals.h>
#include "ps3emu/ps3_ftrace.h"
#include <execinfo.h>
#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <mach/mach_time.h>
#include <pthread.h>
#include <atomic>
#include <algorithm>

// One strong allocation: weak definitions of different sizes must never be
// coalesced into a too-small object when instrumentation extends the state.
extern "C" { ps3_ft_state g_ps3_ft={}; }

namespace {
char directory[1024],token[80];
int status=0;
std::atomic<uint64_t> ppu_native[PS3_FT_TIDS]{};
#if TARGET_OS_IPHONE
constexpr unsigned capacity=500000;
#else
constexpr unsigned capacity=2000000;
#endif
std::atomic<uint32_t> dependency_sequence{0};
}
extern "C" void bces_frame_trace_dma(uint32_t spu_id,int image,uint32_t pc,uint32_t lr,
    uint64_t ea,uint32_t lsa,uint32_t size,const uint8_t* source,
    uint32_t label_base,uint64_t begin,uint64_t end) {
    if(!PS3_FT_ON() || end<g_ps3_ft.start || begin>g_ps3_ft.end)return;
    uint64_t native=0;pthread_threadid_np(nullptr,&native);
    // Rare filtered writes only. Native ancestry identifies the lifted caller
    // even when ctx->pc/image still describe a dispatcher rather than the job.
    void* stack[12];int depth=backtrace(stack,12);
    for(uint32_t offset : {0x870u,0x880u,0x890u}) {
        uint32_t word=label_base+offset;
        if(!bces_trace_covers_word(ea,size,word))continue;
        uint32_t tag=++dependency_sequence;
        uint32_t value=bces_trace_be_word(source+(word-ea));
        ps3_ft_span(21,tag,offset,value,begin,end);
        ps3_ft_span(22,tag,spu_id,(uint32_t)image,begin,end);
        ps3_ft_span(23,tag,pc,lr,begin,end);
        ps3_ft_span(24,tag,lsa,size,begin,end);
        ps3_ft_span(18,spu_id|0x80000000u,(uint32_t)native,(uint32_t)(native>>32),begin,end);
        for(int i=0;i<depth;++i) {
            uintptr_t addr=(uintptr_t)stack[i];
            // Remove arm64 return-address authentication bits, as CPUProfile does.
            addr&=0x0000ffffffffffffull;
            ps3_ft_span(64+i,tag,(uint32_t)addr,(uint32_t)(addr>>32),begin,end);
        }
    }
}
extern "C" void bces_frame_trace_configure(const char* path) {
    if(path)snprintf(directory,sizeof directory,"%s",path);
}
extern "C" int bces_frame_trace_state(void){return status;}
extern "C" void bces_frame_trace_register_ppu(uint32_t id) {
    if(id<PS3_FT_TIDS){uint64_t tid=0;pthread_threadid_np(nullptr,&tid);ppu_native[id]=tid;}
}
extern "C" void bces_frame_trace_poll(void) {
    if(!directory[0])return;
    auto* s=&g_ps3_ft;
    if(status==1 && ps3_ft_now()>s->end) {
        __atomic_store_n(&s->on,3,__ATOMIC_RELEASE);status=2;
    }
    if(status==2) {
        // Never read partially filled records or reset a live writer's storage.
        if(__atomic_load_n(&s->writers,__ATOMIC_ACQUIRE))return;
        char path[1200];snprintf(path,sizeof path,"%s/frame-trace.csv",directory);
        FILE* out=fopen(path,"w");if(!out){status=-1;return;}
        unsigned n=std::min(s->n,s->cap);
        mach_timebase_info_data_t scale;mach_timebase_info(&scale);
        double before=double(mach_absolute_time())*scale.numer/scale.denom/1e9;
        double clock=double(ps3_ft_now())/1e9;
        double after=double(mach_absolute_time())*scale.numer/scale.denom/1e9;
        const auto* header=(const mach_header_64*)_dyld_get_image_header(0);
        const load_command* command=(const load_command*)(header+1);char uuid[37]={};
        uintptr_t app_end=(uintptr_t)header;
        for(unsigned i=0;i<header->ncmds;++i) {
            if(command->cmd==LC_UUID) {
                const auto* u=((const uuid_command*)command)->uuid;
                snprintf(uuid,sizeof uuid,"%02X%02X%02X%02X-%02X%02X-%02X%02X-%02X%02X-%02X%02X%02X%02X%02X%02X",u[0],u[1],u[2],u[3],u[4],u[5],u[6],u[7],u[8],u[9],u[10],u[11],u[12],u[13],u[14],u[15]);
            } else if(command->cmd==LC_SEGMENT_64) {
                const auto* segment=(const segment_command_64*)command;
                if(strcmp(segment->segname,"__PAGEZERO"))
                    app_end=std::max(app_end,uintptr_t(segment->vmaddr+segment->vmsize+_dyld_get_image_vmaddr_slide(0)));
            }
            command=(const load_command*)((const char*)command+command->cmdsize);
        }
        fprintf(out,"# {\"token\":\"%s\",\"start\":%.9f,\"end\":%.9f,\"rows\":%u,\"dropped\":%u,\"monotonic_minus_mach_s\":%.9f,\"clock_calibration_width_s\":%.9f,\"uuid\":\"%s\",\"app_base\":%llu,\"app_end\":%llu}\n",token,s->start/1e9,s->end/1e9,n,s->dropped,clock-(before+after)/2,after-before,uuid,(unsigned long long)header,(unsigned long long)app_end);
        fputs("kind,who,a,b,start_s,end_s\n",out);
        for(unsigned i=0;i<n;++i) {
            const auto& r=s->buf[i];
            fprintf(out,"%u,%u,%u,%u,%.9f,%.9f\n",r.kind,r.who,r.a,r.b,r.t0/1e9,r.t1/1e9);
        }
        if(fclose(out))status=-1;else status=3;
        char names[PS3_FT_TIDS][28];
        while(__atomic_exchange_n(&s->names_lock,1,__ATOMIC_ACQUIRE)) {}
        memcpy(names,s->names,sizeof names);
        __atomic_store_n(&s->names_lock,0,__ATOMIC_RELEASE);
        snprintf(path,sizeof path,"%s/frame-thread-map.csv",directory);
        out=fopen(path,"w");
        if(out){fputs("logical_id,native_id,name\n",out);for(unsigned i=0;i<PS3_FT_TIDS;++i)if(ppu_native[i].load())fprintf(out,"%u,%llu,%s\n",i,(unsigned long long)ppu_native[i].load(),names[i]);fclose(out);}
        return;
    }
    if(status==1)return;
    char path[1200];snprintf(path,sizeof path,"%s/frame-trace-control.txt",directory);
    FILE* f=fopen(path,"r");if(!f)return;
    char command[16]={},next[80]={};unsigned seconds=10;
    int count=fscanf(f,"%15s %79s %u",command,next,&seconds);fclose(f);
    if(count<2 || strcmp(command,"start") || !strcmp(next,token) || seconds<1 || seconds>30)return;
    for(char* p=next;*p;++p)if(!((*p>='a'&&*p<='z')||(*p>='A'&&*p<='Z')||(*p>='0'&&*p<='9')||*p=='-'||*p=='_'))return;
    if(__atomic_load_n(&s->writers,__ATOMIC_ACQUIRE))return;
    if(!s->buf){s->buf=(ps3_ft_rec*)calloc(capacity,sizeof(ps3_ft_rec));if(!s->buf){status=-1;return;}}
    strcpy(token,next);s->cap=capacity;s->n=0;s->dropped=0;s->dumped=0;
    s->base=ps3_ft_now();s->start=s->base+250000000;s->end=s->start+uint64_t(seconds)*1000000000;
    s->min=20000;s->merge=0;status=1;
    __atomic_store_n(&s->on,2,__ATOMIC_RELEASE);
}
