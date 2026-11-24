#include "GameTelemetry.h"
#include <cassert>
#include <cmath>
#include <thread>
#include <vector>
#include <cstdio>
#include <atomic>
int main() {
    auto empty=game_telemetry_snapshot(10);assert(empty.fps==0 && empty.gpu_samples==0);
    for(unsigned i=1;i<=120;++i)game_telemetry_present(10+i/60.0);
    auto s=game_telemetry_snapshot(12);
    assert(s.fps==60 && s.frame_intervals==119);
    assert(std::abs(s.frame_mean_ms-1000.0/60)<.001);
    assert(std::abs(s.frame_p95_ms-1000.0/60)<.001);
    game_telemetry_present(11);game_telemetry_present(NAN);
    assert(game_telemetry_snapshot(12).fps==60);
    game_telemetry_gpu(12,3);game_telemetry_gpu(12,5);game_telemetry_gpu(12,NAN);
    game_telemetry_render(12,10);
    s=game_telemetry_snapshot(12);assert(s.gpu_samples==2 && s.gpu_mean_ms==4 && s.render_mean_ms==10);
    s=game_telemetry_snapshot(15);assert(s.fps==0 && !s.frame_intervals && !s.gpu_samples);
    std::vector<std::thread> writers;
    for(int i=0;i<4;++i)writers.emplace_back([]{for(int j=0;j<1000;++j)game_telemetry_gpu(20,7);});
    for(auto& t:writers)t.join();s=game_telemetry_snapshot(20);
    assert(s.gpu_samples==512 && s.gpu_mean_ms==7);
    game_telemetry_pipeline(0,21);game_telemetry_pipeline(1,21.1);
    game_telemetry_pipeline(0,22);game_telemetry_pipeline(2,22.1);
    game_telemetry_pipeline(0,23);
    s=game_telemetry_snapshot(23);assert(s.pipeline_started==3 && s.pipeline_finished==1 && s.pipeline_failed==1);
    assert(s.present_total==120&&s.present_time==12);
    GameFrameEvent first[121];uint64_t dropped=99;unsigned count=game_telemetry_frame_events(0,first,121,&dropped);assert(count==120&&!dropped);
    for(unsigned i=0;i<count;i++){assert(first[i].sequence==i+1);if(i)assert(first[i].seconds>first[i-1].seconds);}
    std::atomic<bool> finished{false};std::thread present_writer([&]{for(unsigned i=1;i<=10000;i++)game_telemetry_present(30+i/120.0);finished=true;});
    do{auto coherent=game_telemetry_snapshot(1000);if(coherent.present_total>120)assert(std::abs(coherent.present_time-(30+(coherent.present_total-120)/120.0))<1e-10);}while(!finished);
    present_writer.join();std::vector<GameFrameEvent> events(8192);count=game_telemetry_frame_events(0,events.data(),8192,&dropped);assert(count==8192&&dropped==10120-8192);
    for(unsigned i=1;i<count;i++){assert(events[i].sequence==events[i-1].sequence+1);assert(events[i].seconds>events[i-1].seconds);}
    assert(game_telemetry_frame_events(10120,events.data(),8192,&dropped)==0&&!dropped);
    std::puts("PASS coherent presentation counter/timestamp under concurrency, raw event continuity and bounded wrap detection");
    std::puts("PASS: pipeline begin/success/failure/in-flight counters; actual presentation window, frame mean/p95, stale/invalid samples, bounded concurrent GPU ring");
}
