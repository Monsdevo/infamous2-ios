# Mimari ve iOS engelleri — 17 Ekim 2026

Bu belge ilk kaynak incelemesini kaydeder. Sonraki oturumdaki gerçek RSX
renderer/CAMetalLayer entegrasyonu ve güncel durum için
[2. adım notuna](step2-renderer-tr.md) ve shader çevirisi için
[3. adım notuna](step3-shaders-tr.md), VM/thread/fiber için
[4. adım notuna](step4-runtime-tr.md), tam bağlantı ve PPU başlangıcı için
[5. adım notuna](step5-full-runtime-tr.md), gerçek GCM FIFO/flip bağlantısı için
[6. adım notuna](step6-gcm-tr.md), ayrı thread ve yaşam döngüsü için
[7. adım notuna](step7-lifecycle-tr.md) bakın; aşağıdaki engel tablosu ilk
incelemedeki kaynak durumunu anlatır. Upstream kaynaklar değişmeden
korunur, yeni platform yaması build overlay'inde uygulanır.

Bu not `sources.lock.json` içindeki sürümlerin yerel kaynak incelemesine dayanır.
`upstream/infamous2-recomp/infamous2-lle` etkin porttur; `infamous2` eski HLE
denemesidir. İkincisinin `game/`, `fw/`, `vfs/` yolları etkin portça paylaşılır.

## Başlangıçtan görüntüye

1. Portun `tools/setup_toolkit.sh` dosyası **NoahBPeterson/ps3recomp**,
   `infamous/rebase-v0.13.0`, `770660a3971b87a453677e46125e5e01ac7891c0`
   sürümünü ve `ps3recomp-fork-770660a-with-upstream-prs.patch` yamasını seçer.
   Yama SHA-256: `11846458ab9b3b29655e3dd3775fe6bd38e1001b406a60f6ed5ac76fcb5e9866`.
   `tools/setup_sources.py` aynı kaynakları yeniden kurar; tüm yamanın beklenen
   dosya içeriklerini geçici bir Git index'iyle doğrular, yerel değişiklikleri silmez.
   Genel `sp00nznet/ps3recomp` yalnızca karşılaştırma kaynağıdır.
2. Python `ppu_loader.py` / `ppu_lifter.py`, kullanıcının çözülmüş EBOOT ELF'ini
   PPU fonksiyon tablosu ve C/C++ dosyalarına dönüştürür. SPU iş/modülleri ve
   firmware ayrıca dönüştürülür. Bunlar hedef derleyicide önceden derlenir.
3. `infamous2-lle/main.cpp::main()` önce `infamous2_gpu_light_install()` ve
   `infamous2_gpu_ssao_install()` kancalarını kurar. `alloc_guest_vm()` guest
   adres alanını ayırır; `ppu_load_elf()` segmentleri buraya yükler.
4. `derive_vfs_root()` ve `cellGame_init_from_paramsfo()` veri kökünü ve gerçek
   oyun kimliğini belirler. `ppu_recomp_register()`, `ps3_load_prx_modules()`
   (`stubs.cpp`), `ppu_hle_init()`, `ppu_sysprx_register()`, `ppu_fs_register()`
   ve `lv2_init_syscalls()` kod/adres, firmware, dosya ve syscall eşlemelerini kurar.
   `stubs.cpp` ayrıca Wws_Job policy modülünü guest `0x008E5B00`, LS `0xA00`,
   11904 bayt ve image id 3 ile kaydeder. Başka oyun sürümüne körlemesine taşınamaz.
5. `ppu_run(entry, STACK_TOP)` oyuna girer. Guest PPU/SPU kodu ve HLE/LLE
   sistem işlevleri birlikte yürür; çözülmemiş bazı SPU yollarında yorumlayıcı
   fallback vardır. CPU için çalışma zamanında yerel makine kodu üretmek gerekmez.
6. `main.cpp::frame_clock()` vblank/flip callback'lerini üretir;
   `cellGcmSys.c::cellGcm_rsx_process_fifo()` FIFO'yu boşaltır. RSX register,
   shader, doku ve draw bilgileri `rsx_draw_engine.c` üzerinden backend'e gider.
7. `rsx_shader_msl.cpp::rsx_hlsl_to_msl()` HLSL → glslang/SPIR-V → SPIRV-Cross/MSL
   çevirisini yapar. `rsx_metal_backend.m` pipeline, render target ve draw
   işlerini kodlar. `newLibraryWithSource` GPU shader derlemesidir; CPU JIT değildir.
   `present_guest_frame()` flip sınırında bitmiş kareyi sunar; sunumdan önce/sonra
   FIFO sırasını değiştirmek senkronizasyon ve görüntü doğruluğunu bozabilir.

## Platform sınırları

