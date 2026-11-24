#pragma once
#include <stddef.h>
#include <stdint.h>
#include "rsx_vertex_compact.h"

#ifdef __cplusplus
extern "C" {
#endif
unsigned bces_compact_vertex_mode(void);
void bces_compact_vertex_set(unsigned enabled);
void bces_compact_vertex_draw(uint32_t vertices, uint32_t saved_per_vertex);
uint64_t bces_compact_vertex_draws(void);
uint64_t bces_compact_vertex_bytes_saved(void);

uint32_t bces_compact_vertex_mask(const rsx_vertex_fetch_plan* plan,
                                  const rsx_vertex_ref* refs, uint32_t count);
uint32_t bces_compact_vertex_stride(const rsx_vertex_layout_plan* layout, uint32_t mask);
uint32_t bces_compact_vertex_offset(const rsx_vertex_layout_plan* layout, uint32_t mask, uint32_t slot);
int bces_compact_vertex_pack(const rsx_vertex_fetch_plan* plan, const rsx_vertex_ref* refs,
                             uint32_t count, uint32_t mask, uint8_t* out);
int bces_compact_vertex_shader(char* shader, size_t capacity, uint32_t mask);
#ifdef __cplusplus
}
#endif
