# Tile alpha düzeltmesi — 25 Ekim 2026

## Değişen davranış

Özgün C6 SPU işinde LS 0x4AC8, hiç ışık seçilmeyen veya tamamen sky olan
32×40 tile'ı sıfırlar. Işık seçilen tile'da, RGB'si sıfır olan piksellerde bile
diffuse RGBM alpha tabanı 90'dır. Bu seçim N·L veya ışığın rengi değildir.
`eng_light_fs` önceden bu tile ayrımını yapmıyordu; boş tile'da alpha 90 üretiyordu.

`src/platform/LightingCulling.metal:bces_light_tile_mask` tile başına bir maske
üretir. `LightingRZ.metal:bgrid/bposition/bmember`, özgün SPU'nun konum
rekonstrüksiyonunu, yuvarlamasını, reciprocal tablolarını ve point/spot üyeliğini
kullanır. `tools/light_shader_culling.py:patch` aynı maskeyi hem renderer'a hem
referans replay'e bağlar. Fragment shader reddedilen tile'ı sıfırlar; kabul
edilen tile'ın sky/karanlık pikselindeki alpha tabanını korur. RGB==0 testi yok.

Özgün kaba frustum/AABB/cone testleri tek tek taşınmadı; gerçek piksel üyeliği
kullanılıyor. Olağan geometrik eşdeğerlik test edildi, bütün olası oyun girdileri
üzerinde kanıtlanmadı. SPU genişletilmiş float işlemleri bit düzeyinde testlidir;
spot predicate'in son karşılaştırmaları hâlâ Metal float karşılaştırmasıdır.

`prepare_metal_lighting.py:prepare_renderer`, maskeyi lighting render pass'inden
önce aynı command buffer'a encode eder. 8 kalıcı maske buffer'ı ve compute PSO
SPU işi atlanmadan önce hazırlanır. Yeni CPU readback veya bekleme eklenmedi.
Pinned runtime/port kaynakları değiştirilmez; build altındaki overlay üretilir.
SSAO özgün SPU yolunda kalır.

## Gerçekten yapılan kontroller

- Özgün üretilmiş C6 kodu macOS'ta O2 ile bağımsız harness'e bağlandı
  (`tools/lighting_spu_fixture.c`). Üç gerçek cihaz tile'ında diffuse/specular
  sonuçları cihazın özgün SPU çıktılarıyla bit düzeyinde aynı.
- Aynı gerçek tile geometrisine sentetik ışıklar konarak dokuz senaryo üretildi:
  point/spot aydınlık, ters normal, siyah ışık, uzak ışık, ters spot, sıfır ışık,
  tümü sky ve karışık sky. Referans çıktıları özgün SPU harness'inden gelir.
- 64 deterministik rastgele point/spot senaryosu ve 18 teğet sınır senaryosu
  geçti. İlk basit float classifier iki teğet testi kaçırdı; SPU uyumlu konum
  ve RZ işlemlerine geçilince 18/18 geçti.
- Mac GPU'da 16.384 add/mul/fma/FREST+FI bit karşılaştırması geçti; rastgele
  genişletilmiş exponent/denormal girdileri de kapsanıyor.
- Build 30 iPhoneOS Release `-jobs 1` derlendi, imzalandı, iPhone'a kuruldu.
  UUID `E0E88905-84EF-30A1-B35F-AF8297BFBDD8`.
- Gerçek A17 Pro'da 16 sınırlı fixture replay'i tamamlandı. Hedef diffuse
  alpha farkı hepsinde sıfır. Üç gerçek boş tile, dört sınır testi ve karanlık/
  elenen senaryoların iki çıktısı bit düzeyinde aynı. Sentetik aydınlık point,
  spot ve mixed-sky senaryolarında RGB/specular'da en fazla 1 byte-seviye fark
  kaldı; specular alpha da buna dahil. Bu tüm sahneler için ±1 garantisi değildir.

Gerçek oyundan yakalanan üç tile'ın özgün çıktıları sıfırdır. Sıfırdan farklı
aydınlık referanslar sentetik ışıklı testlerdir; gerçek ışıklı oyun tile'ı veya
tam kare eşdeğerliği doğrulanmış gibi sunulamaz.

Kanıtlar (Git dışında): `out/lighting-cull-A17-report.json`,
`out/lighting-cull-rz-stress/summary.json`, `out/lighting-cull-rz-results.json`,
`out/lighting-cull-rz-device-build.log`, `out/lighting-cull-binary.json`.

## Sinematik donması: kabul hâlâ açık

Build 30 normal oyun PID 13215 sinematikte dondu, ardından kapandı. Son raporda
2572 guest frame, 2576 Metal submitted/completed/presented, 0 Metal hatası,
0 lighting fault, thermal normal, footprint yaklaşık 862 MB vardı. Tamamlanan
Metal işleri donmanın GPU hatası olduğunu göstermiyor; kesin neden açık.

`out/lighting-cull-hang-runtime-retry.log` içinde self-JUMP 0x15270'te
`FIFO resync (jump-park) -> put 0x11058` ve bir kurtarılan fence var.
Pinned `cellGcmSys.c` ve port ROADMAP bu timeout kurtarmasının, inFAMOUS'un
henüz bağlamadığı komut segmentlerini atlayıp beklemeleri bozabileceğini belirtir.
Mevcut usleep callback pump düzeltmesi zaten pinned kaynakta vardır; tekrar
eklenmedi. iOS overlay'de sadece self-JUMP timeout'unda komut atlama kaldırıldı:
`tools/prepare_frame_diagnostics.py:prepare`. Donanım gibi parkın patch'lenmesi
beklenir, en fazla 64 uzun bekleme kaydı yazılır. Diğer FIFO kurtarmaları korunur.
Bu düzeltme tek başına başka bir kilidi çözmez; park patch'lenmezse bekleme
sürer. O nedenle tek resync kaydı kök neden kanıtı sayılmaz, cihaz tekrarı gerekir.

