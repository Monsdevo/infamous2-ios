# 3. adım — RSX shader programlarını iOS Metal'e çevirme

Bu aşama CPU yeniden derlemesine dokunmaz. Sentetik NV40 vertex/fragment
programları mevcut decompiler → HLSL → glslang/SPIR-V → SPIRV-Cross/MSL →
Metal pipeline zincirinden geçirilir. Oyun/firmware kodu yüklenmez.

## Bağımlılık sınırı

`sources.lock.json` içindeki kaynaklar:

| Kaynak | Sabit sürüm / commit |
| --- | --- |
| glslang | 15.1.0 / `1062752a891c95b2bfeed9e356562d88f9df84ac` |
| SPIRV-Tools | `4d2f0b40bfe290dea6c6904dafdf7fd8328ba346` |
| SPIRV-Headers | `3f17b2af6784bfa2c5aa5dbb8e0e74a607dd8b3b` |
| SPIRV-Cross | vulkan-sdk-1.4.304.0 / `ebe2aa0cd80f5eb5cd8a605da604cacf72205f3b` |

Tools/Headers eşleşmesi glslang'ın bu sürümdeki `known_good.json` dosyasından
alındı. Bu seçim en güncel sürüm iddiası değildir; mevcut runtime API'siyle
doğrulanabilir bir başlangıç setidir. HLSL legalization gerektiği için optimizer
kapalı değildir. Googletest ve komut satırı araçları hedef uygulamaya alınmaz.

`tools/setup_shader_sources.py` kaynakları getirir veya mevcut commit/origin ve
yerel değişiklikleri denetler. `--verify-only` ağ kullanmadan doğrular.
`cmake/ShaderDependencies.cmake` her SDK için bu kaynakları statik hedefler
olarak ayrı derler; Homebrew/pkg-config/imported host arşivi keşfi yapmaz.

## Önemli dosya ve fonksiyonlar

- `patches/ios-metal-surface.patch`: artık `rsx_shader_msl.cpp` için de overlay
  içerir. `spirv_to_msl()` iPhone SDK'sında `SPVC_MSL_PLATFORM_IOS`, macOS'ta
  `SPVC_MSL_PLATFORM_MACOS` seçer. MSL 2.1, mevcut resource binding kuralları,
  HLSL legalization ve NaN için `precise::` düzeltmesi korunur. glslang'ın
  kurulu paket ve source-tree header yolları arasındaki fark ayrıca ele alınır.
- `CMakeLists.txt::rsx_core`: önceki stub yerine
  `PS3RECOMP_HAVE_MSL_TRANSLATION=1` ve kaynak hedeflerini bağlar. Bilerek
  `-DPROBE_ENABLE_SHADER_TRANSLATION=OFF -DPROBE_BUILD_FULL_RUNTIME=OFF`
  seçilirse eski clear-only derlemesi
  kurulabilir; normal yapılandırmada eksik bağımlılık sessiz fallback yapmaz.
- `src/common/RSXSmoke.c::prepare_shader()`: upstream'in `rsx_test_programs.h`
  encoder'larıyla `MOV o0,v0; MOV o1,v3` vertex programı ve
  `MOV r0,COL0.zyxw` fragment programını hazırlar. Opcode/endian düzenini yeniden
  icat etmek yerine mevcut test encoder'ı kullanılır.
- `rsx_smoke_present_shader()`: üçgen vertex'lerini guest big-endian float
  düzeninde yazar; program/vertex/renk register'larını gerçek dispatcher'a
  gönderir. Fragment programı R/B kanallarını değiştirir. Beklenen çıktılar:
  kırmızı giriş → mavi, yeşil → yeşil, mavi → kırmızı.
- `src/ios/App.mm::drawFrame()`: ilk üç kare clear, sonraki üç kare shader
  readback kontrolüdür. Pikselin doğru olması **ve**
  `rsx_draw_engine_guest_draws()==1` şarttır. Buradaki sayaç sentetik programla
  çizimi sayar; orijinal oyunun karesi değildir. Tanı okumaları dışında steady
  state çizime GPU beklemesi eklenmez.
- `tools/check_shader_archives.py`: dokuz statik arşivin her object üyesindeki
  `LC_BUILD_VERSION` platformunu kontrol eder; yalnızca arm64 etiketiyle
  yetinmez. macOS=1, iOS=2, iOS Simulator=7 ayrımını doğrular ve hash raporlar.
- `resources/ThirdPartyNotices.txt`: bağımlılıkların lisans metinlerini ve
  kaynak sürümlerini içerir; iOS uygulama bundle'ına eklenir.

CPU JIT veya executable-memory yetkisi eklenmedi. glslang/SPIRV-Cross uygulamada
önceden derlenmiş C++ kodu olarak çalışır; ürettikleri çıktı GPU shader'ıdır.

