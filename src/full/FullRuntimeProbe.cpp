#define SDL_MAIN_HANDLED
#include "FullRuntimeProbe.h"
#include "RuntimeCoordinator.hpp"
#include <pthread.h>
#include "ppu_recomp.h"
#define PPU_CONTEXT_H // generated header already supplied the identical type
#include "sys_ppu_thread.h"
#include "win32_compat.h"
#include "ps3emu/guest_call.h"
#include "cellGcmSys.h"
#include "rsx_metal_backend.h"
#include "rsx_draw_engine.h"
#include "rsx_test_programs.h"
#include "RSXMetalSurface.h"
#include <TargetConditionals.h>
#include <SDL.h>
#include <atomic>
#include <cstdarg>
#include <cstring>
#include <string>
#include <mach/mach.h>

extern "C" {
uint8_t* vm_base = nullptr;
extern uint32_t ppu_vm_size;
extern const char* ppu_vfs_root;
void ppu_recomp_register(void);
uint32_t ppu_load_elf(const char*);
void ppu_hle_init(void);
void ppu_sysprx_register(void);
void ppu_fs_register(void);
void lv2_init_syscalls(void);
uint32_t ps3_hle_count(void);
void ps3_hle_call(uint32_t, ppu_context*);
void lv2_syscall(ppu_context*);
int ppu_run(uint32_t, uint32_t);
extern PPU_THREAD_LOCAL ppu_context* g_active_ctx;
uint64_t ppu_guest_call(uint32_t, uint64_t, uint64_t, uint64_t, uint64_t,
                        uint64_t, uint64_t, uint64_t, uint64_t);
void cellGcm_rsx_process_fifo(void);
int cellGcm_take_flip_pending(void);
uint32_t cellGcm_flip_request_count(void);
void ppu_gcm_pump(void);
}
static FullRuntimeLog logger;
static void* logger_context;
static FullRuntimeFrameGate frame_gate;
static FullRuntimeControl* lifecycle;
static unsigned requested_frames = 6, frame_interval_ms;
static unsigned failures, entry_calls;
static std::atomic<unsigned> worker_calls;
static std::atomic<DWORD> worker_host_tid;
static DWORD main_host_tid;
static std::atomic<bool> started;
static std::string vfs_root;
int lifted_ppu_probe(const char*, FullRuntimeLog, void*);
static const char vfs_canary[] = "runtime-vfs-verified\n";
static unsigned flip_callbacks, vblank_callbacks, callback_errors;
static unsigned synthetic_frames;
static void emit(const char* format, ...) {
    char line[768]; va_list args; va_start(args, format);
    vsnprintf(line, sizeof line, format, args); va_end(args);
    fprintf(stderr, "[full runtime] %s\n", line);
    if (logger) logger(line, logger_context);
}
static void check(bool ok, const char* name) {
    if (!ok) failures++;
    emit("check=%s result=%s", name, ok ? "PASS" : "FAIL");
}
static void memory(const char* phase) {
    task_vm_info_data_t info{};
    mach_msg_type_number_t n = TASK_VM_INFO_COUNT;
    if (task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&info, &n) == KERN_SUCCESS)
        emit("memory=%s virtual_bytes=%llu physical_footprint=%llu", phase,
             (unsigned long long)info.virtual_size, (unsigned long long)info.phys_footprint);
}
static void worker(ppu_context* ctx) {
    worker_host_tid.store(GetCurrentThreadId());
    if (ctx->gpr[3] == UINT64_C(0x1122334455667788)) worker_calls++;
    ctx->gpr[11] = SYS_PPU_THREAD_EXIT; ctx->gpr[3] = 0x1234; lv2_syscall(ctx);
}
static void flip_callback(ppu_context* ctx) {
    flip_callbacks++;
    if (ctx->gpr[3] != 1 || GetCurrentThreadId() != main_host_tid) callback_errors++;
}
static void vblank_callback(ppu_context* ctx) {
    vblank_callbacks++;
    if (ctx->gpr[3] != vblank_callbacks || GetCurrentThreadId() != main_host_tid) callback_errors++;
}
static void guest_caller(uint32_t opd, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3,
                          uint64_t a4, uint64_t a5, uint64_t a6, uint64_t a7) {
    ppu_guest_call(opd, a0, a1, a2, a3, a4, a5, a6, a7);
}
// The synthetic PPU writes BE guest words. Only the pinned GCM walker calls
// the RSX dispatcher; there are no host-memory/GCM substitutes in this target.
static constexpr uint32_t io_base = 0x00100000, fp_offset = 0x00100000,
                          vertex_offset = 0x00101000;
