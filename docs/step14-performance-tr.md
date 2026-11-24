# 14. adım — performans göstergeleri, ayarlar, ikon ve imza

24 Ekim 2026. iPhone 15 Pro üzerinde derlendi, imzalandı ve çalıştırıldı.

## Kullanım

Sağ üstteki üç nokta, UIKit ayar panelini açar. FPS, kare süresi (ortalama / p95), toplam uygulama CPU kullanımı, ekran sunum komut tamponunun GPU süresi, anlık/örneklenmiş tepe fiziksel bellek, ısınma/pil, Metal kuyruğu/hata sayısı ve render döngüsü süresi ayrı açılıp kapatılabilir. Gösterge konumu, yazı boyutu, ekranı açık tutma ve CSV kaydı da değiştirilebilir. Tercihler NSUserDefaults içinde saklanır. Panel oyunu duraklatmaz; devam eden gerçek workload ölçülür.

CPU %100 bir çekirdeğin tam kullanımını ifade eder; çok thread'li süreçte %100'ün üzerine çıkması normaldir. Isınma göstergesi derece değil iOS thermalState sınıfıdır. FPS, Metal drawable'ın gerçek presented callback'lerini sayar; guest'in aynı görüntüyü tekrar sunmasını ayıramaz. Simülatörde sahte presented sayacı üretilmez.

`Documents/performance.csv` saniyede bir ölçüm satırı alır; 5 MiB sınırı vardır. Yeni kayıt açıldığında önceki dosya `performance-previous.csv` olarak korunur (yalnız bir önceki). Paneldeki paylaşma satırı sistem paylaşım arayüzünü açar; kullanıcı paylaşım hedefini seçer. Dosyalar uygulamasından da alınabilir. CSV geçerli örnek sayıları ve CPU/bellek geçerlilik bayrakları taşır; GPU örneği yokken 0 değeri gerçek sıfır maliyet olarak yorumlanmamalıdır. Dosya paylaşımı uçtan uca denenmedi; dosyanın oluşması ve içerik kontrol edildi.

## Ölçüm yolu

- `src/platform/GameTelemetry.cpp`: 512 elemanlı sabit ring'ler, mutex ile callback/snapshot güvenliği. Son 2 saniyeden FPS, kare aralığı ortalaması/p95, GPU ve render döngüsü ortalaması. Heap büyümesi, frame başına IO veya ek GPU beklemesi yok.
- `patches/ios-metal-surface.patch`: mevcut iOS `addPresentedHandler` yolu gerçek `presentedTime` kaydeder. Tamamlanan ekran komut tamponu `GPUStartTime/GPUEndTime` farkını verir. Ayrı offscreen/compute komut tamponları bu GPU ölçümüne dahil değildir; GPU kullanım yüzdesi veya bütün karenin toplam GPU süresi değildir.
- `src/game/BCESRenderGate.cpp`: admission sonrası başlayıp frame scope çıkışında biten duvar saati ölçülür; beklemeler dahildir. Bu CPU yürütme süresi veya guest'in tüm frame süresi değildir. Zaman tabanı Metal/QuartzCore ile aynı mach_absolute_time birimindedir.
- `src/ios/GamePerformance.mm`: saniyelik getrusage CPU delta'sı / gerçek geçen süre, task_info physical footprint, örneklenmiş tepe, thermalState/pil, HUD, ayar paneli ve CSV. Kayıt ayarı HUD görünürlüğünden bağımsızdır.
- `GameApp.mm`: mevcut rapora `performance` sözlüğü ekler. Timer common run-loop modunda çalışır; panel kaydırılırken örnekleme devam eder. Eski zorunlu tanı HUD'ı gizlenmiştir.

Renderer hook'ları weak-import kullanır: eski macOS ve sentetik hedeflerin GameTelemetry'ye bağlanması gerekmez. Sabitlenmiş runtime checkout'u değiştirilmedi. Yalnız kendi overlay patch hash'i `sources.lock.json` içinde kasıtlı güncellendi; kaynak pinleri aynı. Hazırlama aracı kaynak SHA'larını ve patch SHA'sını kontrol eder.

## İkon

Kullanıcının köke koyduğu `infamous-2---button-1546993244378.jpg` 1024×1024 doğrulandı, görüntü incelendi. İçeriği değiştirilmeden PNG olarak `resources/GameAssets.xcassets/AppIcon.appiconset/AppIcon.png` dosyasına dönüştürüldü. CMake asset catalog'u Resources olarak işaretler; Xcode actool çalıştı. Paket Info.plist içinde `CFBundlePrimaryIcon/CFBundleIconName=AppIcon`, AppIcon60x60 ve Assets.car doğrulandı. Kaynak JPG korunur. Görsel yeniden üretilmedi.

## “No Longer Available” ve imza

Eski embedded.mobileprovision: CreationDate 17 Ekim 12:57:12 UTC, ExpirationDate 24 Ekim 12:57:12 UTC; kullanıcı saatinde **24 Ekim 15:57:12**. Uyarı anında profilin süresi dolmuştu.

