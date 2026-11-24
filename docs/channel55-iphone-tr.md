# Sık MFC kanallarını inline işleme — build 55

4 Kasım 2026. Linux portunun sık kullanılan kanal çağrılarını satır içine alma
uyarlaması; MFC yuva ipucu ve overlay filtresinden ayrı deneydir.

## Değişiklik ve kaynak

Kaynak: yerelde sabitlenmiş Linux `1ab02e702c37247ad4f53ac0b361d92e8b3269bc`,
`out/dma-upstream-audit/linux-work_patches_ps3recomp.patch` içindeki
`SPU_WRCH_INLINE`, `spu_wrch_fast` / `spu_rdch_fast`.

`src/platform/SpuChannelInline.h::bces_channel_wrch_inline`, yalnız kanal numarası
derleme zamanında sabitse MFC_LSA/EAH/EAL/Size/TagID/WrTagMask alanlarını doğrudan
context'e yazar; TagID 31 ile maskelenir. Cmd ve WrTagUpdate ayrı küçük runtime
fonksiyonlarına gider. Atomik DMA rezervasyon yolu, gerçek transfer, tag, olay
ve uyandırma sırası korunur. `bces_channel_rdch_inline`, yalnız RdTagStat için
önceden latched edilen durumu tercih edilen 32-bit slota koyar. Diğer/dinamik
kanallar özgün fonksiyonlara gider. Fence kaldırılmadı, context ABI değişmedi.

Linux yardımcıları doğrudan güncel genel runtime ile değiştirilmedi.
`tools/prepare_channel_inline.py::patch`, sabit çalışma kanal kaynağına iki
küçük helper ekler. `tools/build_bces_channel_inline.py`, ayrı arşivde 70 SPU
C birimini O2/iPhoneOS olarak yeniden derler; diğer 13 nesneyi byte olarak korur.
Özgün kaynak ve arşiv değişmez. Lighting, SSAO ve Edge için arşivden çıkarılıp
ayrıca derlenen üç referans kaynak da aynı header'ı içerir. Header, üretilen
prototiplerden sonra eklenir. Clang ARM64 assembly probe etkin dalda doğrudan
store/load gösterir; ayrıca wrapper fonksiyon çağrısı yoktur.

`SpuChannelControl`: 0 özgün, 1 inline, 2 kapsam/doğrulama. Kanal başına atomik
sayaçlar yalnız mode2'de artar. Parametre ve tag okuması gerçek oyunda özgün
kodla karşılaştırılır; yan etkili DMA komutu iki kez çalıştırılmaz. Bunun durum
eşitliği native testte sınanır. CHHIST/POLLTRACE/TAGPROBE ortam değişkenlerinden
biri varsa tanı bozulmasın diye inline zorla kapalı kalır. Hata mode0'a döndürür.
Kontrol yalnız derlenmiş varyant + `--channel-inline-control` ile kullanılabilir;
session/token ve katı integer 0/1/2 denetimi geçerlidir. Kullanıcı menüsüne henüz
yeni optimizasyon seçeneği eklenmedi.

## Tamamlanan doğrulama

- ASan/UBSan native: 4 x 768 = 3.072 referans/aday durum karşılaştırması geçti.
  Normal koşuda 256 gerçek hızlı yol vakası; üç tanı env koşulunda hızlı yol 0.
  Gerçek MFC engine/header ve özgün MFC dispatch dalı; context, VM, engine,
  preferred-word, tag/event/wake fingerprint eşit. Atomik handler ve MFC dışı
  hizmetler stub; tam rezervasyon simülasyonu iddia edilmiyor.
- Session-bound kontrol ayrıştırma testi geçti. Geçersiz tür/aralık reddedildi.
- 70/70 SPU birimi + 13 korunmuş nesne, platform IOS ve kaynak/nesne/arşiv SHA
  doğrulaması geçti. Native Mac testi FPS ölçümü değildir.
- Xcode 27.2 / iPhoneOS SDK 27.2 ile Release build 55 imzalı derlendi ve iPhone'a
  kuruldu. Sandbox içindeki ilk Xcode çağrısı DerivedData erişiminde durdu;
  yetkili tekrar başarılı. `out/channel55-build-signed.log`,
  `out/ios-channel55/install.json`. Paralellik 1.
- Bu varyant SDK 27.2 ile derlendi; eski arşivin kayıtlı komutları 27.1 idi.
  Aynı yeni binary'de mode0/1 bunu eşitler. mode0 ek bayrak kontrolü içerir;
  anlamlı kazanım çıkarsa, temiz build54 ile ayrıca doğrulanmadan net kazanç
  ilan edilmemelidir. Saf referans uygulama `baselines/channel55-reference54/`
  altında korunur.

## Tekrar üretim

```sh
env DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
 python3 tools/test_channel_inline.py
python3 tools/build_bces_channel_inline.py
python3 tools/prepare_bces_ios.py --support-report out/bces-support-channel55.json
cmake -S cmake/bces-ios -B build/bces01229/ios -DBCES_DMA_ORIGINAL_SCAN=ON
# Imzalı Xcode Release, -jobs 1. Launch: --channel-inline-control.
python3 tools/measure_device_channel55.py --device 00008130-001129E00243001C \
 --run out/ios-channel55 --windows 3 --warmup-seconds 90
```

