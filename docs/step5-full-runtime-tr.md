# 5. adım — tam runtime derleme/bağlama ve sentetik PPU başlangıcı

Güncel GCM/Metal bağlantısı ve kapanış değişiklikleri: [6. adım](step6-gcm-tr.md).
Bu belge 5. adımda ölçülen durumu kaydeder.

Bu aşama orijinal oyunu veya firmware'i içermez. Genel runtime'ın tamamı ile
gerçek PPU yükleyicisi, HLE/NID köprüsü ve syscall yolları ayrı bir uygulamada
birleştirilir. Sentetik program lifter ABI'sinde elle yazılmış iki önceden
derlenen fonksiyondur; oyun kodu veya CPU JIT değildir.

## Hangi parçalar bağlandı?

- `cmake/SDLDependency.cmake`: SDL2 **release-2.32.10**,
  `5d249570393f7a37e037abf22cd6012a4cc56a71`, her SDK için kaynak koddan
  statik derlenir. `tools/setup_sdl_sources.py` commit/origin/yerel değişiklik
  kontrolü yapar. SDL2main bağlanmaz; UIApplicationMain ve scene sahipliği
  UIKit'tedir. Gerçek SDL input/audio backend'leri derlenir, dummy driver
  seçilmez. Lisans uygulama bildirimlerine eklendi.
- `cmake/FullRuntime.cmake`: sabit SDK'nın kaynak toplama kurallarını izleyen
  **159 kaynaklık** `ps3recomp_full_runtime` hedefi. Bütün HLE modülleri,
  syscall, bellek, SPU ve ATRAC standalone codec kaynakları dahil. SDK'nın
  kendi CMake dosyasındaki host `find_package`/pkg-config keşfi kullanılmaz.
  Önceki doğrulanmış renderer ve VM/fiber overlay'leri uygulanır. UIKit/Metal
  framework'leri iOS'a, AppKit yalnız macOS'a bağlanır. Codec'in LGPL metni ve
  kaynak kökeni `ThirdPartyNotices.txt` içine eklendi.
- `full_runtime_boot`: `ppu_loader.cpp`, `ppu_hle.cpp`, `ppu_fs.cpp`,
  `ppu_sysprx.cpp`, gerçek `gen_hle_nids.py --all` tablosu ve Clang musttail
  SPU dispatch dosyası. **OBJECT** hedefidir: NID tablosu arşiv içinde kalıp
  weak boş varsayılana düşmez. Entegrasyon executable'ında tam runtime arşivi
  `-force_load` ile alınır; iOS hedefinde dead-code stripping kapatılır.
  Böylece yalnız seçilmiş birkaç modülün bağlanması başarı sayılmaz.
- `src/full/FullRuntimeProbe.cpp`: portun aynı `calloc(0xE0000000)` yolu ve
  `ppu_vm_size` sınırı; gerçek ELF64 big-endian loader/OPD, PT_LOAD/BSS/TLS,
  `ppu_recomp_register()` → `ppu_run()` dispatch'i. `function_table` yalnızca
  açıkça sentetik entry ve worker fonksiyonlarını içerir.
- `entry()`: gerçek NID üzerinden `cellSysutilGetSystemParamInt` big-endian
  writeback, `/app_home/runtime-canary.bin` için gerçek PPU VFS open/read/close,
  HLE thread-create ve LV2 join/exit. Worker 64-bit argümanı ve başka host
  thread'de çalıştığını doğrular. Test dosyası yalnızca verilen özel VFS
  kökünde oluşturulur; Mac kökü geçici dizindir, iOS Documents içindedir.
- `src/ios/RuntimeApp.mm`: ayrı UIKit tanı kabuğu. Uzun PPU işi ana thread'de
  veya GCD'nin küçük varsayılan stack'inde çalışmaz; **256 MiB stack isteyen
  ayrı bir pthread** başlatılır, gerçek stack boyutu raporlanır. Kurulum
  başarısızsa küçük stack'e sessiz fallback yapılmaz. Her aşama
  `Documents/full-runtime-report.txt` içine kaydedilir.
  Önceki `Infamous2Probe` renderer hedefi korunur; yeni scheme
  **Infamous2FullRuntime** aynı bundle kimliğiyle cihazdaki tanıyı günceller.

