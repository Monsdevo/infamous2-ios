#pragma once
#include "spu_context.h"
void skin_dispatch(spu_context* context);
void skin_visit(spu_context* context,uint32_t pc);
void skin_assert(spu_context* context);
u128 skin_read(const spu_context* context,uint32_t address);
void skin_write(spu_context* context,uint32_t address,u128 value);
