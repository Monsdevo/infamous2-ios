# Build 65 · G-buffer DMA tüketicisi teşhisi

BCES01229 iPhoneOS Release. Renk ve derinlik kopyalarının sırası,
Metal yolları ve fallback davranışı korunur. Ölçüm yalnız
`--gbuffer-flow` ile türetilen build'de ve frame trace açıkken çalışır.

- `nv3089_blit` iki parçalı guest kopyasının başlangıcını, bitişini,
  I/O offsetini ve çözülmüş guest EA'sını kaydeder (kind 460).
- `mfc_do_transfer` GET ve GETL elemanlarının ortak kopya noktasında
  iki yüzeyle çakışan DMA adresini ve boyunu kaydeder (461).
  SPU image/overlay, PC/dönüş adresi ve SPU numarası aynı etiketle
  kaydedilir (462–464). Her SPU bağlamı, yüzey ve rol için blit sınırları
  arasındaki ilk okuma saklanır. SSAO pass 0, özgün çağrının mevcut
  thread-local kapsamıyla tanınır. Örnek sayısı toplam DMA sayısı değildir.
- Aydınlatma Metal uygunluk reddi, ilgili koşul grubunu ve epoch'u
  ayrı kaydeder (465). Guard reddi tek başına yüzey DMA'sı değildir.
- Analiz iki blit ile bir sonraki aynı yüzey blit'i arasındaki kapalı
  pencereleri kullanır. İkinci blit bitmeden gözlenen okumaları ayrı
  tutar. PPU, atomik ve RSX okumaları bu izde kapsam dışındadır.
  Bu yüzden ilk gözlenen DMA, tüm sistemdeki ilk tüketici garantisi vermez.

```sh
PYTHONPATH=tools python3 tools/prepare_bces_ios.py \
  --support-report out/bces-support-critical62.json --gbuffer-flow
cmake -S cmake/bces-ios -B build/bces01229/ios
# Release / generic platform=iOS / -jobs 1, mevcut geliştirme imzasıyla.
# --diagnose-frame ile aç ve mevcut sabit oynanış sahnesine gel.
PYTHONPATH=tools python3 tools/capture_frame_trace.py \
  --device "$DEVICE" --output out/ios-gbuffer65/trace-A --seconds 1
python3 tools/analyze_gbuffer_flow.py out/ios-gbuffer65/trace-A/frame-trace.csv \
  --output out/ios-gbuffer65/trace-A/gbuffer-flow.json
```

Sentetik kontrol, farklı sırada yazılan iz alanları, blit bitmeden
gelen okuma, blit sonrasındaki ilk pass 0 okuması ve aydınlatma guard
retinin ayrı raporlanması için geçti.

## iPhone 15 Pro sonucu

Build 65 imzalandı, kuruldu ve aynı süreçte üç adet bir saniyelik iz
alındı. A sinematik, B ve C görüntüyle doğrulanmış sabit bataklık
oynanışı. Termal kategori 1, iz kaybı sıfır. UUID
`B03463CB-4CAF-3E01-BFB2-EE80EB37E80F`.

| İz | Olay | Tam derinlik penceresi | İlk DMA pass 0 | Tam normal penceresi | Gözlenen normal DMA |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 177.435 | 9 | 9 | 9 | 0 |
| B | 174.258 | 7 | 7 | 8 | 0 |
| C | 151.331 | 8 | 8 | 7 | 0 |

Derinlik guest EA `0x47877B80`, normaller `0x474F3B80`.
Gözlenen tüm derinlik okumaları SPU image 100, overlay 225,
PC `0x5F90`, dönüş adresi `0x591C` ve özgün pass 0 kapsamına
ait. Üretilen `ssao_spu_reference.c` aynı dönüş adresini
`jobmod_e6fe749031f8_e2060` içindeki `0x5F70` yardımcısına bağlıyor.
Sabit oynanışta ikinci blit'in sonu ile ilk DMA arası 4,17–21,72 ms.
Tam pencerelerde iki parçalı yayım bitmeden örneklenmiş okuma yok.
Bu gecikme kendi başına kaldırılabilir kare süresi değildir.

Aydınlatma guard retleri A/B/C'de 133/115/118; tümü aynı pass veya
tablo doğrulamasında. Bu iz o koşulun hangi dalının tuttuğunu ayırmaz.
Retler ölçülen yüzeylerde başka bir DMA tüketicisine dönüşmedi.
Başka sahnelerdeki fallback ve izlenmeyen erişimler hâlâ korunmalı.

Metal'de `ssao_hd_fs` hâlihazırda yarım derinliği R32Float olarak
hesaplıyor. Üretim davranışı değişmeden sıradaki sınama, bu dokuyu
özgün 640×360 guest pass 0 çıktısıyla aynı karede karşılaştırmak ve
bu guest çıktının ilk gerçek okuyucusunu izlemek. Mevcut Metal SSAO
kaydı sonuç dokusuna ihtiyaç doğunca kuyruğa girdiğinden, pass 0
sonucunu daha önce isteyen bir guest tüketicisi varsa GPU işini
öne almak gerekebilir. Derinlik veya normal kopyası kaldırılmadı.