## Testin yakaladığı ayrıntılar

İlk bağlantıda HLE kayıt sayısı 0 çıktı: weak `ppu_hle_register_all` gövdesi
statik arşivdeki gerçek tabloyu çekmiyordu. OBJECT hedefi bunu giderdi. HLE
writeback testi ayrıca önceden `0xFFFFFFFF` yazar; çözülmemiş bir HLE'nin
yalnızca 0 döndürüp belleği değiştirmemesi başarı sayılmaz.

Fork'un eski smoke örneği thread-create için syscall 41 yazıyordu. Bu pin'de
41 **exit**, 52 raw create'dir; raw create ayrıca parametre bloğu bekler.
Deneme güncel `sys_ppu_thread.h` / `lv2_syscall_table.h` sabitlerini ve
`ppu_sysprx.cpp::hle_ppu_thread_create()` NID yolunu kullanır. Runtime'ı eski
örneğe uydurmak için syscall anlamları değiştirilmedi.

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

Derlemeler sırayla ve **2 iş** ile yapılır. SDL'nin ilk yapılandırması çok
sayıda SDK derleme kontrolü çalıştırır. Sandbox'ın Xcode servislerini engellemesi
başlıkları yanlışlıkla "yok" gösterebilir; bu oturumdaki böyle bir denemenin
önbelleği ayrıldı ve izinli ortamda yeniden oluşturuldu. Bu durum SDK'da
`ctype.h` olmadığı anlamına gelmez. Normal Terminal/Xcode kullanımı için özel
bir sistem ayarı yapılmadı.

İmzalamada kök README'deki komutta scheme'i `Infamous2FullRuntime`, kurulum
yolunu `build/ios/Release-iphoneos/Infamous2FullRuntime.app` seçin. Çalıştırılacak
bundle kimliği aynı: `dev.infamous2.iosprobe`.

```sh
xcrun devicectl device copy from --device "$PROBE_DEVICE_ID" \
  --domain-type appDataContainer --domain-identifier dev.infamous2.iosprobe \
  --source Documents/full-runtime-report.txt --destination out/step5-device-full-runtime-report.txt
python3 tools/check_shader_archives.py --build build/ios --platform IOS \
  --include-runtime --include-full-runtime
```

## Doğrulama

Mac kontrol grubu **9/9** geçti. Tam bağlantıda **1192 HLE kaydı**; ELF,
TLS/BSS/argv, gerçek VFS, PPU worker argümanı/dispatch/join ve SDL controller
backend başlangıcı geçti. Önceki shader/fiber/renderer regresyon kontrolleri
korundu. Bilinen dört upstream draw-engine beklenti uyumsuzluğu önceki gibi
açık karşılaştırma testinde izlenir; ham testlerin hepsinin yeşil olduğu
iddia edilmez. Host'ta 14 arşiv/597 object için MACOS platformu doğrulandı.

Loglar `out/step5-host-build.log`, `step5-host-archives.json` ve CTest'in
`build/host/Testing/Temporary/LastTest.log` dosyasında, Git dışındadır.

Gerçek **iPhone 15 Pro / iOS 27.2** çalıştırması da geçti: **17 kontrol,
0 hata, `full_runtime_result=PASS`**. 1192 HLE kaydı, gerçek ELF/TLS, VFS ve
PPU thread-create/exit/join yolları doğrulandı. Ana PPU host thread'i
268.435.456 bayt stack istedi, 268.447.744 bayt bildirdi (+12 KiB).
SDL 2.32.10 controller backend başlangıcı başarılı; bir joystick kaydı
raporladı. Bu sayı fiziksel kontrolcü veya doğru tuş eşlemesi kanıtı değildir.

