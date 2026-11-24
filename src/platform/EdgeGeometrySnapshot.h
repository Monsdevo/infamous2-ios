#pragma once
#include "spu_context.h"
/* Private, local diagnostic file. Contains game-derived data; never publish. */
typedef struct EdgeSnapshot {
    uint32_t magic,context_size,ls_size,block;
    uint64_t fpcr;
    spu_context input,reference,actual;
    uint8_t input_ls[SPU_LS_SIZE],reference_ls[SPU_LS_SIZE],actual_ls[SPU_LS_SIZE];
} EdgeSnapshot;