Runtime yolları aşağıdaki tabloda `upstream/infamous2-recomp/ps3recomp-fork/`
köküne göredir. Doğrulanmış derleme hataları `python3 tools/audit_ios.py` ile
yeniden üretilebilir. Bu araç tam runtime derlemesi yapmaz.

| Dosya / fonksiyon | Bulgular ve uygulanacak sınır |
| --- | --- |
| `libs/video/rsx_metal_backend.m:83` | `static NSWindow* s_window` iOS koruması dışında. iOS SDK syntax kontrolünde gerçek hata. AppKit pencere, başlık/FPS, klavye/fare olaylarını macOS kabuğunda tut. |
| Aynı dosya, `create_window_impl`, `create_window`, `pump_messages_impl` | NSApplication/NSView/NSEvent ve main queue senkron çağrıları masaüstüne ait. UIKit ana thread'i kendisi yönetir; iOS'ta AppKit event pump taşınmaz. |
| Aynı dosya, `rsx_metal_backend_init()` | `TARGET_OS_IPHONE` dalı `s_headless=1; create_offscreen()` yapıyor. Hazır iPhone ekran desteği yok. Bir sonraki köprü UIKit'in oluşturduğu CAMetalLayer'ı almalı; mevcut offscreen davranışı ve macOS yolu korunmalı. |
| Aynı dosya, `eng_present`, `rsx_metal_backend_present`, `eng_make_texture` | Drawable ve boyut/yaşam döngüsü ayrılmalı. BGRA/RGBA, sRGB, MRT, readback, semaphore, kaynak ömrü ortak kalmalı. BC1/2/3 desteği `MTLDevice.supportsBCTextureCompression` ile cihazda sorgulanmalı; destek yoksa dönüşüm yolu gerekli. Bu oturum BC desteğini varsaymadı. |
| `libs/video/rsx_shader_msl.cpp:141` | `SPVC_MSL_PLATFORM_MACOS` sabit. iOS çeviri hedefini seçen ayrı dal gerekli. Shader sürümü, resource limitleri ve derleyici çıktıları gerçek guest shader'larla doğrulanmalı. |
| Runtime `CMakeLists.txt` | `if(APPLE)` koşulu AppKit bağlıyor; iOS da APPLE'dır. iOS/macOS framework listeleri ayrı olmalı. `find_package(SDL2)`, glslang ve pkg-config/Homebrew keşfi host arşivi getirebilir. iOS kaynak derlemeleri ve kapalı bir iOS prefix'i kullan; arm64 etiketi tek başına doğru platform demek değildir. |
| `runtime/platform/win32_compat.c:52`, `os_region()` | iOS SDK `mach/mach_vm.h` için açıkça `unsupported` hatası verir; `mach_vm_region` de bildirimsiz kalır. Gerçek derleme engeli. iOS'ta desteklenen VM sorgusu/ayırma soyutlaması gerekli. |
| Aynı dosya, context/suspend/VEH yolları | `thread_suspend`, `thread_get_state`, `thread_set_state`, sinyal/ucontext ve fault handler'ları mevcut. Bunların derlenmesi cihazdaki tüm davranışları kanıtlamaz. Diagnostic test gerçek runtime suspend/resume veya fault recovery'yi çalıştırmadı. |
| `runtime/memory/vm.h::vm_init`, `vm_protect`, `vm_stack_allocate` | Başlatıcıdaki calloc yolundan farklı olarak mmap/mprotect ve guest guard page mantığı da var. Host sayfa boyutu 16 KiB; guest 4 KiB kabulüyle mprotect yapmak komşu sayfalara dokunabilir. Guest yürütme izni host PROT_EXEC gerektirmemeli; çalışan lifter kodu zaten uygulama binary'sindedir. JIT entitlement çözüm olarak eklenmedi. |
| `runtime/syscalls/sys_ppu_thread.c::sys_ppu_thread_create` | Guest stack adresi ile host C stack farklıdır. PPU host stack sabiti 256 MiB; hata durumunda küçük varsayılan stack'e düşme yolunu görünür kılmak gerekir. Sadece başarılı pthread_create, derin oyun çağrılarının sığdığını kanıtlamaz. |
| `runtime/syscalls/lv2_register.c::spu_host_stack_bytes`, `spu_spawn_host_thread` | SPU için normal 16 MiB, `SPU_HOST_STACK_BIG` ile 512 MiB. `spu_dispatch_mt.c` içindeki Clang musttail yolu korunmalı; düz çağrıya dönüşmesi stack'i tüketebilir. |
| `libs/spurs/cellFiber.c::cellFiberPpuCreateFiber/SwitchFiber/YieldFiber` | `_XOPEN_SOURCE=600`, `getcontext/makecontext/swapcontext/setcontext` kullanıyor. iOS 27.1 SDK'sında dosya syntax kontrolü ve küçük getcontext link denemesi geçiyor; API eski/deprecated, tam fiber geçişi cihazda doğrulanmış değil. Bu yolu henüz değiştirmedik. |
| `runtime/spu/spu_context.h` | SPU çıkışı `_setjmp/_longjmp` kullanıyor. Tanı bu unwind primitifini sınar; gerçek SPURS scheduling/fiber doğrulaması yerine geçmez. |
| `runtime/spu/spu_coherency.c` | Apple yolunda Mach thread/barrier işlemleri var. Guest/SPU veri görünürlüğü korunmalı; gereksiz kilit kaldırma veya atomik sıralama değişikliği yapılmadı. |
| `libs/input/cellPad.c`, `libs/audio/cellAudio.c` | Non-Windows SDL2 backend'leri seçiliyor. Bu ilk tanı bunları bağlamıyor. Sonraki aşamada iOS SDL2 derlemesi veya GameController/AVAudioSession adaptörleri gerekli; dokunmatik GCVirtualController/özel UI aynı PS3 pad durumuna yazmalı. |
| `runtime/ppu/ppu_fs.cpp`, `libs/filesystem/cellFs.c`, port `run.sh` | cwd, HOME ve RPCS3 dev_flash yolları iPhone'a taşınamaz. Oyun girdileri uygulamanın erişebildiği alana alınmalı; kayıtlar Application Support/Documents altında olmalı. `cellGame.c` disk boşluğu kontrolü gerçek uygulama veri kökünü kullanmalı. |
| Port `main.cpp::main/frame_clock` | Masaüstü CLI + CFRunLoop yerine iOS UIKit scene yaşam döngüsü gerekli. Main thread'de uzun ppu_run/FIFO çalıştırma; UIKit'i bloklama. Arka plana geçerken çizim ve zamanlayıcıların kontrollü durması ayrı entegrasyon işi. |