3,5 GiB calloc sonrası sanal boyut tam **3584 MiB** arttı. Fiziksel footprint
başlangıçta/calloc sonrasında yaklaşık **8,3 MiB**, sentetik PPU sonrasında
**14,7 MiB** idi; anlık örnekler küçük dalgalanmalar gösterebilir. Büyük stack
rezervasyonunun tamamına yazılmadı. Gerçek oyun bellek tüketimi çıkarılamaz.
Rapor: `out/step5-device-full-runtime-report.txt`.

iPhoneOS derleme/bağlama/imza geçti; uygulama cihaza kurulup çalıştırıldı.
Mach-O platformu IOS, minimum sürüm 17.0, SDK 27.1. Shader/runtime/fiber/SDL
dahil **14 arşiv / 598 object** IOS platformuyla doğrulandı. Son bundle'ın
imzası ve lisans metni kontrol edildi; AppKit veya Homebrew dylib'i yok.
Derleme logları `out/step5-ios-sign.log`, `step5-ios-final-sign.log`,
arşiv raporu `step5-ios-archives.json` içinde.

Simulator SDK derlemesi de geçti. Ayrı uygulamanın Mach-O platformu
IOSSIMULATOR; **14 arşiv / 598 object** aynı platformla doğrulandı. Ayrıca
PPU boot hedefinin 7 object'i her SDK'da ayrı derlendi. Simülatörde uygulama
çalıştırılmadı ve performans ölçülmedi. Log/rapor:
`out/step5-simulator-build.log`, `step5-simulator-archives.json`.

## Sınırlar

- Bu uygulama Metal görünümü veya oyun karesi üretmez. Önceki renderer
  hedefinin shader başarısı ayrı ölçüttür. **Oyun karesi 0.**
- Gerçek oyunun üretilmiş PPU/SPU ve firmware kodu henüz yok. SPU runtime ve
  musttail dispatch derlenip bağlanır; bu test SPURS/gerçek SPU iş yükü çalıştırmaz.
- Oyunun GPU light/SSAO dosyaları değiştirilmedi; üç dosyanın iPhoneOS syntax
  kontrolü geçti (`out/step5-title-gpu-ios-syntax.log`). Bu, gerçek shader/iş
  verisiyle doğrulandıkları veya bu sentetik hedefte etkin oldukları anlamına gelmez.
- SDL controller backend başlangıcı dokunmatik/fiziksel kontrolcü eşlemesi
  değildir. Ses backend'i bağlandı; ses çıkışı/kayıt desteği henüz sınanmadı.
- Tek çalışımlık tanı, kayıtlı guest/context referansları nedeniyle arena'yı
  sonuç ekranında tutar. Tam oyun shutdown/restart/arka plan protokolü ayrı
  entegrasyondur. `ppu_run()` dönüşünden sonra guest yürütme yeniden başlatılmaz;
  ikinci çağrı reddedilir. Registry/context temizliği henüz uygulanmadı.
  Büyük sanal rezervasyon fiziksel RAM kullanımı değildir;
  log ikisini ayrı raporlar. Performans sonucu çıkarılmaz.
- Guest 4 KiB/host 16 KiB koruma semantiği, tüm VM exec/fault yolları, cihaz
  ısınması ve gerçek oyun davranışı henüz doğrulanmadı.

Sonraki eşik doğru NPUA80638 / APP_VER 01.03 ve kullanıcının firmware
girdileriyle aynı pin'de macOS referans boot'u; ardından iOS scene kabuğunda
gerçek PPU/SPU ve cellGcm FIFO/flip entegrasyonu. Girdiler olmadan ilerleyebilen
sonraki bağımsız çalışma, bu tam runtime hedefindeki sentetik PPU programını
gerçek cellGcm → Metal sunumuyla birleştirmek ve shutdown protokolünü kurmaktır.

Kaynak: [SDL2 2.32.10](https://github.com/libsdl-org/SDL/tree/release-2.32.10).
