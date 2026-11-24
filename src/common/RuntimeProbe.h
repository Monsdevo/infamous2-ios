#pragma once
#ifdef __cplusplus
extern "C" {
#endif
typedef void (*RuntimeProbeLog)(const char* line, void* context);
// A diagnostic fixture around real runtime sources; never link into the game.
int runtime_probe_run(RuntimeProbeLog log, void* context);
int runtime_probe_ucontext(int* get_rc, int* get_error, int* swap_rc, int* swap_error);
#ifdef __cplusplus
}
#endif
