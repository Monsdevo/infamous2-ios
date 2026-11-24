#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
// Monotonic seconds. Callback-safe; no GPU waits or file IO here.
void game_telemetry_present(double seconds);
// phase 0 starts a render pipeline, 1 succeeds, 2 fails. Optional bounded log.
void game_telemetry_pipeline(int phase, double seconds);
void game_telemetry_pipeline_log(const char* path);
void game_telemetry_gpu(double seconds, double milliseconds);
void game_telemetry_render(double seconds, double milliseconds);
typedef struct {
    double fps, frame_mean_ms, frame_p95_ms, gpu_mean_ms, render_mean_ms;
    unsigned frame_intervals, gpu_samples, render_samples;
    uint64_t pipeline_started, pipeline_finished, pipeline_failed;
    uint64_t present_total;
    double present_time, sample_time;
} GameTelemetrySnapshot;
GameTelemetrySnapshot game_telemetry_snapshot(double seconds);
typedef struct {uint64_t sequence;double seconds;} GameFrameEvent;
// Coherent bounded event export. No allocation or IO in present callbacks.
unsigned game_telemetry_frame_events(uint64_t after,GameFrameEvent*out,unsigned capacity,uint64_t*dropped);
#ifdef __cplusplus
}
#endif
