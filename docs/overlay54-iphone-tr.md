# Overlay imza/sayfa filtresi — build 54

4 Kasım 2026. Kullanıcı uygulama ve ayrı iPhone ölçümü istedi. Yeni ölçüm
koşulu soğutmasız, doğal olarak ısınmış cihazdır; nominal kategori zorunluluğu yok.

## Uygulama

`tools/prepare_overlay_filter.py::patch`, upstream DMA_LEAN yaklaşımındaki
imza ilk-kelime hash özetini ve 1 KiB LS sayfa haritasını iOS kanal kaynağına
uyarlar. Mevcut EA özeti korunur. Hash çakışmaları yalnız gereksiz aramayı
koruyabilir; gerçek eşleşmeyi elememelidir.

`bces_overlay_candidate` her thread'e ait özet kullanır. Overlay kayıt
fonksiyonları kayıt sırasında kısa bir kilit ve generation yayını kullanır;
iç içe kayıt çağrıları aynı kilidi tekrar almadan tamamlanır. Özet değişen
generation'da shared kilitle yeniden oluşturulur. Böylece count arttıktan
sonra yazılan span/LSA bilgileri de geçersizleştirmeye dahil edilir. Normal
sorguda registry kilidi alınmaz; generation değişiyorsa eleme yapılmaz.

`spu_overlay_note_get` gövdesinde yalnız erken dönüş predicate'i değişir.
Mevcut resident-code eviction bu dönüşten önce kalır. Kaynak eşleştirme
sırası ve context güncellemeleri aynıdır. Dönüşüm bunu kaynak karşılaştırmasıyla
kontrol eder. `spu_context` ABI'si ve hazır arşivler değişmedi.

`OverlayFilterControl` modları: 0 eski özet, 1 yeni filtre, 2 eleme doğrulaması.
Mode2 her reddedilen girdide özgün tam eşleştirme koşulunu kontrol eder;
eşleşme bulunursa özgün yola döner ve filtreyi kapatır. Çağrı başına atomik
sayaçlar yalnız mode2'de çalışır. Gerçek context mutasyonları native testte
ayrıca bağımsız özgün tam kaynak yürüyüşüyle karşılaştırılır.

Deney `--overlay-filter-experiment` hazırlama seçeneğiyle eklenir. Varsayılan
kapalıdır. `--overlay-filter-control` ile başlayan süreçte session/token ve
katı integer 0/1/2 denetimli `overlay_filter` komutu kullanılabilir. Derlenmiş
deney yoksa açık mod kabul edilmez. Normal kullanıcı arayüzüne yeni satır eklenmedi.

Poison taraması sayaçsız özgün biçimde açık (`BCES_DMA_ORIGINAL_SCAN=ON`),
MFC ipucu üretilen çalışma kodunda yok. Metal lighting/SSAO, SSAO temizliği ve
önceki doğrulanmış birleşik yollar aynı karşılaştırma boyunca açık tutulur.

## Tamamlanan doğrulama

- Native ASan/UBSan: 36.000 gerçek context sonucu, 120.000 paralel sorgu,
  mismatch 0. 2.581 eleme; bunların 2.437'si eski kaba özete göre ek eleme.
  Rastgele/boundary girdileri, sıfır boyut, imza çakışması, sabit bölge,
  metadata güncellemesi, eviction ve paralel kayıt/özet sorguları sınandı.
- Test gerçek `spu_context` düzenini ve gerçek `spu_overlay_note_get` gövdesini
  kullanır. Referans erken özetleri bypass eden özgün tam yürüyüştür.
  Dump stub'ı ve sabit bellek için byte-comparator `gm_equal` stub'ı kullanılır;
  değişen guest bellek yarışlarının tam simülasyonu değildir.
- Session-bound komut ayrıştırma testi geçti; geçersiz tür/aralıklar reddedildi.
- Test edilen filtre metni ve note_get gövdesi üretilen iPhone kaynağıyla aynı.
  `out/ios-overlay54/source-hashes.json`.
- macOS 27.0.1/arm64, Xcode 27.2 (27B52), iPhoneOS SDK 27.2 doğrulandı.
  Aktif xcode-select CLT olsa da komutlar açık `DEVELOPER_DIR` kullanır.
