# 2. adım — gerçek RSX Metal backend'ini iPhone yüzeyine bağlama

Bu belge ikinci adımın tarihsel sonucudur. Sonraki shader bağımlılıkları ve
sentetik program çizimi [3. adım notunda](step3-shaders-tr.md) tutulur;
aşağıdaki stub/eksik bağımlılık ifadeleri ikinci adımın yapılandırmasına aittir.

17 Ekim 2026. Önceki MTKView tanı üçgeninin yerini mevcut portun gerçek
**NV4097 dispatcher → rsx_draw_engine → rsx_metal_backend → CAMetalLayer**
yolu aldı. iPhone 15 Pro / iOS 27.2 üzerinde kırmızı, yeşil ve mavi temizleme
değerleri GPU'dan birebir geri okundu; backend completion ve drawable
presentation sayaçları ilerledi, Metal hatası görülmedi. **Oyun karesi hâlâ 0.**

## Değişiklikler

- `patches/ios-metal-surface.patch`: `NSWindow` yalnızca macOS'ta bildirilir.
  iOS'ta UIKit'in verdiği layer varsa ekrana, yoksa önceki gibi offscreen hedefe
  çizilir. macOS pencere ve headless yolları korunur.
- `src/platform/RSXMetalSurface.h`: `rsx_metal_backend_attach_ios_layer()`
  başlatmadan önce main thread'de çağrılır. Çalışan backend'e layer değişimi
  reddedilir. UIKit layer boyutunu yönetir; guest render target boyutu buna
  zorla yazılmaz. Shutdown layer referanslarını GPU işleri bittikten sonra bırakır.
- Aynı API'deki `rsx_metal_backend_ios_stats()` gerçek Metal submission,
  completion, presentation ve hata sayılarını atomik olarak okur. Bunlar guest
  draw/flip veya FPS sayacı değildir; oturumlar boyunca birikir.
- `src/ios/App.mm`: UIKit/UIScene ve özel `RSXMetalView` layer sahibidir.
  `viewDidLayoutSubviews()` yüzeyi bağlar; tek bir seri render kuyruğu bütün RSX
  durumunu yönetir. CADisplayLink en fazla bir CPU işi bekletir; backend'in
  mevcut GPU in-flight sınırı ayrıca korunur. Arka planda yeni CPU çizim işi
  kuyruğa alınmaz; daha önce alınmış en fazla bir iş tamamlanabilir.
- `src/common/RSXSmoke.c`: yalnızca tanı hedefinin 32 MiB sentetik belleği,
  basit cellGcm adres eşlemesi, nötr gamma ve boş input durumu vardır. Gerçek
  oyunun cellGcm, VFS, PPU/SPU veya firmware uygulaması yerine kullanılamaz.
  `rsx_smoke_present()` gerçek RSX clear yöntemlerini gönderir. Yalnızca ilk
  üç pixel kontrolünde `rsx_draw_engine_flush()` ile GPU beklenir; normal
  sunumda yeni bir per-frame wait/readback eklenmez.
- `CMakeLists.txt`: `rsx_core`, `rsx_metal`, `rsx_smoke_fixture` ayrı hedeflerdir.
  iOS hedefi AppKit veya Homebrew kütüphanesi bağlamaz. SDL2 ve guest shader
  çeviricisinin bağımlılıkları bu clear denemesine dahil edilmemiştir.
- Draw engine'in optional const-log bellek aramasındaki `mach_vm` kodu iOS'ta
  derlenmez; bu, tanı amaçlı okunabilir bölge taramasıdır. Ortak RSX işleme,
  senkronizasyon, writeback ve GPU light/SSAO kodu korunur. Tam runtime'daki
  `win32_compat.c::os_region()` iOS engeli hâlâ ayrı bir iştir.
- Mevcut backend'deki `++s_eng_slot_waits` ile aynı ifadede okuma ayrıldı;
  tanımlanmamış değerlendirme sırası kaldırıldı, sayaç mantığı korundu.

## Kaynakların korunması

`upstream/` değişmedi. `tools/prepare_renderer.py`, doğrulanan iki kaynak
dosyasının kopyasına yamayı uygular ve yalnızca `build/*/renderer-overlay/`
altına yazar. Kaynak ve yerel yama SHA-256 değerleri `sources.lock.json`
içindedir; uyuşmazlıkta derleme durur. `tools/setup_sources.py` ayrıca orijinal
fork + portun birleşik yamasının değişmediğini doğrular.

