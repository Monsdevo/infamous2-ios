# Aşama 1 / Deneme 1 — cihaz testi, 25 Ekim 2026

Güncelleme: tile maskesi ve build 30 sinematik donması için
[ayrı güncel notu](lighting-tile-alpha-tr.md) okuyun. Aşağıdaki FPS karşılaştırması
maskesiz önceki binary içindir; yeni düzeltmenin FPS sonucu değildir.

## İlk Metal pilotu

Kullanıcı Cole'un kontrol edilebildiği ilk oynanış konumunu ve sabit kamerayı
teyit etti. Build 27 UUID A9022DCC-179A-3904-B456-722B2742C261; Metal aydınlatma,
SPU SSAO, native SPU copy kapalı. CPU profiler ve tile capture kapalı.

`out/phase1-exp1-B-window1/summary.json`: 32,999639 saniyede 149 guest present,
**4,5152 FPS**. 11 telemetri snapshot'ında thermal state 2 (serious), fiziksel
footprint 1023643072–1028836800 byte; yeni pipeline 0. Metal light 148 pass,
296 binding ve 106560 atlanan tile: pass başına 720 tile. Bu yalnız Metal
pilotudur; eski 3,8 FPS kaydı farklı koşullardan geldiği için A/B kazancı değildir.

Ayrı 10 saniyelik iz (`out/phase1-exp1-B-trace.csv`): 43 tam iç kare aralığının
medyanı 217,588 ms, p95 245,997 ms. GPU execution union medyanı 48,015 ms/kare,
RSX acquire union 71,888 ms/kare; CPU GPU wait 15,510 ms, readback 3,421 ms.
Bu sütunlar örtüşür, toplanmaz. İz kayıt maliyeti hafif sayaç penceresinden ayrıdır.
Aynı izde gerçek drawable sunumları ayrıca 45 olay, ilk–son aralıkta 4,567 FPS,
medyan 216,710 ms verdi (`out/phase1-exp1-B-display-cadence.json`).
52 acquire'ın 52'si kayıtlı label yazısıyla tek eşleşti; eksik provenance grubu 0.
0x870 için yalnız 6 acquire, medyan 5,186 ms; 0x890 için 46 acquire,
medyan 71,8545 ms. Kalan belirgin bekleme SSAO üreticisine bağlıdır; bu,
SSAO'nun bütün CPU süresi veya gelecekteki FPS kazancı ölçümü değildir.

## Doğruluk kapısı

SPU referans açılışında üç non-sky tile yakalandı; hepsinde 52 geçerli ışık
(21 point, 31 spot) var, ancak özgün SPU diffuse/specular çıktıları tamamen
sıfır. A17 Pro Metal replay: diffuse 5120 byte'ın 1280 alpha byte'ında +90;
RGB ve specular aynı. Fixture'lar `out/phase1-exp1-lit-fixtures/tile-0..2`,
rapor `out/phase1-exp1-lit-validation.json`. Mac Metal replay aynı farkı üretti.

Pinned portun `infamous2-lle/notes/spu_light/README.md` §5–6 açıklıyor:
hiç ışık tile culling'i geçmezse özgün iş tile'ı sıfırlar; en az bir ışık
geçen tile'ın ışık almayan piksellerinde bile alpha 90 paketlenir.
`reference.py` karşılaştırması da yalnız job-lit tile'ların alpha'sını doğrular.
Dolayısıyla sırf pikselin RGB'si sıfır diye alpha'yı sıfırlamak doğru bir genel
çözüm değildir. Orijinal tile seçim davranışı veya bütün tüketicilerde eşdeğer
semantik ayrıca doğrulanmalı. Hatalı bir per-pixel düzeltme eklenmedi.

Kullanıcı sahnelerde görünür aydınlatma farkı gözlemedi; bu faydalı bir görsel
kontrol, tam buffer eşdeğerliği kanıtı değildir. Gerçekten sıfırdan farklı SPU
aydınlatması içeren örnekler henüz doğrulanmadığından Deneme 1 kabul edilmedi,
SSAO optimizasyonu etkinleştirilmedi.