- iPhoneOS Release build 54 tek derleme işiyle başarılı:
  `out/overlay54-build.log`. İlk ağ kurulum resetinden sonra tekrar kurulum
  başarılı: `out/ios-overlay54/install-retry.json`. Oyun dosyaları korunur.

## Soğutmasız ölçüm yöntemi

Sahne doğrulandıktan sonra oracle kontrolü FPS pencerelerinin dışında yapılır.
En az 120 saniye doğal oynanış ısınması beklenir. Son yaklaşık bir dakikada
termal kategori/log durumu/shader sayısı sabit, üç alt FPS penceresinin aralığı
en fazla %8 olmalıdır. Nominal, ılık veya sıcak kategori kabul edilir; kategori
zorlanmaz. Kritik durum karşılaştırmaya katılmaz, stress kaydı olarak korunur.

A/B/A/B/A: her pencere en az 30 saniye ve 120 ham sunum aralığı, en fazla
75 saniye. Sabit scene/PID/session, aynı termal kategori ve log durumu aranır.
Geçiş olursa ilk tur dışlanıp doğal koşulların yeniden durulması beklenebilir.
FPS sırasında overlay/mask oracle sayaçları sabit, profiler kapalı olmalıdır.
İki durumun aynı termal etiketi eşit saat hızını garanti etmez. Son oracle
kontrolü ve özgün moda geri dönüşle tur tamamlanır.

```sh
env DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
 python3 tools/test_overlay_filter.py
python3 tools/prepare_bces_ios.py \
 --support-report out/bces-support-compile-iphoneos-spu-O2-copy.json \
 --overlay-filter-experiment
cmake -S cmake/bces-ios -B build/bces01229/ios -DBCES_DMA_ORIGINAL_SCAN=ON
# İmzalı Release iPhoneOS build; -jobs 1. Launch'a --overlay-filter-control ekle.
# Mevcut kayıt bu turda doğrudan bataklık oynanışına açıldı. Nötr input ve
# iki gerçek yüzey görüntüsüyle scene-ready.json kaydedildi; yeni oyuna gidilmedi.
python3 tools/measure_device_overlay54.py --device 00008130-001129E00243001C \
 --run out/ios-overlay54
# Doğal dinlenme sonrası aynı süreçte kısa kontrol:
python3 tools/measure_device_overlay54.py --device 00008130-001129E00243001C \
 --run out/ios-overlay54-short --windows 3 --warmup-seconds 90
```

## Gerçek cihaz oturumu ve termal geçişler

PID 4014, kayıtlı bataklık sahnesinde Cole sabit ahşap iskelede. HUD/minimap
ve iki gerçek yüzey görüntüsüyle serbest oynanış doğrulandı. Yalnız nötr input
gönderildi; karakter/kamera taşınmadı. Önceki liman sonuçlarıyla doğrudan FPS
karşılaştırması yapılmaz. Yeni oyunun girişini tekrar oynatmak gerekmedi.

İlk oracle: 1.289.460 sorgu, 771.502 eleme, 84.945 ek eleme, mismatch 0.
Bu sayılar ölçüm pencerelerindeki çağrı sayıları değildir.

İlk soğutmasız tur termal 2'de başladı. A/B/C/D sırasıyla
7,79512 / 8,24905 / 8,26551 / 8,17187 FPS verdi. Son kapalı pencere sırasında
termal 3'e geçildi; o pencere geçersizdir. Tam beşli karşılaştırma yapılmış
gibi toplu sonuç verilmedi. İlk geçerli A/B/A'da %2,77 gözlenen farkın yanında
kapalı referanslar %6,03 değiştiğinden kazanç iddiası yapılmadı.
`out/ios-overlay54/partial-verdict.json`, `partial-aba.json`.

Harici soğutma kullanılmadı. Oyun duraklatma menüsüne alındı; menü hâlâ yüksek
CPU kullandığından Settings öne getirilerek doğal arka plan dinlenmesi yapıldı.
İlk yaklaşık 90 saniye kritik durumdan çıkarmadı; ikinci dinlenmeden sonra
cihaz kategori 0'a indi. Aynı PID korunarak oyun menüsü kapatıldı ve aynı
konum tekrar görüntüyle doğrulandı. Telefonu nominalde tutmak istenmedi;
oynanışta yeniden doğal olarak ısınması beklendi.

