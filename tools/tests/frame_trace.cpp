#include "FrameTrace.h"
#include "ps3emu/ps3_ftrace.h"
#include <atomic>
#include <cassert>
#include <thread>
#include <unistd.h>
int main(int argc,char** argv) {
    assert(argc==2);bces_frame_trace_configure(argv[1]);bces_frame_trace_register_ppu(1);
    ps3_ft_name(1,"host-main");
    char path[1200];snprintf(path,sizeof path,"%s/frame-trace-control.txt",argv[1]);
    FILE* f=fopen(path,"w");assert(f);fputs("start host_concurrent 1\n",f);fclose(f);
    std::atomic<bool> done{false};std::thread workers[4];
    for(unsigned i=0;i<4;++i)workers[i]=std::thread([&,i]{
        while(!done) {if(PS3_FT_ON()){uint64_t t=ps3_ft_now();ps3_ft_span(1,i,97,0,t,t+1000);}usleep(100);}
    });
    bces_frame_trace_poll();assert(bces_frame_trace_state()==1);
    for(unsigned i=0;i<500 && bces_frame_trace_state()!=3;++i){usleep(10000);bces_frame_trace_poll();}
    done=true;for(auto& worker:workers)worker.join();
    assert(bces_frame_trace_state()==3 && g_ps3_ft.writers==0 && g_ps3_ft.on==3);
    assert(g_ps3_ft.n>100 && !g_ps3_ft.dropped);
    bces_frame_trace_poll();assert(bces_frame_trace_state()==3);
    puts("PASS: concurrent trace writers, quiescent flush, bounded capture and token replay prevention");
}