Build 28 tanı kodu lit-only/non-sky seçim ekledi. CMake yeniden configure
edilmediği için uygulama plist'i hâlâ 27 yazdı; gerçek binary UUID
4DE058B1-5382-3203-89B2-1A87502CAB1A (önceki Metal binary'den farklı).
Build 29 hazırlığında CMake yeniden configure edildi; lit-only mod artık
özgün SPU çıktısı da tamamen sıfırsa slotu serbest bırakıp sonraki uygun
örneği bekler. Üç snapshot sınırı korunur. Zero-output ret sayacı raporda görünür.
Normal oyun algoritması değişmedi. Aynı gerçek 52 ışıklı fixture'ın yeni
seçici tarafından reddi test edildi (beklenen exit 6).

## Isınma nedeniyle geçersiz karşılaştırma

Kullanıcı SPU referansında aynı ilk oynanış konumuna geldi; cihazın önceki
Metal denemesinden daha sıcak olduğunu bildirdi. `out/phase1-exp1-A-window1`
ilk snapshot'ında thermal state 3 (critical) görüldü. Araç 30 saniye yük
ölçümüne devam etmedi. Bu koşudan FPS kazancı/yavaşlama yüzdesi çıkarılmaz.
Kullanıcının çizgi roman için gözlediği 6–10 ve önceki 25–30 FPS de sıcaklık ve
sahne farkı kontrol edilmediği için kontrollü A/B değildir.

## Araçlar ve komutlar

```sh
python3 tools/capture_device_window.py --device 00008130-001129E00243001C --output out/UNIQUE-window --seconds 30 --scene 'Teyit edilmiş sahne ve kamera'
# Ham kare aralıkları ayrı trace kaydından:
python3 tools/analyze_frame_trace.py out/phase1-exp1-B-trace.csv --output out/phase1-exp1-B-trace-analysis.json
python3 tools/analyze_frame_dependencies.py out/phase1-exp1-B-trace.csv --binary build/bces01229/symbols/A9022DCC-179A-3904-B456-722B2742C261/Infamous2Game --output out/phase1-exp1-B-dependencies.json
# Derlenmiş yerel replay (gerçek eşlenmiş fixture'ı kullanır):
build/bces01229/lighting-replay out/phase1-exp1-lit-fixtures/tile-1 /Volumes/monssd/Infamous2-iOS/out/UNIQUE-replay
```

Sayaç aracı aynı process/session ve ilerleyen monotonic rapor zamanı arar;
stale rapor, kritik sıcaklık, Metal hatası ve sıfır kareyi geçerli saymaz.
HUD pencere ortalamalarından ham kare p95'i türetmez. Aynı thermal=2 bile aynı
sıcaklık/frekans demek değildir; üç dengeli A/B çifti henüz yapılmadı.

## Sıradaki teknik iş

Build 29 kaynak/derlemesi hazır: UUID 7F51A8E1-E402-331F-A256-78CA111DB71F.
Bu not yazılırken telefona kurulmadı; soğutma için mevcut referans süreci
korundu. Yeni `--spu-lighting --validate-lit-lighting` çalıştırması gerçekten
ışık alan çıktı yakalayacak. `lighting_validation_zero_outputs_rejected`
artarken completed=0 ise bu bir shader başarı sonucu değildir; uygun örnek
henüz bulunamamıştır. `tools/replay_lighting_tile.mm` bu aynı eşlenmiş girdileri
Mac Metal'de oyunu boot etmeden tekrar oynatır.

Önce gerçek lit tile'larda matematik/packing farkını belirle; empty-tile
maskesinin özgün AABB/frustum/spot-cone culling koşullarını koruyan Metal
karşılığını bu referansa karşı sınamadan genel alpha değişikliği yapma.
Aynı binary/mod ve eşleşen termal koşullarda A/B tamamlanıp doğruluk kapısı
geçilmeden SSAO'yu açma. Bu oturum bir FPS artışı kabulü değildir.

## Soğutma sonrası SPU referansı — tamamlandı

Kullanıcı telefonu soğutup devam istedi. İlk okunan rapor eski PID 12644'e
ait, durmuş oturum raporuydu; güncel sıcaklık diye kullanılmadı. Sonlandırma
bayrağı olmadan yapılan öne getirme isteği yeni PID 12758'i başlattı. Kullanıcı
bu oturumda tekrar Cole'un kontrol edildiği ilk sahneye ulaştığını ve kamerayı
sabit bıraktığını doğruladı. Yeni kurulum yapılmadı; telefondaki tanı binary'si
UUID 4DE058B1-5382-3203-89B2-1A87502CAB1A, SPU reference, native copy-off.
Tile karşılaştırmalarının üçü de oynanış ölçümünden önce tamamlanmıştı.

İlk hafif pencere: 31,999932 saniyede 121 guest frame = 3,78126 FPS,
thermal 0; iki yeni pipeline oluştu. Bu yüzden ısınma/derleme etkisini ayırmak
için aynı süreç/sahnede ikinci pencere alındı. İkinci pencere:

- `out/phase1-exp1-A-cooled-window2/summary.json`
- 32,000498 saniyede 127 guest frame = **3,96869 FPS**;
- 127 Metal present / completed;
- thermal state 0 (normal), yeni pipeline 0, Metal/pipeline hatası 0;
- fiziksel footprint 955338104–955469176 byte (yaklaşık 911 MiB);
- Metal lighting pass/binding/skipped tile sayıları sıfır: gerçek SPU referansı.

Ayrı 10 saniyelik izde 94842 satır, dropped=0, UUID eşleşti. 37 tam iç kare
aralığı medyan 250,051 ms, p95 274,554 ms. GPU execution union medyanı
37,856 ms/kare, toplam RSX acquire union 131,878 ms/kare. 80 acquire'ın
78'i tek kayıtlı DMA yazısıyla eşleşti; iki eşleşmeyen acquire kayıt penceresi
başlangıcı/sonunu aşıyor. Eksik provenance grubu 0. Bunlar yeni bir yazıcı veya
oyun hatası diye sınıflandırılmadı; sınır kayıtları ayrı tutuldu.

Kare bazında her etikete ait bekleme aralıklarının union'u hesaplandı;
hiç bekleme gözlenmeyen kareler sıfır olarak dahil edildi. Yalnız beklenen
olayların medyanını bütün karelerin medyanı diye kullanmadık:

| Ölçüm | SPU / soğutulmuş, thermal 0 | Önceki Metal / thermal 2 |
| --- | ---: | ---: |
| Hafif pencerede gerçek kare/süre | 3,969 FPS | 4,515 FPS |
| İzde kare aralığı medyanı | 250,051 ms | 217,588 ms |
| İzde kare aralığı p95 | 274,554 ms | 245,997 ms |
| Aydınlatma 0x870 bekleme union medyanı/kare | 70,929 ms | 0 ms |
| SSAO 0x890 bekleme union medyanı/kare | 59,356 ms | 71,888 ms |
| Kapsanan GPU execution union medyanı/kare | 37,856 ms | 48,015 ms |

Metal izinde 43 tam kare penceresinin 37'sinde 0x870 beklemesi kaydedilmedi;
önce bildirilen ~5 ms, yalnız bekleme olan altı olayın medyanıydı.
İz eşiğinin altındaki beklemeler ve ölçüm kapsamı dışında kalan işler için
mutlak sıfır çalışma süresi iddiası yok. Aydınlatma beklemesinin azalmasıyla
GPU maliyetinin artması ve SSAO'nun beklenen bağımlılık olarak kalması tutarlı.
Tablodaki CPU/GPU/bekleme süreleri örtüştüğünden birbirinden çıkarılarak veya
toplanarak yeni FPS tahmini yapılmaz.

**Kabul durumu hâlâ açık.** Ham FPS oranı yaklaşık 1,138 (%13,8 gözlenen fark),
fakat thermal 0/2 farklı; binary UUID'leri de farklı (ikinci tanı kodu yalnız
capture seçimini değiştirdi). Bu yüzde kontrollü/tekrarlanmış optimizasyon
kazancı diye sunulmaz. En az üç dengeli, aynı binary ve termal koşullu A/B çifti
yapılmadı. Önceden saptanan empty-tile alpha farkı ve gerçek nonzero lit tile
karşılaştırması kapanmadığı için SSAO optimizasyonu açılmadı.

