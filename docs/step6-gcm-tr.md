# 6. adım — tam runtime: PPU → gerçek GCM FIFO/flip → Metal

Güncel ayrı PPU/renderer ve pause/stop uygulaması: [7. adım](step7-lifecycle-tr.md).
Bu belge 6. adımın seri testini kaydeder.

Bu hedef önceki tam runtime testine ekran yolunu ekler. Sentetik ELF gerçek
loader ile yüklenir; çalıştırılan entry/worker ve iki callback C++ fonksiyonu
lifter ABI'sine uygun elle yazılmıştır ve önceden derlenir. Bu aşama gerçek
oyunun PPC kodunun lifter ile dönüşümünü sınamaz. Oyun kodu, firmware yürütmesi
veya CPU JIT kullanılmaz.
**Oyun karesi 0.** Metal shader derlemesi mevcut NV40 → HLSL → SPIR-V → MSL
zincirinden geçer; CPU yeniden derlemesiyle ayrı süreçlerdir.

## Akış ve kararlar

1. `src/ios/RuntimeApp.mm::startIfReady()` UIKit'in oluşturduğu CAMetalLayer'ı
   ana thread'de bağlar. `runPPU()` 256 MiB stack isteyen, artık **joinable**
   bir pthread'de çalışır. UI raporu `Documents/gcm-runtime-report.txt`'dir.
2. `src/full/FullRuntimeProbe.cpp::entry()` önce ELF/TLS, VFS ve gerçek guest
   thread/join kontrollerini yürütür, sonra `graphics()` fonksiyonuna geçer.
   Tam runtime, kaynak pin'i ve yamalar önceki aşamayla aynıdır. Önceki
   `RSXSmoke.c` fixture'ının sahte belleği/GCM işlevleri bu hedefe bağlanmaz.
3. `_cellGcmInitBody` NID **0x15BAE46B**, gerçek
   `ppu_sysprx.cpp::hle_cellGcmInitBody()` → `cellGcmSetupContext()` yoluyla
   guest context ve IO tablolarını kurar. FIFO EA **0x00100000**, IO bölgesi
   2 MiB; kontrol register'ı ve label adresleri gerçek GCM NID'lerinden alınır.
4. `packet()` yalnızca guest belleğe big-endian FIFO paketleri yazar. Surface
   ve shader register'ları doğrudan host draw-engine çağrısıyla ayarlanmaz.
   FP/vertex adresleri GCM'nin gerçek IO→EA eşlemesiyle çözülür; framebuffer
   RSX local belleğinde **0xC0040000**, guest render boyutu **640×360**'tır.
5. `_cellGcmSetFlipCommand` NID **0x21397818**, FIFO'ya **0xFEAD0100** yazar.
   `cellGcmSys.c::cellGcm_rsx_process_fifo()` işarete gelince durur ve pending
   flip üretir. Test pending'i bir kez tüketip `rsx_metal_backend_present()`
   çağırır; sonraki komutları tüketmeden önce tamamlanmış kareyi sunar.
6. Her flip'in arkasına label 5 için semaphore RELEASE konur. İlk drain'de
   **get < put**, label önceki değerinde; ikinci drain'de **get == put**, label
   yeni değerindedir. Bu, kare sınırının gerçekten korunduğunu ve tail drain'in
   fazladan sunum üretmediğini sınar. Backend'in `debug_color()` değeri clear
   register yazmasını değil son uygulanan clear'ı gösterdiğinden, tail için
   gözlem noktası olarak guest label belleği kullanılır.
7. `GCM_FLIPCB_ONTICK=1` yalnız bu sentetik süreçte seçilir. `cellGcmTickFlip()`
   ve `cellGcmTickVBlank()` ardından `ppu_gcm_pump()` gerçek OPD köprüsüyle
   `ppu_guest_call()` çağırır. Altı flip ve altı VBlank callback'i, argümanları,
   host thread kimlikleri ve DONE durumu kontrol edilir. Bu manuel tanı tick'i
   gerçek oyunun vsync/pacing doğrulaması değildir.
8. Altı tanı karesi GPU flush/readback ile doğrulanır: RGB clear, sonra
   R/B kanallarını değiştiren guest shader ile **RGB → BGR** üçgen. Her shader
   karesinde `translated_draws == 1` aranır; yerleşik shader başarı sayılmaz.
   Bu GPU beklemeleri ve 250 ms UI test aralıkları FPS ölçümü için kullanılamaz.
9. İş bitince GPU işi tamamlanır, backend shutdown olur ve draw engine kaydı
   kaldırılır. Utility queue pthread'i join eder; ardından ana thread layer'ı
   ayırır. Ana thread join bekleyerek worker'ın senkron loglarını kilitlemez.
   **Guest VM ve bazı registry'ler süreç boyunca tutulur; tam runtime yeniden
   başlatılabilir hâle geldiği iddia edilmez.**

## Doğrulama

Mac kontrol grubu **9/9 PASS**; tam runtime testi **60 kontrol / 0 hata**.
Altı GPU pikseli ve üç guest shader draw doğru. Bilinen dört upstream draw
engine beklenti farkı, önceki baseline karşılaştırma kontrolünde aynı kalır.
Mac testi headless Metal'dir; UIKit ekran sunumu sonucu sayılmaz.

Gerçek **iPhone 15 Pro / Apple A17 Pro GPU / iOS 27.2** üzerinde **61 kontrol,
0 hata, PASS**. Altı karenin pikseli doğru; üç shader karesinde birer guest
draw var. Yüzey sayaçları **submitted=6, completed=6, presented=6, errors=0**.
Son satır: `pthread_join=0 worker_result=0 layer_detach=0 PASS`.
1192 HLE kaydı ve önceki ELF/TLS/VFS/thread kontrolleri de geçti.

