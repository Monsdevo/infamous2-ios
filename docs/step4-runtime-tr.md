# 4. adım — iOS VM sorgusu, gerçek thread ve cellFiber denemesi

Bu aşama tam oyun runtime'ını başlatmaz. Sabitlenmiş runtime'ın gerçek
`win32_compat.c` ve `cellFiber.c` dosyalarını küçük, oyun girdisinden bağımsız
bir tanıda derler. Shader aşamasının gerçek iPhone sonucu da tamamlandı:
[3. adım](step3-shaders-tr.md), üç shader/üç clear PASS, Metal hatası 0,
oyun karesi 0.

## Değişiklik ve gerekçe

- `patches/ios-runtime-vm.patch`: `os_region()` iOS'ta SDK'nın sunduğu
  `<mach/vm_map.h>` / `vm_region_64()` yolunu kullanır. `vm_address_t` ve
  `uintptr_t` genişliği compile-time kontrol edilir; yüksek host adresleri
  32 bite kırpılmaz. macOS `mach_vm_region()` yolu korunur. Dönen bölge,
  koruma, boşluk/sonraki eşleme ve object-name portunu bırakma mantığı aynıdır.
  Bu, kendi sürecinin sorgusudur; private symbol bildirimi eklenmez.
- `tools/prepare_runtime.py`: kaynak/yama SHA-256 değerlerini
  `sources.lock.json` ile doğrular, yalnızca `build/*/runtime-overlay/` içine
  yazar. `cellFiber.c` için yalnız iOS context mekanizmasını seçen dallar eklenir;
  fiber durumları, guest adres/endian işlemleri ve 64 KiB stack varsayılanı
  korunur. macOS/Windows mekanizmaları ve orijinal port/fork kaynakları korunur.
- `src/platform/IOSFiberContext.c`: iOS'a özel kooperatif context adaptörü.
  Boost.Context **boost-1.88.0 / afd2ce33722e223d75723f3b44dc9fa94302e764**
  sürümünün değiştirilmemiş `make_arm64_aapcs_macho_gas.S` ve
  `jump_arm64_aapcs_macho_gas.S` dosyaları SDK'ya ayrı derlenir. Yeni stack'e
  giriş ve geri dönüşte transfer'in döndürdüğü önceki context handle'ı
  kaydedilir; A → B doğrudan geçişi scheduler context'ini ezmez. `setcontext`
  karşılığı terminal fiber'den scheduler'a döner. Yeni CPU kodu üretilmez.
  `tools/setup_context_sources.py` commit/origin ve kaynak temizliğini kontrol
  eder; Boost'un C++ bağımlılık zinciri veya binary paketi bağlanmaz. Boost
  lisansı uygulamanın `ThirdPartyNotices.txt` kaynağına eklendi.
- `CMakeLists.txt`: `runtime_platform` gerçek platform kodudur.
  `runtime_probe_fixture` bunun etrafındaki tanıdır; gelecekteki oyun hedefine
  eklenmemelidir. iOS/macOS aynı kaynakları kendi SDK'sıyla ayrı derler.
- `src/common/RuntimeProbe.c::virtual_memory()`: üç host sayfası reserve,
  yalnızca ortayı commit, okuma/yazma, read-only koruma, decommit, release ve
  `VirtualQuery` sonuçlarını sınar. Komşu guard bölgelerin değişmediğini ve
  sınırı aşan aralıkların erişilebilir sayılmadığını denetler. Shim tablosuna
  kayıtlı olmayan heap/stack/text eşlemeleri de sorgulanır; yalnızca kayıt
  tablosuna bakıp başarı verme ihtimali dışlanır.
- `threads()`: mevcut `CreateThread()` ile sırasıyla 16 ve 256 MiB host stack,
  CREATE_SUSPENDED kapısı, çalışma sırasında Mach suspend, aynı context'i
  okuma/yazma, iç içe suspend/resume ve gerçek çıkış kodu/join beklemesi sınanır.
  Durdurulan worker yalnızca lock-free atomik döngü çalıştırır; malloc veya
  başka thread'in bekleyeceği bir kilit tutmaz. Stack raporu istenenden küçük
  olmamalıdır; tam eşitlik aranmaz. Mac ve iPhone'da ek 12 KiB raporlandı.
