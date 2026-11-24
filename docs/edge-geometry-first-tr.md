# Edge geometri — ilk ARM64 denemesi / build 36

26 Ekim 2026. Bu aşama bütün Edge işini Metal'e taşımıyor. İkinci teşhiste
`jobmod_d0d15ec83992_ea2a0` doğrudan CPU örneklerinin %16,138'ini,
stack atası olarak %19,917'sini oluşturdu. Bu oranlar paralel CPU çalışmasının
payıdır; kare süresinden doğrudan çıkarılamaz. D808, D8A8 ve DA28'in toplam
doğrudan payı yaklaşık %7,16 idi. İlk deneme bu üç blokla sınırlı.

## Seçilen değişiklik

`tools/prepare_edge_geometry.py:derive` doğrulanmış üretim kaynağından
`build/bces01229/ios-prepared/edge_geometry.c` türetir. Kaynak, kilitli fork ve
macOS hedefi değişmez. `prepare_bces_ios.py` yalnız türetilmiş iOS destek
arşivinden özgün Edge nesnesini çıkarır; CMake aynı modülün değiştirilmiş
kopyasını O2/SPU_USE_DISPATCH_MT ile derler.

- **D808:** indekslenmiş matris/palet yükleri ve ağırlıklı çarpma/toplama;
  sonraki D8A8'e özgün trampoline geçişi korunur.
- **D8A8:** ağırlıklı matris sonuçlarının devamı, LS sonuç yazıları ve sonraki
  üç dallanma korunur. CUFLT dönüşümleri mevcut tamsayı `spu__sf_pack` yolunu
  kullanır; host yuvarlamasına bağımlı bir C float dönüşümü eklenmez.
- **DA28:** dört öğelik matris dönüşüm döngüsü; özgün sayaç, bellek sırası ve
  D698 çıkışı korunur.

`spu_fm/fma/fms` yerine önceden ayrı test edilmiş `BCESSpuRZ.h` kullanılır.
Normal sayılar ARM64 NEON ve donanımın sıfıra doğru yuvarlama modu ile
hesaplanır. SPU'nun geniş üs aralığı gibi özel durumlarda kesin tamsayı
yardımcısına dönülür. Blok başında FPCR/FPSR saklanır, **her çıkışta** geri
yüklenir. Modüller birleştirilmez; dispatch/interrupt sınırları korunur.
DMA, RSX çıktıları, vertex biçimi, culling kararları veya çizilen nesne sayısı
değişmez. Bu nedenle henüz "culling optimizasyonu" sonucu da değildir.

Mevcut runtime'ın double/TwoSum yolu round-to-nearest varsayar. Diğer host
yuvarlama modlarında ilk testte eşdeğerlik geçmedi; hızlı yolu bu koşulda
çalıştırmak yerine **özgün fonksiyona dönen guard** eklendi. Testler hem bu
fallback'i hem RN hızlı yolu kapsar. CPU JIT yoktur.

## Doğrulama ve deney kontrolü

`src/platform/EdgeGeometry.c` etkinlik bayrağı, çağrı sayaçları ve tanı
kontrolünü içerir. Her bloğun ilk sekiz gerçek çağrısında bağımsız ctx/LS
kopyası üzerinde özgün blok da çalıştırılır. Bloğun değiştirdiği register, çıkış pc/trampoline
ve 256 KiB LS karşılaştırılır. Asenkron host alanları bu karşılaştırmaya girmez. Fark olursa özgün sonuç geri konur, mismatch
sayacı artar ve deneme süreç boyunca kapatılır. Bu 24 sınırlı kontrol bütün
oyun için matematiksel ispat veya tüm görüntü eşdeğerliği değildir.
Bu ilk kontrollerin süresi FPS penceresine dahil edilmemeli.

Normal başlatmada deneme **kapalıdır**. `--edge-arm64` açar;
`--diagnose-edge` UI thread'inde `Documents/edge-control.txt` okumasını açar:
`on BENZERSIZ_TOKEN` / `off BENZERSIZ_TOKEN`. Aynı token tekrar uygulanmaz.
Değişiklik yalnız sonraki blok çağrılarına uygulanır, devam eden işi iptal etmez.
`bces-device-report.json`: `edge_arm64_enabled`, üç çağrı sayacı,
`edge_arm64_validations`, `edge_arm64_mismatches`.

