#include "GameTelemetry.h"
#include <array>
#include <algorithm>
#include <cmath>
#include <mutex>
#include <cstdio>
namespace {
struct Sample { double time = 0, value = 0; };
struct Ring {
    std::array<Sample, 512> values{};
    unsigned cursor = 0, count = 0;
    void add(double t, double v) { values[cursor] = {t,v}; cursor = (cursor+1)%values.size(); count = std::min(count+1, unsigned(values.size())); }
};
std::mutex mutex;
Ring frames, gpu, render;
double last_present = 0;
uint64_t present_total=0;
std::array<GameFrameEvent,8192> frame_events{};
uint64_t pipeline_started=0, pipeline_finished=0, pipeline_failed=0;
FILE* pipeline_log=nullptr;
unsigned pipeline_log_rows=0;
void add(Ring& ring, double t, double value) {
    if (std::isfinite(t) && std::isfinite(value) && t > 0 && value >= 0) ring.add(t,value);
}
unsigned recent(const Ring& ring, double now, double* out) {
    unsigned n = 0;
    for (unsigned i=0; i<ring.count; ++i) {
        const auto& s=ring.values[i];
        if (s.time > now-2 && s.time <= now) out[n++] = s.value;
    }
    return n;
}
double mean(double* values, unsigned n) { double sum=0; for(unsigned i=0;i<n;++i)sum+=values[i]; return n?sum/n:0; }
}
void game_telemetry_present(double t) {
    std::lock_guard<std::mutex> lock(mutex);
    if (!std::isfinite(t) || t <= last_present) return;
    add(frames,t,last_present ? (t-last_present)*1000 : 0);
    last_present=t;++present_total;frame_events[(present_total-1)%frame_events.size()]={present_total,t};
}
void game_telemetry_gpu(double t,double ms) { std::lock_guard<std::mutex> lock(mutex); add(gpu,t,ms); }
void game_telemetry_render(double t,double ms) { std::lock_guard<std::mutex> lock(mutex); add(render,t,ms); }
void game_telemetry_pipeline_log(const char* path) {
    std::lock_guard<std::mutex> lock(mutex);
    if(pipeline_log)std::fclose(pipeline_log);
    pipeline_log=path?std::fopen(path,"w"):nullptr; pipeline_log_rows=0;
    if(pipeline_log) { std::fputs("monotonic_s,phase,started,finished,failed\n",pipeline_log);std::fflush(pipeline_log); }
}
void game_telemetry_pipeline(int phase,double seconds) {
    std::lock_guard<std::mutex> lock(mutex);
    if(phase==0)++pipeline_started;
    else if(phase==1)++pipeline_finished;
    else if(phase==2)++pipeline_failed;
    else return;
    if(pipeline_log && pipeline_log_rows<20000) {
        std::fprintf(pipeline_log,"%.6f,%d,%llu,%llu,%llu\n",seconds,phase,(unsigned long long)pipeline_started,(unsigned long long)pipeline_finished,(unsigned long long)pipeline_failed);
        std::fflush(pipeline_log);++pipeline_log_rows;
    }
}
GameTelemetrySnapshot game_telemetry_snapshot(double now) {
    std::lock_guard<std::mutex> lock(mutex);
    GameTelemetrySnapshot s{}; double v[512];
    s.present_total=present_total;s.present_time=last_present;s.sample_time=now;
    s.pipeline_started=pipeline_started;s.pipeline_finished=pipeline_finished;s.pipeline_failed=pipeline_failed;
    unsigned n=recent(frames,now,v); s.fps=n/2.0;
    unsigned valid=0; for(unsigned i=0;i<n;++i)if(v[i]>0)v[valid++]=v[i];
    s.frame_intervals=valid; s.frame_mean_ms=mean(v,valid);
    if(valid) { std::sort(v,v+valid); s.frame_p95_ms=v[unsigned(std::ceil(valid*.95))-1]; }
    s.gpu_samples=recent(gpu,now,v); s.gpu_mean_ms=mean(v,s.gpu_samples);
    s.render_samples=recent(render,now,v); s.render_mean_ms=mean(v,s.render_samples);
    return s;
}

unsigned game_telemetry_frame_events(uint64_t after,GameFrameEvent*out,unsigned capacity,uint64_t*dropped){
    std::lock_guard<std::mutex> lock(mutex);*dropped=0;if(after>=present_total||!capacity)return 0;
    uint64_t oldest=present_total>=frame_events.size()?present_total-frame_events.size()+1:1;
    uint64_t first=after+1;if(first<oldest){*dropped=oldest-first;first=oldest;}
    unsigned n=(unsigned)std::min<uint64_t>(capacity,present_total-first+1);
    for(unsigned i=0;i<n;i++)out[i]=frame_events[(first+i-1)%frame_events.size()];return n;
}
