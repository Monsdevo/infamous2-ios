# 21. adım — RSX label üreticisi teşhisi

25 Ekim 2026. Amaç: 20. adımda yaklaşık 137 ms/kare görülen `0x870` ve
`0x890` acquire beklemelerini gerçek SPU DMA yazılarıyla eşlemek. Optimizasyon
adayı etkinleştirilmez. Sabit runtime, title/support arşivleri korunur.

## Kapsam ve uygulama

Build 24'te yazıcı provenance kaydı yoktu. Açık sürece yeni native ölçüm kodu
aktarılmadı; build 25 gerekli oldu. Eski süreç PID 11328, yeni süreç PID 11342.
Aynı bundle üzerine güncelleme Documents oyun verilerini korudu. Yeni sürüm
`--boot --spu-copy-off --profile-cpu --diagnose-frame` ile açıldı; otomatik kapanış yok.
İlk kontrolde guest present 240, Metal hata 0. Kullanıcı daha sonra gerçek
oynanışa geldiğini ve kumandayı bıraktığını doğruladı. Aşağıdaki kayıtlar o sahnedendir.

`tools/prepare_frame_diagnostics.py`, kilitli `runtime/spu/spu_dma.h` kaynağından
`ios-prepared/diagnostic_spu_dma.h` üretir; yalnız türetilmiş spu_channels.c bunu
kullanır. Kaynak runtime/header, macOS hedefi ve diğer destek birimleri değişmez.
`mfc_do_transfer` ordinary PUT yolunun iki `gm_copy_to` noktasında, yalnız
`ppu_hle_inject_base+0x870/+0x890` tam 32 bit sözcüklerini kapsayan transferler
zamanlanır. Reserved/unreserved copy, coherency notify ve kilitler korunur.
Çağrı zinciri toplama coherency kilitleri/notify sonrasındadır; dosya yazılmaz.

`FrameDependency.h` adres sınırı ve big-endian sözcük okumasını ayırır.
`FrameTrace.cpp:bces_frame_trace_dma` filtrelenen yazının kaynak LS değerini,
SPU/image/PC/LR/LSA/size ve en çok 12 native stack adresini kaydeder. Native
çağrı zinciri önemli: ctx->pc/image dispatcher'a ait olabilir. Yazıyı gönderen
işlev, sonuçları hesaplayan bütün önceki job'ların tek başına süresi değildir.

Yeni event şeması (önceki genel trace şeması korunur):

| Kind | who | a | b |
| --- | --- | --- | --- |
| 21 | benzersiz yazı tag | label offset | big-endian değer |
| 22 | tag | SPU id | image id |
| 23 | tag | guest PC | guest LR |
| 24 | tag | LSA | transfer size |
| 64..75 | tag | native PC düşük 32 bit | yüksek 32 bit |
| 18 | SPU id/high bit | native thread id düşük | yüksek |

21–24 ve native stack olaylarının zaman aralığı gerçek copy'nin hemen
öncesi/sonrasıdır; backtrace süresini copy zamanı diye göstermez. Trace header
UUID/app_base/app_end içerir; atos yalnız eşleşen binary ile çalışır. Kayıt
penceresinin kenarında eksik bir grup oluşursa analiz sayar, tam üretici saymaz.

SPU native-id eşlemesi artık arming süresinden sonra ilk uygun kanal beklemesinde
üretilir; label yazılarında da eşleme gelir. 20. adımdaki arming kaybı düzeltildi.

`tools/analyze_frame_dependencies.py`: label+değer ve copy/acquire zaman
aralıklarıyla eşler. Tek kayıtlı aday / birden fazla aday / eşleşmeyen ayrı
raporlanır. Tek aday kesin bütün-job maliyeti veya tek mümkün writer demek değildir.
Atomic/partial PUT ve doğrudan PPU store bu ölçümün kapsamı dışında. Eşleşmeyen
beklemeler varsa bunlar ayrıca incelenmeli; PPU writer olduğu varsayılmamalı.

## Doğrulama ve tekrar üretim

Build 25 UUID `E556C6D1-170F-3E06-B873-A1A8DFA09710`, iPhoneOS Release,
`-jobs 1`. `out/step21-binary-validation.json`: yedi TU canonical ftrace header,
tek güçlü `g_ps3_ft`, güncel DMA header dependency ve object/source mtime kontrolü.
`codesign --verify --deep --strict` PASS. Kaynak pins/83 support unit/12 iOS arşivi
prepare aşamasında doğrulandı. İlk derlemedeki t1 declaration sırası düzeltildi;
cihaza yalnız başarılı son derleme kuruldu.

Host: tam sözcük filtreleri, taşmayan EA sınırı, iki label'ı kapsayan aralık,
big-endian değerler, provenance/flush PASS. Concurrent writer/quiescence testi
PASS. Python interval/dependency testleri 4/4 PASS: yanlış değer/zaman
ilişkilendirilmez; çoklu aday ve eksik grup gizlenmez.

