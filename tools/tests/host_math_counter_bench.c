#include "HostSpuMath.h"
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <assert.h>
#include <time.h>
#include <sched.h>
static uint64_t shared;
static unsigned ready,go;
typedef struct {unsigned slot,mode;} Args;
static __attribute__((noinline)) void common_note(void){__atomic_fetch_add(&shared,1,__ATOMIC_RELAXED);}
static void* worker(void* opaque){Args*a=opaque;__atomic_fetch_sub(&ready,1,__ATOMIC_RELEASE);while(!__atomic_load_n(&go,__ATOMIC_ACQUIRE))sched_yield();for(unsigned i=0;i<1000000;i++){if(a->mode)bces_host_math_note(1|(a->slot<<8));else common_note();}return 0;}
static double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
int main(void){for(unsigned n=1;n<=8;n+=(n==1?4:3))for(unsigned mode=0;mode<2;mode++){
 pthread_t threads[8];Args args[8];ready=n;go=0;__atomic_store_n(&shared,0,__ATOMIC_RELAXED);uint64_t before=bces_host_math_stats().fast;
 for(unsigned i=0;i<n;i++){args[i]=(Args){i,mode};assert(!pthread_create(&threads[i],0,worker,&args[i]));}
 while(__atomic_load_n(&ready,__ATOMIC_ACQUIRE))sched_yield();double start=now();__atomic_store_n(&go,1,__ATOMIC_RELEASE);for(unsigned i=0;i<n;i++)assert(!pthread_join(threads[i],0));double elapsed=now()-start;
 uint64_t count=mode?bces_host_math_stats().fast-before:shared;assert(count==1000000ull*n);
 printf("{\"threads\":%u,\"slotted\":%u,\"calls\":%llu,\"wall_ms\":%.6f,\"scope\":\"counter throughput only; not game FPS\"}\n",n,mode,(unsigned long long)count,elapsed*1000);
}return 0;}
