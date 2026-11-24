# 20. adım — kare / bekleme / GPU teşhisi

25 Ekim 2026. Yalnız ölçüm; RZ adayı uygulamaya bağlanmadı. Sabitlenmiş runtime,
O2 destek arşivi, mmap guest arena, 64 MiB PPU host stack ve macOS hedefi korunur.

## Mevcut altyapı ve kapsam

Sabitlenmiş yamalı runtime'ın ps3_ftrace hook'ları kullanılır: PPU syscall duvar
süreleri/guest LR; SPU kanal beklemeleri; RSX acquire, FIFO drain, flip request,
FIFO flip ve CPU present. SPU_BUSY iki kanal beklemesi arasındaki DUVAR süresidir,
job CPU süresi değildir. Image id aralığın sonunda okunur; bütün aralığı aynı
job'a atfetmek yanlış olabilir. Her job sınırı henüz ölçülmüş değildir.

`tools/prepare_frame_diagnostics.py` doğrulanmış kaynaklardan build overlay üretir.
Kayıt yapısına aktif-yazar sayısı eklenir. UI kontrolcüsü pencere sonunda on=3
yapar, bütün yazarlar çıktıktan sonra dosyayı okur; guest/render thread'i dosya
flush yapmaz. usleep aralıkları birleştirilmez; gerçek aralıklar korunur. 500000
kayıt / 16 MB sınırı ve dropped sayacı vardır. Analiz dropped>0 kaydı reddeder.

`src/platform/FrameTrace.cpp`: --diagnose-frame ile yapılandırılır; 1 Hz poll,
Documents/frame-trace-control.txt içinde start TOKEN SECONDS görünce ölçer.
250 ms arming boşluğu, 1–30 s pencere. Aynı token yeniden başlamaz. PPU logical
id'leri native thread id'lerine bağlanır. SPU id/native eşlemesi ölçüm sırasında
ilk kanal beklemesinde gelir; hiç beklemeyen thread için eşleme olmayabilir.

Metal backend'deki 11 commit ve 9 mevcut CPU wait yeri sarılır. Yeni GPU wait
EKLENMEZ. Capture açıkken commit/completion ve gerçek GPUStartTime/GPUEndTime
kaydedilir; bütün mevcut s_queue komut tamponları kapsanır. GPU light/SSAO zaten
BCES yapılandırmasında kapalıdır; açılırsa başka kuyruk kapsamı ayrıca incelenir.
Eski GPU_EXEC (kind14) CPU completion zamanından yaklaşık konumlanıyordu; yeni
kind15 gerçek Metal zamanlarıdır. Analiz kind14'ü GPU bütçesine katmaz.

CLOCK_MONOTONIC ile mach_absolute_time / CACurrentMediaTime farklı tabanlarda
olabilir: host testte yaklaşık 52294 s fark görüldü. Trace metadata'sı farkı ve
kalibrasyon aralığını içerir; Metal timestamp'leri event saatine çevrilir. CPU
profili ve performance.csv Mach tabanındadır; birleştirmede offset kullanılmalı.

CPUProfile.cpp ayrıca her onuncu tick'te bütün thread durumlarını örnekler.
Running PC sıralaması ayrı tutulur; bekleyen PC'ler CPU tüketimi diye sayılmaz.
Periodic state census yaklaşık 5 Hz gözlemdir, kısa beklemelerin kesin süresi
değildir. PPU wait-syscall süreleri CPU ve scheduler süresini de içerir.

## Kontroller

Host concurrent trace testi ve aktif worker / uyuyan main CPU testi PASS.
Bilinen worker exclusive CPU ağırlığı %99,98. Interval union testi iç içe GPU
span'lerini toplamaz; sentetik actual/legacy GPU ayrımı ve dropped reddi PASS.
`tools/analyze_frame_trace.py` JSON özet + Chrome trace formatı üretir; frame
pencereleri iki guest flip request arasındadır, simulation tick değildir.

## Build 23 açılış regresyonu ve düzeltmesi

İlk sürüm siyah ekranda kaldı. CPU tanısı ppu_thread_register_main içinde %93,9
exclusive ağırlık gösterdi (`out/step20-black-analysis.json`). cellGcmSys.c,
başlığı include araması yerine doğrudan ../../include yolu ile alıyordu.
Bu yüzden eski/yeni boyutlu weak g_ps3_ft tanımları karıştı; linker küçük eski
nesneyi seçti. Yeni names_lock alanı sonraki global bellekle çakışıp spin yaptı.
Bu tanı ekinin regresyonudur, oyun dosyası veya önceki optimizasyon hatası değil.

Düzeltme: türetilmiş cellGcmSys canonical diagnostic header'ı kullanır; g_ps3_ft
yalnız FrameTrace.cpp içinde güçlü tek tanım olur. Diğer ölçüm TU'ları extern
tanımı görür. Host concurrent test tekrar PASS. Build 24 ve include dependency /
strong-symbol kontrolü PASS; aynı bundle üstüne kurulum veriyi korudu.
Build 24 UUID: `02E57369-3272-314F-B75E-BF5E583917D2`. Yedi derleme
biriminin dependency dosyası aynı overlay başlığını gösteriyor; nm tek güçlü
`g_ps3_ft` tanımı gösteriyor. Kullanıcı gerçek oynanışa ulaşıldığını doğruladı.