Host testi iki ayrı binary'de (ASan/UBSan ve Release) **6.144 tam context/LS
karşılaştırması** geçti: rastgele bitler/özel üsler, dört yuvarlama modu,
FZ açık/kapalı, iç/dış LS yerleşimi, D8A8'in üç çıkışı ve DA28'in 1..8 iterasyonu.
`tools/tests/edge_geometry.c` gerçek türetilmiş blokları çalıştırır.
Sentetik M3 mikrotestinde Release blok süreleri yaklaşık 1,16 / 1,13 / 1,60
kat hızlıydı; timer maliyeti dahil, fixture kopyası hariç. Bu tek sentetik
koşu **iPhone FPS tahmini değildir**; gerçek veri, fallback oranı, bellek ve
işler arası bekleme farklı olabilir. Cihaz A/B sonucu aşağıda: anlamlı FPS kazancı saptanmadı.

## Tekrar üretim

```sh
python3 tools/test_edge_geometry.py
python3 tools/prepare_bces_ios.py --support-report out/bces-support-compile-iphoneos-spu-O2-copy.json
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer /opt/homebrew/bin/cmake -S cmake/bces-ios -B build/bces01229/ios
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp xcodebuild -project build/bces01229/ios/Infamous2BCESIOS.xcodeproj -scheme Infamous2Game -configuration Release -destination 'generic/platform=iOS' -jobs 1 DEVELOPMENT_TEAM=BJ266NGN3H -allowProvisioningUpdates
```

Build36 UUID `8A53F8D7-B258-3E2B-8390-838F0A0E7F69`, arm64 iPhoneOS,
strict imza doğrulaması geçti. iPhone'a mevcut uygulama güncellenerek kuruldu;
17,8 GB oyun verisi tekrar aktarılmadı. Build33 geri dönüş paketi
`build/bces01229/baselines/step26-edge-build33/Infamous2Game.app`.
Kanıtlar `out/edge36-*`, host test kaydı
`out/edge-geometry-host-test.log`. Önceki aralıklı sinematik donması ayrı açık
konudur; bu değişiklik onu çözdüğünü iddia etmez.

## Gerçek veriyle kontrol hatasının ayrılması

Build34/35 ilk gerçek çağrılarda deney kapandı. Build35 kaydı
`out/edge35-failure.bin`, block D8A8, FPCR=0. Yanlış kontrol tüm ctx'yi
karşılaştırıyordu: üretim bağlamının `ls` işaretçisi kendi `ls_store` alanını
hedefliyor; shadow ise ayrı LS kullanıyor. 100 farklı baytın **tamamı**
2048..264191 iç LS alanındaydı. Gerçek LS sonuç farkı 0, bu alan dışında ctx
farkı 0. Host'ta gerçek girdiyle, iç LS yerleşimi korunarak ASan/UBSan tekrar
testi geçti (`out/edge36-replay.log`). Bu fark aritmetik uyuşmazlığı değildi.

Build36 kontrolü GPR/pc/trampoline + gerçek LS ile sınırlar. Geri dönüşte
stale host bağlamı kopyalanmaz; yalnız blok çıktıları geri alınır. Eski geniş
kopyalama kodu iç LS'yi eski verilerle ezebildiği için kaldırıldı. Testler artık
her iki LS yerleşimini de kapsıyor; tek seferlik token ve mismatch latch de
sınanıyor. Yakalanan binary fixture oyun kaynaklı özel veri içerir; ignored
out altında kalır, yayımlanmaz.

Kullanıcı build34/35 sinematiğinde iki kapanma bildirdi. Yeni paketlerin
kurulumuyla zaman çakışması mümkün; bunları doğrulanmış iki crash diye
saymıyoruz. Bugünkü mevcut Jetsam raporlarında bu süreçler görülmedi; yeni
Infamous2Game crash raporu henüz alınamadı. Build36 üzerinden yeni kurulum
olmadan oynanışa geçiş takip edilecek. Kalıcı crash çözümü iddiası yok.

## Build36 ilk cihaz doğrulaması