## Tekrar üretme

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
python3 tools/setup_sources.py
python3 tools/setup_sdl_sources.py # güncel tam runtime hedefi için
python3 tools/setup_context_sources.py # güncel runtime tanısı için
python3 tools/setup_shader_sources.py
tools/build_probe.sh host
tools/build_probe.sh ios
tools/build_probe.sh simulator
python3 tools/check_shader_archives.py --build build/host --platform MACOS
python3 tools/check_shader_archives.py --build build/ios --platform IOS
python3 tools/check_shader_archives.py --build build/simulator --platform IOSSIMULATOR
```

Üç derlemeyi aynı anda çalıştırma; her biri iki iş ile sınırlı. İlk kurulum
SPIRV-Tools optimizer dahil yüzlerce C++ dosyası derler. Sonraki derlemeler
aynı SDK'nın çıktısını kullanır. İmzalama/cihaza kurulum kök README'deki gibi;
yeni uygulama raporu `Documents/shader-report.txt` yolundadır:

```sh
xcrun devicectl device copy from --device "$PROBE_DEVICE_ID" \
  --domain-type appDataContainer --domain-identifier dev.infamous2.iosprobe \
  --source Documents/shader-report.txt --destination out/step3-device-shader-report.txt
```

## Doğrulama

macOS kontrol grubu 6/6 geçti. Upstream shader çeviri testi **104 passed,
0 failed** raporladı. İki renderer yaşam döngüsünde clear kontrolü ve gerçek
sentetik shader çıktısı doğrulandı. `PS3RECOMP_METAL_FIXED_FUNCTION=1` negatif
kontrolünde draw reddedildi: siyah clear kaldı ve translated draw sayacı 0 oldu.
Böylece testin built-in passthrough ile yanlışlıkla geçmediği kontrol edildi.
Upstream'in önceki dört draw-engine test uyumsuzluğu değişmeden sürüyor;
regresyon karşılaştırması bunları açıkça raporlamaya devam eder.

Host bağımlılıklarının dokuz arşivindeki **245 object** için MACOS platform
kontrolü geçti. `out/step3-host-build.log`, `step3-host-archives.json` ve
`build/host/Testing/Temporary/LastTest.log` ayrıntıları tutar; Git dışındadır.

İmzalı iPhoneOS uygulaması derlendi ve iPhone'a yüklendi. İmza doğrulaması
geçti; Mach-O platformu IOS, minimum iOS 17.0, SDK 27.1. Son imzalama
çıktısındaki dokuz shader arşivinin **245 object** dosyasının tamamı IOS olarak
doğrulandı (`out/step3-ios-archives.json`). Bundle'da AppKit/Homebrew dylib'i yok;
üçüncü taraf lisans metinleri mevcut. İlk başlatma cihaz kilitli olduğu için
reddedilmişti. Kilit açıldıktan sonraki gerçek iPhone 15 Pro çalıştırması geçti:
üç clear ve üç çevrilmiş shader kontrolü birebir piksel eşleşmesi verdi;
her shader karesinde `translated_draws=1`. Kontrol noktasında 31 submission,
30 completion, 29 presentation, **0 hata** ve `shader_result=PASS` kaydedildi.
Cihaz `Apple A17 Pro GPU`, `simulator=0`, `MSL_target=iOS` bildirdi.
Rapor: `out/step3-device-shader-report.txt`. **Oyun karesi: 0.**

iOS Simulator SDK derlemesi de geçti. Simülatörün dokuz shader arşivindeki
245 object dosyası IOSSIMULATOR platformuyla doğrulandı; son Mach-O da aynı
platformu, minimum iOS 17.0 ve SDK 27.1'i bildiriyor.
`out/step3-simulator-build.log` ve `step3-simulator-archives.json` sonuçları
tutar. Bu sürüm simülatörde çalıştırılmadı; performans ölçümü yapılmadı.

## Sınır ve sonraki somut adım

Oyun girdileri hâlâ yok; `out/step3-input-check.json` eksik SFO/EBOOT/firmware
ve arşivleri raporluyor. NPUA80638 / APP_VER 01.03 yolları kök README'de.
Bu adım NV40 program çevirisini sınar; PPU/SPU kodu, gerçek oyun shader seti,
doku örneklemesi ve orijinal oyunun menü/ilk bölümü henüz yürütülmez.
Sentetik üçgenin 30 Hz sunumu oyun FPS'i değildir.

Sıradaki bağımsız adım `runtime/platform/win32_compat.c::os_region()` için
oyunun ihtiyaç duyduğu anlamı koruyan iOS VM adaptörü; ardından gerçek
thread/fiber ve context yollarının ayrı cihaz tanısıdır. SDL2'nin iOS kaynaktan
derlenmesi ve tam runtime bağlantısı bununla birlikte ilerletilebilir.
Oyun girdileri geldiğinde aynı pinlerle macOS referans boot'u ve iOS PPU/SPU +
FIFO/flip entegrasyonu yapılacak. Shader cache/ilk derleme gecikmesi ve
optimizasyon bütçesi gerçek iş yüküyle ölçülecek.

Kaynaklar: [glslang 15.1.0](https://github.com/KhronosGroup/glslang/tree/15.1.0),
[known_good.json](https://github.com/KhronosGroup/glslang/blob/15.1.0/known_good.json),
[SPIRV-Cross](https://github.com/KhronosGroup/SPIRV-Cross/tree/vulkan-sdk-1.4.304.0).