- `fiber_round()`: gerçek `cellFiberPpu*` fonksiyonlarıyla scheduler'a yield
  ve fiber'den fiber'e doğrudan geçiş ayrı sınanır. Her düzende iki fiber'in
  her biri 4000 kez çalışır. 64-bit giriş argümanları, sıra ve stack canary'leri
  korunmalıdır. Son dönüşte trampoline'in `setcontext()` yolu, TERMINATED
  durumu, delete ve finalize da doğrulanır.
- `src/common/RuntimeProbeMemory.c`: fiber HLE'sinin guest big-endian
  erişimleri için ayrı 1 MiB sentetik alan ve pasif coherence/watch hook'ları.
  `vm_base` yalnız bu hedefte `runtime_probe_vm_base` olarak adlandırılır;
  RSX tanısının belleğini ezmez. Bu fixture gerçek PPU/SPU coherence değildir.
- `src/ios/App.mm::appendRuntime()`: shader kontrolünden sonra seri render
  kuyruğunda tanıyı çalıştırır; UIKit ana thread'i test çalıştırmaz. Her aşama
  satırı main thread'de atomik dosya yazımıyla `Documents/runtime-report.txt`
  içine kaydedilir; context primitifinde crash olursa son aşama korunur.

CPU JIT, PROT_EXEC eşlemesi veya executable-memory yetkisi eklenmedi.
Mevcut SPU/RSX senkronizasyonu ve oyuna özel light/SSAO yamaları değişmedi.

## Tekrar üretme

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
python3 tools/setup_sources.py
python3 tools/setup_sdl_sources.py # güncel tam runtime hedefi için
python3 tools/setup_shader_sources.py
python3 tools/setup_context_sources.py
tools/build_probe.sh host
tools/build_probe.sh ios
tools/build_probe.sh simulator
```

SDK derlemelerini sırayla çalıştır; her biri 2 işle sınırlı. İmzalama/kurulum
kök README'deki gibi yapılır. Zaten yapılandırılmış projede doğrudan imzalı
`xcodebuild` yapmak, ayrı imzasız/sonra imzalı derleme tekrarını önleyebilir.
Uygulama aynı `dev.infamous2.iosprobe` kimliğini kullanır; başka uygulama
kaldırılmaz. Cihazdan yeni rapor:

```sh
xcrun devicectl device copy from --device "$PROBE_DEVICE_ID" \
  --domain-type appDataContainer --domain-identifier dev.infamous2.iosprobe \
  --source Documents/runtime-report.txt --destination out/step4-device-runtime-report.txt
