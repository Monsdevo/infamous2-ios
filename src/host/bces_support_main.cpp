// Host-only registration/leaf check of locally generated support code.
// No title PPU entry, firmware start routine, renderer or game loop runs here.
#include "prx_loader.h"
#include "spu_context.h"
#include <cstdio>
#include <cstdint>
#include <memory>

extern "C" {
using SpuFunction = void (*)(spu_context*);
SpuFunction spu_lookup(uint32_t address, int image_id);
void jobmod_77f8b0e2e976_efe70_spu_func_0001DC1C(spu_context*);
}

int main() {
    unsigned failed = 0;
    auto check = [&](bool ok, const char* name) {
        std::printf("check=%s result=%s\n", name, ok ? "PASS" : "FAIL");
        failed += !ok;
    };
    struct Module { const char* name; uint32_t base; uint64_t functions; };
    for (const auto& expected : {Module{"liblv2.sprx", 0x30000000, 335},
                                 Module{"libsysmodule.sprx", 0x30180000, 220},
                                 Module{"libsre.sprx", 0x30100000, 440}}) {
        const auto* module = prx_static_find(expected.name);
        check(module && module->mod.base == expected.base && module->mod.func_count == expected.functions,
              expected.name);
        if (module) {
            bool valid = module->mod.image && module->mod.image_size && module->mod.funcs;
            for (uint64_t i = 0; valid && i < module->mod.func_count; ++i) {
                const auto& entry = module->mod.funcs[i];
                valid = entry.func && entry.addr >= expected.base &&
                        entry.addr < expected.base + module->mod.image_size;
            }
            check(valid, "firmware_function_table_range");
        }
    }
    check(spu_lookup(0xa00, 3) && spu_lookup(0xa2c, 3), "WWS_entry_and_resume_registered");
    check(spu_lookup(0x9400, 221) && spu_lookup(0x4ac8, 221), "BCES_light_registered");
    check(spu_lookup(0x6060, 225) && spu_lookup(0x4330, 225), "BCES_SSAO_registered");
    check(spu_lookup(0x818, 100) && spu_lookup(0x848, 101) &&
          spu_lookup(0xa00, 102) && spu_lookup(0xa00, 103) && spu_lookup(0xa00, 104), "firmware_SPU_images_registered");
    auto context = std::make_unique<spu_context>();
    // This actual translated two-instruction leaf sets r3=-10 and returns.
    // A caller frame keeps SPU_RET from initiating an indirect driver loop.
    context->host_depth = 1;
    context->gpr[0]._u32[0] = 0x1234;
    jobmod_77f8b0e2e976_efe70_spu_func_0001DC1C(context.get());
    check(context->gpr[3]._u32[0] == uint32_t(-10) && context->pc == 0x1234,
          "actual_BCES_SPU_leaf_result_and_return");
    std::printf("support_diagnostic=%s game_started=false game_frames=0\n", failed ? "FAIL" : "PASS");
    return failed ? 1 : 0;
}
