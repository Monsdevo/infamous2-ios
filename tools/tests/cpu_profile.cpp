#include "CPUProfile.h"
#include <atomic>
#include <cassert>
#include <cstdio>
#include <thread>
#include <unistd.h>
static std::atomic<bool> done{false};
__attribute__((noinline)) static void known_cpu_work() {
    volatile unsigned long long value=1;
    while(!done.load(std::memory_order_relaxed))value=value*1664525+1013904223;
}
int main(int argc,char** argv) {
    assert(argc==2);bces_cpu_profile_configure(argv[1]);
    char file[1200];snprintf(file,sizeof file,"%s/cpu-profile-control.txt",argv[1]);
    FILE* f=fopen(file,"w");assert(f);fputs("start host_known_work 2\n",f);fclose(f);
    std::thread worker(known_cpu_work);bces_cpu_profile_poll();
    for(unsigned i=0;i<1000 && bces_cpu_profile_state()!=3 && bces_cpu_profile_state()!=-1;++i)usleep(10000);
    done=true;worker.join();assert(bces_cpu_profile_state()==3);
    bces_cpu_profile_poll();assert(bces_cpu_profile_state()==3); // token cannot retrigger
    puts("PASS: bounded running-thread profile completed; token not replayed");
}
