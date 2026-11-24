#include "CompactVertex.h"
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>

static _Atomic unsigned mode;
static _Atomic uint64_t draws, saved_bytes;

unsigned bces_compact_vertex_mode(void) { return atomic_load_explicit(&mode, memory_order_relaxed); }
void bces_compact_vertex_set(unsigned enabled) { atomic_store_explicit(&mode, !!enabled, memory_order_relaxed); }
uint64_t bces_compact_vertex_draws(void) { return atomic_load_explicit(&draws, memory_order_relaxed); }
uint64_t bces_compact_vertex_bytes_saved(void) { return atomic_load_explicit(&saved_bytes, memory_order_relaxed); }
void bces_compact_vertex_draw(uint32_t vertices, uint32_t saved_per_vertex) {
    atomic_fetch_add_explicit(&draws, 1, memory_order_relaxed);
    atomic_fetch_add_explicit(&saved_bytes, (uint64_t)vertices * saved_per_vertex, memory_order_relaxed);
}

// The caller admits a consecutive, single-base run from the range remapper.
// The resolved source and its 20-bit effective index must cover the run.
uint32_t bces_compact_vertex_mask(const rsx_vertex_fetch_plan* plan,
                                  const rsx_vertex_ref* refs, uint32_t count) {
    if (!count || plan->inline_data) return 0;
    const uint32_t first = (refs[0].vertex_id + refs[0].base_index) & 0xfffffu;
    const uint64_t last = (uint64_t)first + count - 1;
    if (last > 0xfffffu) return 0;
    uint32_t mask = 0;
    for (unsigned slot = 0; slot < plan->layout.count; ++slot) {
        const unsigned attr = plan->layout.attrs[slot];
        const rsx_vertex_fetch_attr* source = &plan->attr[attr];
        if (source->desc.type == RSX_VTX_TYPE_SNORM16 && source->desc.size == 3 &&
            source->desc.frequency <= 1 && source->elem_size == 6 && source->stable_base &&
            first >= source->stable_first && last <= source->stable_last)
            mask |= 1u << attr;
    }
    return mask;
}

uint32_t bces_compact_vertex_stride(const rsx_vertex_layout_plan* layout, uint32_t mask) {
    return layout->count * 16u - __builtin_popcount(mask) * 8u;
}

uint32_t bces_compact_vertex_offset(const rsx_vertex_layout_plan* layout, uint32_t mask, uint32_t slot) {
    const uint32_t attr_bit = 1u << layout->attrs[slot];
    const uint32_t packed_before = __builtin_popcount(mask & (attr_bit - 1u));
    if (!(mask & attr_bit)) return (slot - packed_before) * 16u;
    return (layout->count - __builtin_popcount(mask)) * 16u + packed_before * 8u;
}

int bces_compact_vertex_pack(const rsx_vertex_fetch_plan* plan, const rsx_vertex_ref* refs,
                             uint32_t count, uint32_t mask, uint8_t* out) {
    rsx_vertex_fetch_plan floats = *plan;
    const uint32_t stride = bces_compact_vertex_stride(&plan->layout, mask);
    const uint32_t first = (refs[0].vertex_id + refs[0].base_index) & 0xfffffu;
    floats.layout.count = 0;
    floats.layout.stride = stride;
    for (unsigned slot = 0; slot < plan->layout.count; ++slot) {
        const unsigned attr = plan->layout.attrs[slot];
        if (!(mask & (1u << attr))) {
            floats.layout.attrs[floats.layout.count++] = attr;
            continue;
        }
        const rsx_vertex_fetch_attr* source = &plan->attr[attr];
        const uint8_t* input = source->stable_base + (uint64_t)(first - source->stable_first) * source->stride;
        uint8_t* output = out + bces_compact_vertex_offset(&plan->layout, mask, slot);
        for (uint32_t i = 0; i < count; ++i) {
            const uint8_t* src = input + (uint64_t)i * source->stride;
            uint8_t* dst = output + (uint64_t)i * stride;
            uint32_t xy;
            uint16_t z;
            memcpy(&xy, src, 4);
            memcpy(&z, src + 4, 2);
            xy = ((xy & 0xff00ff00u) >> 8) | ((xy & 0x00ff00ffu) << 8);
            const uint32_t zw = __builtin_bswap16(z);
            memcpy(dst, &xy, 4);
            memcpy(dst + 4, &zw, 4);
        }
    }
    return rsx_vertex_fetch_all(&floats, refs, count, out);
}

int bces_compact_vertex_shader(char* shader, size_t capacity, uint32_t mask) {
    for (unsigned attr = 0; attr < 16; ++attr) {
        if (!(mask & (1u << attr))) continue;
        char from[48], to[160];
        snprintf(from, sizeof from, "v[%u]=input.a%u;", attr, attr);
        // Short4 widens exactly to float4 in vertex fetch. Two power-scaled
        // terms reproduce signed /32767, including -32768, without clamping.
        snprintf(to, sizeof to,
                 "v[%u]=float4(input.a%u.xyz*0.000030517578125+input.a%u.xyz*9.31350996324909e-10,1.0);",
                 attr, attr, attr);
        char* at = strstr(shader, from);
        const size_t before = strlen(from), after = strlen(to);
        if (!at || strlen(shader) + after - before >= capacity) return 0;
        memmove(at + after, at + before, strlen(at + before) + 1);
        memcpy(at, to, after);
    }
    return 1;
}
