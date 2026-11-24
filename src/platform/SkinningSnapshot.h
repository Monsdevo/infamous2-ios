#pragma once
#include "spu_context.h"
/* Private game-derived diagnostic data; never distribute fixtures. */
typedef struct SkinningSnapshot {
    uint32_t magic,version,context_size,index;
    spu_context input,output;
    uint8_t input_ls[SPU_LS_SIZE],output_ls[SPU_LS_SIZE];
} SkinningSnapshot;
