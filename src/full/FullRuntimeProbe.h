#pragma once
#ifdef __cplusplus
extern "C" {
#endif
typedef void (*FullRuntimeLog)(const char*, void*);
// Worker calls before a GPU batch. UIKit may wait for foreground activation;
// return zero to abort the finite diagnostic. No renderer calls on main.
typedef int (*FullRuntimeFrameGate)(void*);
typedef struct FullRuntimeControl FullRuntimeControl;
typedef struct {
    unsigned long long submitted_jobs, completed_jobs, cancelled_jobs;
    int active, stop_requested, renderer_running, renderer_busy, renderer_idle;
    int ppu_registered, ppu_parked, ppu_finished;
} FullRuntimeSnapshot;
FullRuntimeControl* full_runtime_control_create(void);
// Destroy only after full_runtime_probe_threaded AND the outer PPU pthread join.
void full_runtime_control_destroy(FullRuntimeControl*);
void full_runtime_set_active(FullRuntimeControl*, int active);
void full_runtime_request_stop(FullRuntimeControl*);
int full_runtime_wait_quiescent(FullRuntimeControl*, unsigned timeout_ms);
FullRuntimeSnapshot full_runtime_snapshot(FullRuntimeControl*);
// Same synthetic title, separate renderer owner. 0=PASS, 1=FAIL, 2=STOPPED.
int full_runtime_probe_threaded(const char* elf, const char* vfs, FullRuntimeLog, void*,
                               FullRuntimeControl*, unsigned frames, unsigned interval_ms);
// Owns a one-shot synthetic title. Never call alongside RSXSmoke/RuntimeProbe.
int full_runtime_probe(const char* elf, const char* vfs, FullRuntimeLog log, void* context,
                       FullRuntimeFrameGate gate);
#ifdef __cplusplus
}
#endif