Toplu analiz: `out/phase1-exp1-A-cooled-vs-B-pilot.json`.
Ham iz/analiz/bağımlılık: `out/phase1-exp1-A-cooled-trace.csv`,
`out/phase1-exp1-A-cooled-trace-analysis.json`,
`out/phase1-exp1-A-cooled-dependencies.json`.
Kontrol dosyası tekrar `idle` yapıldı; profiler kapalı, trace tamamlandı.
Son rapor PID 12758, thermal 0, Metal/pipeline hatası 0. Oyun açık bırakıldı;
build 29 kurulmadı, kaynakta GPU/oyun algoritması değiştirilmedi.

## Aynı normal sıcaklıkta Metal karşılığı — tamamlandı

Kullanıcı son bir Metal testi istedi; aynı kurulu binary yeniden başlatıldı,
yeni kurulum/oyun kodu değişikliği yapılmadı. PID 12801, UUID
4DE058B1-5382-3203-89B2-1A87502CAB1A: soğutulmuş SPU testinin binary'siyle
aynı. `--boot --spu-copy-off --diagnose-frame -performance.metal-lighting YES`;
CLI'ye tek tireli uygulama argümanını geçirmek için bundle adından önce `--`
ayracı kullanıldı. Bu açılışta tile capture ve CPU profiler kapalı. SSAO SPU'da.

