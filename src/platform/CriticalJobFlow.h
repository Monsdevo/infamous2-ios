#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
extern unsigned bces_critical_flow_enabled;
extern unsigned bces_critical_phases_enabled;
void bces_critical_phases_enable(int enabled);
void bces_critical_phase(void* context, unsigned phase, int entering);
void bces_critical_flow_enable(int enabled);
int bces_critical_flow_transfer(void* context, uint64_t address, uint32_t size, int put);
void bces_critical_flow_dma(void* context, uint32_t address, uint32_t size,
                            uint32_t lsa, const uint8_t* put_source, uint64_t start, uint64_t end);
void bces_critical_flow_rsx(uint32_t address, uint32_t size, uint32_t source);
void bces_critical_flow_fifo(uint32_t address, uint32_t word, int header);
void bces_critical_flow_ppu(uint32_t address, uint32_t size, uintptr_t caller, uint32_t thread);
#ifdef __cplusplus
}
#endif