## Doğrulama

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
python3 tools/setup_sources.py
python3 tools/setup_sdl_sources.py # güncel tam runtime hedefi için
python3 tools/setup_context_sources.py # güncel runtime tanısı için
python3 tools/setup_shader_sources.py # güncel varsayılan build için
tools/build_probe.sh host
tools/build_probe.sh ios
tools/build_probe.sh simulator
```

Derlemeleri sırayla çalıştır; her biri 2 işle sınırlı. macOS Metal testleri
gerçek GPU erişimi ister. Ortam sandbox'ı GPU'ya erişimi engellerse
`no Metal device available` bir kaynak derleme hatası olarak yorumlanmamalı.

Host CTest kontrol grubu **4/4** geçti: önceki doku ve bellek/thread kontrolleri,
iki başlatma/kapatma çevriminde altı gerçek Metal pixel kontrolü ve yamasız/yamalı
draw-engine regresyon karşılaştırması. Sonuncusu, upstream'in bütün testlerinin
yeşil olduğu anlamına gelmez: sabitlenmiş fork'ta **dört mevcut beklenti
uyuşmazlığı** hem yamasız hem yamalı kaynakta aynı şekilde sürüyor:

- Yüzey boyutu/offset/context değişiminde eski target'ın release sayısı: 3 kontrol.
- Üç farklı vertex'in triangle-list draw'ında index kullanımı: 1 kontrol.

`tools/check_renderer_regression.py` bu tam listeyi ve exit code'u karşılaştırır;
başka bir hata gelirse testi başarısız yapar. Ham sonuçlar da çalıştırılabilir:

```sh
build/host/rsx_engine_tests_baseline  # mevcut 4 hata nedeniyle exit 1
build/host/rsx_engine_tests           # aynı 4 hata; yeni regresyon yok
```

Cihaz imzalama/kurulum komutları kök README'dekiyle aynı. Yeni raporu alma:

```sh
xcrun devicectl device copy from --device "$PROBE_DEVICE_ID" \
  --domain-type appDataContainer --domain-identifier dev.infamous2.iosprobe \
  --source Documents/renderer-report.txt --destination out/step2-device-renderer-report.txt
```

`out/step2-host-build.log`, `step2-ios-sign.log`, `step2-simulator-build.log`
ve cihaz raporları Git dışında saklanır. Simülatör SDK derlemesi doğrulandı;
simülatör performans ölçümü yapılmadı. Bağlanan Mach-O'nun platformu IOS;
AppKit veya macOS dylib'i yok. Cihaz `supportsBCTextureCompression=1` bildirdi;
bu oturumda gerçek oyunun BC dokuları henüz yüklenmedi.

Son cihaz raporu: üç renk kontrolü PASS; ilk kontrol noktasında 31 submission,
30 completion, 29 presentation, 0 hata. Ayarlar yalnızca açılarak uygulama arka
plana alındı, sonra tekrar öne getirildi. Rapor sırası `paused → resumed →
resume_verified` oldu; öne dönüş sonrasında completion sayısı 791'e ilerledi,
hata sayısı 0 kaldı. Bu toplam sayaçlardan oyun FPS'i çıkarılmaz. Ayarlarda
değişiklik yapılmadı ve tanı uygulaması tekrar önde bırakıldı.

## Optimizasyon hedefi ve sonraki iş

Sıkı optimizasyon hedefi kaydedildi. Önce doğru oyun görüntüsü ve davranış,
ardından ölçülmüş CPU/PPU, SPU, FIFO/semaphore bekleme, shader çevirisi, GPU,
bellek ve ısıl yük bütçeleri çıkarılacak. İlk değerlendirme bütçesi 30 FPS için
33,3 ms/kare; 60 FPS için 16,7 ms/kare. Bunlar hedef bütçelerdir, sonuç garantisi
değildir. Tanı uygulamasının 30 Hz sunumu oyun performansı sayılmaz.

M4 Pro'da bildirilen 20–27 FPS, iPhone'da ulaşılabilecek hız için tek başına
sınır değildir. Bu yeniden derleme yolunda orijinal Cell/SPU iş yükü, host çağrı
zincirleri ve senkronizasyon maliyetleri vardır; başka yerel iOS oyunlarıyla
görüntü yaşı/kalitesi üzerinden doğrudan FPS çıkarımı yapılamaz. İş parçacığı
bekleme zincirini ve gerçek kare sürelerini ölçmeden doğruluk düzeltmeleri
kaldırılmayacak veya stack boyutları körlemesine küçültülmeyecek.

Sıradaki bağımsız teknik adım: **glslang ve SPIRV-Cross'u iOS için kaynak koddan
derlemek ve `rsx_shader_msl.cpp` için iOS MSL hedefini seçmek**; ardından sentetik
bir NV40 vertex/fragment programını bu gerçek backend üzerinden çizip doğrulamak.
Şu anki build shader çeviricisinde açıkça stub kullanır; clear geçmesi guest
shader desteğinin hazır olduğunu göstermez. Tam runtime VM adaptörü ve SDL2
bağımlılığı bunun ardından entegre edilecek. Oyun girdileri hâlâ bekleniyor.
