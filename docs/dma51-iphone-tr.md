# Build 51 — DMA tanı taramasını ayırma

1 Kasım 2026. Performans karşılaştırması kullanıcının tercihiyle doğrudan
iPhone 15 Pro üzerinde yapılır. Mac üzerinde oyun benchmark'ı yapılmadı.

## Deneyin sınırı

Bu ilk DMA deneyi yalnız PUT sonrasında yerel belleği tekrar okuyarak
`0xC708C708` tanı desenini arayan döngüyü isteğe bağlı atlar. Gerçek DMA
kopyası, fence/barrier, tag tamamlanması, reservation kilitleri, coherency,
overlay ve RSX bildirimleri korunur. `haspoison` yalnız tanı logunu etkiler.
Dolayısıyla bunu DMA aktarımını bütünüyle yeniden yazmış gibi değerlendirmeyiz.

- `tools/prepare_dma_poison.py::patch`: üretilen `diagnostic_spu_dma.h`
  içindeki tek tanı döngüsüne koşul ekler; geri dönüşüm kontrolü kaynak
  metnin geri kalanının aynı olduğunu doğrular.
- `src/platform/DmaPoisonControl.h::bces_dma_poison_scan`: çalışma modu ve
  1/256 örneklemeli yol kapsamı. Sayaçlar kesin transfer/byte toplamı değildir.
- `src/platform/DmaPoisonControl.c`: varsayılan özgün tarama açık.
  `SPU_POISON_DMA=1` tanı taramasını zorunlu kılar, atlama isteğini geçersiz kılar.
- `GameApp.mm` raporu ve session/token kontrollü `dma_poison_skip` komutu
  aynı oyun sürecinde A/B testi sağlar. Ayarlardaki deneysel tercih varsayılan
  kapalıdır. Önceden doğrulanmış birleşik optimizasyon profili korunur.

## Tamamlanan doğrulama

`python3 tools/test_dma_poison.py`: gerçek üretilen DMA header'ı ile
ASan/UBSan altında dört ayrı 9.000-transfer koşusu geçti. Özgün kod,
tarama açık, tarama atlanmış ve zorunlu tanı varyantlarında veri/tag/coherency
olay fingerprint'i aynı: `5397671830134287196`. GET/PUT, fence/barrier
varyantları, reserved/unreserved dallar ve poison içeren veri sınandı.
Host servisleri stub'dır; bu test eşzamanlılık modelini veya FPS'yi doğrulamaz.
Ham sonuç: `out/dma51-native-test.json`.

iPhoneOS Release build 51 tek derleme işiyle başarıyla derlendi ve mevcut
uygulamanın üzerine kuruldu; oyun verileri silinmedi. Son derleme logu:
`out/dma51-build-final.log`. Hazırlayıcı pinned runtime'ı güncellemez.

## Cihaz ölçüm durumu

Önceki turda bataklık kaydı otomatik yüklendi. Kullanıcının tarif ettiği
duraklatma → Kaydedilen → Yeni Oyun yoluyla başlangıca dönüldü. Kamera
öğreticisindeki yukarı/sol girdiler tamamlandı, fakat son görüntü isteği
başarısız oldu. Ölçüm sürücüsü sahne doğrulaması gelmeyince durdu;
`out/ios-dma51-newgame` içinde tamamlanmış FPS penceresi yoktur.

1 Kasım devamında eski süreç kapanmıştı. Kurulu build yeniden açıldı
(`out/ios-dma51-resume/launch.json`, PID 4504). Yine kayıtlı sahne yüklendiği
için Yeni Oyun menüsüne dönüldü. Kamera öğreticisinin yukarı/sol girdileri
otomatik verildi. Önce gerçek liman görüntüsü elle incelendi; ardından
`capture-025` ve `capture-026` OCR'ında serbest görev yazısı da doğrulandı.
Ekran yardımcısı FPS pencerelerinden önce çıktı.

İlk pencere `runtime_log_capped` geçişi nedeniyle geçersiz sayıldı.
`out/ios-dma51-stable` içindeki tekrar ise Wi-Fi dosya aktarımı zaman aşımı
yüzünden eksik kaldı. Bu iki denemeden FPS kazancı çıkarılmadı.
Kullanıcı USB'yi bağladı; aynı oyun süreci ve sabit kamera korunarak
`out/ios-dma51-retry` içinde beş geçerli pencere tamamlandı.

