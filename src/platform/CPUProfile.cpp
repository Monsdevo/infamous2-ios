#include "CPUProfile.h"
#include <mach/mach.h>
#include <mach/mach_time.h>
#include <mach/arm/thread_status.h>
#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <pthread.h>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <unistd.h>

namespace {
constexpr unsigned capacity=50000,depth_limit=16;
struct Row { double time; uint64_t tid,cpu_us; unsigned depth,run_state,census; uintptr_t pc[depth_limit]; };
std::atomic<int> state{0};
char directory[1024],last_token[80];
unsigned duration=30;
double seconds() {
    static mach_timebase_info_data_t scale=[] { mach_timebase_info_data_t t;mach_timebase_info(&t);return t; }();
    return double(mach_absolute_time())*scale.numer/scale.denom/1e9;
}
void* capture(void*) {
    pthread_setname_np("BCES CPU sampler");
    Row* rows=static_cast<Row*>(calloc(capacity,sizeof(Row)));
    if(!rows){state=-1;return nullptr;}
    thread_t own=mach_thread_self();
    unsigned count=0,errors=0,truncated=0,ticks=0;
    double start=seconds(),finish=start+duration;
    while(seconds()<finish && count<capacity) {
        double tick=seconds();
        thread_act_array_t threads=nullptr;mach_msg_type_number_t n=0;
        if(task_threads(mach_task_self(),&threads,&n)!=KERN_SUCCESS){++errors;usleep(20000);continue;}
        for(unsigned i=0;i<n;++i) {
            thread_t thread=threads[i];
            if(thread!=own) {
                thread_basic_info_data_t basic={};mach_msg_type_number_t size=THREAD_BASIC_INFO_COUNT;
                kern_return_t rc=thread_info(thread,THREAD_BASIC_INFO,(thread_info_t)&basic,&size);
                const bool census=(ticks%10)==0;
                if(rc==KERN_SUCCESS && (basic.run_state==TH_STATE_RUNNING || census) && !(basic.flags&TH_FLAGS_IDLE) && count<capacity) {
                    arm_thread_state64_t regs={};size=ARM_THREAD_STATE64_COUNT;
                    if(thread_get_state(thread,ARM_THREAD_STATE64,(thread_state_t)&regs,&size)==KERN_SUCCESS) {
                        thread_identifier_info_data_t id={};size=THREAD_IDENTIFIER_INFO_COUNT;
                        if(thread_info(thread,THREAD_IDENTIFIER_INFO,(thread_info_t)&id,&size)!=KERN_SUCCESS)id.thread_id=thread;
                        Row& r=rows[count++];r.time=seconds();r.tid=id.thread_id;r.run_state=basic.run_state;r.census=census;
                        r.cpu_us=uint64_t(basic.user_time.seconds+basic.system_time.seconds)*1000000+basic.user_time.microseconds+basic.system_time.microseconds;
                        r.pc[0]=arm_thread_state64_get_pc(regs);r.depth=1;
                        uintptr_t fp=arm_thread_state64_get_fp(regs),sp=arm_thread_state64_get_sp(regs);
                        // Never suspend a thread or directly dereference its changing stack.
                        // Best-effort FP ancestry is secondary to the sampled PC.
                        while(r.depth<depth_limit && fp>=sp && fp-sp<8*1024*1024 && !(fp&15)) {
                            uintptr_t frame[2]={};vm_size_t got=0;
                            if(vm_read_overwrite(mach_task_self(),fp,sizeof frame,(vm_address_t)frame,&got)!=KERN_SUCCESS || got!=sizeof frame)break;
                            // iOS arm64 return addresses may carry pointer-authentication bits.
                            r.pc[r.depth++]=frame[1]&0x0000ffffffffffffull;
                            if(frame[0]<=fp)break;
                            fp=frame[0];
                        }
                    } else ++errors;
                }
            }
            mach_port_deallocate(mach_task_self(),thread);
        }
        vm_deallocate(mach_task_self(),(vm_address_t)threads,n*sizeof(thread_t));
        ++ticks;
        double remaining=0.020-(seconds()-tick);
        if(remaining>0)usleep(useconds_t(remaining*1e6));
    }
    if(count==capacity)truncated=1;
    double end=seconds();mach_port_deallocate(mach_task_self(),own);state=2;
    const mach_header_64* header=(const mach_header_64*)_dyld_get_image_header(0);
    uintptr_t base=(uintptr_t)header,limit=base;char uuid[37]={};
    const load_command* cmd=(const load_command*)(header+1);
    for(unsigned i=0;i<header->ncmds;++i) {
        if(cmd->cmd==LC_UUID) {
            const unsigned char* u=((const uuid_command*)cmd)->uuid;
            snprintf(uuid,sizeof uuid,"%02X%02X%02X%02X-%02X%02X-%02X%02X-%02X%02X-%02X%02X%02X%02X%02X%02X",u[0],u[1],u[2],u[3],u[4],u[5],u[6],u[7],u[8],u[9],u[10],u[11],u[12],u[13],u[14],u[15]);
        } else if(cmd->cmd==LC_SEGMENT_64) {
            const auto* segment=(const segment_command_64*)cmd;
            if(strcmp(segment->segname,"__PAGEZERO")) {
                uintptr_t top=segment->vmaddr+segment->vmsize+_dyld_get_image_vmaddr_slide(0);
                if(top>limit)limit=top;
            }
        }
        cmd=(const load_command*)((const char*)cmd+cmd->cmdsize);
    }
    char path[1200];snprintf(path,sizeof path,"%s/cpu-profile.csv",directory);
    FILE* out=fopen(path,"w");
    if(out) {
        fprintf(out,"# {\"uuid\":\"%s\",\"app_base\":%llu,\"app_end\":%llu,\"start\":%.9f,\"end\":%.9f,\"rows\":%u,\"ticks\":%u,\"errors\":%u,\"truncated\":%u,\"token\":\"%s\",\"method\":\"50Hz running-thread PC; unsuspended best-effort FP ancestry\"}\n",uuid,(unsigned long long)base,(unsigned long long)limit,start,end,count,ticks,errors,truncated,last_token);
        fputs("monotonic_s,thread_id,cpu_us,state,census,pcs\n",out);
        for(unsigned i=0;i<count;++i) {
            const auto& r=rows[i];fprintf(out,"%.9f,%llu,%llu,%u,%u,",r.time,(unsigned long long)r.tid,(unsigned long long)r.cpu_us,r.run_state,r.census);
            for(unsigned j=0;j<r.depth;++j)fprintf(out,"%s%llx",j?";":"",(unsigned long long)r.pc[j]);
            fputc('\n',out);
        }
        if(fclose(out))state=-1;else state=3;
    } else state=-1;
    free(rows);return nullptr;
}
}
extern "C" void bces_cpu_profile_configure(const char* path) {
    if(path)snprintf(directory,sizeof directory,"%s",path);
}
extern "C" int bces_cpu_profile_state(void){return state.load();}
extern "C" void bces_cpu_profile_poll(void) {
    if(!directory[0] || state==1 || state==2)return;
    char path[1200];snprintf(path,sizeof path,"%s/cpu-profile-control.txt",directory);
    FILE* f=fopen(path,"r");if(!f)return;
    char command[16]={},token[80]={};unsigned requested=30;
    int n=fscanf(f,"%15s %79s %u",command,token,&requested);fclose(f);
    if(n<2 || strcmp(command,"start") || !strcmp(token,last_token))return;
    // Keep metadata JSON valid; tokens are simple identifiers.
    for(char* p=token;*p;++p)if(!((*p>='a'&&*p<='z')||(*p>='A'&&*p<='Z')||(*p>='0'&&*p<='9')||*p=='-'||*p=='_'))return;
    if(requested<1 || requested>60)return;
    strcpy(last_token,token);duration=requested;state=1;
    pthread_t t;int rc=pthread_create(&t,nullptr,capture,nullptr);
    if(rc)state=-1;else pthread_detach(t);
}
