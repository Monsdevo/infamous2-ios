#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
void bces_host_normals_set(unsigned enabled);
unsigned bces_host_normals_enabled(void);
void bces_host_normals_begin(void);
int bces_host_normals_skip(int eligible);
void bces_host_normals_require(void);
uint64_t bces_host_normals_skipped(void);
#ifdef __cplusplus
}
#endif
