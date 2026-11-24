#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
uint64_t bces_texture_hash_memo(const uint8_t* source,uint32_t bytes,
    uint64_t (*reference)(const uint8_t*,uint32_t));
#ifdef __cplusplus
}
#endif