## İlk oturumdaki ayrım

`src/common/Probe.cpp` C++ ölçüm kodudur; aynı kaynak host ve iOS hedeflerinde
derlenir. `rsx_texture_common`, sabitlenmiş ve yamalanmış runtime'ın
**değiştirilmemiş** `rsx_texture_layout.c` dosyasını her SDK için ayrı derler.
`diagnosticTexture()` ARGB Morton doku üretir, `rsx_texture_decode()` ile RGBA'ya
çevirir. `0xAAEE` / X16 tek kanal remap testi oyunun lighting ramp düzeltmesini
doğrudan korur. `src/ios/App.mm` MTKView, texture upload, fullscreen triangle,
Metal sunumu, rapor kaydı ve scene yaşam döngüsünü sağlar.

Bu ilk sürüm tam `rsx_draw_engine` veya guest shader zincirini bağlamıyordu.
İkinci adımda gerçek renderer, üçüncü adımda shader çeviricisi bağlandı.
Güncel sentetik deneme oyun görüntüsü üretmez; gerçek PPU/SPU boot'u ayrı iştir.

Mevcut port ve toolkit dosyaları değiştirilmedi; portun GPU light/SSAO kancaları,
SPU overlay/rejoin, FIFO park grace, semaphore acquire, writeback, sRGB ve shader
pack/unpack yamaları baz çizgi olarak korunuyor. `run.sh` bazı occlusion shader'larını
geçici atlıyor; bu upstream görüntü doğruluğu kısıtı da var. Orijinal davranışla
eşdeğerlik henüz iddia edilemez. Genel runtime'a güncelleme ayrı bir karşılaştırma
ve regresyon çalışması gerektirir.

## REA

İncelenen commit `7aa4b98c9829148b81211aff4e0413cb4ff2ff92`:
`docs/ghidra-ppc.md` ve `src/ghidra/GhidraPowerPcProfile.ts` yalnızca big-endian
ELF32 ET_EXEC yolunu kabul ediyor; ELF64/PPC64 açıkça reddediliyor. PS3 PPU
ELF64 big-endian/EM_PPC64 girdisi için hazır destek varsayılmadı. REA kurulmadı
ve ilk derlemenin bağımlılığı yapılmadı. Gerektiğinde doğrudan uygun Ghidra
PowerPC64 analizi veya ayrıca doğrulanan bir bağlantı değerlendirilecek.

Kaynaklar: [port](https://github.com/erikomis/infamous2-recomp),
[genel runtime](https://github.com/sp00nznet/ps3recomp),
[REA PPC sınırı](https://github.com/morluto/rea/blob/7aa4b98c9829148b81211aff4e0413cb4ff2ff92/docs/ghidra-ppc.md),
[Apple UIScene zorunluluğu](https://developer.apple.com/documentation/uikit/transitioning-to-the-uikit-scene-based-life-cycle).