## Cihaz ölçüm sırası

Oynanış teyidi → ölçüm kapalı sabit kamera baz kaydı → yalnız timeline → tekrar
ölçüm kapalı → CPU+timeline → tekrar ölçüm kapalı. Isı, pil ve shader/pipeline
sayaçları aynı pencerelerden kaydedilir. Aktivasyon yükü ile termal drift ayrılır;
uyuşmayan koşullarda kesin karşılaştırma yapılmaz. Otomatik kapanış süresi yok.


## Gerçek iPhone sonuçları — build 24

Kullanıcı Cole'u kontrol edebildiğini ve kamerayı sabit bıraktığını doğruladı.
Aynı süreç PID 11328; `--boot --spu-copy-off --profile-cpu --diagnose-frame`.
RZ bağlı değil, native SPU kopyalama kapalı. Otomatik kapanış yok. Önce 2 s
kayıt sağlık kontrolü, sonra OFF 30 s → trace 10 s → OFF 30 s → CPU 30 s
(içinde trace 10 s) → OFF 30 s. Cihaz oyunda açık bırakıldı; yeniden başlatılmadı.

| Pencere | Medyan HUD kare ortalaması | HUD FPS medyanı |
| --- | ---: | ---: |
| Önce OFF | 266,72 ms | 3,5 |
| Yalnız trace | 268,95 ms | 3,5 |
| Arada OFF | 268,28 ms | 3,5 |
| CPU kaydı 30 s | 268,66 ms | 3,5 |
| CPU + trace ortak bölüm | 266,98 ms | 3,5 |
| Sonra OFF | 266,46 ms | 4,0 |

HUD FPS kısa pencere nedeniyle 3,5/4 basamaklanır; 4,0 medyanını optimizasyon
kazancı saymıyoruz. Aktivasyonun büyük bir etkisi görünmüyor; bu kısa tek sahne,
kesin overhead yüzdesi vermez. OFF demek ölçüm başlıklarının binary'den çıkarılması
değil, kayıtların kapalı olmasıdır; instrumentation-free binary karşılaştırması yok.
Bütün pencerelerde thermal_state=2 (serious), pil %95; sabit thermal kategori
sabit CPU frekansı garantisi değildir. Soğuk cihazın azami performansı ölçülmedi.
Pipeline sayısı 1036'da sabit, failure/Metal hata 0. Footprint yaklaşık
954–968 MB; yeni shader derleme dalgası bu pencereleri açıklamıyor.

İki ayrı 10 s trace'in her birinde 37 flip, 35 iç kare aralığı, 111 commit ve
111 gerçek GPU execution kaydı var. Kayıp olay 0, GPU sonucu eksik commit 0.
Yalnız trace / CPU+trace medyanları:

| Ölçüm | Yalnız trace | CPU + trace |
| --- | ---: | ---: |
| Guest flip aralığı | 265,96 ms | 266,98 ms |
| Backend GPU interval birleşimi / kare | 36,73 ms | 36,03 ms |
| RSX acquire bekleme birleşimi / kare | 136,88 ms | 137,22 ms |
| FIFO drain duvar süresi / kare | 118,74 ms | 118,14 ms |
| CPU'nun GPU bitişini beklemesi / kare | 14,15 ms | 14,03 ms |
| Readback duvar süresi / kare | 3,10 ms | 3,12 ms |

Satırlar toplanamaz: iç içe/örtüşen duvar aralıklarıdır. GPU zamanlarının birleşimi
10 s pencerenin yaklaşık %13,3–13,7'si; donanım utilization sayacı değildir.
Kapsanan Metal komut tamponları içinde display yaklaşık 24 ms ve iki ara flush
vardır. Önceki HUD GPU süresi tek display tamponuyla sınırlıyken burada backend'in
11 commit yeri ölçülüyor. `eng_metal_flush` (derived renderer overlay) bu sahnede
çalışan iki commit yolunu içerir.

`cellGcmSys.c:gcm_rsx_process_fifo_unlocked` içindeki ACQUIRE beklemeleri:
`0x870` 38 olay, medyan 77,16 ms; `0x890` 37 olay, medyan 60,10 ms.
Ortak kayıtta pencereye kırpılmış toplam bekleme 5,156 s; bu bekleme aralıklarıyla
kapsanan GPU execution aralıklarının kesişimi 0 s. Bu, yalnızca bu kuyrukların
ölçülen işi için geçerlidir. Beklemeyi kaldırmak doğru optimizasyon değildir;
grafik verisinin üreticisini bulup hızlandırmak gerekir. Etiketi yazan kesin
SPU job/işlevi henüz saptanmadı. Eski kaynak yorumları bu atamanın kanıtı değildir.

