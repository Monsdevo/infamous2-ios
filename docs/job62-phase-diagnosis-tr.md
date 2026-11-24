# 1774dd komut üretim aşamaları

Build 62, Build 59'un 82 destek nesnesini aynen kullanır ve yalnızca
`1774dd` nesnesini tanı işaretleriyle yeniden derler. Açılışta
`--diagnose-frame --diagnose-job-phases` ile etkinleşir. FIFO'nun
her sözcüğünü kaydetmek yerine, yazma konumu ilerideyken kendi adresine
atlayan komutta durduğu ve aynı komutun değiştiğini gördüğü anı kaydeder.
Adres değişirse bölüm çözüldü olarak sayılmaz. CPU saati SPU worker'ına,
duvar saati ortak iz zaman çizelgesine aittir.

| Ölçülen bölüm | Sınırlar |
| --- | --- |
| Komut üretim çağrısının bütünü | `12C50` girişinden `13F9C` çağrı devamına |
| 512 baytlık kayıtların alınması | `43D0` başarılı dalından `4460` başarılı tag kontrolüne |
| Değişken boylu verilerin alınması | `13030` girişinden `130C8` başarılı tag kontrolüne |
| Birinci komut yayımı | `13BC8 → 14388 → 143C0`, bitiş `13C00` |
| Rezervasyon ve ikinci yayım | `14160` girişinden `142B8` dönüşüne |

`14160` bazı çağrılarda yalnızca rezervasyon ve durum güncellemesi yapar.
İç aşamalar ana çağrının süresinden yalnız birbirleriyle örtüşmüyor ve
bütün sınırlar geçerliyse çıkarılır. Kalan süre komut hazırlığına ek olarak
ölçüm dışında kalan kurulum, filtreleme ve başka transferleri kapsar.
Normal emüle DMA kopyaları çağrı içinde yürütülür. Tag kontrolü bu nedenle
PS3 donanım DMA gecikmesi olarak yorumlanmaz.

Alt ajan kaynak incelemesi `44D0` ve `4624` zincirinde 512 baytlık
kayıtlardan alan seçildiğini ve çıkan aralıkların `13030` okumalarını
belirlediğini gösterdi. Build 61'de hem `867e` hem `43398b` yazıları
iki okuma noktasına da bağlanmıştı. İkinci alt ajan bu kayıtların olay
kayıplarını, PUT sayımlarını ve FIFO okuma aralıklarını kontrol etti.

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
export PYTHONPATH=tools
python3 tools/build_bces_job_phases.py
python3 tools/prepare_bces_ios.py --support-report out/bces-support-critical62.json --job-flow
python3 tools/analyze_critical_job.py out/ios-job62/trace-A/frame-trace.csv \
  --output out/ios-job62/trace-A/critical.json
python3 tools/analyze_job_phases.py out/ios-job62/trace-A/frame-trace.csv \
  --output out/ios-job62/trace-A/phases.json --progress out/ios-job62/trace-A/critical.json
```

## iPhone 15 Pro sonucu

6 Kasım 2026. Build 62 Release iPhoneOS derlemesi, kurulumu ve açılışı
tamamlandı. İlk kurulum bağlantısı sıfırlandı, tekrar denemesi geçti.
Nötr girişle aynı kayıtlı bataklık iskelesine gelindi ve oyun yüzeyi
`scene-B/frame.png` ile kontrol edildi. İki ayrı 2 saniyelik kayıt aynı
PID ve binary UUID'ye ait. Her iki pencere `fair` termal kategorisinde.
408.846 ve 413.151 olayda kayıp sıfır. Tam işlerden 8.797 ve 8.948
komut üretim çağrısının bütün iç kapsamları doğrulandı. İki kayıtta
toplam 24 tam kare penceresi var. Test süreci kapatıldı.

| Bir duvar saniyesindeki toplam worker CPU süresi | İz A | İz B |
| --- | ---: | ---: |
| Komut üretim çağrısının bütünü | 301,66 ms | 302,64 ms |
| 512 baytlık kayıtları alma | 14,69 ms | 14,10 ms |
| Değişken boylu verileri alma | 4,52 ms | 4,23 ms |
| Birinci yayım | 6,26 ms | 6,13 ms |
| Rezervasyon ve ikinci yayım | 9,11 ms | 9,16 ms |
| Ayrı ölçülen bölümler çıkarıldıktan sonra kalan | 267,08 ms | 269,03 ms |

Kalan bölüm, komut üretim çağrısı CPU maliyetinin %88,5–88,9'unu kapsıyor.
Tek çağrı için bu bölümün CPU p95'i 0,316–0,319 ms. Toplam iş miktarı
birden çok SPU worker'ında ölçüldü. Kare başına kazanımı belirlemek için
tüketicinin beklediği süreye ayrı bakıldı.

Komut FIFO'sunda yazma konumu ilerideyken self-JUMP üzerinde durma olayı
iki kayıtta da sıfır. Tam kare pencerelerinde RSX acquire da sıfır.
Ana PPU için özel lane sahipliği ve tek geride üretici koşulunu A'da
1.895 yoklamadan 155'i, B'de 1.055 yoklamadan 73'ü sağladı.
`1774dd` işlerinin bu yoklamalarla doğrulanmış zaman örtüşmesi
tüm kayıt başına 5,731 ve 1,055 ms. Kare başı medyan 0,114 ve 0 ms.
Örtüşmenin 3,138 ve 0,941 ms'lik bölümü komut üretiminin kalan kısmında.
İki girdi ve iki yayım aşamasının toplam örtüşmesi her kayıtta
0,07 ms'nin altında. Bu eşlemeler dar kapsama sahip. Belirsiz
yoklamalar ve başka bekleme türleri için süre çıkarılmadı.

Bu sahne `1774dd` yayımını veya girdi kopyasını FPS için öncelikli
prototip olarak seçmeyi desteklemiyor. Komut üretiminin kalan kısmı CPU
yükü için aday olarak duruyor. Kare süresine yönelik sonraki hedef
iki kayıtta medyan 98,86 ve 94,98 ms süren RSX drain içinde çizim
hazırlığını GPU'ya gönderim ve bekleme anlarıyla ilişkilendirmek.
Drain kapsamındaki süreler örtüşebilir. Bu kayıtlar FPS karşılaştırması
veya kazanım tahmini için kullanılmadı.

Kayıtlar `out/ios-job62/trace-{A,B}` altında. ASan/UBSan kapsam kontrolü,
17 mevcut analiz testi ve iç içe süre muhasebesi ile yanlış FIFO
sözcüğünün reddine yönelik sentetik kontrol geçti.