## Cihaz sonucu: aday kabul edilmedi

| Pencere | Tanı taraması | FPS | Ortalama kare aralığı |
|---|---|---:|---:|
| A | Açık (özgün) | 6,11478 | 163,54 ms |
| B | Atlanıyor | 5,99720 | 166,74 ms |
| C | Açık (özgün) | 6,19913 | 161,31 ms |
| D | Atlanıyor | 6,49334 | 154,00 ms |
| E | Açık (özgün) | 6,83788 | 146,24 ms |

Toplam **1.018 ham sunum aralığı**; her pencere yaklaşık 32 saniye.
Frame/süre ağırlıklı özgün sonuç **6,38449 FPS / 156,62965 ms**;
atlama **6,24887 FPS / 160,02902 ms**. Gözlenen fark FPS'de **-%2,124**,
kare aralığında **+3,399 ms**; **kazanç doğrulanmadı**.

Referanslar da zamanla yükseldiği için bu farkın tamamını adayın neden olduğu
bir yavaşlama diye yorumlamak doğru olmaz. B iki komşu referanstan da düşük;
D komşu referansların arasında. Sonuç adayın bu sahnede tekrarlanabilir
bir hızlandırma sağlamadığıdır. Bu deney diğer DMA alt adaylarını veya
bütün büyük hesaplama optimizasyonlarını reddetmez.

Beş pencerede de termal kategori 0, aynı PID/session, shader sayısı
1.367→1.367, log sınırı sabit ve geometri SPU/SPU kaldı. GPU maske
doğrulaması/profiling kapalıydı. Her pencerede Metal lighting/SSAO
sayaçları ilerledi. Örneklemeli tarama/atlama sayacı yalnız beklenen yönde
arttı: A 6.427 tarama; B 6.437 atlama; C 6.671 tarama; D 7.085 atlama;
E 7.150 tarama. Bunlar toplam DMA sayıları değildir.

Sürücü başarıyla bitti; `restore-reference/ack-*.json` DMA atlama=0,
interval maske=1, uzak ışık=1, hızlı SPU dispatch=1 durumunu doğruladı.
Deneysel tercih varsayılan kapalı kalıyor; önceden doğrulanmış yollar açık.
Ham kanıt: `out/ios-dma51-retry/comparison.json`, A–E `summary.json`,
`frames.csv` ve rapor snapshot'ları. Başarılı ölçümün `valid=true` alanı
ölçümün geçerli olduğunu belirtir; optimizasyonun başarılı olduğu anlamına gelmez.

Ölçüm komutları (her tur için yeni çıktı klasörü kullanılır):

```sh
python3 tools/drive_device_gameplay.py \
  --device 00008130-001129E00243001C --output out/ios-dma51-resume/tutorial
python3 tools/measure_device_dma51.py \
  --device 00008130-001129E00243001C --run out/ios-dma51-resume
```

Sürücü önce sahne kanıtını bekler; diğer optimizasyonlar açıkken
tarama/atlama/tarama/atlama/tarama sırasıyla beş pencere alır. Her pencerede
en az 30 saniye ve 180 ham sunum aralığı, sabit PID/session, gerçek yol
sayaçları, termal kategori, shader/validation ve hata kontrolleri aranır.
Ekran okuma ve GPU görüntü kopyası FPS pencerelerinin dışında kalır.
Sonunda özgün tarama geri açılır. Aynı termal kategori eşit saat hızını
garanti etmez; tek sahne sonucu bütün oyun için FPS garantisi değildir.

Sonraki bağımsız DMA adayı `spu_channels.c::mfc_for` içindeki 128 slotlu
arama için doğrulanan son eşleşme ipucu. Slotun context kimliği her kullanımda
atomik kontrol edilmeli; eşleşme yoksa özgün aramaya dönülmeli. Slot bırakma,
yeniden kullanım ve context yaşam döngüsü korunmadan salt pointer cache
eklenmeyecek. Overlay aday taraması bununla aynı deneyde karıştırılmayacak.