Kaynak manifesti: `out/ios-channel55/source-hashes.json`. Ölçüm sürücüsü aynı
PID/kamera, sabit termal kategori/log durumu, shader/renderer hata kontrolü,
FPS sırasında dondurulmuş tanı sayaçları ve ham sunum zamanları ister. Önce
mode2 kapsamı, doğal ısınma, sonra A/B/A (0/1/0) 30'ar saniye; her pencerede en
az 120 ham aralık. Harici soğutma zorunlu değil. Kritik termal kategori küçük
kazanç kıyasına alınmaz. Aynı etiket eşit saat hızını kanıtlamaz.

Cihaz ölçümü aşağıda tamamlandı.

İlk gerçek cihaz kapsamı: dokuz kanal türünün hepsi görüldü; parametre/okuma
kontrolü 11.258.183; mismatch 0. Yan etkili
komutlar bu sayıya karşılaştırma olarak dahil değildir.

## Tamamlanan iPhone sonucu: anlamlı kazanç yok

PID 4263, aynı kayıtlı bataklık/iskele sahnesi. Kayıt yüklenirkenki kısa
sinematik ölçülmedi; iki gerçek oynanış yüzeyi incelenerek serbest oynanış ve
sabit konum doğrulandı. Yalnız nötr girdi gönderildi. Kamera/karakter taşınmadı.
Kapanış görüntüsü de aynı konumu koruyor. Eski ilk liman FPS'siyle kıyaslanmaz.

Harici soğutma kullanılmadı. Doğal ısınma sonunda üç alt FPS grubuyla durulma
koşulu sağlandı; üç pencerede sıcak kategori 2 sabitti. Düşük güç kapalı,
uygulama aktif, ayarlar kapalı, shader 488→488, log sınırı kapalı ve sabit.
Kontrol/oracle sayaçları FPS sırasında sabit, profiler kapalıydı. Her pencerede
Metal lighting/SSAO geçişleri ilerledi; renderer/compute fault 0.

| Pencere | Inline | FPS | Ortalama kare aralığı | Ham aralık |
|---|---|---:|---:|---:|
| A | Kapalı | 9,01293 | 110,95170 ms | 297 |
| B | Açık | 8,72988 | 114,54918 ms | 288 |
| C | Kapalı | 8,64003 | 115,74033 ms | 285 |

Toplam 870 ham sunum aralığı, yaklaşık 33'er saniyelik üç pencere.
Frame/süre ağırlıklı kapalı 8,82639 FPS / 113,29665 ms; açık 8,72988 FPS /
114,54918 ms. Gözlenen fark FPS'de -%1,09344, aralıkta +1,25253 ms.
Kapalı referansların kendisi %4,13739 düştü. Aynı termal etiket eşit saat
hızını kanıtlamadığından bu küçük fark nedensel yavaşlama diye sunulmaz.
**Bu koşulda tekrarlanabilir anlamlı FPS kazancı doğrulanmadı; aday varsayılana
alınmadı.** Başka sahneler ve enerji tüketimi hakkında sonuç çıkarılmadı.

İlk ve son mode2 kontrollerinde 11.258.183 + 7.687.040 = 18.945.223 parametre/
okuma kontrolü, uyuşmazlık 0. Dokuz kanalın tümü her iki turda da görüldü.
Bu gerçek çağrı kapsamıdır; yan etkili DMA/state eşitliğinin native testteki
stub sınırlarını ortadan kaldırmaz. Son oracle sonrası mode0'a dönüş ack'i var.

Kanıt: `out/ios-channel55/comparison.json`, `verdict.json`, üç `trial0-*`
klasöründeki snapshot ve `frames.csv`, `oracle-before.json`, `oracle-after.json`,
`final-scene/frame.png`. Ölçüm sürücüsü başarıyla tamamlandı. Deneysel imzalı
uygulama `build/bces01229/baselines/channel55-experiment/` altında; kaynaklar ve
orijinal yama `channel55-experiment-source/` altında, her dosyanın SHA eşlemesi
`out/ios-channel55/source-archive.json` içindedir. Temiz hazırlama sonrası
üzerine yazılan üretilmiş dosyaların da deney sürümleri bu arşivden doğrulanır.

## Son durum ve sıradaki adım

Özgün O2-copy destek arşiviyle deney seçeneği olmadan yeniden hazırlama yapıldı.
Üretilmiş SPU/reference kaynaklarında inline header ve kanal helper'ları yok.
Dört yeniden derlenmiş nesne ve destek arşivinde `_bces_channel_` sıcak-yol
sembol erişimi olmadığı doğrulandı: `out/ios-channel55/clean-reference-proof.json`.
Temiz build55 başarıyla derlendi, imzası doğrulandı ve iPhone'a kuruldu:
`out/channel55-reference-build.log`, `out/ios-channel55/install-clean-reference.json`.
Böylece deneyin çağrı başına bayrak kontrolü normal oyunda kalmaz. Kurulumdan
sonra uygulama yeniden başlatılmadı; FPS kaydı arşivdeki deneysel build55 ile
yapıldı. Oyun verileri korunur; önceki doğrulanmış birleşik yollar değişmedi.

Sıradaki ayrı küçük upstream adayı, MFC yuvalarını 128 bayta hizalamaktır.
Bu tur denenmedi ve kazanç vaat edilmiyor. Ardından küçük DMA varyasyonlarını
uzatmadan, önceki kritik yol kayıtlarının işaret ettiği büyük iş alt ağının
süresini ayırıp hesap düzeyindeki dönüşümü seçmek gerekir.
Oyun/firmware dosyaları veya proje kodu GitHub'a gönderilmedi.
