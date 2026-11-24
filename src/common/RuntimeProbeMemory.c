#include <stdint.h>
// Isolated synthetic memory for cellFiber's genuine guest-endian accessors.
// The target renames vm_base so it cannot replace the RSX fixture's arena.
uint8_t* vm_base;
uint32_t g_ww_lo = UINT32_MAX, g_ww_hi;
int g_resv_store_active;
void ppu_resv_break_store(uint64_t ea) { (void)ea; }
void ps3_ww_report_inline(uint32_t a, uint64_t v, int n) { (void)a; (void)v; (void)n; }
int spu_coh_is_reserved(uint32_t a) { (void)a; return 0; }
uint64_t spu_lockline_mask_range(uint32_t a, uint32_t n) { (void)a; (void)n; return 0; }
void spu_lockline_lock_mask(uint64_t mask) { (void)mask; }
void spu_lockline_unlock_mask(uint64_t mask) { (void)mask; }
void spu_coh_notify_write_from_ppu(uint32_t a) { (void)a; }