Kullanıcı yine ilk kontrol edilebilir Cole sahnesinde kamerayı sabit bıraktığını
teyit etti. `capture_device_window.py` artık isteğe bağlı
`--max-thermal-state 0` ile yalnız normal sıcaklığı kabul ediyor; herhangi bir
örnekte durum 1 veya üstüne çıkarsa pencere başarısız sayılıp duruyor. Varsayılan
eski davranış (critical düzeyinde durma) korunuyor. Python syntax kontrolü geçti.

Metal'in 10 snapshot'ı da thermal 0; 32,000475 saniyede 159 guest frame =
**4,96868 FPS**. Metal submitted/completed/presented farkları da 159. Yeni
pipeline 0; 159 light pass, 318 binding, 114480 atlanan tile (720 tile/pass).
Fiziksel footprint 961105272–966102392 byte. Metal ve lighting fault sayacı,
pipeline failure ve memory warning sıfır. Sayaç penceresinde ağır trace kapalıydı.

Ardından ayrı 10 saniyelik iz alındı: dropped=0, 47 tam iç kare aralığı,
59 acquire'ın tamamı kayıtlı DMA yazısıyla tek eşleşti. Eksik provenance grubu 0;
151 GPU commit'in execution kaydı var. Son raporda thermal 0, hata 0.

| Gösterge | SPU normal | Metal normal | Gözlenen değişim |
| --- | ---: | ---: | ---: |
| Hafif pencere FPS | 3,96869 | 4,96868 | +%25,20 |
| Ham kare aralığı medyanı | 250,051 ms | 196,975 ms | -%21,23 |
| Ham kare aralığı p95 | 274,554 ms | 213,984 ms | -%22,06 |
| Aydınlatma wait union medyanı/kare | 70,929 ms | 0 ms | Çoğu karede bekleme kaydı yok |
| SSAO wait union medyanı/kare | 59,356 ms | 65,462 ms | SPU bağımlılığı sürüyor |
| Kapsanan GPU execution union medyanı/kare | 37,856 ms | 48,198 ms | GPU yükü artıyor |

Metal'in 47 tam kare penceresinin 39'unda aydınlatma beklemesi kaydedilmedi;
bu, eşiğin altında kalan beklemeler veya aydınlatmanın GPU çalışma süresi için
mutlak sıfır iddiası değildir. Paralel/örtüşen süreler toplanmadı.

**Performans pilotu olumlu:** aynı binary ve aynı raporlanan normal termal
seviyede bu sahnede FPS +%25,2, medyan ve p95 kare süreleri iyileşiyor. Bu tek
ardışık A/B pilotudur; üç dengeli A/B/B/A tekrar veya uzun süreli kararlılık
sonucu değildir. Kullanıcı başlangıç konumu/kamerayı teyit etti; aynı kaydedilmiş
simülasyon anının birebir replay'i yapılmadı. SPU tarafının sınırlı doğrulama
capture'ları ölçümden önce tamamlandı; Metal tarafında capture kapalıydı.

Genel optimizasyon kabulü hâlâ açık: empty-tile alpha farkı ve sıfırdan farklı
SPU ışık çıktısının eşlenmiş doğrulaması kapanmadı. Bunları çözmeden SSAO yolu
açılmadı. Sonuç önceki farklı sıcaklıkta +%13,8 gözleminin yerine kullanılan
**normal/normal performans pilotudur**; uzun vadeli/genel FPS vaadi değildir.

Kanıtlar: `out/phase1-exp1-B-normal-window1/`,
`out/phase1-exp1-B-normal-trace.csv`, `out/phase1-exp1-B-normal-trace-analysis.json`,
`out/phase1-exp1-B-normal-dependencies.json`,
`out/phase1-exp1-normal-comparison.json`. Ham trace UUID'siyle iki koşunun aynı
binary olduğu doğrulandı; iki hafif pencerede de yeni pipeline sayısı sıfır.

Tekrar ölçüm komutu (dizin adı yeni olmalı):

```sh
python3 tools/capture_device_window.py --device 00008130-001129E00243001C --output out/UNIQUE-normal-window --seconds 30 --max-thermal-state 0 --scene 'Teyit edilmiş sabit ilk oynanış'
```

Kontrol dosyası tekrar `idle` yapıldı; trace tamamlandı, CPU profiler kapalı.
Mevcut oyun Metal aydınlatmayla açık bırakıldı; yeni paket kurulmadı.
