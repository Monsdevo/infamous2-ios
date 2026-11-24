# SSAO cihaz ölçümü — 26 Ekim 2026

Build 32 aynı binary üzerinde karşılaştırılır. C = Metal aydınlatma + Metal
SSAO; B = Metal aydınlatma + özgün SPU SSAO. Native copy kapalı; özgün SPU
half-depth ve her iki input writeback'i korunur. Yeni oyun/runtime değişikliği,
derleme veya kurulum yapılmaz.

İlk okunan PID 14065 / 25 Ekim raporu eskiydi; çalışan süreç bulunmadı.
Yeni C süreci PID 14564 açıldı, `--diagnose-frame` ile yalnız dışarıdan istenen
kısa iz hazırlandı. İzin verilen `--seconds` kapanma sınırı kullanılmadı.
Kullanıcı ilk oynanış/kamera teyidi verince ölçüm başlatılır.

Koşullar: ilk Cole kontrol sahnesi, karakter ve kamera sabit; kullanıcı harici
soğutma uyguluyor. Karşılaştırmada aynı soğutma korunmalı. Thermal state 0
normal zorunlu. Bu sınıflama aynı fiziksel sıcaklık/frekans garantisi değildir.
Sonuçlar bu soğutma koşuluna aittir; soğutmasız uzun oyun performansı sayılmaz.

Önce 30 s hafif sayaç penceresi; sonra ayrı 10 s trace. Aktif scene, aynı PID/
session, artan monotonic zaman, yeni pipeline sayısı, GPU hataları ve SSAO
fault'ları kontrol edilir. Geçerli C ölçümünde SSAO pass/binding/skipped_tiles
artışı gerekir; yalnız requested=true optimizasyon kanıtı değildir.

Host `capture_device_window.py` SSAO counter delta/fault kontrolü eklendi;
iPhone uygulaması değişmedi. Rapor alanı yoksa delta null'dır, sıfır varsayılmaz.

Cihazdan 1936 byte `ssao-pass-capture.bin` alındı; ilk geçerli tablonun
snapshot'ıdır, belirli bir oynanış karesi/oturumu olarak kabul edilmez.
Beş BCES module adresi, stream zinciri ve pitch'ler beklenen düzende; depth
0x47877B80, normals 0x474F3B80, half depth 0x47BFBB80, half AO 0x47CDCB80.
Bu metadata kontrolüdür; SPU/GPU görüntü eşdeğerliği kanıtı değildir.

Kanıt: `out/ssao-real-passes-20261026.bin` ve `.json`. Oyun verisi/snapshot
Git'e eklenmez. İlk eski rapor ve canlı raporlar ayrı dosyalarda tutulur.

Komut örneği:

```sh
python3 tools/capture_device_window.py --device 00008130-001129E00243001C --output out/UNIQUE-ssao-window --seconds 30 --scene 'Kullanıcının teyit ettiği sabit ilk oynanış' --max-thermal-state 0
python3 tools/analyze_frame_trace.py out/UNIQUE-trace.csv --output out/UNIQUE-trace-analysis.json
```

## C — Metal SSAO açık

Kullanıcı ilk oynanış/kamera sabit teyidini verdi. PID 14564, 30,999830 s,
191 guest present / 191 Metal present: **6,161324 FPS**, ortalama sayaç aralığı
162,303 ms/kare. 10 snapshot thermal normal, yeni pipeline 0; SSAO pass/binding
+191, skipped tiles +43689, fallback +0, SSAO/Metal fault 0. Footprint
1031294376–1035406760 byte. Tamamlanan CB delta 190/submitted191 sınırda bir
in-flight iş olabilir; tamamlandı sayacıyla FPS hesaplanmadı.

Ayrı 10 s iz: doğru build 32 UUID/token, 57 tam iç kare. Medyan 158,453 ms,
p95 198,919 ms, GPU execution union medyan 52,291 ms/kare. 29 acquire'ın
29'u gerçek label DMA yazısıyla tek eşleşti, eksik provenance grubu 0.
Ham trace ile hafif pencerenin FPS/p95'i aynı veri değildir.

C analizi: `out/ssao-C-result-20261026.json`, pencere
`out/ssao-C-gameplay-window-20261026`, ham iz `out/ssao-C-gameplay-trace-20261026.csv`.
B kontrolü için aynı kurulu binary SSAO kapalı/aydınlatma açık yeniden başlatıldı.