| Kontrol | Sonuç |
| --- | --- |
| macOS testleri | 9/9; bu tam runtime testinde 60 kontrol PASS |
| iPhoneOS derleme/bağlama/imza | Son kaynaklarla geçti, aynı test uygulamasının üstüne kuruldu |
| Gerçek iPhone çalışması | 61 kontrol PASS; 6 GPU sunumu, doğru pikseller, temiz renderer/worker kapanışı |
| Simulator SDK derleme/bağlama | Geçti; **çalışma başarısı yok** |
| Bağımlılık platform denetimi | Her hedefte 14 arşiv; macOS 597, IOS ve IOSSIMULATOR 598'er object doğru platformda |

Simülatör kuruldu fakat launch istemi sonuçlanmadı. Kullanıcı onayıyla yalnız
test için açılan simülatör kapatıldı; buna bağlı launch istemi `server died`
ile sonlandı. Simülatörün çalıştığı veya bu gecikmenin RAM/oyun kaynaklı olduğu
iddia edilmez. Yetkili temizlik komutları öncesinde otomatik izin incelemesi
zaman aşımları görüldü; son kapatma komutu başarıyla tamamlandı. Son iPhone
imzalama işi de başarıyla bitti. Simulator performans ölçümü yok.

Cihazın fiziksel footprint örnekleri: başlangıç **23,85 MiB**, 3,5 GiB calloc
sonrası **24,33 MiB**, sentetik PPU/GCM ve renderer kapanışından sonra
**81,67 MiB**. calloc aşamasında toplam sanal boyut **3584,11 MiB** arttı;
aynı aralıkta UIKit/allocator da çalıştığından fark yalnız calloc'un kesin
boyutu değildir. Stack istenen **268435456**, bildirilen **268447744** bayt.
Bu örnekler UIKit/Metal/runtime maliyetlerini içerir; gerçek oyun belleğini
veya bellek iadesinin tamamlandığını kanıtlamaz. SDL controller init başarılı,
cihaz kaydı 1; fiziksel kontrolcü eşlemesi veya ses doğrulanmadı.

Kanıtlar Git dışındaki `out/step6-device-gcm-report.txt`,
`step6-verification.json`, `step6-host-tests.log`, `step6-host-test-details.log`,
`step6-ios-final-sign.log`, `step6-simulator-final-build.log` ve üç
`step6-*-archives.json` dosyasında. Son iPhone bundle imzası ayrıca doğrulandı;
AppKit/Homebrew dylib bağımlılığı yok. Shader/runtime pin'leri yeniden kontrol
edildi, değiştirilmedi.

## Tekrar üretme

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
python3 tools/setup_sources.py
python3 tools/setup_shader_sources.py
python3 tools/setup_context_sources.py
python3 tools/setup_sdl_sources.py
tools/build_probe.sh host
tools/build_probe.sh ios
tools/build_probe.sh simulator
```

SDK derlemeleri sırayla, her biri 2 iş ile yapılır. Cihazda aynı bundle kimliği
kullanılır; önceki uygulamanın üstüne kurulur. İmzalama:

```sh
xcodebuild -quiet -project build/ios/Infamous2IOSProbe.xcodeproj \
  -scheme Infamous2FullRuntime -configuration Release \
  -destination 'generic/platform=iOS' -jobs 2 \
  CODE_SIGNING_ALLOWED=YES DEVELOPMENT_TEAM="$PROBE_TEAM_ID" \
  -allowProvisioningUpdates
xcrun devicectl device install app --device "$PROBE_DEVICE_ID" \
  build/ios/Release-iphoneos/Infamous2FullRuntime.app
xcrun devicectl device process launch --device "$PROBE_DEVICE_ID" dev.infamous2.iosprobe
xcrun devicectl device copy from --device "$PROBE_DEVICE_ID" \
  --domain-type appDataContainer --domain-identifier dev.infamous2.iosprobe \
  --source Documents/gcm-runtime-report.txt --destination out/step6-device-gcm-report.txt
python3 tools/check_shader_archives.py --build build/ios --platform IOS \
  --include-runtime --include-full-runtime
```

`out/step6-*` ve build çıktıları Git dışındadır. Kaynak kod/yamalar ve proje
notları tutulur; oyun/firmware veya büyük üretilmiş çıktılar eklenmez.

## Sınırlar ve sıradaki adım

Bu sonlu tanıda PPU ve RSX tüketimi **aynı worker'da sıralı** çalışır. Bu,
gerçek GCM/Metal entegrasyonunu kanıtlar; ayrı PPU/SPU üreticilerinin eşzamanlı
FIFO tüketimi ve uzun oyun çalışması ayrıca sınanmalı. Foreground kontrolü yeni
GPU batch'ini bekletebilir; tam oyunun arka plan/ses/fiber/PPU durdurma protokolü
henüz yoktur. Sonraki bağımsız adım ayrı renderer thread'i, kontrollü stop ve
arka plan/geçiş testidir. Oyun girdileri gelince gerçek boot bağlanacaktır.

Girdi kontrolü yeniden çalıştırıldı: **PARAM.SFO, çözülmüş EBOOT.elf, .psarc
arşivleri ve liblv2/libsysmodule/libsre PRX seti hâlâ yok**. Beklenen sürüm
NPUA80638 / APP_VER 01.03; yollar README'de. Dosyalar geldiğinde aynı pin ile
macOS referans boot'u ve iOS ilk gerçek kare doğrulanacak. Mevcut title SPU,
GPU light/SSAO ve senkronizasyon düzeltmeleri değiştirilmedi. Gerçek oyun
belleği veya FPS'i bu sentetik sonuçlardan çıkarılamaz.
