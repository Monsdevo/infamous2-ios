# Uzak ışık elemesi — iPhone 15 Pro ölçümü

28 Ekim 2026. Build 48 fiziksel iPhone'a kuruldu ve ilk serbest oynanışta
tekrarlanabilir, sınırlı bir kazanç ölçüldü: iki kontrol dizisinde **5,73–8,11 ms**,
yaklaşık **%3,83–5,14 FPS artışı**. Bütün kabul edilen pencereler termal
sınıf2 (sıcak). Aşağıdaki kısa normal sıcaklık takibinde de kazanç görüldü;
bu kısa takip uzun süreli performans doğrulaması değildir.

## Derlenen değişiklik

`prepare_bces_ios.py` Mac üzerinde doğrulanan `ensure_backend` dönüşümünü
iOS hazırlama hattına ekler. İki hedefin aydınlatma shader metni aynı:
SHA256 `9006138e7288eb75706cf050207cb2e0c243349c81493baac4146f015edafbea`.
`GameApp.mm` başlangıçta adayı kapalı tutar; `--light-far-control` ile
aynı süreçte geliştirme komutundan açılıp kapatılabilir. `LightingFarReject.c`
seçilen yolun gerçek kullanımını ve hatalarını sayar.

O2 SPU destek raporu, 64 MiB host stack, Metal aydınlatma/SSAO ve özgün
kompakt vertex nesnesi korunur. Skinning/culling SPU/SPU; dispatch ve iki
renderer memo denemesi kapalıdır. Aynı bundle güncellenmiştir; oyun verisi
yeniden kopyalanmamıştır.

Binary UUID `97CB9062-4FF7-38C1-9E11-D4942A747601`,
SHA256 `188ea53faed580ac2a9a79845524a5506db35f5f3bb9b830d015572c46b4c235`.
Derleme `out/critical-path43/ios48-build.log` içinde BUILD SUCCEEDED;
platform IOS, imza ve özgün compact nesnesinin korunması denetlendi.
Kontrol paketi geçerli/geçersiz `light_far` değerleri için host testini geçti.

## Yöntem ve tekrar üretim

`drive_device_gameplay.py` mevcut `PS3_PAD_FILE` girişinden kamera
öğreticisini tamamlar; her komut öncesinde gerçek oyun yüzeyini OCR ile okur.
Yukarı/sol talimatlarının tamamlanması ve serbest görev hedefi aynı PID/session
ile doğrulanmadan ölçüm başlamaz. Geçiş sırasında kullanıcıdan gelen harici
bir menü girdisi de mümkün olduğundan yalnız kayıtlı komutlar otomatik sayılır.

