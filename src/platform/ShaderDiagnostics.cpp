// Explicit shader diagnosis: retain the latest input and allocation failure.
// No shader is skipped and no compiler optimization pass is disabled.
#include "ShaderDiagnostics.h"
#include <atomic>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <new>
#include <unistd.h>
#include <TargetConditionals.h>
#if TARGET_OS_IPHONE
#include <os/proc.h>
#endif

namespace {
int log_fd=-1;
char input_path[1024];
std::atomic<unsigned long long> sequence{0};
thread_local unsigned long long active_sequence=0;
thread_local int active_stage=0;
void write_all(int fd,const char* p,size_t n) {
    while(n) { ssize_t w=write(fd,p,n); if(w<0 && errno==EINTR)continue; if(w<=0)break;p+=w;n-=size_t(w); }
}
// Failure-path formatting must not allocate, call a C++ logger or recurse.
void failure(size_t requested) noexcept {
    if(log_fd<0 || !active_sequence)return;
    char text[256];size_t used=0;
    auto literal=[&](const char* s){size_t n=strlen(s);memcpy(text+used,s,n);used+=n;};
    auto number=[&](unsigned long long v){char digits[24];unsigned n=0;do{digits[n++]=char('0'+v%10);v/=10;}while(v);while(n)text[used++]=digits[--n];};
    literal("allocation_failure sequence=");number(active_sequence);
    literal(" stage=");number(active_stage);literal(" requested_bytes=");number(requested);
#if TARGET_OS_IPHONE
    literal(" available_bytes=");number(os_proc_available_memory());
#endif
    literal("\n");write_all(log_fd,text,used);
}
}
extern "C" void bces_shader_diagnostics_configure(const char* directory) {
    if(log_fd>=0){close(log_fd);log_fd=-1;}
    if(!directory)return;
    char log_path[1024];
    if(snprintf(input_path,sizeof input_path,"%s/shader-current.hlsl",directory)>=int(sizeof input_path))return;
    if(snprintf(log_path,sizeof log_path,"%s/shader-diagnostics.log",directory)>=int(sizeof log_path))return;
    log_fd=open(log_path,O_WRONLY|O_CREAT|O_TRUNC,0600);
}
extern "C" void bces_shader_trace_begin(const char* hlsl,int stage) {
    if(log_fd<0)return;
    active_sequence=++sequence;active_stage=stage;
    size_t n=strnlen(hlsl,512*1024);
    int fd=open(input_path,O_WRONLY|O_CREAT|O_TRUNC,0600);
    if(fd>=0){write_all(fd,hlsl,n);close(fd);}
    char row[160];int size=snprintf(row,sizeof row,"begin sequence=%llu stage=%d hlsl_bytes=%zu\n",active_sequence,stage,n);
    write_all(log_fd,row,size_t(size));
}
extern "C" void bces_shader_trace_end(int result) {
    if(log_fd<0 || !active_sequence)return;
    char row[128];int n=snprintf(row,sizeof row,"end sequence=%llu result=%d\n",active_sequence,result);
    write_all(log_fd,row,size_t(n));active_sequence=0;
}

#if BCES_TRACE_NEW_FAILURES
// Diagnostic build only. Preserve the standard malloc/new-handler/throw loop.
// Successful allocations take the same malloc path and do no tracing.
void* operator new(std::size_t size) {
    if(!size)size=1;
    for(;;) {
        if(void* p=std::malloc(size))return p;
        failure(size);
        if(auto handler=std::get_new_handler())handler();else throw std::bad_alloc();
    }
}
void* operator new[](std::size_t size) { return ::operator new(size); }
#endif