Kontrol PID 14577'de metal_lighting_requested=true, metal_ssao_requested=false,
SSAO GPU pass/skip sayaçları sıfır olarak doğrulandı. Kullanıcı aynı ilk
oynanışta sabit bıraktığını teyit etti. Menüde SSAO SPU sürümünün Metal'e göre
bariz, yaklaşık yarı FPS gösterdiğini gözledi; menü için kontrollü sayaç
penceresi alınmadığından bu gözlem oynanış kazanç hesabına dahil edilmez.

## B — SPU SSAO kontrolü ve karşılaştırma

PID 14577, 31,999097 s / 155 guest frame ve Metal present: **4,843887 FPS**.
10 snapshot thermal normal, yeni pipeline 0, SSAO pass/binding/skip delta 0,
aydınlatma +155 pass; hata yok. Footprint 1027034560–1031130560 byte.
Ayrı 10 s trace doğru build/token: 45 iç karede medyan 204,971 ms,
p95 218,211 ms; GPU execution union medyanı 51,862 ms/kare. 62 acquire'ın
62'si gerçek label DMA yazısıyla tek eşleşti, eksik provenance grubu 0.

| Metrik | B: SPU SSAO | C: Metal SSAO |
|---|---:|---:|
| Hafif pencere FPS | 4,843887 | 6,161324 |
| Sayaçlardan ortalama ms/kare | 206,446 | 162,303 |
| Ayrı trace kare medyanı ms | 204,971 | 158,453 |
| Ayrı trace kare p95 ms | 218,211 | 198,919 |
| GPU execution union medyan ms/kare | 51,862 | 52,291 |
| 0x890 acquire union medyan ms/kare | 69,702 | 0 |
| 0x890 beklemesi olmayan kare | 0/45 | 40/57 |

**Bu pilotta +%27,198 FPS**, sayaç ortalamasından **44,143 ms/kare** tasarruf;
ham kare medyanından 46,518 ms düşüş, p95'ten 19,292 ms düşüş görüldü.
SSAO beklemesinin 69,7→0 ms medyan farkını kare kazancına birebir eklemiyoruz:
CPU/GPU işleri örtüşür, görevlerin sıralanışı ve yeni GPU işi hesaba katılmalı.
GPU union farkı da SSAO shader'larının tek başına süresi değildir.

B izinde bitişten yalnız 0,209 ms önce bir CB commit'i var; execution olayı
iz sınırının dışında kalmış. Saklanan iç kare aralıklarının dışında. İz sonrası
raporda 5456 submitted = 5456 completed, hata 0, thermal normal görüldü;
bu tek sınır olayı kayıp GPU işi veya çökme diye yorumlanmadı.

Sınırlar: **tek C/B sıralı pilot**, üç dengeli çift veya deterministik replay
değil. Her iki ilk sahne/kamera kullanıcı teyitli; NPC/animasyon zamanlaması
birebir aynı değil. Normal termal sınıf ve aynı harici soğutma, birebir aynı
fiziksel sıcaklık/frekans garantisi vermez. Soğutmasız uzun oyun ve diğer
sahneler için FPS garantisi yok. Gerçek SPU/Metal ara çıktı/tam görüntü
eşdeğerliği ayrı açık iş; sayaçlar yalnız GPU yolunun etkinliğini doğrular.

Birleşik kanıt: `out/ssao-comparison-20261026.json`; B/C sonuçları ve ham trace
aynı isim ailesinde. Oyun/runtime binary'si değiştirilmedi, yeniden kurulum
yapılmadı. Sonunda trace komutu idle yapılıp Metal aydınlatma + Metal SSAO açık
normal süreç yeniden başlatıldı (`out/ssao-measure-restored-C-20261026.json`).

Sıradaki iş: doğruluk için gerçek SSAO ara çıktıları karşılaştırması; daha geniş
kabul için dengeli tekrarlı A/B. Yeni optimizasyon hedefi seçmeden önce kalan
SPU/PPU/RSX native CPU yükü yeniden profillenmeli. Bu iz tek başına kalan
~160 ms'nin hangi fonksiyona ait olduğunu belirlemez.
