#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
void bces_host_stack_register(void);
typedef struct {
    uint64_t reserved_bytes, peak_sampled_used_bytes, minimum_sampled_margin_bytes;
    unsigned registered, sampled;
} BCESHostStackStats;
BCESHostStackStats bces_host_stack_sample(void);
#ifdef __cplusplus
}
#endif