static void packet(uint32_t& cursor, uint32_t method, uint32_t value) {
    vm_write32(cursor, (1u << 18) | method);
    vm_write32(cursor + 4, value); cursor += 8;
}
static void guest_float(uint32_t address, float value) {
    uint32_t word; memcpy(&word, &value, sizeof word); vm_write32(address, word);
}
static void shader_packets(uint32_t& cursor, uint32_t argb) {
    uint8_t vp[32];
    rsx_test_vp_mov_out(vp, 0, RSX_TEST_VP_SWZ_IDENT, 0, 0);
    rsx_test_vp_mov_out(vp + 16, 3, RSX_TEST_VP_SWZ_IDENT, 1, 1);
    rsx_test_fp_mov_r0_col0(vm_base + io_base + fp_offset, RSX_TEST_FP_SWZ(2, 1, 0, 3));
    packet(cursor, 0x1E9C, 0);
    for (unsigned k = 0; k < sizeof vp / 4; ++k) {
        const uint8_t* p = vp + k * 4;
        packet(cursor, 0x0B80 + k * 4,
            (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24));
    }
    packet(cursor, 0x1EA0, 0);
    packet(cursor, 0x08E4, fp_offset | 2); // actual GCM IO translation -> guest EA
    packet(cursor, 0x1D60, 0x40);
    const float position[3][4] = {{-.9f,-.8f,0,1}, {.9f,-.8f,0,1}, {0,.9f,0,1}};
    const float rgba[4] = {((argb >> 16) & 255) / 255.f, ((argb >> 8) & 255) / 255.f,
                           (argb & 255) / 255.f, ((argb >> 24) & 255) / 255.f};
    for (unsigned i = 0; i < 3; ++i)
        for (unsigned k = 0; k < 4; ++k) {
            guest_float(io_base + vertex_offset + i * 32 + k * 4, position[i][k]);
            guest_float(io_base + vertex_offset + i * 32 + 16 + k * 4, rgba[k]);
        }
    packet(cursor, 0x1680, 0x80000000u | vertex_offset);
    packet(cursor, 0x1740, 2 | (4 << 4) | (32 << 8));
    packet(cursor, 0x168C, 0x80000000u | (vertex_offset + 16));
    packet(cursor, 0x174C, 2 | (4 << 4) | (32 << 8));
    packet(cursor, 0x0324, 0x01010101);
    packet(cursor, 0x0A00, 640u << 16); packet(cursor, 0x0A04, 360u << 16);
    packet(cursor, 0x1808, 5); packet(cursor, 0x1814, 2u << 24); packet(cursor, 0x1808, 0);
}
static bool stopped() { return lifecycle && full_runtime_snapshot(lifecycle).stop_requested; }
static bool render_call(std::function<void()> fn) {
    if (lifecycle) return runtime_render_call(lifecycle, std::move(fn));
    fn(); return true;
}
struct RenderLifetime {
    std::function<void()> finish;
    ~RenderLifetime() { finish(); }
};
static void graphics(ppu_context* ctx) {
    if (frame_gate && !frame_gate(logger_context)) { check(false, "foreground_GPU_admission"); return; }
    bool metal_ready = false;
#if TARGET_OS_IPHONE
    RSXSurfaceStats before{};
#endif
    auto shutdown = [&] {
        if (!metal_ready) return;
        rsx_draw_engine_flush();
#if TARGET_OS_IPHONE
        for (unsigned n = 0; n < 300; ++n) {
            RSXSurfaceStats s = rsx_metal_backend_ios_stats();
            if (s.completed - before.completed >= synthetic_frames &&
                (TARGET_OS_SIMULATOR || s.presented - before.presented >= synthetic_frames)) break;
            Sleep(10);
        }
        RSXSurfaceStats s = rsx_metal_backend_ios_stats();
        emit("GCM_surface submitted=%llu completed=%llu presented=%llu errors=%llu simulator=%d",
             (unsigned long long)(s.submitted - before.submitted),
             (unsigned long long)(s.completed - before.completed),
             (unsigned long long)(s.presented - before.presented),
             (unsigned long long)(s.errors - before.errors), TARGET_OS_SIMULATOR);
        check(s.submitted - before.submitted == synthetic_frames &&
              s.completed - before.completed == synthetic_frames && s.errors == before.errors &&
              (TARGET_OS_SIMULATOR || s.presented - before.presented == synthetic_frames),
              "real_Metal_surface_completion_presentation");
#endif
        rsx_metal_backend_shutdown(); metal_ready = false;
        check(!rsx_draw_engine_enabled(), "renderer_shutdown_unregisters_engine");
        emit("GCM_shutdown renderer_stopped=1 synthetic_frames=%u game_frames=0 VM_retained=1", synthetic_frames);
    };
    if (lifecycle) {
        bool launched = runtime_renderer_start(lifecycle, [&] {
            if (metal_ready) rsx_draw_engine_flush();
        }, shutdown);
        if (!launched) { if (!stopped()) check(false, "renderer_thread_create"); return; }
    }
    RenderLifetime lifetime{[&] {
        if (lifecycle) runtime_renderer_finish(lifecycle); else shutdown();
        g_ps3_guest_caller = nullptr;
    }};
    if (!render_call([&] {
        if (lifecycle) {
            emit("renderer_host_tid=%u PPU_host_tid=%u requested_stack=16777216 actual_stack=%zu",
                 GetCurrentThreadId(), main_host_tid, pthread_get_stacksize_np(pthread_self()));
            check(GetCurrentThreadId() != main_host_tid, "separate_PPU_renderer_host_threads");
        }
        int rc = rsx_metal_backend_init(640, 360, "Full runtime GCM diagnostic");
        metal_ready = rc == 0 && rsx_draw_engine_enabled();
        check(metal_ready, "full_runtime_Metal_init");
        if (!metal_ready) rsx_metal_backend_shutdown();
#if TARGET_OS_IPHONE
        before = rsx_metal_backend_ios_stats();
#endif
    }) || !metal_ready) return;
    ctx->gpr[3] = 0x22400; ctx->gpr[4] = lifecycle ? 0x80000 : 0x10000;
    ctx->gpr[5] = 0x200000; ctx->gpr[6] = io_base;
    ps3_hle_call(0x15BAE46B, ctx); // _cellGcmInitBody
    uint32_t gcm = vm_read32(0x22400);
    bool initialized = (int32_t)ctx->gpr[3] == 0 && gcm && vm_read32(gcm) == io_base;
    check(initialized, "real_GCM_NID_context_IO_mapping");
    if (!initialized) return;
    ctx->gpr[3] = 0; ctx->gpr[4] = 0x40000; ctx->gpr[5] = 640 * 4;
    ctx->gpr[6] = 640; ctx->gpr[7] = 360; ps3_hle_call(0xA53D12AE, ctx);
    check((int32_t)ctx->gpr[3] == 0, "real_GCM_display_buffer");
    ps3_hle_call(0xA547ADDE, ctx); // cellGcmGetControlRegister, guest pointer
    uint32_t control = (uint32_t)ctx->gpr[3];
    bool control_ok = control && control < ppu_vm_size - 12 &&
                      vm_read32(control) == 0 && vm_read32(control + 4) == 0;
    check(control_ok, "real_GCM_guest_control_registers");
    if (!control_ok) return;
    ctx->gpr[3] = 5; ps3_hle_call(0xF80196C1, ctx); // label address is also a guest EA
    uint32_t label = (uint32_t)ctx->gpr[3];
    bool label_ok = label && label < ppu_vm_size - 4;
    check(label_ok, "real_GCM_guest_label_address");
    if (!label_ok) return;
    vm_write32(label, 0);
    vm_write32(0x22300, 0x10200); vm_write32(0x22304, 0);
    vm_write32(0x22310, 0x10300); vm_write32(0x22314, 0);
    ctx->gpr[3] = 0x22300; ps3_hle_call(0xA41EF7E8, ctx);
    ctx->gpr[3] = 0x22310; ps3_hle_call(0xA91B0402, ctx);
    g_ps3_guest_caller = guest_caller;
    uint32_t cursor = io_base;
    // Configure the RSX surface through FIFO packets, not host dispatcher calls.
    packet(cursor, 0x0194, 0xFEED0000);
    packet(cursor, 0x0200, 640u << 16); packet(cursor, 0x0204, 360u << 16);
    packet(cursor, 0x0208, 8); packet(cursor, 0x020C, 640 * 4);
    packet(cursor, 0x0210, 0x40000); packet(cursor, 0x0220, 1);
    const uint32_t colors[] = {0xFFFF0000, 0xFF00FF00, 0xFF0000FF};
    const uint32_t swapped[] = {0xFF0000FF, 0xFF00FF00, 0xFFFF0000};
    const uint32_t initial_flips = cellGcm_flip_request_count();
    for (unsigned f = 0; f < requested_frames; ++f) {
        if (lifecycle && !runtime_ppu_checkpoint(lifecycle, frame_interval_ms)) break;
        if (frame_gate && !frame_gate(logger_context)) { check(false, "foreground_GPU_admission"); break; }
        const bool shader = f >= 3;
        const unsigned color_index = shader ? (f - 3) % 3 : f;
        const uint32_t clear = shader ? 0xFF000000 : colors[color_index];
        packet(cursor, 0x1D90, clear); packet(cursor, 0x1D94, 0xF0);
        if (shader) shader_packets(cursor, colors[color_index]);
        vm_write32(gcm + 8, cursor);
        ctx->gpr[3] = gcm; ctx->gpr[4] = 0; ps3_hle_call(0x21397818, ctx);
        const uint32_t flip_end = vm_read32(gcm + 8);
        check((int32_t)ctx->gpr[3] == 0 && flip_end == cursor + 4 &&
              vm_read32(cursor) == 0xFEAD0100 && !cellGcm_take_flip_pending() &&
              cellGcm_flip_request_count() == initial_flips + f && flip_callbacks == f,
              "flip_queued_not_presented_early");
        cursor = flip_end;
        // A post-flip sentinel proves that the walker stops at the frame
        // boundary even when put contains more work. It must not mix frames.
        packet(cursor, 0x0064, 5 * 16); // semaphore offset, label 5
        packet(cursor, 0x006C, f + 1);  // release: visible in guest RAM only when consumed
        vm_write32(gcm + 8, cursor); vm_write32(control, cursor - io_base);
        if (!render_call([&] {
            cellGcm_rsx_process_fifo();
            check(vm_read32(control + 4) == flip_end - io_base &&
                  vm_read32(control + 4) != vm_read32(control) &&
                  vm_read32(label) == f &&
                  rsx_metal_backend_debug_color() == clear &&
                  cellGcm_flip_request_count() == initial_flips + f + 1,
                  "FIFO_stops_at_flip_before_next_commands");
            const bool pending = cellGcm_take_flip_pending() != 0;
            check(pending && !cellGcm_take_flip_pending(), "flip_consumed_exactly_once");
            if (pending) { rsx_metal_backend_present(); synthetic_frames++; }
            // Diagnostic mode forces GPU completion + readback for every test frame.
            // No FPS is inferred from this deliberately serialized workload.
            rsx_draw_engine_flush();
            uint32_t pixel = rsx_draw_engine_readback_center();
            uint32_t draws = rsx_draw_engine_guest_draws();
            const uint32_t expected = shader ? swapped[color_index] : colors[color_index];
            emit("GCM_frame=%u kind=%s expected=%08X pixel=%08X translated_draws=%u get=%08X put=%08X",
                 f, shader ? "shader" : "clear", expected, pixel, draws,
                 vm_read32(control + 4), vm_read32(control));
            check(pixel == expected && draws == (shader ? 1u : 0u), "FIFO_Metal_GPU_pixel_and_guest_shader");
            cellGcmTickVBlank(); cellGcmTickFlip();
        })) break;
        // Callback dispatch remains on the PPU, never on the render owner.
        ppu_gcm_pump();
        ps3_hle_call(0x72A577CE, ctx);
        check(ctx->gpr[3] == CELL_GCM_FLIP_STATUS_DONE && flip_callbacks == f + 1 &&
              vblank_callbacks == f + 1 && !callback_errors, "real_OPD_flip_vblank_callbacks_and_DONE");
        if (!render_call([&] {
            cellGcm_rsx_process_fifo();
            check(vm_read32(control + 4) == vm_read32(control) && !cellGcm_take_flip_pending() &&
                  vm_read32(label) == f + 1, "post_flip_tail_drained_without_duplicate_present");
        })) break;
    }
    if (!stopped()) check(synthetic_frames == requested_frames,
        lifecycle ? "requested_synthetic_GCM_frames" : "six_synthetic_GCM_frames");

}
static void entry(ppu_context* ctx) {
    entry_calls++;
    check(vm_read32(0x20FF0) == 0x50533352, "ELF_PT_LOAD_canary");
    check(vm_read32(0x22040) == 0, "ELF_BSS_zero");
    check(ctx->gpr[13] && vm_read32(ctx->gpr[13] - 0x7000) == 0x544C5330, "ELF_TLS_template");
    check(vm_read32(ctx->gpr[4] + 4) != 0, "PPU_argv");
    // Real generated NID bridge, guest pointer and big-endian writeback.
    vm_write32(0x22080, UINT32_MAX);
    ctx->gpr[3] = 0x111; ctx->gpr[4] = 0x22080;
    ps3_hle_call(0x40E895D3, ctx); // cellSysutilGetSystemParamInt(LANG)
    check((int32_t)ctx->gpr[3] == 0 && vm_read32(0x22080) < 32, "HLE_NID_guest_writeback");
    const char path[] = "/app_home/runtime-canary.bin";
    memcpy(vm_base + 0x22100, path, sizeof path);
    ctx->gpr[3] = 0x22100; ctx->gpr[4] = 0; ctx->gpr[5] = 0x22200;
    ctx->gpr[6] = 0; ctx->gpr[7] = 0; ctx->gpr[8] = 0;
    ps3_hle_call(0x718BF5F8, ctx); // cellFsOpen
    const bool opened = (int32_t)ctx->gpr[3] == 0;
    check(opened, "real_VFS_app_home_open");
    if (opened) {
        uint32_t fd = vm_read32(0x22200);
        ctx->gpr[3] = fd; ctx->gpr[4] = 0x22280;
        ctx->gpr[5] = sizeof vfs_canary - 1; ctx->gpr[6] = 0x22210;
        ps3_hle_call(0x4D5FF8E2, ctx); // cellFsRead
        check((int32_t)ctx->gpr[3] == 0 && vm_read64(0x22210) == sizeof vfs_canary - 1 &&
              !memcmp(vm_base + 0x22280, vfs_canary, sizeof vfs_canary - 1), "real_VFS_read_bytes_and_count");
        ctx->gpr[3] = fd; ps3_hle_call(0x2CB51F0D, ctx);
        check((int32_t)ctx->gpr[3] == 0, "real_VFS_close");
    }
    main_host_tid = GetCurrentThreadId();
    ctx->gpr[3] = 0x22020; ctx->gpr[4] = 0x20008;
    ctx->gpr[5] = UINT64_C(0x1122334455667788); ctx->gpr[6] = 1000;
    ctx->gpr[7] = 0x10000; ctx->gpr[8] = 1; ctx->gpr[9] = 0x20E00;
    ps3_hle_call(0x24A1EA07, ctx); // HLE create ABI, not LV2 raw param-block ABI
    const uint64_t tid = vm_read64(0x22020);
    bool created = (int32_t)ctx->gpr[3] == 0 && tid;
    check(created, "real_PPU_thread_create");
    if (created) {
        ctx->gpr[11] = SYS_PPU_THREAD_JOIN; ctx->gpr[3] = tid; ctx->gpr[4] = 0x22030; lv2_syscall(ctx);
        check((int32_t)ctx->gpr[3] == 0 && vm_read64(0x22030) == 0x1234, "real_PPU_thread_join_status");
        check(worker_calls == 1 && worker_host_tid != main_host_tid, "worker_dispatch_argument_host_thread");
    }
    graphics(ctx);
}
const func_entry function_table[] = {
    {0x10000, entry, "synthetic_entry"}, {0x10100, worker, "synthetic_worker"},
    {0x10200, flip_callback, "synthetic_flip_callback"}, {0x10300, vblank_callback, "synthetic_vblank_callback"},
    {0, nullptr, nullptr}};
