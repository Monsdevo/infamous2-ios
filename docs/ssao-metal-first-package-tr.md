# Metal SSAO — ilk korumalı paket, 25 Ekim 2026

26 Ekim güncellemesi: gerçek cihazda GPU yolu ve ilk C/B performans pilotu
doğrulandı; [güncel ölçüm notu](ssao-device-measurement-tr.md). Aşağıdaki
kurulum/ilk doğrulama sınırları tarihsel ilk paket kaydıdır.

## Kapsam

Build 32: Metal aydınlatma ve deneysel Metal SSAO seçeneği. Kullanıcının isteğiyle
kurulum/açılış kontrolünden sonra oturum sonlanır; uzun oynanış ve FPS A/B bu
oturuma dahil değildir. Oyun dosyaları yeniden aktarılmaz.

SSAO shader'ları sıfırdan yazılmadı: pinned runtime'daki `eng_ssao_pass` beş
geçişi kullanılır. AO 12 örnekli, yarı çözünürlükte; iki 5-tap derinlik duyarlı
filtre ve bilateral 2x büyütme korunur. Kalite/çözünürlük düşürülmedi.

İlk paket **özgün SPU derinlik üretimini** (pass E) korur: `ssao_skip_step`,
header pass 0 iken gerçek `jobmod_e6fe749031f8...5258` adımını çağırır. Böylece
label 136'yı bekleyen henüz tanımlanmamış tüketicilerin gerçek half-depth
bellek çıktısı korunur. Metal, kendi AO zinciri için derinliği ayrıca üretir;
bu ilk doğruluk aşamasındaki bilinçli ek iştir. CPU'da yalnız sonraki dört
pass'in tile matematiği/DMA'sı atlanır. Claim/completion/barrier/yield ve
label 137 gerçek job fonksiyonlarıyla yürür. Her iki giriş writeback'i korunur.

## Sürüm eşlemesi

`tools/prepare_metal_ssao.py` yalnız build altındaki overlay'i değiştirir.
`ssao_gpu.h/c` türetilir; BCES module adresleri:

| İş | Genel repo | BCES |
|---|---|---|
| Depth | 0x87D500 | 0x81ED00 |
| AO | 0x87F880 | 0x821080 |
| Blur H | 0x87D880 | 0x81F080 |
| Blur V | 0x87E480 | 0x81FC80 |
| Upsample | 0x87EC80 | 0x820480 |

BCES registration/lift girdileri doğrulanmış support arşivinden gelir; image
225, walk LS 0x4330 registry binding kontrol edilir. Orijinal kaynak/fork,
macOS hedefi ve kilitli arşivler değiştirilmez.

## Koruma ve sayaçlar

`src/platform/MetalSSAO.c:bces_ssao_allow_job`, yürütme context'ini değiştirmeden
r83'ün gösterdiği gerçek state/pass tablosunu okur. Beş pass'in sırası,
parametre boyutları, 1280×720/640×360 boyutlar, stream adres/pitch/formatları,
normals/depth girişlerinin mevcut IO eşlemesi, label EA/değerleri, ortak blur
sabitleri ve sonlu sayılar denetlenir. Çıktı VRAM adresi pass B'den türetilir;
genel reponun 0x0F800000 varsayımıyla iş atlanmaz. Eşleşmezse özgün SPU walk.

Renderer, aynı snapshot generation için beş PSO, dört kalıcı ara/çıktı dokusu
ve sekiz parametre buffer'ını SPU atlamasından önce hazırlar. Epoch eşleşmeden
GPU dokusu bağlanmaz. Geç GPU kayıt hatası mevcut kareyi geri oynatamaz; fault
sayar ve gelecekteki işler SPU'ya döner. Bu durum başarılı fallback gibi
sunulmaz. Yeni CPU GPU-wait/readback yok; shader'lar mevcut command buffer'a
composite öncesinde sıralanır.

