#pragma once
#ifdef __cplusplus
extern "C" {
#endif
void bces_shader_diagnostics_configure(const char* directory);
void bces_shader_trace_begin(const char* hlsl, int stage);
void bces_shader_trace_end(int result);
#ifdef __cplusplus
}
#endif