`xcodebuild -allowProvisioningUpdates`, aynı Team BJ266NGN3H ve aynı bundle ID `dev.infamous2.iosprobe` ile yeni profil aldı. Yeni profil: 24 Ekim 13:35:34 UTC → 31 Ekim 13:35:34 UTC (**31 Ekim 16:35:34 İstanbul**). Uygulama 0.3 / build 14 olarak imzalandı ve aynı app üzerine kuruldu. Silme veya yeniden 17,80 GB aktarım yapılmadı. Yeniden açılış fiziksel cihazda başarılı. Bu bir kalıcı imza çözümü değildir; geliştirme profilinin süresi sonunda yenileme gerekir.

## Doğrulama

- `out/step14-verified-build.log`: BUILD SUCCEEDED, tek iş (`-jobs 1`).
- `tools/tests/game_telemetry.cpp`: 60 FPS düzenli zaman çizelgesi, ortalama/p95, eski/ters/NaN örnekler, 512 örneklik sınır ve 4 eşzamanlı GPU yazıcısı PASS.
- `tools/tests/bces_render_gate.cpp` GameTelemetry ile tekrar derlendi, idle/GPU fence regresyonu PASS. Bu gerçek oyunun tüm background sorunlarının çözüldüğü anlamına gelmez; 13. adımdaki sınır sürer.
- Fiziksel cihazda gerçek oyun çalışırken `out/step14-performance-report.json` içinde CPU/GPU/frame/bellek alanları ve geçerli GPU örnekleri görüldü; Metal errors 0.
- Kullanıcı üç nokta panelini açtı, CPU göstergesini kapattı ve CSV kaydını açtı. Cihaz preferences plist'inde `performance.cpu=false`, `performance.csv=true`, `performance.right=true`; CSV satırları okundu. Kanıtlar `out/step14-preferences-before.plist` ve `out/step14-performance-before.csv`.
- `out/step14-settings-screen.png` panel açıkken yakalanamadı; kullanıcı daha önce kapatmıştı. Bu görüntü HUD'ın gerçek oyun üstünde görünmesini doğrular. Panelin final görsel kontrolü ayrıca kaydedilir.

Bu oturum optimizasyon uygulamaz; sayaçlar ölçüm altyapısıdır. İlk örnekler shader/asset ısınmasını ve farklı sahneleri içerdiği için bunlardan kontrollü bölüm benchmark'ı çıkarılmadı. Sonraki adım aynı sahne/aynı kontrolcü koşullarında CSV ölçümüyle CPU/GPU darboğazını ayırmaktır.

## Tekrarlanabilir komutlar

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
export TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp
xcrun clang++ -std=c++20 -pthread -Isrc/platform tools/tests/game_telemetry.cpp src/platform/GameTelemetry.cpp -o build/bces01229/telemetry-test
build/bces01229/telemetry-test
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 tools/prepare_bces_ios.py
cmake -S cmake/bces-ios -B build/bces01229/ios
xcodebuild -project build/bces01229/ios/Infamous2BCESIOS.xcodeproj -scheme Infamous2Game -configuration Release -destination id=00008130-001129E00243001C -jobs 1 CODE_SIGNING_ALLOWED=YES DEVELOPMENT_TEAM=BJ266NGN3H -allowProvisioningUpdates
xcrun devicectl device install app --device 00008130-001129E00243001C build/bces01229/ios/Release-iphoneos/Infamous2Game.app
# Paneli oyun yükünü başlatmadan inceleme:
xcrun devicectl device process launch --device 00008130-001129E00243001C --terminate-existing dev.infamous2.iosprobe --validate-only --show-settings
# Normal açılışta kullanıcı “Oyunu başlat” düğmesine basar; süre sınırı yok.
```

## Son cihaz kontrolü

`out/step14-final-panel.png` gerçek UIKit panelini gösterir; görüntü incelendi. `out/step14-preferences-after.plist`, güncelleme/yeniden açılış sonrası CPU kapalı, CSV açık ve sağ konum seçimlerinin korunduğunu doğruladı. `out/step14-performance-final.csv` içinde 17 sütunlu yeni biçim ve ölçüm satırları doğrulandı. Son görsel kontrol oyun yükü olmadan `--validate-only --show-settings` ile yapıldı. Bu denetim argümanı paneli yalnız bir kez açar; normal ikon açılışında panel kendi kendine açılmaz.

Son kurulumdan sonra uygulama yalnız `--validate-only` ile açıldı. Son cihaz raporu alınırken oyun yeniden başlatılmıştı: `game_booted=true`, `inputs_ready=true`, eksik/uyumsuz dosya 0 ve Metal errors 0. Bu son süreçte `--seconds` yok; oyun süre sınırı olmadan çalışır. Son paket ve kaynak hash'leri `out/step14-verification.json` içindedir. Otomatik performans optimizasyonu veya 21:9 görüş değişikliği yapılmadı.
