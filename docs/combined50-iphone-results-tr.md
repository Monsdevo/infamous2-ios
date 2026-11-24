# Build50 — birleşik profil, gerçek iPhone ölçümü

31 Ekim2026. Kullanıcı soğutmayı hazırladı; aynı Wi-Fi, kilit açık, düşük güç kapalı. iPhone15Pro üzerinde build50 kuruldu, yeni geliştirme profilinin güveni kullanıcı tarafından onaylandı. Profil7Kasım2026 16:26:56UTC'ye kadar geçerli. İlk ağ kurulum isteği reset oldu, tekrarı başarılı. Sandbox dışı codesign verify ve profil/application-identifier/team uyumu geçti. Tek işte imzalı derleme başarılı: `out/combined50-build.log`.

## Dahil edilenler

- Önceden doğrulanmış iPhoneOS O2 SPU arşivi,64MiB host stack ve önceki correctness düzeltmeleri.
- Metal lighting, Metal SSAO ve SSAO'nun kalan özgün derinlik çağrısı çevresindeki temizleme.
- Uzak ışık elemesi ve WWS fast-dispatch/stack-reset sayfa negatif testi.
- Mac'te kazanç göstermiş interval tile-mask çekirdeği bu oturumda ilk kez iOS'a aktarıldı. Aynı `src/host/LightMaskInterval.metal` metni kullanılır; SHA256 `38d6bae248c5f25bd026bc3f89f3a1be69897715786647762fffbe4a385325be`. Donanımsal Mac probe/capture bağımlılıkları iOS'a alınmadı.
- Deneysel geometry, renderer memo, geniş SPU RZ matematik, yeni IB cache ve normal writeback atlama kapalı. İki G-buffer guest writeback'i korunuyor.
- Mevcut RSX legacy fast yolu iki kolda da açık; bu deneyde onun bağımsız kazancı hesaplanmıyor.

İngilizce panelde `Combined optimizations · restart required` anahtarı eklendi. Yeni `performance.verified-fast-paths` tercihi varsayılan açık. Yeniden açılışta bu profil uzak ışık, intervalmask ve hızlıdispatch'i açar; Metal lighting/SSAO tercihlerini açık, geometriyiSPU/SPU ve validationOFF olarak seçer. Eski deneyler bu profile eklenmez. Normal ikon açılışında da bu yolların açılması, önceki build49'dan farklıdır. Mode2 yalnız explicit doğrulama launch argümanıdır; normal ikon açılışı mode1.

## Kaynak/araç kontrolleri

`prepare_light_mask_empty.patch(..., capture_inputs=False)` iOS'un mevcut compute encoder'ını korur, timestamp probe veya capture/readback eklemez. Mode2 özgün ve interval maskeyi aynı gerçek girdide hesaplayıp GPU'da karşılaştırır; oyun daima özgün maskeyi tüketir. Mode1 yalnız interval adayı çalıştırır. Hata/mismatch maskeyi özgün yola kapatır ve performans penceresini geçersiz kılar.

`GeometryControl.mm` yeni `light_mask`0/1/2 alanını katı tür/aralık ve session/token kontrolleriyle kabul eder. Native kontrol testi geçti; bool, kesir, string ve sınır dışı değerler reddedildi. `HostLightMask.c` iOS hedefinde ayrı C kaynağıdır. Hazırlayıcı pinned fork veya Mac objelerini iOS'a bağlamaz.

Wi-Fi'da görülen geçici bağlantı resetleri için `geometry_device_control.call` yalnız idempotent device-copy işlemlerinde en fazla3deneme yapar. Diğer komutlar ve farklı hatalar yeniden çalıştırılmaz. Bu yalnız host araç değişikliğidir.

## Doğrulama ve sahne

`out/ios-combined50/launch-retry.json` gerçek süreç başlatmasını belgeler. Kamera öğreticisinin artık aktif olmadığı ve serbest görev yazısı iki gerçek oyun yüzeyi/OCR ile doğrulandı; süreç ve session sabit kaldı. Otomatik olarak verilen girdiler `tutorial/actions.json`/`scene-ready.json` içinde; bu tur yalnız kaydedilmiş girdiler otomatik sayılır. Sahne boyunca karakter/kamera sabit bırakıldı. Menü/sinematik ve capture süreleri FPS hesabına alınmadı.