const uint64_t function_table_count = 4;

static int probe(const char* elf, const char* vfs, FullRuntimeLog log, void* context, FullRuntimeFrameGate gate) {
    if (started.exchange(true)) {
        if (log) log("full_runtime already tested; restart app for a fresh process", context);
        return 2;
    }
    logger = log; logger_context = context; frame_gate = gate;
    setenv("GCM_FLIPCB_ONTICK", "1", 1); // exactly one completion callback per flip
    emit("full_runtime begin synthetic_PPU=1 game_execution=0 game_frames=0 CPU_JIT=0");
    emit("mode=%s requested_frames=%u", lifecycle ? "separate_PPU_renderer" : "serial_regression", requested_frames);
    if (lifecycle && !runtime_ppu_checkpoint(lifecycle)) return 2;
    memory("before");
    // Preserve the current inFAMOUS launcher allocation path and bounds.
    vm_base = (uint8_t*)calloc(1, 0xE0000000u); ppu_vm_size = vm_base ? 0xE0000000u : 0;
    check(vm_base != nullptr, "original_launcher_3_5_GiB_calloc");
    if (!vm_base) return 1;
    memory("after_calloc");
    // Run actual offline-generated instructions before the handwritten GCM
    // fixture. Its ELF sits next to synthetic.elf on host and in the bundle.
    std::string aot_path = elf;
    auto separator = aot_path.find_last_of('/');
    aot_path = (separator == std::string::npos ? "" : aot_path.substr(0, separator + 1)) + "lifted-probe.elf";
    check(lifted_ppu_probe(aot_path.c_str(), logger, logger_context) == 0,
          "offline_generated_PPC_to_native_execution");
    vfs_root = vfs; ppu_vfs_root = vfs_root.c_str();
    FILE* canary = fopen((vfs_root + "/runtime-canary.bin").c_str(), "wb");
    bool canary_ok = canary && fwrite(vfs_canary, 1, sizeof vfs_canary - 1, canary) == sizeof vfs_canary - 1;
    if (canary) fclose(canary);
    check(canary_ok, "private_VFS_fixture_created");
    uint32_t opd = ppu_load_elf(elf);
    check(opd == 0x20000, "real_ELF_loader_entry_OPD");
    ppu_recomp_register(); ppu_hle_init(); ppu_sysprx_register(); ppu_fs_register(); lv2_init_syscalls();
    emit("HLE_registered=%u", ps3_hle_count());
    check(ps3_hle_count() > 100, "generated_HLE_table_registered");
    if (lifecycle && !runtime_ppu_checkpoint(lifecycle)) return 2;
    if (opd == 0x20000) check(ppu_run(opd, 0x0FF00000) == 0 && entry_calls == 1, "PPU_run_entry_return");
    g_active_ctx = nullptr; // ppu_run's entry context was on its own stack.
    memory("after_PPU");
    // SDL is linked from this SDK. Exercise only controller discovery here;
    // actual audio samples, touch mapping and full game input are later tests.
    if (lifecycle && !runtime_ppu_checkpoint(lifecycle)) {
        emit("SDL_controller_init=SKIPPED reason=stop_requested");
    } else {
    SDL_SetMainReady();
    int sdl_rc = SDL_InitSubSystem(SDL_INIT_GAMECONTROLLER);
    SDL_version ver; SDL_GetVersion(&ver);
    emit("SDL=%u.%u.%u controller_init=%d devices=%d error=%s", ver.major, ver.minor, ver.patch,
         sdl_rc, sdl_rc == 0 ? SDL_NumJoysticks() : -1, SDL_GetError());
    check(sdl_rc == 0, "real_SDL_controller_backend_init");
    if (!sdl_rc) SDL_QuitSubSystem(SDL_INIT_GAMECONTROLLER);
    }
    // Keep the one-shot guest arena alive while the app shows results. Some
    // runtime registries retain guest/entry references; teardown is separate.
    emit("full_runtime_result=%s failures=%u synthetic_GCM_frames=%u game_frames=0 arena_retained=1",
         failures ? "FAIL" : stopped() ? "STOPPED" : "PASS", failures, synthetic_frames);
    logger = nullptr; logger_context = nullptr;
    return failures ? 1 : stopped() ? 2 : 0;
}
int full_runtime_probe(const char* elf, const char* vfs, FullRuntimeLog log, void* context, FullRuntimeFrameGate gate) {
    return probe(elf, vfs, log, context, gate);
}
int full_runtime_probe_threaded(const char* elf, const char* vfs, FullRuntimeLog log, void* context,
                               FullRuntimeControl* control, unsigned frames, unsigned interval_ms) {
    if (!control || !frames || frames > 1000) return 1;
    lifecycle = control; requested_frames = frames; frame_interval_ms = interval_ms;
    runtime_ppu_begin(control);
    int rc = probe(elf, vfs, log, context, nullptr);
    runtime_ppu_end(control);
    FullRuntimeSnapshot s = full_runtime_snapshot(control);
    if (log) {
        char line[240];
        snprintf(line, sizeof line, "coordinator submitted=%llu completed=%llu cancelled=%llu renderer_running=%d ppu_finished=%d",
                 s.submitted_jobs, s.completed_jobs, s.cancelled_jobs, s.renderer_running, s.ppu_finished);
        log(line, context);
        snprintf(line, sizeof line, "threaded_result=%s game_frames=0", rc == 0 ? "PASS" : rc == 2 ? "STOPPED" : "FAIL");
        log(line, context);
    }
    return rc;
}
