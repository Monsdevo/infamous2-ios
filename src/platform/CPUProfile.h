#pragma once
#ifdef __cplusplus
extern "C" {
#endif
void bces_cpu_profile_configure(const char* directory);
// Development-only control file: start UNIQUE_TOKEN [seconds: 1..60].
// Poll on the existing 1 Hz UI tick, never from a guest hot path.
void bces_cpu_profile_poll(void);
int bces_cpu_profile_state(void); // 0 idle, 1 sampling, 2 writing, 3 done, -1 error
#ifdef __cplusplus
}
#endif
