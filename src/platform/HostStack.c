#include "HostStack.h"
#include <pthread.h>
#include <mach/mach.h>
#include <mach/arm/thread_status.h>
// Bounds are registered by the owning thread, avoiding reads through a pthread
// pointer that could be destroyed by another thread during sampling.
static struct { thread_t port; uintptr_t top; size_t size; } slots[128];
static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static uint64_t peak_used, min_margin=UINT64_MAX;
void bces_host_stack_register(void) {
    thread_t port=mach_thread_self();
    uintptr_t top=(uintptr_t)pthread_get_stackaddr_np(pthread_self());
    size_t size=pthread_get_stacksize_np(pthread_self());
    pthread_mutex_lock(&lock);
    for(unsigned i=0;i<128;++i) if(!slots[i].port) {
        slots[i].port=port;slots[i].top=top;slots[i].size=size;port=MACH_PORT_NULL;break;
    }
    pthread_mutex_unlock(&lock);
    if(port)mach_port_deallocate(mach_task_self(),port);
}
BCESHostStackStats bces_host_stack_sample(void) {
    BCESHostStackStats result={0};
    pthread_mutex_lock(&lock);
    for(unsigned i=0;i<128;++i) if(slots[i].port) {
        arm_thread_state64_t state={0}; mach_msg_type_number_t n=ARM_THREAD_STATE64_COUNT;
        kern_return_t rc=thread_get_state(slots[i].port,ARM_THREAD_STATE64,(thread_state_t)&state,&n);
        if(rc!=KERN_SUCCESS) {
            // Includes terminated threads. Release our send right, never leak it.
            mach_port_deallocate(mach_task_self(),slots[i].port);slots[i].port=0;continue;
        }
        ++result.registered;result.reserved_bytes+=slots[i].size;
        uintptr_t sp=arm_thread_state64_get_sp(state);
        if(sp<=slots[i].top && slots[i].top-sp<=slots[i].size) {
            uint64_t used=slots[i].top-sp,margin=slots[i].size-used;
            if(used>peak_used)peak_used=used;
            if(margin<min_margin)min_margin=margin;
            ++result.sampled;
        }
    }
    result.peak_sampled_used_bytes=peak_used;
    result.minimum_sampled_margin_bytes=min_margin==UINT64_MAX?0:min_margin;
    pthread_mutex_unlock(&lock);
    return result;
}
