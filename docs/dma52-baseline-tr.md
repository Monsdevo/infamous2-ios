# DMA ölçüm yükü için ayrı referans

1 Kasım 2026. Kullanıcı build 51 ölçümünün önceki FPS'den düşük göründüğünü
sordu. HUD son iki saniyedeki frame sayısını ikiye böler; yaklaşık 32 saniyelik
ham presented interval ortalamasıyla aynı büyüklük değildir. Ancak önceki
referanslar 6,11→6,20→6,84 FPS değiştiği için gerçek bir zaman değişkenliği de
vardır. Termal kategori 0 olması bu değişkenin nedenini belirlemez.

## Deney

Birebir build 50 uygulama yedeği bulunmadı. Build 50 yeniden üretilmiş gibi
sunulmaz. Bunun yerine build 51 ile yalnız per-DMA deney kontrolü/sayaçları
çıkarılmış build 52 karşılaştırılır. Gerçek DMA kopyası, özgün poison taraması,
fence, coherency ve tag tamamlanması korunur. Yeni optimizasyon eklenmez.

`BCES_DMA_ORIGINAL_SCAN=ON` CMake seçeneği `diagnostic_spu_channels.c`,
`DmaPoisonControl.c` ve `GameApp.mm` için uygulanır. Header'daki inline tarama
izni sabit 1 olur; setter atlamayı açamaz. iPhoneOS arm64 nesnesinin undefined
sembollerinde `bces_dma_poison_counts`/`bces_dma_skip_poison` erişimi olmadığı
kontrol edildi (`out/ios-dma-baseline52/object-proof.json`). İki saniyelik
rapor oluşturma kodu korunur: deney per-transfer ek yükünü sınar, bütün
gözlem altyapısının sıfır maliyetli olduğunu iddia etmez.

Native ASan/UBSan testi beş varyantta 9.000'er gerçek DMA submit geçti;
veri/tag/coherency fingerprint'leri aynı. Sayaçsız varyantta poison tanısı
çalışır, sayaçlar sıfırdır. `python3 tools/test_dma_poison.py`.
Build 52 tek işte imzalı derlendi: `out/dma52-build-final.log`.

```sh
cmake -S cmake/bces-ios -B build/bces01229/ios -DBCES_DMA_ORIGINAL_SCAN=ON
# Mevcut iPhoneOS Xcode projesini Release, -jobs 1 ile derle.
python3 tools/measure_dma_baseline52.py --device 00008130-001129E00243001C \
  --proof out/ios-dma-baseline52/tutorial52/scene-ready.json \
  --output out/ios-dma-baseline52/B52 --original-build 1
```

## İlerleme

Build 51 arşivi: `build/bces01229/baselines/dma51-instrumented/Infamous2Game.app`.
Build 52 arşivi: `build/bces01229/baselines/dma52-original-scan/Infamous2Game.app`.
Oyun/firmware veya bu derlemeler Git'e eklenmedi.

A51, mevcut gerçek iPhone'da aynı ilk liman serbest oynanış konumunda
**6,93245 FPS** verdi; termal 0 ve diğer doğrulanmış yollar açık.
`out/ios-dma-baseline52/A51/result.json`. Başlangıçta bataklık sinematiği
görüldü, ardından akış giriş anlatımına ve ilk limana geçti; sinematik/anlatım
FPS'si sonuçlara dahil edilmedi. Ekran yardımcısı görev yazısını iki kez
doğrulayıp çıktıktan sonra shader durulması beklendi.

Build 52 mevcut uygulamanın üzerine kuruldu, veri silinmedi; PID 4885.
`dma_original_scan_build=1` ve sayaçların sıfır olduğu raporla doğrulandı.
B52'nin ilk turunda kullanıcı yanlışlıkla Cole'u hareket ettirdiğini bildirdi.
Kamera ve konum eşleşmediğinden bu tur dışlandı. Karakter yaklaşık geri
getirildi, fakat bu konum da küçük maliyet karşılaştırması için kabul edilmedi.
Build 52 yeniden başlatıldı (PID 4901), kayıtlı bataklık akışından START → UP →
CROSS → UP → CROSS ile Yeni Oyun seçildi. Otomasyon yalnız CROSS, RY=0 ve
RX=0 gönderdi; yürütme girdisi yoktu. Görev yazısı ve sabit başlangıç limanı
gerçek görüntüyle doğrulandı. Kamera görsel olarak yaklaşık eşleşir; deterministik
oyun durumu veya birebir aynı iş yükü iddiası yoktur.

Bu turda telefon termal 1'e geçtiğinden ölçüm bekletildi. Kullanıcı soğutmayı
yeniledi; cihaz kategori 0'da en az 15 saniye kaldıktan sonra `B52-normal`
penceresi alındı. `B52-retry` içindeki kısmi pencere kullanılmadı.

## Sonuç

| Varyant | FPS | Ortalama kare aralığı | Ham aralık |
|---|---:|---:|---:|
| A51 — kontrol/sayaçlar var, özgün tarama açık | 6,93245 | 144,24908 ms | 222 |
| B52 — per-DMA kontrol/sayaçlar derlemeden çıkarıldı | 6,62622 | 150,91568 ms | 212 |

İki geçerli pencere yaklaşık 32'şer saniye ve termal 0. Sayaçları kaldırmak
bu kontrolde performansı geri getirmedi. Gözlenen FPS farkı -%4,42;
**bu, sayaçları kaldırmanın nedensel olarak yavaşlattığı anlamına gelmez**.
A/B ayrı açılışlardır; A/B/A tekrarı yapılmadı, saat hızları ölçülmedi ve
konum/kamera yalnız görsel olarak eşleştirildi. Birebir build 50 karşılaştırması
değildir. Buradan kesin sayaç maliyeti veya regresyon olmadığı kanıtı çıkarılmaz.

Önceki düşük 6,38 FPS ortalamasının temel nedeninin yeni DMA sayaçları olduğu
hipotezini destekleyen bir geri kazanım gözlenmedi. Aynı build 51 bu turda
6,93 FPS verdi; önceki oturumun değişkenliği hâlâ önemlidir. Küçük farkların
nedeni çözülmüş gibi sunulmaz.

Kanıt: `out/ios-dma-baseline52/comparison.json`, A51/B52-normal `result.json`,
ham `frames.csv`, snapshot'lar ve sahne görüntüleri. Ölçüm sürücüsü bitti.
iPhone'da build 52 sayaçsız referans açık bırakıldı; özgün DMA taraması ve
önceden doğrulanmış birleşik yollar açık. Bu bir yeni FPS optimizasyonu olarak
kabul edilmedi. CMake cache bu referans için `BCES_DMA_ORIGINAL_SCAN=ON`;
seçeneğin kaynak varsayılanı OFF'tur. Gelecek derlemede amaçlanan varyant açıkça
seçilmeli; DMA skip deneyi yeniden sınanacaksa OFF gereklidir.

Sonraki bağımsız optimizasyon adayı `spu_channels.c::mfc_for` için atomik
context kimliği doğrulanan son eşleşme ipucu. Bu oturumda uygulanmadı.
