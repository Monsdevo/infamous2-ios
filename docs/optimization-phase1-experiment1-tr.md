# Aşama 1 / Deneme 1 — ilk uygulama paketi

25 Ekim 2026. Build 26. **Aydınlatma hızlandırması henüz etkin değil.**
Bu paket planın referans yakalama ve Metal karşılaştırma altyapısını uygular.
SSAO ve ekranda kullanılan aydınlatma özgün SPU yolundadır. FPS kazancı iddiası yok.

## Uygulanan değişiklik

- `tools/prepare_lighting_validation.py`, doğrulanmış BCES c6e7 kaynak kopyasında
  0x6728'deki tile callback çağrısının çevresine before/after ekler. Özgün
  `spu_indirect_branch → spu_drain_call(0x6730)` ve register/state akışı aynen
  korunur; fazladan drain, tile skip veya sahte label yok.
- Yalnız bu derleme birimi destek arşivinin türetilmiş kopyasından çıkarılıp
  `lighting_spu_reference.c` olarak aynı O2/float seçenekleriyle derlenir.
  Doğrulanmış özgün destek arşivi ve generated kaynak değişmez.
- `LightingTile.h`: LS parametre/descriptor/tile/ışık/buffer sınırları kontrol
  edilir; bilinmeyen layout ve >128 ışık reddedilir, sessiz kırpma yapılmaz.
- `LightingValidation.mm`: en fazla üç farklı tile (sol üst, orta, sağ alt)
  için 256 KiB LS önce/sonra ve register girdisi alınır. Bunlar aynı drained
  callback'in iki yanıdır; ayrı kareler birbirine referans yapılmaz.
- Girdiler ayrı serial utility kuyruğunda Metal ile karşılaştırılır. Oyunun
  komut kuyruğuna yeni GPU wait veya shader sonucu bağlanmaz. Diagnostic kuyrukta
  readback için wait vardır; bunun zamanı oyun performansı değildir.
- Shader, pinned backend'in `eng_light_fs` metninden çıkarılır. Yalnız küçük
  texture içinde tam ekran tile koordinatını koruyan origin adaptörü ve vertex
  giriş noktası eklenir. Fast math kapalıdır. Bu seçenek gelecekte gerçek GPU
  yolunda da ayrıca doğrulanmalıdır; mevcut oyun yolunu doğruladık denmez.
- Big-endian/half frame+light parametreleri aktarılır; ARGB tile girdi/çıktıları
  Metal RGBA ile karşılaştırılır. Diffuse/specular için değişen byte sayısı,
  max/ortalama hata ve bit eşitliği raporlanır. Fark olsa da SPU sonucu korunur.
- GameApp varsayılan olarak üç örneklik karşılaştırmayı kurar; `--no-light-validation`
  yalnız referans çalıştırma için kapatır. Tamamlandıktan sonra yeni capture alınmaz.
  Report'ta `lighting_validation_completed` ve açık SPU mod etiketi vardır.

## Sınır

Bu, bütün ekranın GPU ışıklandırmasına geçiş değildir. Buffer EA/IO eşlemesi,
aynı frame generation'a ait bütün ekran, tile walk skip state'i ve gerçek
oynanış görüntü doğruluğu henüz kabul edilmiş değil. Bu nedenle LIGHT/SSAO env
ayarları boş kalır. Üç tile bit-exact çıksa bile tek başına tam-frame kabul sayılmaz.
İlk üç örnek menü/sinematikte de oluşabilir; oynanış ölçümü diye etiketlenmez.

Örneklerin ilk toplanması ve shader karşılaştırması ek iş yükü getirir; bu süreçteki
FPS değerleri optimizasyon sonucu değildir. Sonradan kullanıcı yaklaşık FPS
bildirebilir, ancak B modu henüz olmadığı için A/B kazancı çıkarılamaz.

## Testler

- Tile decode/bounds: 1280x720 layout, yanlış koordinat, fazla ışık, taşan LS
  aralığı kontrolleri PASS.