```sh
cd /Volumes/monssd/Infamous2-iOS
python3 -m unittest discover -s tools -p 'test_frame*.py'
python3 tools/prepare_bces_ios.py --support-report out/bces-support-compile-iphoneos-spu-O2-copy.json
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer /opt/homebrew/bin/cmake -S cmake/bces-ios -B build/bces01229/ios
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp xcodebuild -project build/bces01229/ios/Infamous2BCESIOS.xcodeproj -scheme Infamous2Game -configuration Release -destination id=00008130-001129E00243001C -jobs 1 DEVELOPMENT_TEAM=BJ266NGN3H -allowProvisioningUpdates
```

Cihaz ölçümü mevcut `Documents/frame-trace-control.txt` üzerinden benzersiz
`start TOKEN 10` ile tetiklenir; çıktı `Documents/frame-trace.csv`. İşlem sonunda
kontrol tekrar idle yapılır. Genel analiz:

```sh
python3 tools/analyze_frame_trace.py out/step21-gameplay-trace.csv --output out/step21-gameplay-trace-analysis.json
python3 tools/analyze_frame_dependencies.py out/step21-gameplay-trace.csv --binary build/bces01229/symbols/E556C6D1-170F-3E06-B873-A1A8DFA09710/Infamous2Game --output out/step21-gameplay-dependencies.json
```


## Gerçek iPhone oynanış sonucu

Ölçüm sırası OFF 20 s → yalnız trace 10 s → CPU 30 s (başında 10 s trace)
→ OFF 20 s. Kontroller sonunda `idle` yapıldı; uygulama açık bırakıldı.
Kısa ilk sağlık kaydı oynanış teyidinden önceydi; FPS benchmark'ı olarak kullanılmadı.

Yalnız trace: 85.825 kayıt, dropped=0, 37 guest flip, 34 iç kare aralığı.
111 Metal commit / 111 execution; eksik GPU sonucu 0. 75 label yazısı eksiksiz
provenance ile geldi. 76 acquire olayının 75'i tek kayıtlı yazıcıyla eşleşti.
Kalan acquire 195787,685624–195787,782647 aralığında; capture end
195787,732324. Dolayısıyla yazıcı pencere sonunun dışında; gizli writer diye
sınıflandırılmadı. Ortak CPU+trace kaydında 75/75 acquire tek yazıcıyla eşleşti,
hiç eksik provenance grubu yok. Bağımsız ikinci kayıt aynı iki native işlevi verdi.

| Bekleme | Gerçek native yazıcı | Tek eşleşme | Bekleme medyanı | Yazıdan sonraki kontrol gecikmesi medyanı |
| --- | --- | ---: | ---: | ---: |
| 0x870 / label 135 | jobmod_c6e7383dc013_e5400_spu_func_00005A40 | 37 | 75,79 ms | 2,77 ms |
| 0x890 / label 137 | jobmod_e6fe749031f8_e2060_spu_func_000049C8 | 38 | 58,83 ms | 2,44 ms |

Aydınlatma stack'i: `45C4 → 68B8 → 5A40 → spu_wrch → mfc_submit_body → mfc_do_transfer`.
Tiled SSAO stack'i: `437C → 5840 → 49C8 → spu_wrch → mfc_submit_body → mfc_do_transfer`.
İki son işlev de kaynakta size=4, command=32 ordinary PUT kuruyor. Bu, yalnız
zaman yakınlığına göre tahmin değil; beklenen label/değer ile gerçek kopya ve
onu çağıran kod birlikte gözlendi. `image_id=100` SPURS bağlamı olarak kaldı;
ona bakıp asıl iş kodunu kernel sanmak yanlış olurdu. SPU id/native-id eşlemesi
altı SPU için de kayda girdi; yazıcılar 8192..8196 arasındaki worker'lar.

Modül anlamları pinned repo'nun `notes/spu_light/README.md`, `gpu_light.c`,
`gpu_ssao.c` ve üretilmiş BCES kaynaklarıyla karşılaştırıldı: c6e7 aydınlatma,
e6fe generic tiled SSAO pipeline. Bu, belirli bir 75 ms beklemenin tamamının
tek bir matematik işlevinde geçtiği anlamına gelmez. Tile paylaşımı, önceki
pass'ler ve diğer işler hâlâ toplam hazırlık gecikmesinin parçası olabilir.

Yalnız trace medyanları: guest flip 266,52 ms; GPU interval birleşimi 35,85 ms;
RSX acquire birleşimi 135,25 ms; FIFO drain duvarı 118,13 ms; CPU GPU wait
14,00 ms. Ortak CPU+trace: 265,91 / 35,59 / 137,04 / 117,22 / 13,96 ms.
GPU birleşimi pencerenin yaklaşık %13,3–13,4'ü (donanım utilization değildir).
İç içe duvar süreleri toplanmaz. Her iki kayıtta Metal/pipeline hata 0.

