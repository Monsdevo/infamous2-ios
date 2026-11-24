"""Optional Linux slot alignment; no context ABI or per-access control change."""
SLOT = '''typedef struct {
    spu_context* ctx;
    mfc_engine   mfc;
} spu_mfc_slot;'''
MARKER = '/* ===========================================================================\n * Atomic reservation'

def patch(source, enabled=False):
    assert source.count(SLOT) == 1 and source.count(MARKER) == 1
    assert 'void bces_mfc_layout(' not in source
    if enabled:
        source = source.replace(SLOT, SLOT.replace('} spu_mfc_slot;', '} __attribute__((aligned(128))) spu_mfc_slot;'), 1)
    # This is read once per telemetry tick, never in mfc_for/transfer paths.
    layout = '''
void bces_mfc_layout(uint64_t out[8]) {
    out[0] = ENABLED;
    out[1] = sizeof(spu_mfc_slot);
    out[2] = _Alignof(spu_mfc_slot);
    out[3] = (uintptr_t)&s_mfc_slots[0] & 127u;
    out[4] = (uintptr_t)&s_mfc_slots[1] - (uintptr_t)&s_mfc_slots[0];
    out[5] = offsetof(spu_mfc_slot, mfc);
    out[6] = sizeof(s_mfc_slots);
    out[7] = sizeof(mfc_engine);
}
'''.replace('ENABLED', '1' if enabled else '0')
    return '#include <stddef.h>\n' + source.replace(MARKER, layout + '\n' + MARKER, 1)
