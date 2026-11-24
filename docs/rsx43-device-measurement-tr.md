# RSX build 43 — gerçek iPhone ölçümü

27 Ekim 2026. Karşılaştırma tamamlandı. **Bu denemede anlamlı FPS kazancı gösterilemedi.** Yeni yol gerçekten çalışıyor ve eski RSX durum işlemcisinin yükünü azaltıyor; bu azalma toplam kare süresine belirgin biçimde yansımadı.

## Koşullar ve sonuç

Aynı build 43, iPhone 15 Pro / A17 Pro; UUID `E23215F7-09F9-32A0-B980-E69D7AF6B452`, uygulama SHA256 `800a3b8e53668c762ed68a45d0e514fe0c93ce6f070017bcfb7e69f96ebfefb5`.
Her yeni süreçte kullanıcı aynı ilk oynanış konumunu, sabit karakter ve kamerayı teyit etti. Geometri SPU/SPU; doğrulama ve geometri kayıtları kapalı; Metal aydınlatma/SSAO ve mevcut SSAO temizliği açık. CPU örnekleyici ve zaman izi FPS pencerelerinde etkin değildi. RSX seçimi süreç başında sabitlendi; uygulama içinde değiştirilmedi.

| Tur | RSX yolu | Termal sınıf | Gerçek kare aralığı | Süre | FPS | Ortalama kare | p95 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| A | Kapalı | Sıcak (2) | 161 | 32,073 s | 5,02 | 199,21 ms | 233,38 ms |
| B | Açık | Normal (0) | 199 | 32,040 s | 6,21 | 161,00 ms | 200,04 ms |
| C | Kapalı, yeniden başlatılmış | Normal (0) | 195 | 31,040 s | 6,28 | 159,18 ms | 200,04 ms |
| C tekrar | Kapalı, aynı süreç | Normal (0) | 199 | 31,073 s | 6,40 | 156,15 ms | 200,04 ms |

Her FPS penceresinde 10 termal örneğin tamamı belirtilen sınıftaydı. Kare zamanları HUD ortalamalarından değil, gerçek drawable sunum zamanlarının ham aralıklarından hesaplandı. Kontrollerde yeni pipeline/hata görülmedi.

Normal sınıftaki iki kapalı pencerenin toplamı **6,34 FPS / 157,65 ms**; açık pencere **6,21 FPS / 161,00 ms**. Gözlenen fark açık yol aleyhine yaklaşık **%2,09 / +3,36 ms**. Kapalı tekrarın kendisi önceki kapalı pencereden yaklaşık %1,94 daha hızlı. Tek açık süreç ve ardışık pencereler, bu küçük farkı kesin regresyon veya istatistiksel olarak kanıtlanmış fark saymak için yeterli değil. Açık yol için FPS kazancı iddiası da desteklenmiyor.

A sıcak, B normal olduğundan A→B'deki yaklaşık %23,7 FPS farkı optimizasyon kazancı olarak kullanılamaz. Aynı termal sınıf bile aynı CPU/GPU frekansını kanıtlamaz. Yeni süreçler, sahne teyidi ve benzer komut yükü; NPC/animasyon zamanlamasının deterministik eşitliğini sağlamaz. Bu sonuçlar ilk sabit oynanış sahnesiyle sınırlıdır.

## Yeni yol gerçekten çalıştı mı?

Evet. Açık FPS penceresinde 67.606.337 method bildiriminin **51.796.612'si (%76,62)** eski durum işlemcisine tekrar gönderilmedi; 15.809.725'i iletildi. Debug geri dönüşü kapalıydı. Kapalı pencerelerde atlanan bildirim sıfırdı. Senkronizasyon ve draw bildirimleri iletilmeye devam etti.

B'de 2.651.784 draw bildirimi / 199 kare aralığı ≈ 13.325,55 bildirim/kare. A'da 13.325,52 idi. Bu sayaçlar gerçek Metal draw-call sayısı değildir. Benzerlik yükün karşılaştırılabilirliğini destekler; görüntünün piksel düzeyinde eşitliğini kanıtlamaz.

Bu değişiklik, etkin çizim motorunun işini kaldırmıyor. Eski işlemcideki kullanılmayan durum yazılarının tekrarını azaltıyor; etkin RSX dispatch, vertex hazırlama, texture kontrolü ve Metal gönderimleri sürüyor.

## Ayrı CPU kayıtları

FPS pencerelerinden sonra ayrı 15 saniyelik kayıtlar alındı. Her kayıtta UUID eşleşti, örnekleme hatası ve kesilme sıfırdı. Bunlar örnekleyici açık kayıtlar olduğundan FPS benchmark'ı olarak kullanılmadı.