CPU: 30,016 s, 13.926 satır, 1328 tick, error=0, truncated=0. Gözlenen thread
CPU delta ağırlıkları: SPU %84,86, renderer %7,14, PPU %6,91, diğer %1,09.
Çağrı zincirinde gözlenen job aileleri ayrık bölümlendiğinde aydınlatma %23,07,
SSAO pipeline %22,17; bunlar job wall-time ölçümü veya FPS yüzdesi değildir.
Kalan %54,76 diğer ancestry veya belirlenemeyen işlere gider; atılan CPU yok.
En yoğun self işlevler: `datamod_00821080...7320` %8,60;
`datamod_00820480...6F80` %4,82; `jobmod_c6e7...9248` %4,31.
System/unresolved self PC %10,82; örneklemenin sınırı olarak korunur.

CPU kaydının trace ile ortak ilk 10 saniyesi CLOCK_MONOTONIC−Mach offset'iyle
kırpıldı: 4663 satır. Aynı pencerede aydınlatma ancestry %22,61, SSAO %22,10.
Native ancestry eksik olabilir; bu oranlar sampled CPU maliyetidir. Tek 10 s
pencerede aynı kayıtlı modüllerin hem CPU maliyeti hem RSX label üretimi görüldü.
Bu, önceki yalnız “SPU %85” gözleminden daha dar ve kullanılabilir bir hedeftir.

### Isı ve ölçüm etkisi

| Pencere | HUD kare ortalaması medyanı | Thermal |
| --- | ---: | --- |
| Önce OFF | 267,28 ms | 2 serious |
| Yalnız trace | 268,95 ms | 2 serious |
| CPU+trace ortak iç bölüm | 267,58 ms | 2 serious |
| CPU 30 s | 266,72 ms | 2→3 |
| Sonra OFF | 268,81 ms | 3 critical |

FPS yaklaşık 3,5–4; pipeline 1024'te sabit. İlk soğuk cihaz durumu yok; pil %95.
Son CPU kısmında serious→critical geçişi olduğundan bütün 30 s ile OFF-after'ı
kesin overhead A/B saymıyoruz. İlk iki 10 s trace'in iç örnekleri thermal=2;
iş kimliği eşleşmeleri geçerli, maksimum cihaz performansı veya yeni FPS
kazancı iddiası yok. Ek uzun ölçüm başlatılmadı.

## Bu ölçümün seçtirdiği yön

- Artık ilk aday soyut “SPU hızlandırma” değil: **SPU aydınlatma ve tiled SSAO
  işi**. Bunlar hem CPU'da pahalı hem gerçek RSX bağımlılığının üreticileri.
- Yalnız final PUT işlevini hızlandırmak hedef değildir; o işlev 4 byte sonucu
  yayımlar. Asıl tile işini ve/veya veri taşımayı azaltmak gerekir.
- Polling gecikmesi iki etikette birkaç ms; 135 ms toplam beklemeyi açıklamaz.
  Beklemeyi kaldırmak veri hazır olmadan çizmek olur. Spin/QoS/thread sayısı
  rastgele ilk müdahale olarak seçilmedi.
- Önerilen ilk optimizasyon deneyi: mevcut repo'nun **Metal aydınlatma yolunu**
  BCES/iOS için girdi/çıktı karşılaştırmasıyla doğrulamak ve yalnız aydınlatmayı
  seçenekli A/B testine almak; ardından SSAO. `gpu_light.c`/`gpu_ssao.c` yeniden
  yazılmak zorunda değil, fakat iOS doğrulaması yapılmadan env açmak yeterli değil.
  Frame constants, buffer/format eşlemesi, label protokolü, shader sonucu ve
  iş atlama state'i SPU referansına karşı kontrol edilmeli. Bu yollar bu oturumda
  açılmadı. CPU tarafında kalınacaksa aynı job ailelerine yönelik blok/SIMD
  alternatifleri değerlendirilebilir; tek bir self işlevin küçük payıyla sınırlı kalınmamalı.
- GPU'ya taşıma GPU süresini yükseltebilir; 30 FPS vaadi yok. Renderer CPU/drain
  tarafı da yaklaşık 118 ms wall içeriyor; iki efekt çözülünce kalan sınır yeniden
  ölçülmeli. Yeni CPU profile göre bütün optimizasyon projesi bitmiş sayılmıyor.

## Kaydedilen kanıtlar

`out/step21-gameplay-{trace,combined-trace}.csv`, `*-dependencies.json`,
`*-trace-analysis.json` ve `.chrome.json`; `step21-gameplay-cpu.csv`,
`step21-gameplay-overlap-cpu.csv`, bunların UUID eşleşen analizleri;
`step21-label-summary.json`, `step21-session-summary.json`, performance.csv,
thread map, pencere işaretleri ve capture script'i Git dışında tutuldu.
`tools/analyze_native_profile.py` yeni ancestry gruplarını raporlar; pencere
kırpma için trace start/end'den `monotonic_minus_mach_s` çıkarılır. Job ailesi
başlıkları, dahilî ancestry yüzdelerini üst üste eklemek yerine ayrık sınıflandırılır.

Oyunun tekrar görüntüsü yalnız kullanıcı teyidiyle doğrulandı; yeni screenshot
iddiası yok. Cihazda gerçek native oyun ölçüldü, simülatör kullanılmadı.
