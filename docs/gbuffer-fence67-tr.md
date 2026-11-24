# Build 67 · G-buffer gönderimlerini ayırma

İlk deney, derinlik gönderiminin tamamlanma kanıtını onu takip eden normal
tamponu geri okumasında yeniden kullanır. Derinlik ve normal guest
kopyaları aynı blit noktalarında, özgün biçim ve bellek görünürlüğüyle
üretilir. SSAO pass 0 ve SPU fallback akışı korunur. Derinliğin ilk
senkron beklemesi bu build'de sürer.

`rsx_draw_engine_write_back_to` tamamlanmış derinlik gönderiminin
kimliğini normal blit'e taşır. `bces_metal_gbuffer_reuse` yalnız aynı
gönderim hâlâ son gönderimse, normal yüzey paylaşımlıysa, boyutlar
eşleşiyorsa ve birikmiş tek kayıt bu yüzeyi **okuyan** GPU snapshot'ıysa
onaylar. Snapshot sıradaki komut tamponuna bırakılır. Başka bir GPU
yazma kaydı, private yüzey veya farklı gönderim görülürse özgün
senkron yol seçilir.

İlk uygun normal yüzey, aynı karede ikinci fence öncesi ve sonrasında
3.686.400 RGBA baytı üzerinden karşılaştırılır. Bu doğrulama karesinde
özgün yol çalışır. Sonraki kareler ancak eşleşme sağlanırsa uygunluk
kontrolünü yeniden geçerek fence'i atlayabilir. Deney varsayılan kapalıdır.
`--geometry-control --gbuffer-fence-control` ile açılan geliştirme
oturumunda komut alanı `gbuffer_fence` 0 veya 1 olabilir.

```sh
PYTHONPATH=tools python3 tools/prepare_bces_ios.py \
  --support-report out/bces-support-critical62.json --gbuffer-fence --renderer-stages
cmake -S cmake/bces-ios -B build/bces01229/ios
# Release / generic platform=iOS / -jobs 1, mevcut geliştirme imzasıyla.
```

Bu, [iki fence tasarımının](gbuffer-fence-audit-tr.md) ilk güvenli
adımıdır. Tek başına tam boy geri okumayı veya 14–17 ms'lik ilk fence'i
kaldırmaz. İkinci fence'in ölçülen bütçesi yaklaşık 1–2 ms'dir.

## iPhone 15 Pro sonucu

İmzalı Release build kuruldu ve cihaz kilidi açılınca çalıştırıldı.
UUID `7D192E11-5A1E-3EB2-84E3-587F67D4260E`. İlk FPS referansı
pencerede yeni shader derlendiği için reddedildi. Geçerli üç pencere
aynı süreç, sabit bataklık kamerası ve termal kategori 2 ile alındı.

| Mod | Kare aralığı | Ortalama, ms | Medyan, ms | FPS |
| --- | ---: | ---: | ---: | ---: |
| A kapalı | 168 | 107,56 | 108,36 | 9,30 |
| B açık | 170 | 106,17 | 108,36 | 9,42 |
| C kapalı | 166 | 108,71 | 108,36 | 9,20 |

İlk 3.686.400 baytlık normal karşılaştırması birebir eşleşti.
B penceresinde 169 fence atlandı ve uygunluk reddi sıfırdı. Açık ve
kapalı görüntülerde görünür geometri/aydınlatma sorunu görülmedi.
Bu görüntüler farklı oyun kareleri ve kapalı görüntüde zamanla
kaybolan eğitim yazısı var. Tüm oyun ve fallback tetikleme testi
yapılmadı.

Ayrı birer saniyelik GPU izlerinde dört tam kare/mod doğrulandı.
İki gerçek geri okuma da devam etti. İzlenen komut gönderimi karede
3'ten 2'ye indi. Toplam senkron bekleme medyanı yaklaşık 15,09 ms'den
14,12 ms'ye düştü. Açık izde bir kare 20,07 ms bekledi.
Profilsiz ortalama kare farkı iki kapalı pencerenin ortalamasına göre
1,96 ms. Tek açık pencere ve değişmeyen medyan nedeniyle tekrarlanabilir
oynanış kazancı kabul edilmedi. Deney tekrar kapalıya alındı.

Ham izler, oyun yüzeyleri ve gerçek sunum zaman damgaları
`out/ios-gbuffer67` altında. Aynı sabit sahnede tekrar ölçüm:

```sh
PYTHONPATH=tools python3 tools/measure_gbuffer_fence.py \
  --device "$DEVICE" --seconds 16 --output out/ios-gbuffer67/perf-new
```
