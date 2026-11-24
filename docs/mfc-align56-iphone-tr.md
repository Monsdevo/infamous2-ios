# MFC yuvalarını 128 bayta hizalama — build 56

4 Kasım 2026. Kullanıcı önce kazanç ihtimalini sordu: hesap miktarı azalmadığı
ve henüz cache-contention ölçülmediği için büyük ms kazancının beklentisi düşük
olarak açıklandı. Bağımsız, sınırlı cihaz A/B/A denemesi; vaat edilmiş FPS yok.

Kaynak: Linux portu `1ab02e702c37247ad4f53ac0b361d92e8b3269bc`, yerel
`out/dma-upstream-audit/linux-work_patches_ps3recomp.patch`, 30978. satırdaki
`spu_mfc_slot` için `__attribute__((aligned(128)))`. Genel runtime güncellenmedi.

`tools/prepare_mfc_alignment.py::patch`, yalnız özel `spu_mfc_slot` tipinin
hizalamasını değiştirir. `mfc_for`, claim/release kilidi, owner atomikleri,
DMA/queue/tag ve reservation algoritmaları aynı kalır. `spu_context` ABI'si
ve hazır SPU arşivleri değişmez. `--mfc-align128` seçeneği verilmezse özgün
yerleşim korunur. Yeni hot-path switch veya çağrı sayacı eklenmedi.

`bces_mfc_layout` gerçek derlenmiş slot boyut/hizalama, tablo adres mod128,
stride ve engine offset/boyutunu GameApp raporuna yazar. Bu saniyelik telemetri
çağrısıdır; her MFC erişiminde çalışmaz. Değişim yeniden başlatma gerektirir.
Aynı build56'nın iki imzalı kopyası kullanılır; tek uygulama içinde canlı
geçişle nesne yerleşimini değiştirmek denenmez.

Native ASan/UBSan her iki düzenle geçti: 128 yuva, overflow, release/yeniden
claim ve reset, 32 paralel claimant x500 lookup; ayrı engine sahipliği.
Gerçek özel registry gövdesi ve gerçek context/engine tipleri kullanılır;
tam DMA/atomic reservation simülasyonu veya Mac FPS ölçümü değildir.
Özgün slot 528 bayt/alignment8, hizalı slot 640 bayt/alignment128; engine
520 bayt ve offset8 aynıdır. 128'lik tablo 67.584 → 81.920 bayt (+14.336,
14 KiB). Bu toplam uygulama RAM kazancı değildir; az miktarda padding eklenir.
`out/align56-native.json`.

Hazırlanmış iki kanal kaynağı, yalnız tip attribute'ü ve rapor flag'ı dışında
byte olarak aynı doğrulandı. MFC hint, overlay ve inline-channel deneyleri
kapalı/derlenmemiş; özgün poison taraması sayaçsız açık. Metal lighting/SSAO,
SSAO depth cleanup ve daha önce doğrulanmış birleşik yollar korunur.

```sh
python3 tools/test_mfc_alignment.py
python3 tools/prepare_bces_ios.py \
 --support-report out/bces-support-compile-iphoneos-spu-O2-copy.json
# Aynı Xcode Release / -jobs 1 ile derle, align56-reference altına arşivle.
python3 tools/prepare_bces_ios.py \
 --support-report out/bces-support-compile-iphoneos-spu-O2-copy.json --mfc-align128
# Aynı şekilde derle, align56-aligned altına arşivle.
python3 tools/measure_device_align56.py --device 00008130-001129E00243001C \
 --run out/ios-align56
```

Ölçüm sürücüsü her turu yeni süreçte aynı kayıtlı sahneden başlatır. İki gerçek
render yüzeyi incelenmeden scene-ready.json verilmez. Yalnız nötr input.
Her yeni süreç en az90s doğal ısınır; son yaklaşık65s termal/log/shader sabit
ve üç alt FPS grubu en fazla%8 aralıkta olmalıdır. Sonraki turlar ilk turun
termal kategorisini sağlamalıdır. Kritik kategori dışlanır. Her pencere en
az30s /120 ham sunum aralığı; sayaçsız gerçek Metal compute kapsamı doğrulanır.
Eşit termal kategori aynı saat hızını kanıtlamaz; kapalı referansın sürüklenmesi
ayrıca raporlanır. Yeni kurulumlarda oyun dosyaları ve saves korunur.

Cihaz karşılaştırması aşağıda tamamlandı.

## Gerçek cihaz sonucu: kazanç doğrulanmadı

İki imzalı Release build56 üretildi; derleme paralelliği1. Üç kurulum ve yeni
süreç sırasıyla A özgün/PID4356, B hizalı/PID4359, C özgün/PID4362.
`out/align56-reference-build.log`, `out/align56-aligned-build.log`,
`out/ios-align56/{A-base,B-aligned,C-base}/install.json`.