| Kayıt | Termal | Süre | Renderer CPU süresi | Çalışan PC örneği | Eski parser payı | Adaptör payı | İkisi toplam |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A kapalı | Sıcak (2) | 15,024 s | 7,594 s | 587 | %7,33 | %0,51 | %7,84 |
| B açık | Normal (0) | 15,021 s | 8,441 s | 591 | %1,86 | %3,38 | %5,25 |
| C kapalı | Normal (0) | 15,013 s | 9,148 s | 583 | %9,43 | %1,89 | %11,32 |

Parser `rsx_process_method`, adaptör `bces_rsx_legacy_method`. Normal sınıftaki C→B kayıtlarında parserın örneklenen CPU payı düşüyor; adaptörün payı yükseliyor. Birlikte örneklenen pay %11,32→%5,25. Bu yüzdeler **renderer thread CPU'sunun** istatistiksel dağılımıdır; kare süresinden doğrudan çıkarılamaz. Toplam renderer CPU süresi de daha düşük, ancak kayıtlar ayrı zamanlarda ve aynı frekans garantisi olmadan alındığından kesin neden-sonuç miktarı verilemez. Örnek sayısı sınırlı, stack ancestry best-effort; sistem/çözümlenemeyen yapraklar A/B/C'de yaklaşık %28/%27/%26 ve hesapta korunuyor.

Sonuç: eski parser işinin azalması sayaçlar ve örneklerle destekleniyor; bu iş ilk sahnede toplam FPS'yi belirleyen tek sınır değil. Diğer thread/GPU işleriyle örtüşme, bekleme ve sunum zamanlaması bu kayıttan kesin ayrıştırılamıyor. CPU azalmasını FPS kazancı diye sunmuyoruz.

Açık/kapatılmış normal kayıtlarında `rsx_vertex_fetch_all` yaklaşık %20/%18, `eng_texture_content_hash` yaklaşık %9/%9 renderer CPU payında kalıyor. Kapalı C'de remap yaklaşık %3,95, topology/index hazırlama %3,43. Sonraki aday **vertex verisi hazırlama, remap/index ve kopyalama zinciri**; önceki kaynak incelemesiyle uyumlu. Bunlar adaydır, garantili kare kazancı değildir. Bu oturumda yeni bir optimizasyon uygulanmadı.

## Tekrar üretme ve kayıtlar

Ham kayıtlar, analiz ve kontrol noktası `out/rsx43-device-measurement/` altında. `result.json` bütün pencere özetlerini ve örnek CPU paylarını birleştirir. `analyze_results.py` cihazla iletişim kurmadan yeniden hesaplar. Önceden bulunan cihaz CSV'leri `preexisting/` içinde korundu. Bu oturumda uygulama derlenmedi veya yeniden kurulmadı; GitHub'a dokunulmadı.

Ölçüm için önce aynı build uygun `--rsx-legacy-on` veya `--rsx-legacy-off` ile yeni süreçte açılır. `--geometry-control --profile-cpu` ölçüm bağlantısını sağlar; CPU kaydı komut verilene kadar bekler. İlk oynanış/sabit kamera teyidi ve termal durum kontrolünden sonra, **yeni çıktı klasörleriyle**:

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
export TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp
python3 tools/measure_rsx.py --device 00008130-001129E00243001C --mode on --thermal-state 0 --scene first-gameplay-fixed-camera --output out/rsx43-new-on-window
python3 tools/capture_cpu_profile.py --device 00008130-001129E00243001C --seconds 15 --output out/rsx43-new-on-cpu
python3 tools/analyze_rsx_cpu.py --profile out/rsx43-new-on-cpu/cpu-profile.csv --binary build/bces01229/symbols/E23215F7-09F9-32A0-B980-E69D7AF6B452/Infamous2Game --output out/rsx43-new-on-cpu/renderer-analysis.json
python3 out/rsx43-device-measurement/analyze_results.py
```

`--thermal-state` gerçekten gözlenen sınıfa göre seçilir. Sınıfı değişen pencere reddedilir; sıcak/ılık kayıtlar normal performans diye etiketlenmez. Doğrulayıcıların 6 testi ve Python syntax kontrolleri geçti.

Son oyun süreci C kapalı referanstır (PID 6740). CPU kontrolü yeniden `idle` yazılarak durduruldu; kullanıcıdaki kalıcı RSX tercihine dokunulmadı. Sonraki normal açılış kalıcı tercihi kullanır.