`measure_device_light_far.py` her pencerede en az 45 saniye ve 180 gerçek
kare aralığı ister; ham CSV'yi rapor sayaç/zaman çiftiyle karşılaştırır.
Aynı süreç, sıcaklık sınıfı, ayarlar, etkin uygulama ve gerçek shader kullanım
kapsamı denetlenir. Profil, capture, yeni shader derlemesi veya mod değişimi
olan pencere geçersizdir. Aynı termal sınıf aynı saat frekansı garantisi değildir.
Mac'in ekran dışı GPU tamamlanma FPS'si iPhone ekran sunum FPS'siyle doğrudan
karşılaştırılmaz; yalnız her hedefin kendi kapalı/açık kontrolü kullanılır.

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
export TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp
python3 tools/prepare_bces_ios.py --support-report out/bces-support-compile-iphoneos-spu-O2-copy.json
cmake -S cmake/bces-ios -B build/bces01229/ios -G Xcode -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT=iphoneos -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=17.0 -DCMAKE_XCODE_ATTRIBUTE_DEVELOPMENT_TEAM=BJ266NGN3H
cmake --build build/bces01229/ios --config Release --target Infamous2Game --parallel 1
python3 tools/drive_device_gameplay.py --device 00008130-001129E00243001C --output out/ios-light-far48/tutorial
python3 tools/measure_device_light_far.py --device 00008130-001129E00243001C --mode 0 --output out/ios-light-far48/next-unique-perf-reference --scene out/ios-light-far48/tutorial/scene-ready.json --thermal-state 2
```

Ölçüm için uygulama `--boot --geometry-control --renderer-memo-control
--light-far-control --rsx-legacy-on` argümanlarıyla açılır. Ortam değişkenleri:
`PS3_PAD_FILE=../ios48-pad.txt`, `PS3RECOMP_METAL_FRAME_DUMP=../critical45-frame.ppm`,
`PS3RECOMP_METAL_FRAME_DUMP_TRIGGER=../critical45-frame-request.txt`.
Açık ölçümden önce `geometry_device_control.py --light-far 1` komutu ile
aynı oturumda geçiş yapılır; geçiş ve görüntü alma ölçüm dışında kalır.

## Sonuç

Toplam6 geçerli pencere, **1.765 ham kare aralığı**, aynı PID9277/session
`18399446-4788-4657-8861-9409FA67D38E`. CPU profili, zaman izi ve yüzey yakalama
kapalı; yeni shader derlemesi, bellek uyarısı ve renderer/compute hatası yok.
Her açık turda yalnız fast sayacı, her kapalı turda yalnız reference sayacı arttı.

| Dizi | Kapalı ortalama | Açık ortalama | Tasarruf | FPS değişimi |
| --- | ---: | ---: | ---: | ---: |
| Kapalı/açık/kapalı (A/B/C) |155,49ms|149,76ms|5,73ms /%3,69|6,43→6,68 /+%3,83|
| Açık/kapalı/açık (D2/E2/F2) |165,82ms|157,71ms|8,11ms /%4,89|6,03→6,34 /+%5,14|

| Pencere | Yol | Ham aralık | FPS | Ortalama ms | P95 ms |
| --- | --- | ---: | ---: | ---: | ---: |
| A |Kapalı|295|6,423|155,682|175,036|
| B |Açık|307|6,677|149,760|175,036|
| C |Kapalı|302|6,439|155,303|175,036|
| D2 |Açık|292|6,338|157,767|179,204|
| E2 |Kapalı|278|6,031|165,817|191,706|
| F2 |Açık|291|6,343|157,650|179,204|

Blok içindeki birleştirme toplam süre/toplam kare ile yapılır. İki blok arasında
mutlak performans kaydı; bu yüzden ilk referans ile son açık tur karşılaştırılıp
tek küresel yüzde üretilmedi. İlk bloktaki iki kapalı ortalama0,38ms, ikinci
bloktaki iki açık ortalama0,12ms farklı: her iki yöndeki yerel kontrol kazancı
tekrarlıyor. Aynı termal sınıf aynı saat frekansı garantisi değildir; bu sonuç
sıcak telefonda bu tek sahnenin kontrol deneyidir.

Üç kayıt nihai hesaba alınmadı: ilk kapalı turda günlük henüz sınırlanmamıştı;
ilk açık tur sırasında tanı günlüğü sınırına ulaşıldı; sonraki D turunda kullanıcı
ayar panelini açtı. Aday kapatılarak duruldu, panel kapandıktan sonra D2/E2/F2
dizisi tamamlandı. Bu kayıtların ham kanıtları silinmedi. Ölçüm aracının kısa
pencere mesajı gerçek ret nedenini örtüyordu; `measure_geometry.py` bu nedeni
koruyacak şekilde düzeltildi. Uzak ışık raporunda reddedilmiş son örnek artık
kabul edilmiş endpoint sayılmıyor. Mevcut6 saf ölçüm testi ve Python sözdizimi
kontrolleri geçti.

Bu oturumda makro yukarı kamera talimatını görüp `RY=0` verdi. Sol talimatı/girdisi
makro tarafından gözlenmedi; sonrasında serbest görev hedefi üç görüntüde
(029/031/034) doğrulandı. Sol öğreticisinin tamamlandığı çıkarımı bu açılmış
görev hedefinden gelir; üç girdinin tamamının otomatik verildiği iddia edilmiyor.
Makro kontrollü durduruldu ve analoglar nötrlendi. Final sahne kanıtı bu ayrımı
açıkça kaydeder; performans pencerelerinde giriş veya OCR yapılmadı.

Ölçümden sonra açık ve kapalı gerçek oyun yüzeyleri incelendi: belirgin yeni
aydınlatma/geometri bozulması görülmedi. Parçacıklar ve hedef yazısı zamanla
değiştiğinden piksel eşitliği iddiası yok. Son raporda lighting/SSAO/far fault
sayaçları0; yeni uzak ışık yolu test sonunda **kapalı**, uygulama aynı sahnede
açık bırakıldı. İki görüntü `visual-fast/frame.png` ve `visual-reference/frame.png`.

Mac'te ölçülen%11,20 FPS artışının tamamı iPhone'a taşınmadı; telefon üzerinde
gerçek kazanç daha küçük. CPU darboğazı veya güç tüketimi değişimi bu deneyle
tek başına kanıtlanmış değildir. Sonraki doğrulama normal termalde aynı kısa
kontrol ve farklı sahne olmalıdır; varsayılanı açma kararı bundan ayrı tutulur.

Kanıt kökü: `out/ios-light-far48/`; son bağımsız CSV/koşul denetimi
`final-audit.json`. Oyun verileri yeniden yüklenmedi; GitHub'a gönderim yapılmadı.

## Kullanıcının istediği kısa normal sıcaklık ölçümü

Aynı gün, yeniden başlatılmamış mevcut PID9462 üzerinde kullanıcı ilk oynanışı
sabit bıraktığını doğruladı. Önceki PID9277 kapanmış olduğundan canlı karşılaştırma
kontrolleri bu süreçte etkin değildi; yalnız mevcut FPS ölçüldü. 21 saniyelik
pencerede132 gerçek sunum aralığı: **6,269 FPS /159,503ms ortalama**. Bütün
7 tutarlı raporda termal sınıf0 (normal), uygulama etkin, panel kapalı; yeni
shader derlemesi veya bellek uyarısı yok. Metal aydınlatma/SSAO ve RSX yolu açık,
yeni uzak ışık elemesi kapalı. Bu, aç/kapat optimizasyon kıyası değildir. Ham
aralık CSV'si alınmadığı için medyan/P95 raporlanmadı; FPS tutarlı toplam
sunum sayısı ve son sunum zamanının farkından hesaplandı. Kanıt:
`out/ios-light-far48/cool-short/fps-only/summary.json`.

## Normal sıcaklıkta kısa açık/kapalı takip

Kullanıcı açık yolun da ölçülmesini istedi. Önceki PID9462 geliştirme kontrolü
olmadan açıldığından mevcut oturumda açılamıyordu. Aynı build48, `--light-far-on`
ve canlı kontrolle PID9472 olarak yeniden başlatıldı. Makro menüde CROSS verdi;
kamera öğreticisi girdileri gözlenmedi. Serbest görev hedefi027/029/030 gerçek
yüzey görüntülerinde doğrulandı; görüntü alma döngüsü durdurulup analoglar
nötrlendikten sonra ölçüldü. Makro artık öğretici atlanmışsa/önceden tamamlanmışsa
da iki gerçek serbest görev hedefini kabul eder; verilmemiş analog girdileri
otomatik verilmiş diye kaydetmez.

Aynı süreçte, aynı sahnede, her raporda **termal sınıf0 (normal)**:

| Yol | Süre | Ham kare aralığı | FPS | Ortalama ms | P95 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Uzak ışık elemesi açık |21,89s|145|6,625|150,951|166,701|
| Uzak ışık elemesi kapalı |22,04s|136|6,170|162,074|200,041|

Kısa eşleşmede11,12ms (%6,86) kare süresi tasarrufu, **%7,37 FPS artışı**.
Açık turda yalnız fast, kapalı turda yalnız reference sayacı arttı; faults0.
Yeni shader derlemesi, mod değişimi, panel açılması, profil/capture veya bellek
uyarısı ölçüm pencerelerinde yok. Bu yalnız bir açık/kapalı çiftidir; kısa
test isteği gereği ters sıra/üçüncü tekrar yapılmadı. Termal sınıf0 aynı saat
frekansını garanti etmez; sayılar tüm oyun için sabit kazanç değildir.

Önceki PID9462 üzerindeki6,269FPS ile doğrudan kıyaslanmadı. Aday aynı oturumun
sonunda tekrar **açıldı**; aktiflik ve kontrol ACK raporu saklandı. Kalıcı
varsayılan değiştirilmedi. Kanıt: `out/ios-light-far48/cool-short/short-pair-result.json`;
`short-on/` ve `short-off/` altında JSON raporları ve gerçek ham CSV'ler var.
Tekrar komutu, serbest sahne doğrulandıktan sonra:
`python3 -u out/ios-light-far48/cool-short/measure-pair.py`.
