#include "RSXSmoke.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc, char** argv) {
    const int reject = argc == 2 && !strcmp(argv[1], "--expect-shader-rejection");
    if (reject) setenv("PS3RECOMP_METAL_FIXED_FUNCTION", "1", 1);
    setenv("PS3RECOMP_METAL_HEADLESS", "1", 1);
    // Two lifetimes exercise shutdown/reinitialization as well as the pixel.
    for (unsigned lifetime = 0; lifetime < 2; ++lifetime) {
        if (rsx_smoke_init() != 0) return 1;
        const unsigned colors[] = {0xFFFF0000, 0xFF00FF00, 0xFF0000FF};
        for (unsigned i = 0; i < 3; ++i) {
            unsigned actual = rsx_smoke_present(colors[i], 1);
            printf("[rsx smoke] lifetime=%u expected=%08X actual=%08X\n", lifetime, colors[i], actual);
            if (actual != colors[i]) { rsx_smoke_shutdown(); return 1; }
        }
        if (rsx_smoke_shader_available()) {
            const unsigned expected[] = {0xFF0000FF, 0xFF00FF00, 0xFFFF0000};
            for (unsigned i = 0; i < 3; ++i) {
                RSXShaderSample s = rsx_smoke_present_shader(colors[i], 1);
                printf("[rsx shader] lifetime=%u input=%08X expected=%08X actual=%08X translated_draws=%u reject=%d\n",
                    lifetime, colors[i], expected[i], s.pixel, s.translated_draws, reject);
                int good = reject ? s.translated_draws == 0 && s.pixel == 0xFF000000 :
                    s.pixel == expected[i] && s.translated_draws == 1;
                if (!good) { rsx_smoke_shutdown(); return 1; }
            }
        }
        rsx_smoke_shutdown();
    }
    return 0;
}
