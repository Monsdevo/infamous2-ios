#include "HostStack.h"
#include <atomic>
#include <cassert>
#include <cstdio>
#include <pthread.h>
#include <unistd.h>
static std::atomic<bool> ready{false},done{false};
__attribute__((noinline)) static void* worker(void*) {
    bces_host_stack_register();
    volatile char buffer[256*1024];
    asm volatile("" : : "r"(buffer) : "memory");
    for(unsigned i=0;i<sizeof buffer;i+=4096)buffer[i]=1;
    ready=true;
    while(!done)usleep(1000);
    asm volatile("" : : "r"(buffer) : "memory");
    return nullptr;
}
int main() {
    bces_host_stack_register();
    pthread_attr_t attr;assert(!pthread_attr_init(&attr));
    assert(!pthread_attr_setstacksize(&attr,64*1024*1024));
    pthread_t thread;assert(!pthread_create(&thread,&attr,worker,nullptr));
    pthread_attr_destroy(&attr);
    while(!ready)usleep(1000);
    auto s=bces_host_stack_sample();
    assert(s.registered==2 && s.sampled==2);
    assert(s.reserved_bytes>=64*1024*1024);
    assert(s.peak_sampled_used_bytes>=256*1024);
    assert(s.minimum_sampled_margin_bytes>0);
    done=true;pthread_join(thread,nullptr);
    for(unsigned i=0;i<100;++i) {
        s=bces_host_stack_sample();
        if(s.registered==1)break;
        usleep(1000); // Kernel thread-port death can follow pthread_join.
    }
    assert(s.registered==1 && s.sampled==1);
    puts("PASS: stack bounds, actual SP depth, 64 MiB reservation and dead-thread right cleanup");
}