Panel: `Metal SSAO · deneysel`, varsayılan açık, Metal aydınlatma da açık
olmalı. Değişiklik yeniden açılışta uygulanır. `--spu-ssao` referansı zorlar.
Rapor: `metal_ssao_requested/passes/bindings/skipped_tiles/fallback_jobs/faults`.
Requested=true tek başına etkin optimizasyon kanıtı değildir; passes/bindings
ve skipped_tiles artmalıdır. `metal_ssao_last_rejection` son ret aşamasıdır:
1 header/pass/param; 2 decoder; 3 dims/EA/labels; 4 ara bellek; 5 stream;
6 blur stream; 7 sabitler; 8 kaynak generation/preflight hazır değil.

İlk yapısal olarak geçerli tablonun sınırlı 1936 byte snapshot'ı SPU'da
bir kere kopyalanır; UI timer'ı Documents/ssao-pass-capture.bin'e yazar.
16 byte header + 640 byte pass table + beş 256 byte param slotu. Oyun girdileri
ve bu tanı snapshot'ı Git'e eklenmez. Bu snapshot çıktı eşdeğerliği testi değildir.

## Gerçekten tamamlanan kontroller ve sınırlar

- iPhoneOS Release `-jobs 1`: BUILD SUCCEEDED, build 32.
- ASan/UBSan production guard + BCES decoder testi: desteklenen düzen;
  kaynak hazır değil, yanlış sürüm modülü, yanlış pitch, farklı H/V sabiti ve
  NaN reddi; LS/register değişmemesi geçti.
- Mac GPU: renderer'dan alınan aynı beş SSAO shader'ı derlenip yürütüldü;
  analitik flat-depth, sıfır ve sıfırdan farklı sabit AO girdileri geçti.
  Bu yalnız shader zinciri smoke testidir; iPhone performansı veya gerçek
  SPU/Metal çıktı eşdeğerliği değildir.
- Gerçek oyun girdisiyle beş ara aşama karşılaştırması, görüntü kontrolü,
  sinematik/oynanış kararlılığı ve dengeli SSAO açık/kapalı FPS testi **açık**.
  Upstream'in başka sürümde yaptığı doğrulama bizim BCES doğrulamamız sayılmaz.

## Tekrar üretim

```sh
python3 tools/prepare_bces_ios.py --support-report out/bces-support-compile-iphoneos-spu-O2-copy.json
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer /opt/homebrew/bin/cmake -S cmake/bces-ios -B build/bces01229/ios
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp xcodebuild -project build/bces01229/ios/Infamous2BCESIOS.xcodeproj -scheme Infamous2Game -configuration Release -destination id=00008130-001129E00243001C -jobs 1 DEVELOPMENT_TEAM=BJ266NGN3H -allowProvisioningUpdates
clang -std=gnu17 -O2 -fsanitize=address,undefined -I src/platform -I build/bces01229/ios-prepared -I upstream/infamous2-recomp/ps3recomp-fork/runtime/spu tools/tests/metal_ssao_guard.c src/platform/MetalSSAO.c build/bces01229/ios-prepared/ssao_gpu.c -o build/bces01229/ssao-guard-test
build/bces01229/ssao-guard-test
```

Kanıt: out/ssao32-build.log, ssao32-metal-smoke.log, ssao32-binary.json,
ssao32-install.json ve ssao32-launch.json. UUID
3C9D35C1-C8FD-3974-9654-6FBF77B10BFB. Önceki aydınlatma tabanı build 31,
4,84 FPS; yeni SSAO için henüz kazanç iddiası yok.

## Kurulum son durumu

Build 32 cihaz üzerine başarıyla kuruldu, strict codesign doğrulaması geçti.
Başlatma isteği iOS tarafından `Locked` gerekçesiyle reddedildi. Telefon kilitli
olduğu için yeni süreç başlamadı; sonradan okunabilen eski rapor build 32'nin
çalışma kanıtı olarak kullanılmaz. Kullanıcının kurulumdan sonra turu bitirme
isteği doğrultusunda kilit açma/oynanış talebi gönderilmedi. Uygulama kullanıcı
tarafından açıldığında ilk kontrol: görüntü/kararlılık ve gerçek SSAO counters;
sonra sınırlı aynı-girdi SPU/Metal aşama karşılaştırması ve sabit sahne A/B.