Kısa tur başlangıçta termal 1'de duruldu; ilk pencere içinde 2'ye geçiş oldu,
bu pencere de dışlandı. Yeniden 90 saniyelik durulma sonrasında, sıcak
kategori 2'de aşağıdaki **tam A/B/A** alındı. Böylece farklı kategorilerdeki
pencereler birleştirilmedi.

## Tamamlanan sonuç: anlamlı FPS kazancı yok

| Pencere | Overlay filtresi | FPS | Ortalama aralık | Ham aralık |
|---|---|---:|---:|---:|
| A | Kapalı | 10,10763 | 98,93515 ms | 334 |
| B | Açık | 10,01563 | 99,84390 ms | 330 |
| C | Kapalı | 9,96279 | 100,37344 ms | 319 |

Toplam **983 ham sunum aralığı**; her pencere yaklaşık 32–33 saniye.
Frame/süre ağırlıklı kapalı **10,03635 FPS / 99,63778 ms**, açık
**10,01563 FPS / 99,84390 ms**. Gözlenen fark FPS'de **-%0,20645**;
kare aralığında **+0,20612 ms**. Bu küçük farkı nedensel yavaşlama saymıyoruz;
**tekrarlanabilir, anlamlı hızlanma doğrulanmadı ve aday varsayılana alınmadı**.

Üç pencerede termal 2, aynı PID/session/kamera, log sınırı açık ve sabit,
shader sayısı 482→482, renderer/lighting/SSAO hata 0. Overlay/mask doğrulaması
ve profiler kapalı; overlay sayaçları FPS pencerelerinde sabit. P95 üçünde
de yaklaşık 108,356 ms. Son gerçek oyun görüntüsü başlangıç konumunu koruyor.

Kısa turun ayrı oracle kontrollerinde önce 1.882.723 sorgu / 137.972 ek eleme,
sonra 1.499.531 sorgu / 101.152 ek eleme; mismatch 0. Filtre gerçek kaynak
aramalarını engelliyor, fakat bu sahnede bunun presented frame-time'a anlamlı
katkısı gösterilmedi. CPU enerjisi veya bütün oyunun performansı ölçülmedi.

Kanıt: `out/ios-overlay54-short/comparison.json`, `verdict.json`,
`trial1-A-base`, `trial1-B-filter`, `trial1-C-base` altındaki snapshot/frames.csv,
oracle JSON'ları ve `final-scene/frame.png`. Aggregate ham frame/sürelerden
yeniden hesaplandı; ölçüm sürücüsü başarıyla bitti ve mode0'a döndü.

## Son durum

Deneysel uygulama `build/bces01229/baselines/overlay54-experiment/Infamous2Game.app`
ve tam üretilen kanal kaynağı `overlay54-experiment-source/` altında arşivlendi.
`out/ios-overlay54/source-archive.json` eski kaynak yolunu arşiv SHA256'sına
bağlar. Normal hazırlama deney bayrağı olmadan tekrar çalıştırıldı; overlay
ve MFC hot-path wrapper'ları üretilen kodda yok. Böylece başarısız denemenin
çağrı başına mode kontrolü normal sürüme taşınmaz.

Temiz referans build 54 başarıyla derlendi ve iPhone'a kuruldu; loglar
`out/overlay54-reference-build.log` ve
`out/ios-overlay54-short/install-clean-reference.json`. Kanal nesnesinde overlay,
MFC ipucu ve DMA poison deney kontrol/sayaç sembollerine erişim olmadığı
`clean-reference-proof.json` ile doğrulandı. Temiz referans kurulumdan sonra
yeniden başlatılmadı; gerçek cihaz ölçümü arşivlenmiş deneysel build 54 ile yapıldı.
Önceden doğrulanmış birleşik yollar korunur.
Native Mac testleri doğruluk içindir; Mac FPS ölçülmedi. Oyun/firmware,
büyük çıktılar veya proje kodu GitHub'a gönderilmedi.

Sonraki bağımsız aday Linux'taki sık MFC kanal erişimlerini inline işleme
yoludur. Overlay/MFC yuva ipucu denemelerinin sonucu bunun kazancını kanıtlamaz.