LLDB denemesi process'e bağlanamadı; stack alınamadı. Alınan frame-trace dosyası
eski build UUID/token'ına aitti, bu donmanın ölçümü olarak kullanılmaz.
Kapanış saatinde yeni Infamous crash/Jetsam raporu bulunamadı; dosya servisinin
çökme raporu uygulamanın raporu değildir. Sonlandırma nedeni henüz bilinmiyor.

## Tekrar üretim

```sh
python3 tools/prepare_bces_ios.py --support-report out/bces-support-compile-iphoneos-spu-O2-copy.json
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer /opt/homebrew/bin/cmake -S cmake/bces-ios -B build/bces01229/ios
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp xcodebuild -project build/bces01229/ios/Infamous2BCESIOS.xcodeproj -scheme Infamous2Game -configuration Release -destination id=00008130-001129E00243001C -jobs 1 DEVELOPMENT_TEAM=BJ266NGN3H -allowProvisioningUpdates
build/bces01229/lighting-rz-test
python3 tools/test_lighting_culling.py --output out/UNIQUE-mask-stress --count 64
# Hazır 16 fixture Documents/lighting-test-fixtures'e konduktan sonra:
# devicectl ... process launch ... dev.infamous2.iosprobe --validate-only --replay-lighting-fixtures
```

Alpha düzeltmesinin gerçek oynanış FPS maliyeti henüz ölçülmedi. Önceki 3,97→4,97
FPS pilotu maskesiz binary'ye aittir; build 30/31 sonucuna taşınamaz. Önce
sinematik/oynanış kararlılığı, sonra aynı normal sıcaklık ve sabit kamera FPS,
maske GPU maliyeti ve gerçek aydınlık tile doğrulaması; ardından SSAO.

Build 31 iPhoneOS Release derlemesi ve üzerine kurulum tamamlandı. UUID
`C718184F-42AB-3D54-B885-575BEB0A52E2`. İlk açılışta 779 guest frame ve
105 Metal lighting pass ilerledi; bu oynanış/kararlılık kabulü değildir.

Kullanıcı build 31 ile ilk oynanışa ulaştığını, kamerayı sabit bıraktığını ve
görünür ışık farkı görmediğini teyit etti. Çizgi roman boyunca yaklaşık 30 FPS
gözledi; bu kullanıcı gözlemidir, kontrollü FPS kaydı değildir. Bir başarılı
geçiş, sinematik donmasının kalıcı çözüldüğünü tek başına kanıtlamaz.

## Build 31 cihaz sonucu

`out/lighting-cull-park-gameplay-window/summary.json`: kullanıcı teyitli ilk
oynanış, sabit kamera, PID 13336. 32,000631 saniyede 155 guest frame ve 155 gerçek
Metal present: **4,843654 FPS**. 11 örneğin tamamı thermal normal, yeni pipeline
0; footprint 963366288–967495056 byte. Lighting fault/Metal error sıfır.

Ayrı 10 s trace doğru build 31 UUID ve `lightcull31gameplay` token'ını taşıyor;
104701 olay, düşen kayıt 0. 46 tam iç karede medyan 200,960 ms, p95 230,000 ms.
GPU execution union medyanı 51,983 ms/kare. 64 acquire'ın 64'ü kaydedilmiş label
DMA yazısıyla tek eşleşti. 0x870 union bekleme medyanı 0; 34/46 karede bu bekleme
yok. 0x890 medyanı 67,5585 ms/kare; bütün karelerde bekleme var. Bu SSAO job'unun
süresi değildir, RSX'in üretici etiketini beklediği duvar süresidir.

Önceki maskesiz Metal pilotu 4,968676 FPS, kare medyanı 196,975 ms ve GPU union
48,198 ms idi. Aradaki ~%2,5 FPS / ~3,8 ms GPU union farkı farklı açılışlarda
ölçüldü; doğrudan maskenin maliyeti veya istatistiksel regresyon sayılmaz.
Yeni classifier'ın GPU süresi tek başına timestamp ile izole edilmedi.
Tüm command buffer'ların union süresini maske maliyeti olarak sunmuyoruz.
Önceki SPU 3,968688 FPS de aynı oturumun eşlenmiş kontrolü değildir.

Build 31 bu koşuda önceki sinematik donmasını geçti ve oynanış ölçümlerini
kararlı tamamladı. Self-JUMP değişikliği için tekrar açılış/uzun oyun testi açık;
tek başarılı koşu kalıcı kararlılık veya kök neden kanıtı değildir. Genel tam kare
ve gerçek nonzero lit tile eşdeğerliği de açık kalır. Bununla birlikte hedef
alpha hatası sınırlı A17 testlerinde giderildi, kullanıcı görsel fark görmedi,
oynanışa ulaşıldı ve ölçüm yapıldı. SSAO hâlâ değiştirilmedi.

Birleşik özet: `out/lighting-cull-park-result.json`; ham iz ve analizler
`out/lighting-cull-park-gameplay-trace*`, `out/lighting-cull-park-gameplay-dependencies.json`.