Oynanışta15s ek mode2 doğrulaması:107pass /77.040tile, mismatch0/fault0. Giriş ve sinematik boyunca daha önce karşılaştırılmış tile'lar bu107pass sayısına eklenmedi. Doğrulama mode1'e alınarak duruldu; FPS pencerelerinde validation sayacı artmadı.

## Sonuç

A/B/A, yaklaşık45–47s/pencere, toplam940ham presented interval. B'de yalnız uzak ışık, intervalmaske ve hızlıdispatch kapalı. Metal lighting/SSAO,SSAODepthCleanup,O2veRSX yolu aynı kalıyor.

| Tur | Ek birleşik yollar | FPS | Kare aralığı |
|---|---|---:|---:|
| A | Açık |6,92770|144,35ms|
| B | Kapalı |6,30220|158,67ms|
| C | Açık |7,05480|141,75ms|

İki açık pencerenin toplam frame/süre oranı **6,99117FPS /143,03765ms**. Kapalı **6,30220FPS /158,67482ms**. Fark **15,63718ms**, kare süresinde yaklaşık%9,86azalma, FPS'de **%10,93221artış**. Her iki açık tur da aradaki kapalı turdan yüksek. Aynı termal0kategorisi ve düşük güç kapalı; aynı PID/session, yeni shader derlemesi0, GPU/compute hatası0. Örneklenen fiziksel footprint tepe1078,22MiB.

A:318interval-mask/318far-fast geçiş; özgün geçiş0. B:296özgünmaske/296özgünfar, hızlıgeçiş0. C:324interval/324far-fast, özgün0. Dispatch fast çağrılarıA129.903.817/C129.124.558; B0. Dolayısıyla yalnız ayar isteği değil, gerçek yürütme kapsamı doğrulandı. Metal lighting/SSAO sayaçları her pencerede ilerledi. GPU maske validation ve capture pencerelerde kapalı.

Bu, gerçek iPhone drawable sunum zamanlarından hesaplanan sonuçtur; Mac offscreen completion ile eşitlenmez. Sunulan yinelenmiş görüntüler sayaçtan ayırt edilemez. Bu tek soğutulmuş sabit sahne A/B/A pilotudur; bütün oyunun veya soğutmasız uzun kullanımın FPS garantisi değildir. Tek tek adayların bağımsız kazançları bu ortak sonuçtan çıkarılamaz. P95kare aralığı üç pencerede de yaklaşık183,37ms; ortalama kazanç bütün yavaş kareleri ortadan kaldırmadı.

## Son durum ve yeniden üretme

Uygulama kapatılmadı; `restore-combined/ack-*.json` ile mask1/far1/dispatch1 vefault0doğrulandı. Yeni normal ikon açılışı da bu birleşik profili seçer. Ölçüm sürücüsü bitti, devam eden benchmark yok.

```sh
# Önce iPhoneOS kaynaklarını hazırla ve tek işte imzalı build50derle.
python3 tools/prepare_bces_ios.py --support-report out/bces-support-compile-iphoneos-spu-O2-copy.json
# Uygulamayı --boot --geometry-control --renderer-memo-control --light-far-control
# --spu-dispatch-control --light-mask-control --light-mask-validate --rsx-legacy-on
# ile başlat. PS3_PAD_FILE=../ios48-pad.txt ve capture trigger/output yolları
# ../critical45-frame-request.txt /../critical45-frame.ppm olmalı.
python3 tools/drive_device_gameplay.py --device 00008130-001129E00243001C --output out/ios-combined50/tutorial
python3 tools/measure_device_combined50.py --device 00008130-001129E00243001C --run out/ios-combined50
```

Etiket mevcutsa yeni klasör seçilir. Derleme, OCR/capture ve profiler FPS pencerelerinden ayrı tutulur. Ham kanıt: `out/ios-combined50/comparison.json`, `verification.json`, `mask-validation.json`, A/B/C klasörlerindeki `frames.csv` ve snapshot'lar. Build/install logları `out/combined50-*`.

Sonraki adım: diğer portun G-buffer geri kopyasını kaldırma yöntemini bizde engelleyen fallback'in tam job/koşulunu tanılamak; ardından büyük işlerin hesap/aktarımını bütünüyle değiştirebilecek adayı seçmek. Küçük kazançların yaklaşık143ms'lik kalan kareyi33ms'ye indireceği varsayılmayacak.