CPU profili: 30,018 s, 13.981 satır, 1330 tick, error=0, truncated=0.
Executable UUID ile atos eşleşti. Thread CPU delta ağırlıklarıyla SPU %84,92,
renderer %7,23, PPU %6,73, diğer %1,12. Bunlar kare gecikmesi yüzdeleri değildir.
En yoğun çözülen self işlevi `datamod_00821080_spu_func_00007320` %9,27;
sonraki `datamod_00820480_spu_func_00006F80` %5,22 ve
`jobmod_c6e7383dc013_e5400_spu_func_00009248` %3,85.
Sistem/çözülemeyen PC'ler %10,27; yok sayılmadı. Mach TH_STATE_RUNNING hazır/runnable
thread'i de kapsayabilir; CPU delta toplamı gözlenir, işlevlere dağıtımı örnekleme
tahminidir. En yoğun işlevin kritik bağımlılığın üreticisi olduğu kanıtlanmadı.

Trace ile CPU saatleri arasında 44093,577075542 s offset düzeltildi.
Aynı 10 s'ye kırpılan CPU kaydı 4614 satır; SPU yaklaşık %84,97 ve aynı
ilk üç oyun işlevi önde. PPU native-id/name eşlemesi kaydedildi: örneğin
`Edge Geom Task Kicker`, `SPU Light Task Kicker`. **SPU native-id eşlemesi bu kayıtta
boş:** ilk eşleme arming penceresinde filtrelenip pencere boyunca tekrar
üretilmiyor. Bu nedenle SPU kanal-id zaman çizelgesi ile tek native thread/job
arasında kesin join yapılmadı. Bu sınırlama bulguları üretici kanıtı yapmayı engeller.

## Karar ve sonraki dar teşhis

1. Baskın sorun bu sahnede GPU'nun sürekli çizim yapması değil; CPU/SPU işi ve
   RSX'in üretici beklemesi öne çıkıyor. Bellek entitlement'ı veya çözünürlük ilk
   müdahale olarak seçilmedi. GPU'nun 36 ms işi yine de ileride 30 FPS için önemlidir.
2. Sonraki ölçümde yalnız `0x870/0x890` label yazılarına giden SPU DMA transferi
   (özellikle `mfc_do_transfer`) adres/değer, SPU context, image/job ve guest PC ile
   izlenecek; RSX ACQUIRE release ile eşlenecek. Doğrudan guest PPU store olasılığı
   ayrıca kontrol edilmeli. Genel her-store izleme eklenmemeli.
3. SPU native-id eşlemesi arming sonrası ilk uygun olaya taşınmalı; ardından kritik
   üretici/job'un CPU maliyeti ayrılıp tek bir optimizasyon seçilmeli. İşlev/job
   etiketleri gözlenen sınırlarla doğrulanmalı. Bu takip ölçümü henüz uygulanmadı.
4. Sonrasında aynı sabit sahnede seçenek açık/kapalı A/B; görüntü doğruluğu, çökme,
   p95 ve ısınma birlikte değerlendirilecek. Bu oturum FPS artışı iddiası içermez.

## Kanıtlar ve tekrar üretim

Ham veriler Git dışındaki `out/step20-gameplay-{trace-only,combined-trace}.csv`,
`step20-gameplay-cpu.csv`, `step20-gameplay-performance.csv`, thread-map;
`step20-session-summary.json` ve `step20-dependency-summary.json` içindedir.
Derlenmiş binary UUID klasörü `build/bces01229/symbols/` altında korundu.
Capture sırası `out/step20-capture-session.py` ve pencere işaretlerinde saklıdır.

```sh
cd /Volumes/monssd/Infamous2-iOS
python3 -m unittest discover -s tools -p test_frame_trace_analysis.py
python3 tools/analyze_frame_trace.py out/step20-gameplay-combined-trace.csv --output out/step20-gameplay-combined-trace-analysis.json
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp python3 tools/analyze_native_profile.py out/step20-gameplay-cpu.csv --binary build/bces01229/symbols/02E57369-3272-314F-B75E-BF5E583917D2/Infamous2Game --label 'Cole stationary gameplay' --output out/step20-gameplay-cpu-analysis.json
```

Cihaz kontrol dosyaları `Documents/frame-trace-control.txt` ve
`Documents/cpu-profile-control.txt`: `start BENZERSIZ_TOKEN SANIYE`.
Kopyalama için `xcrun devicectl device copy to/from --device
00008130-001129E00243001C --domain-type appDataContainer --domain-identifier
dev.infamous2.iosprobe --source ... --destination ...` kullanılır.
Uygulama yeniden başlatılmadan önce kontrol dosyaları `idle` yapılmalı;
yoksa aynı token yeni süreçte intro sırasında yeniden tetiklenir.
Analiz `.chrome.json` zaman çizelgesi de üretir; Perfetto/Chrome trace viewer ile
incelenebilir. Ekran görüntüsünden oyun doğrulaması yapılmadı; gerçek oynanış
kullanıcı tarafından doğrulandı, sayaçlar da ilerledi. Simülatör kullanılmadı.
