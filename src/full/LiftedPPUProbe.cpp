#include "FullRuntimeProbe.h"
#include "lifted_ppu.h"
#include <cstdio>
#include <cstring>

extern "C" {
uint32_t ppu_load_elf(const char*);
void ppu_register_function(uint64_t, void (*)(ppu_context*));
int ppu_run(uint32_t, uint32_t);
extern PPU_THREAD_LOCAL ppu_context* g_active_ctx;
}

// Uses the existing arena and pinned PPU loader/dispatch. No handwritten CPU
// function bodies: aot_function_table is emitted by the offline lifter.
int lifted_ppu_probe(const char* elf, FullRuntimeLog log, void* opaque) {
    unsigned failures = 0;
    auto report = [&](bool ok, const char* name) {
        char line[256];
        snprintf(line, sizeof line, "AOT_check=%s result=%s", name, ok ? "PASS" : "FAIL");
        fprintf(stderr, "[lifted PPU] %s\n", line);
        if (log) log(line, opaque);
        if (!ok) failures++;
    };
    memset(vm_base + 0x60100, 0xA5, 0xF00);
    const uint32_t opd = ppu_load_elf(elf);
    report(opd == 0x60000, "ELF_entry_OPD");
    report(aot_function_table_count == 2, "offline_lifter_function_table");
    for (uint64_t i = 0; i < aot_function_table_count; ++i)
        ppu_register_function(aot_function_table[i].addr, aot_function_table[i].func);
    bool bss_zero = true;
    for (unsigned i = 0x60100; i < 0x61000; ++i)
        bss_zero &= vm_base[i] == 0;
    report(bss_zero, "loader_zeroes_BSS");
    if (opd == 0x60000) {
        report(ppu_run(opd, 0x0FE00000) == 0, "generated_PPC_entry_returns");
        g_active_ctx = nullptr;
        report(vm_read32(0x60040) == 55, "PPC_loop_sum_1_to_10");
        report(vm_read32(0x60044) == 172, "PPC_call_multiply_add_LR_stack");
        report(vm_read32(0x60048) == 0x12345678 && vm_read32(0x6004C) == 0x12345678 &&
               memcmp(vm_base + 0x60048, "\x12\x34\x56\x78", 4) == 0,
               "PPC_big_endian_store_load_bytes");
    }
    return failures ? 1 : 0;
}