Her tur aynı kayıtlı bataklık/iskele sahnesine açıldı. Yükleme sinematiği
ölçülmedi; ikişer post-cinematic gerçek yüzey manuel incelendi ve aynı
kamera/karakter konumu/HUD doğrulandı. Nötr girdi dışında input gönderilmedi.
Kullanıcıdan kumanda veya soğutma yardımı gerekmedi. Harici soğutma kullanılmadı.

Cihazda özgün slot528/alignment8/base mod128=80, hizalı slot640/alignment128/
base mod128=0 ölçüldü. Engine520/offset8 her ikisinde aynı. Üç FPS penceresinde
termal2 sabit; düşük güç kapalı, uygulama aktif, ayarlar kapalı. Shader514→514,
log sınırı kapalı/sabit; gerçek Metal lighting/SSAO ilerledi, fault0. Yeni
profiler, kanal oracle veya MFC çağrı sayacı açık değildi. Mac'teki son temiz
referans derlemesi C'nin sahne onayından önce bitti; FPS sırasında derleme yok.

| Tur | Düzen | FPS | Ortalama kare aralığı | Ham aralık |
|---|---|---:|---:|---:|
| A | Özgün | 9,27768 | 107,78561 ms | 307 |
| B | 128 bayt hizalı | 8,73517 | 114,47981 ms | 262 |
| C | Özgün | 8,63534 | 115,80316 ms | 277 |

Toplam846 ham sunum aralığı. Frame/süre ağırlıklı referans8,96150FPS /
111,58845ms; hizalı8,73517FPS /114,47981ms. Gözlenen fark -%2,52564FPS /
+2,89135ms. Kapalı referansın kendisi -%6,92342 değiştiği için bu fark
hizalamanın nedensel yavaşlatması olarak sunulmaz. Eşit termal etiket, eşit
frekans demek değildir. **Anlamlı FPS/ms kazanımı doğrulanmadı; özgün düzen
korundu.** Başka sahne, enerji veya bütün oyunda etkisizlik iddiası yok.

Kanıt: `out/ios-align56/comparison.json`, `verdict.json`, her turun
`measurement/frames.csv` ve snapshot JSON'ları. Sürücü başarıyla tamamlandı.
B'nin ham sunum süresi29,994s, snapshot wall ölçümü en az30s; diğerleri yaklaşık
32–33s. Bütün pencereler120 minimum ham aralığın üzerindedir.

Ayrı görsel gözlem: C özgün referansın erken sinematik karesinde parlak kırmızı
bir blok görüldü (`C-base/scene-0/frame.png`). Bu turun incelenen serbest
oynanış yüzeylerinde ve son görüntüde yok; sinematik ölçüme katılmadı. Nedeni
bu dar yerleşim denemesinde araştırılmadı; bütün oyunun grafik doğruluğunun
kanıtlandığı söylenemez. Hizalı sürümdeki incelenen oynanış kareleri referans
konumunu/görünümünü korudu.

## Bırakılan durum

C turu özgün düzenli build56'yı yeniden kurdu; iPhone'da bu referans kaldı ve
son oyun görüntüsü `out/ios-align56/final-scene/frame.png`. Oyun verileri/saves
korundu. Mac'te normal hazırlama da `--mfc-align128` olmadan yenilendi ve
imzalı temiz build56 derlendi (`out/align56-final-reference-build.log`).
Hazırlanmış kanal kaynağı A arşiviyle byte olarak aynı. Son Mach-O'nun __text
bölümü de ölçülen A binary'siyle aynı SHA256; tüm dosya SHA'sı imzalı çıktıda
farklı, birebir aynı dosya diye sunulmaz. `out/align56-clean-reference-proof.json`.
Sandbox içi codesign trust okuması başarısız oldu; salt okunur yetkili doğrulama
geçti. Global güven/imza ayarları değiştirilmedi.

Hizalı deney `baselines/align56-aligned/`, referans `align56-reference/`, tam
küçük giriş kaynakları `align56-inputs/` altında. SHA eşlemesi
`out/ios-align56/source-archive.json`; üretilmiş eski B kanalı da arşivden
kontrol edilir. Kaynak/paket/oyun dosyaları GitHub'a gönderilmedi.

Sonraki somut adım: küçük DMA/cache varyasyonlarını burada kapatıp önceki
kritik yol kayıtlarındaki `jobmod_638a73a6476e_e60c0` işinin `8648 → 6B90`
çağrısı + `spu_drain_call(ctx,0x866C)` alt ağını birlikte sürelemek. İşin resmi
adı veya kaldırılabilir ms bütçesi henüz bilinmiyor. Bu bütçe ve giriş/çıktı
sınırı belirlendikten sonra büyük hesabın ARM64/Metal dönüşümü seçilmeli;
CPU örnek sayısı doğrudan kare ms'si sayılmamalı.
