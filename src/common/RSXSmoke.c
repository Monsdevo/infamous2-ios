#include "RSXSmoke.h"
#include "rsx_draw_engine.h"
#include "rsx_metal_backend.h"
#include "rsx_shader_msl.h"
#include "rsx_test_programs.h"
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

// Deliberately scoped to rsx_smoke_fixture, never linked into a game target.
uint8_t* vm_base;
uint32_t ppu_vm_size;
uint32_t ppu_hle_inject_base = 0x10000;
volatile uint32_t g_pad_host_keys[4], g_pad_mouse_buttons;
volatile int32_t g_pad_mouse_dx, g_pad_mouse_dy;
// No game brightness option has been loaded in a synthetic clear test.
float cellAvconfExt_display_gamma(void) { return 1.0f; }
enum { FIXTURE_SIZE = 32 * 1024 * 1024, LOCAL_BASE = 16 * 1024 * 1024 };
uint32_t cellGcmResolveLocated(int local, uint32_t offset) {
    return local ? LOCAL_BASE + offset : offset;
}
uint32_t cellGcmResolveOffset(uint32_t offset) { return offset; }
uint32_t cellGcmResolveIO(uint32_t offset) { return offset < LOCAL_BASE ? offset : 0; }
int cellGcmOffsetIsDisplay(uint32_t offset) { return offset == 0x40000; }
void vm_write32(uint32_t address, uint32_t value) {
    if (address > ppu_vm_size - 4) abort();
    for (unsigned i = 0; i < 4; ++i) vm_base[address + i] = (uint8_t)(value >> (24 - i * 8));
}
// Optional diagnostic event sink; this fixture does not execute guest fences.
void rsx_snap_event(int which, uint32_t offset) { (void)which; (void)offset; }

static int shader_prepared;
int rsx_smoke_shader_available(void) { return rsx_hlsl_to_msl_available(); }
static void put_float(uint32_t offset, float value) {
    uint32_t word;
    memcpy(&word, &value, sizeof word);
    vm_write32(offset, word);
}
static void prepare_shader(void) {
    uint8_t vp[32];
    rsx_test_vp_mov_out(vp, 0, RSX_TEST_VP_SWZ_IDENT, 0, 0);
    rsx_test_vp_mov_out(vp + 16, 3, RSX_TEST_VP_SWZ_IDENT, 1, 1);
    // Guest FP swaps R/B. A built-in colour passthrough cannot satisfy the
    // red->blue and blue->red pixel checks even if a triangle appears.
    rsx_test_fp_mov_r0_col0(vm_base + 0x1000, RSX_TEST_FP_SWZ(2, 1, 0, 3));
    rsx_draw_engine_method(0x1E9C, 0);
    for (unsigned k = 0; k < sizeof vp / 4; ++k) {
        const uint8_t* p = vp + k * 4;
        rsx_draw_engine_method(0x0B80 + k * 4,
            (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24));
    }
    rsx_draw_engine_method(0x1EA0, 0);
    rsx_draw_engine_method(0x08E4, 0x1000 | 2); // FP in main guest memory
    rsx_draw_engine_method(0x1D60, 0x40); // 32-bit colour exports
    const float position[3][4] = {{-0.9f,-0.8f,0,1}, {0.9f,-0.8f,0,1}, {0,0.9f,0,1}};
    for (unsigned i = 0; i < 3; ++i)
        for (unsigned k = 0; k < 4; ++k) put_float(0x2000 + i * 32 + k * 4, position[i][k]);
    rsx_draw_engine_method(0x1680, 0x80002000); // ATTR0 position, main memory
    rsx_draw_engine_method(0x1740, 2 | (4 << 4) | (32 << 8));
    rsx_draw_engine_method(0x1680 + 3 * 4, 0x80002010); // ATTR3 colour
    rsx_draw_engine_method(0x1740 + 3 * 4, 2 | (4 << 4) | (32 << 8));
    rsx_draw_engine_method(0x0324, 0x01010101); // RGBA writes
    rsx_draw_engine_method(0x0A00, 640u << 16);
    rsx_draw_engine_method(0x0A04, 360u << 16);
    shader_prepared = 1;
}

int rsx_smoke_init(void) {
    shader_prepared = 0;
    vm_base = calloc(1, FIXTURE_SIZE);
    if (!vm_base) return -1;
    ppu_vm_size = FIXTURE_SIZE;
    if (rsx_metal_backend_init(640, 360, "RSX iOS surface probe") != 0) {
        rsx_metal_backend_shutdown();
        free(vm_base); vm_base = NULL; ppu_vm_size = 0;
        return -1;
    }
    if (!rsx_draw_engine_enabled()) { rsx_smoke_shutdown(); return -1; }
    rsx_draw_engine_method(0x0194, 0xFEED0000); // local color DMA
    rsx_draw_engine_method(0x0200, 640u << 16);
    rsx_draw_engine_method(0x0204, 360u << 16);
    rsx_draw_engine_method(0x0208, 8); // A8R8G8B8
    rsx_draw_engine_method(0x020C, 640 * 4);
    rsx_draw_engine_method(0x0210, 0x40000);
    rsx_draw_engine_method(0x0220, 1); // color target 0
    rsx_draw_engine_set_display_buffer(0, RSX_LOCATION_LOCAL, 0x40000, 640 * 4, 640, 360);
    return 0;
}
uint32_t rsx_smoke_present(uint32_t argb, int readback) {
    rsx_draw_engine_method(0x1D90, argb);
    rsx_draw_engine_method(0x1D94, 0xF0); // clear RGBA via real dispatcher
    rsx_metal_backend_present();
    // Presentation is asynchronous. Only the three diagnostic pixel checks
    // wait for queued GPU writes before reading a shared render target.
    if (readback) rsx_draw_engine_flush();
    return readback ? rsx_draw_engine_readback_center() : 0;
}
RSXShaderSample rsx_smoke_present_shader(uint32_t vertex_argb, int readback) {
    if (!shader_prepared) prepare_shader();
    const float rgba[4] = {((vertex_argb >> 16) & 255) / 255.0f,
        ((vertex_argb >> 8) & 255) / 255.0f, (vertex_argb & 255) / 255.0f,
        ((vertex_argb >> 24) & 255) / 255.0f};
    for (unsigned i = 0; i < 3; ++i)
        for (unsigned k = 0; k < 4; ++k) put_float(0x2010 + i * 32 + k * 4, rgba[k]);
    rsx_draw_engine_method(0x1D90, 0xFF000000);
    rsx_draw_engine_method(0x1D94, 0xF0);
    rsx_draw_engine_method(0x1808, 5); // TRIANGLES
    rsx_draw_engine_method(0x1814, 2u << 24); // first=0, count=3
    rsx_draw_engine_method(0x1808, 0);
    rsx_metal_backend_present();
    RSXShaderSample sample = {0, rsx_draw_engine_guest_draws()};
    if (readback) {
        rsx_draw_engine_flush();
        sample.pixel = rsx_draw_engine_readback_center();
    }
    return sample;
}
void rsx_smoke_shutdown(void) {
    rsx_metal_backend_shutdown();
    free(vm_base); vm_base = NULL; ppu_vm_size = 0;
}
