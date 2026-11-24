#include "../../src/game/BCESGameStorage.c"
#include <assert.h>
uint8_t* vm_base;
uint32_t ppu_vm_size;
int g_resv_store_active;
uint32_t g_ww_lo, g_ww_hi;
void ppu_resv_break_store(uint64_t ea) { (void)ea; }
void ps3_ww_report_inline(uint32_t a, uint64_t v, int w) { (void)a; (void)v; (void)w; }
int spu_coh_is_reserved(uint32_t a) { (void)a; return 0; }
void spu_coh_notify_write(uint32_t a) { (void)a; }
void spu_lockline_lock(void) {}
void spu_lockline_unlock(void) {}
void spu_coh_notify_write_from_ppu(uint32_t a) { (void)a; }
uint64_t spu_lockline_mask_range(uint32_t a, uint32_t n) { (void)a; (void)n; return 0; }
void spu_lockline_lock_mask(uint64_t m) { (void)m; }
void spu_lockline_unlock_mask(uint64_t m) { (void)m; }
ps3_guest_caller_fn g_ps3_guest_caller;
const char* ppu_vfs_root = ".";
static void file_bytes(const char* path, unsigned n) {
    FILE* f = fopen(path, "wb"); assert(f);
    while (n--) fputc(0, f);
    assert(!fclose(f));
}
int main(void) {
    char root[] = "/tmp/bces-game-size-XXXXXX"; assert(mkdtemp(root));
    vm_base = calloc(1, 65536); assert(vm_base);
    cellGame_set_content_path(root);
    char dir[256], nested[256], file[256], link[256];
    snprintf(dir, sizeof dir, "%s/BCES01143_INSTALL", root); assert(!mkdir(dir, 0700));
    snprintf(nested, sizeof nested, "%s/sub", dir); assert(!mkdir(nested, 0700));
    snprintf(file, sizeof file, "%s/a", nested); file_bytes(file, 1025);
    snprintf(link, sizeof link, "%s/external", dir); assert(!symlink("/", link));
    memcpy(vm_base + 0x100, "BCES01143_INSTALL", 18);
    assert(cellGameDataCheck(3, (void*)0x100, NULL) == CELL_OK);
    assert(cellGameGetSizeKB((void*)0x200) == CELL_OK);
    assert(vm_read32(0x200) == 2 && vm_base[0x203] == 2 && vm_base[0x200] == 0);
    assert(cellGameGetSizeKB(NULL) == CELL_GAME_ERROR_PARAM);
    assert(!unlink(file)); assert(!unlink(link)); assert(!rmdir(nested));
    assert(cellGameGetSizeKB((void*)0x200) == CELL_OK && vm_read32(0x200) == 0);
    assert(!rmdir(dir));
    assert(cellGameGetSizeKB((void*)0x200) == CELL_OK && vm_read32(0x200) == 0);
    file_bytes(dir, 1);
    assert(cellGameGetSizeKB((void*)0x200) == CELL_GAME_ERROR_ACCESS_ERROR);
    assert(!unlink(dir)); assert(!rmdir(root)); free(vm_base);
    puts("PASS: installed size, KiB rounding, endian, missing/empty, errors, no symlink traversal");
}