```

## Doğrulama

İlk iPhone testinde VM/thread/context geçti fakat gerçek fiber girişleri
**0** kaldı; ilk hata raporu `out/step4-device-native-fiber-failure.txt` içinde.
`ContextSupport.c` ile ayrı ölçüm nedeni doğruladı: native `getcontext()`
`-1`, `errno=45 (ENOTSUP)` döndürdü, fiber girişi gerçekleşmedi. Upstream'in
bu çağrıların dönüşünü denetlememesi dış API'de sahte başarı üretiyordu.
`out/step4-device-ucontext-report.txt` bu ham tanıyı tutar. iOS fcontext
seçildiğinde native ucontext sonucu tanısal olarak hâlâ raporlanır; seçilen
backend'in gerçek fiber/argüman/stack kontrolleri başarı için zorunludur.

Son macOS CTest grubu **8/8** geçti. Özgün ucontext yolu 8092, ek olarak
zorlanan iOS fcontext yolu 8091 kontrol/0 hata raporladı.
Bu sayı çoğunlukla fiber API dönüş kontrolleridir;
8091 ayrı sistem özelliğinin test edildiği anlamına gelmez. Önceki shader,
renderer, doku ve bellek kontrolleri de geçti. Upstream'in bilinen dört
draw-engine beklenti uyumsuzluğu değişmedi; karşılaştırma testi bunları açıkça
raporlar ([2. adım](step2-renderer-tr.md)).

iPhoneOS imzalı derleme ve Simulator SDK derlemesi geçti. Gerçek iPhone 15 Pro
çalıştırması **runtime_result=PASS / failures=0** verdi. VM reserve/commit,
koruma ve sorguları; iki thread stack boyutu; suspend/resume ve aynı context
okuma/yazma; iki fiber düzeni geçti. Fiber başına 4000 çalışmada argüman,
stack ve sıra hataları **0** oldu. Yeni uygulama raporu
`out/step4-device-runtime-report.txt` içinde. Native ucontext'in ENOTSUP çıktısı
aynı raporda korunur; seçilen backend açıkça `boost_fcontext` olarak yazılır.

Üç platformda shader/runtime/fiber dahil **12 arşiv / 253 object** doğru Mach-O
platformuyla doğrulandı (`out/step4-{host,ios,simulator}-archives.json`). Kontrol:

```sh
python3 tools/check_shader_archives.py --build build/host --platform MACOS --include-runtime
python3 tools/check_shader_archives.py --build build/ios --platform IOS --include-runtime
python3 tools/check_shader_archives.py --build build/simulator --platform IOSSIMULATOR --include-runtime
```

Simulator SDK yalnız derlendi; bu sürüm simülatörde çalıştırılmadı veya
performans ölçülmedi. iOS imzası ve lisans kaynaklarının bundle'a girmesi
doğrulandı; AppKit/Homebrew dylib'i yok. Loglar `out/step4-host-build.log`,
`step4-ios-sign.log`, `step4-simulator-build.log` altında, Git dışındadır.

Son cihaz shader raporu da PASS kaldı. Ayarlar yalnızca açılarak uygulama
arka plana alındı, ardından aynı uygulama tekrar öne getirildi. Rapor sırası
`paused → resumed → resume_verified` oldu; dönüş sonrasında completion 1014'e
ilerledi, Metal hatası **0** kaldı. Ayarlarda değişiklik yapılmadı. Raporlar
`out/step4-device-paused-report.txt` ve `step4-device-shader-report.txt` içinde.
Bu sayaçlardan oyun FPS'i çıkarılmaz.

## Sınırlar ve sonraki adım

- VM kontrolü host'un 16 KiB sayfa sınırındadır. Guest'in 4 KiB sayfasını
  bağımsız koruma, guest VM'nin PROT_EXEC talepleri, tüm fault/VEH recovery
  yolları ve gerçek oyun erişim örüntüsü henüz doğrulanmadı. Genel koruma
  davranışı bu küçük yama içinde değiştirilmedi.
- Thread testi kendi worker'ının aynı context'ini geri yazar. Keyfi PC/stack
  yönlendirme, tüm SIMD/FP register'ları veya diğer runtime watchdog/recovery
  yolları için kapsamlı kanıt değildir. Büyük stack rezervasyonu, o kadar
  fiziksel RAM tüketildiği veya oyunun derin çağrı zincirinin sığdığı anlamına
  gelmez; bu aşama stack küçültmez veya bellek kapasitesi ölçümü yapmaz.
- macOS cellFiber upstream'in ucontext yolunu kullanır; iOS arm64 fcontext
  kullanır. arm64e hedefi bilerek desteklenmez. Testler tek host thread içinde
  koşar; upstream global fiber scheduler'ın çoklu PPU thread kullanımı,
  signal mask/fenv bağımsızlığı veya gerçek guest SPURS scheduling'i sınanmadı.
- Henüz tam runtime, SDL2, PPU/SPU oyun kodu, ses, kayıt veya giriş bağlantısı
  yok. Oyun karesi **0**; sentetik tanı oyun performansı değildir.

Sıradaki bağımsız iş SDL2'yi sabit kaynak sürümüyle iOS'a derlemek ve tam
runtime hedefinin derleme/bağlama engellerini kaldırmak. Guest VM korumaları,
dosya yolları ve iOS yaşam döngüsü bu entegrasyonda açıkça ele alınacak.
Oyun/firmware girdileri geldiğinde aynı pinlerle macOS referans boot'u ve
ardından gerçek iOS PPU/SPU → FIFO/flip entegrasyonu yapılacak.

API kaynağı: [Apple vm_region_64](https://developer.apple.com/documentation/kernel/1585386-vm_region_64).
Kullanılabilirlik ayrıca yerel iPhoneOS 27.1 SDK'sındaki `mach/vm_map.h` ve
`mach/arm/vm_types.h` üzerinden derleme sırasında doğrulandı.

Fiber kaynağı: [Boost.Context 1.88 ARM64 Mach-O](https://github.com/boostorg/context/tree/boost-1.88.0/src/asm).
