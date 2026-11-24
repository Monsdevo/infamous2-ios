# Build 64 · Kompakt vertex aktarımı

`dc_fetch` yolunda düzenli, tek tabandan çözülen üç bileşenli
`SNORM16` öznitelikleri Metal'e 16 baytlık float yerine 8 baytlık
`Short4` olarak aktarılır. Vertex shader özgün normalleştirmeyi yapar.
Diğer öznitelikler mevcut CPU açma yolunu kullanır. Pipeline varyantı
üretilemezse çizim özgün düzenle yeniden hazırlanır. Deney başlangıçta
kapalıdır ve yalnız `--compact-vertex-control` ile değiştirilebilir.

Release iPhoneOS derlemesi ve iPhone 15 Pro kurulumu tamamlandı. Mac M3
Metal doğrulamasında 65.536 signed değer özgün CPU dönüşümüyle bit
düzeyinde eşleşti. Aynı sınama oyunun HLSL çeviri yolu üzerinden de
geçti. Cihazda hem açık hem kapalı bataklık iskelesi yüzeyleri alındı.
Bu iki karede görünür geometri bozulması saptanmadı. Hareketli sahneler
ve oyunun diğer bölümleri ayrıca doğrulanmadı. İlk başlatmada deney
kapalıyken sunum durdu. Aynı kayıtla ikinci başlatma oynanışa ulaştı.

## Tekrar üretme

```sh
PYTHONPATH=tools python3 tools/prepare_bces_ios.py \
  --support-report out/bces-support-critical62.json --compact-vertex --renderer-stages
cmake -S cmake/bces-ios -B build/bces01229/ios
xcodebuild -project build/bces01229/ios/Infamous2BCESIOS.xcodeproj \
  -scheme Infamous2Game -configuration Release -destination generic/platform=iOS \
  -derivedDataPath build/bces01229/DerivedData -jobs 1
```

Cihazı `--boot --geometry-control --compact-vertex-control --rsx-legacy-on`
ile başlat. Aynı sahnede `geometry_device_control.command` üzerinden
`compact_vertex` değerini 0, 1, 0 sırasıyla değiştir. Pipeline derlemeleri
tamamlanınca her pencereyi ayrı kaydet.

```sh
PYTHONPATH=tools python3 tools/measure_compact_vertex.py --device "$DEVICE" \
  --mode 1 --thermal-state 2 --seconds 18 --output out/ios-compact64/perf-B
```

Ham zaman damgaları, görüntüler ve doğrulama kayıtları `out/ios-compact64`
altında. İmzalı uygulama kopyasının arm64 UUID'si
`11498AC4-A4BE-3C11-B493-D7A34FD5E4E7`.

## Cihaz sonucu

Aynı süreç, kayıt ve sabit kamera kullanıldı. Üç pencerede iOS termal
kategorisi 2, derlenmiş pipeline sayısı 595 ve Metal hata sayısı sıfırdı.
Sonuçlar uygulamanın gerçek kare sunum zaman damgalarından hesaplandı.

| Kompakt yol | Kare aralığı | Ortalama, ms | Medyan, ms | p95, ms | FPS |
| --- | ---: | ---: | ---: | ---: | ---: |
| A · Kapalı | 165 | 109,01 | 108,36 | 129,19 | 9,17 |
| B · Açık | 166 | 108,66 | 108,36 | 125,03 | 9,20 |
| C · Kapalı | 165 | 109,11 | 108,36 | 129,19 | 9,16 |

Açık pencere 512.937 kompakt çizim ve 519.804.824 bayt daha az
vertex staging kaydetti. Ortalama kare süresi iki kapalı pencerenin
ortalamasından 0,41 ms düşük. Medyan aynı kaldı. Bu tek açık pencere,
p95 farkının tekrarlanabilirliğini göstermez. Deney varsayılan kapalı
kalır.

A/B/A sonrasında aynı termal kategoride birer saniyelik iki zaman izi
alındı. Kapalı izde dört, açık izde üç tam kare var. Vertex hazırlığının
thread CPU medyanı 21,22 ms'den 16,93 ms'ye indi. İzlenen Metal
komutlarının meşgul sürelerinin kare başına medyanı 37,97 ms'den
40,34 ms'ye çıktı. Bu kısa iz, CPU tasarrufunun varlığını gösteriyor.
GPU farkının tekrarlanabilirliği ve kare sonuna ne kadar yansıdığı
bu örneklemle belirlenemez. Açık yolda eski açma sayacı kompakt
paketlemeyi kapsamadığından karşılaştırmada toplam vertex hazırlığı
kullanıldı.