PID15166, `out/edge36-start-report.json`: 24 gerçek çağrı kontrolü tamamlandı,
mismatch=0, deney açık. D808/D8A8 ayrı ayrı 1.141.760 hızlı çağrı; DA28 10.652.
731 guest present, Metal_errors=0, termal0; CPU/trace örnekleyicileri kapalı.
Bunlar bir FPS penceresi değildir ve henüz oynanış A/B kazancı çıkarmıyoruz.

Gerçek fixture tekrar testi:

```sh
python3 tools/replay_edge_geometry.py out/edge35-failure.bin
```

Bu örnek kalıcı test için kaynak kontrolüne alınmaz. Paylaşılabilir test
`tools/test_edge_geometry.py` sentetik verileri kendi üretir.

## Sabit oynanış ölçümü — 26 Ekim 2026

Kullanıcı Cole'u kontrol edebildiği ilk oynanış sahnesine ulaşıp karakteri ve
kamerayı sabit bıraktığını teyit etti. Build36 **aynı PID15166/süreçte**,
Edge ON → OFF → ON değiştirildi; uygulama yeniden başlatılmadı veya kurulmadı.
Metal aydınlatma/SSAO ve SSAO sınır temizliği her üç pencerede açıktı.
CPU/trace örnekleyicileri idle0; termal durum her örnekte normal0, pipeline
compile artışı0, Edge mismatch0, Metal hata0. İlk 24 gerçek karşılaştırma
ölçümden önce tamamlanmıştı; pencereler sırasında ek doğrulama çalışmadı.

| Pencere | Süre | Oyun karesi | FPS |
|---|---:|---:|---:|
| Edge açık 1 | 31,99965 s | 209 | 6,53132 |
| Edge kapalı | 31,99913 s | 207 | 6,46893 |
| Edge açık 2 | 32,00011 s | 207 | 6,46873 |

Açık pencerelerin kare/süre ağırlıklı birleşimi **6,50002 FPS**; kapalı
**6,46893 FPS**. Gözlenen fark **+%0,4807** veya sayaç ortalamasında
154,585→153,846 ms (**0,740 ms**). Ham kare medyanı/p95 ölçülmedi. İkinci açık
pencere kapalıyla aynı düzeyde; tek ardışık ON/OFF/ON kaydı bu küçük farkın
tekrarlanabilir optimizasyon kazancı olduğunu göstermiyor. **Anlamlı FPS
artışı saptanmadı.** Sentetik host mikrotest kazancı oyun FPS'sine taşınmadı.

Açık 1 / açık 2 D808 ve D8A8 hızlı çağrıları ayrı ayrı
10.647.138 / 10.563.210 arttı; DA28 459.995 / 456.849. Kapalı pencerede
üçünün de hızlı çağrı artışı0. Dolayısıyla "flag açık ama yeni kod çağrılmadı"
durumu değil. Fiziksel footprint bütün pencerelerde yaklaşık 970–974 MB idi.
Bunlar yalnız seçili üç bloğun aritmetik denemesidir; bütün Edge modülünü
veya GPU'ya geçiş potansiyelini değerlendirmez.

Deney kapalıya döndürüldü; Metal aydınlatma ve SSAO açık bırakıldı. Bu turun
sonucu `out/edge36-gameplay-comparison.json`; ayrı pencereler
`out/edge36-gameplay-{on1,off1,on2}/summary.json`. Mevcut kontrol dosyalarıyla
aynı komutu tekrarlamak yerine yeni output klasörleri ve farklı token kullan.

Ölçüm komutu (kontrol dosyasıyla ilgili mod seçilip yerleşmesi beklendikten sonra):

```sh
python3 tools/capture_device_window.py --device 00008130-001129E00243001C --output out/YENI_PENCERE --seconds 30 --scene 'ilk oynanış, sabit kamera, Edge ON veya OFF' --max-thermal-state 0
```

Bu sonuca göre varsayılan hızlandırmayı açmak için gerekçe yok. Yeni kod
yazmadan önce sonraki yararlı teşhis, gerçek Edge girdileriyle bu üç bloğun
cihazdaki toplam süresini ve kritik yoldaki yerini ayırmaktır. Toplam paralel
CPU payı tek başına kazanılabilecek kare süresi değildir; tüm Edge işinin
veri akışı ve diğer sıcak bloklar bu ayrımdan sonra hedeflenmelidir.
