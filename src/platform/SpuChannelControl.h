#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
extern unsigned bces_channel_mode,bces_channel_compiled;
void bces_channel_configure(void);
void bces_channel_set(unsigned mode);
unsigned bces_channel_get(void);
unsigned bces_channel_forced(void);
void bces_channel_record(unsigned channel,int checked,int mismatch);
void bces_channel_stats(uint64_t out[11]);
#ifdef __cplusplus
}
#endif