- Mevcut frame/dependency analiz testleri 4/4 PASS.
- iPhoneOS Release, `-jobs 1` BUILD SUCCEEDED; imza strict doğrulandı.
- Mac M3 GPU'sunda sentetik sky/zero-output pipeline smoke PASS: iki buffer'da
  5120'şer byte bit-exact. Bu test yalnız shader derleme, GPU yürütme, readback
  ve karşılaştırma hattını kontrol eder; gerçek ışıklı görüntü doğruluğu veya
  iPhone performansı kanıtı değildir.
- CLI offline `metal` derlemesi mevcut olmayan Metal Toolchain nedeniyle
  yapılamadı; ek bileşen indirilmedi. Metal runtime shader derlemesi Mac'te
  yukarıdaki smoke ile geçti. Gerçek A17 Pro çıktısı capture sonrasında incelenecek.

## Cihaz çıktıları / devam

Aynı bundle üstüne update oyun verilerini korur. Otomatik kapanış yok. Açılış:
`--boot --spu-copy-off` (CPU sampler/frame trace bu launch'ta açılmaz).

`Documents/lighting-validation/report.json`: yalnız geçerli oturumun özeti.
Her açılış için ayrı UUID fixture dizini açılır; henüz örnek yokken rapor
waiting/completed=0 ile yenilenir. İçinde `tile-0..2/` altında:

- before-ls.bin / after-ls.bin, before-gpr.bin;
- spu-diffuse.argb / spu-specular.argb;
- metal-diffuse.rgba / metal-specular.rgba;
- metadata.json (layout, koordinatlar, ışık/LS bilgisi, farklar).

Başlangıç capture belleği yaklaşık 1,6 MiB + küçük parametre/GPU staging alanı;
fixture'lar yaklaşık birkaç MiB ve Git dışındadır. LS big-endian, ham register
snapshot'ı native ARM64 düzenindedir. Oyun/firmware dosyası yeniden gönderilmez.

Sonraki iş: iPhone raporundaki gerçek tile girdilerini/farkları incele; gerekiyorsa
koordinat, depth/normal packing ve float yuvarlama farklarını düzelt. Ardından
planın tam-frame eşleme/gölge doğrulama ve yalnız aydınlatma Metal B moduna geçişi.
Bu kapılar geçilmeden performans optimizasyonu tamamlandı denmeyecek.

## Tekrar üretim

```sh
python3 tools/prepare_bces_ios.py --support-report out/bces-support-compile-iphoneos-spu-O2-copy.json
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer /opt/homebrew/bin/cmake -S cmake/bces-ios -B build/bces01229/ios
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp xcodebuild -project build/bces01229/ios/Infamous2BCESIOS.xcodeproj -scheme Infamous2Game -configuration Release -destination id=00008130-001129E00243001C -jobs 1 DEVELOPMENT_TEAM=BJ266NGN3H -allowProvisioningUpdates
```

Derleme/install/launch ve binary kimliği `out/phase1-exp1-*` altında.

## Kurulum sonrası kısa kontrol

Build 26 UUID `34761699-E626-37FA-8994-AEF95E1DD4CE` imzalandı, aynı bundle
üzerine kuruldu ve başlatıldı. PID 11455 raporunda guest present 3198, Metal
hata 0, lighting_validation_completed=3. iPhone raporu üç örnek içeriyor;
`out/phase1-exp1-device-validation.json` korundu. Bunlar aşaması kullanıcı
tarafından teyit edilmeyen ilk uygun tile örnekleri; FPS testi değil.

Üç A17 Pro karşılaştırması da `compared` durumunda, GPU pipeline hata vermedi.
Bu ilk örneklerin hepsinde light count=0 ve SPU çıktı buffer'ları sıfırdı.
Specular bit-exact; diffuse her tile'da 5120 byte'ın 1280'inde 90 fark verdi
(ortalama 22,5): Metal RGBA alpha'da 90 üretirken referans sıfır. Bu bir doğruluk
farkıdır; ışıklı oynanış doğrulanmış sayılmaz. Görsel composite etkisi ayrıca
incelenmeli; yalnız bunun görünmez olabileceğine dayanıp otomatik kabul yapılmadı.
Hızlandırma bu nedenle de kapalı tutuldu. Sonraki turda zero-light özel durumu
ve gerçek ışıklı fixture seçimi ele alınmalı. Cihaz performans testi yapılmadı.

## Build 27 — deneysel Metal yolunun etkinleştirilmesi

Build 26'nın zero-light diffuse alpha farkı düzeltildi: ışık sayısı sıfırsa
shader sıfır çıktı döndürür. Yeni test sky yerine sıfır depth kullandı;
Mac M3 Metal testinde diffuse ve specular 5120'şer byte bit-exact geçti.
Bu, ışıklı bütün sahnenin doğruluk testi değildir.

`tools/prepare_metal_lighting.py` sabit runtime kaynaklarını değiştirmeden
üretilen overlay'e uygulanır. `light_skip_4578` önce
`bces_light_allow_job` kontrolünden geçer. Normal/depth girdilerinin aynı
nesilden olması, Metal kaynaklarının önceden hazırlanması, descriptor tile
geometrisi/stride/flags, ışık tipleri ve gerçek GCM adres eşlemesi doğrulanır.
Uygun işin özgün tile hesaplaması atlanır; mevcut `eng_light_pass` Metal
hesabı ve `eng_gpu_light_texture` çıktı bağlaması kullanılır. Kontrolü geçmeyen
iş özgün SPU fonksiyonunda hesaplanır. SSAO ve guest normal/depth writeback
korundu. GPU geçişi atlamadan sonra başarısız olursa o kare geçersizdir;
sayaç artırılır ve sonraki işler SPU'ya döner. Aynı karenin yeniden oynatıldığı
iddia edilmez.

Gerçek yakalanan descriptor stream EA'ları 0x474f3b80 / 0x47877b80;
GCM eşlemesi üzerinden IO offsetleri 0x06ff3b80 / 0x07377b80 olarak kullanıldı.
Mac örneğinin farklı offsetleri taşınmadı. Host guard testi gerçek yakalanmış
LS fixture'ıyla geçerli/eksik GPU epoch, yanlış adres eşlemesi, yanlış geometri
ve context/LS'nin değişmeden kalmasını kontrol etti (PASS). Mevcut analiz
unit testleri 4/4 PASS. Release iPhoneOS derlemesi `-jobs 1` ile geçti;
imza ve tekil runtime sembolleri doğrulandı.

Build 27 UUID `A9022DCC-179A-3904-B456-722B2742C261`, aynı bundle üzerine
veriler korunarak kuruldu; `--boot --spu-copy-off` ile başlatıldı, otomatik
kapanış yok. Normal açılışta tile karşılaştırma capture'ı kapalıdır.
`--validate-lighting --spu-lighting` referans yakalama için kullanılabilir.
Üç nokta panelindeki deneysel Metal aydınlatma anahtarı yeniden açılışta uygulanır.

Kısa cihaz kontrolü: PID 11496, guest present 4348, Metal lighting passes 430,
bindings 860, skipped tiles 2626560, fallback jobs 68609; Metal/lighting fault
sayaçları sıfır. Bunlar etkinleşme kanıtıdır; oynanış aşaması teyit edilmedi,
FPS A/B veya tam görüntü eşdeğerliği kanıtı değildir. Telefon thermal state 2.
Gerçek ışıklı sahnelerde görsel karşılaştırma ve kontrollü FPS ölçümü sonraki iş.

Kanıtlar (Git dışı): `out/phase1-exp1-metal-{binary,install,launch}.json`,
`out/phase1-exp1-metal-early-report.json`, `out/phase1-exp1-metal-build.log`.
Guard testini tekrarlamak için:

```sh
python3 tools/test_metal_lighting_guard.py --fixture out/phase1-exp1-before-ls.bin
```
