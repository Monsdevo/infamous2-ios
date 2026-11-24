# 16. adım — ilk optimizasyon deneyi: statik SPU kodunda O2

24 Ekim 2026. Deney, `-O1` baseline'ını koruyup 70 üretilmiş SPU C dosyasını
`-O2` ile yeniden derler. Bu henüz ölçülmüş bir FPS kazancı iddiası değildir.

## Değişiklik ve sınırı

`tools/build_bces_spu_variant.py`, mevcut başarılı 83 birimlik iPhoneOS
destek raporunu ve arşiv üyelerini SHA-256 ile doğrular. Yalnız
`spu_recomp.c` adlı 70 kaynak için baseline derleme komutundaki `-O1` ve
object çıkış yolunu değiştirir. Diğer 13 firmware/kayıt/stub object'i
baseline'dan byte olarak aynı kalır. Üretilmiş C kaynakları değişmez.
Fast-math, strict-aliasing, overflow ve FP contraction seçenekleri değiştirilmez.
Ana PPU arşivi, runtime, çözünürlük/FOV, bellek entitlement'ı ve SPU
senkronizasyon/stack kontrolleri bu deney kapsamında değiştirilmez.

Tek compiler işi kullanılır; her birimden sonra checkpoint raporu yazılır.
`--resume` aynı kaynak/başlık/toolchain kimliğiyle tamamlanmış object'leri
tekrar kullanır. Böylece kesinti bütün derlemeyi baştan gerektirmez.
Yeni arşiv `build/bces01229/support-compile/iphoneos-spu-O2/libbces_support.a`,
raporu `out/bces-support-compile-iphoneos-spu-O2.json` içindedir.
Varsayılan O1 raporu/arşivi üzerine yazılmaz.

`tools/prepare_bces_ios.py --support-report ...` yalnız başarılı iPhoneOS
raporunu kabul eder; kaynak/object/arşiv üyelerini yine denetler. Normal
argümansız çalışması O1 seçmeye devam eder. Seçilen varyant
`dependencies.cmake` üzerinden `GameApp.mm` raporuna `support_build_variant`
olarak yazılır; dosya adından çalışmakta olan sürüm tahmin edilmez.

## Korunan baseline

- Tam imzalı önceki uygulama:
  `build/bces01229/baselines/step16-O1/Infamous2Game.app`.
- O1 executable UUID: `82DF04B1-E453-3CB0-8DFE-6AF4E40D348B`.
- O1 destek arşivi SHA-256:
  `de6c74d699017ba39cd04a9359176abaa335b71bfe504c4df1fe50e7bf3f5cb4`.
- `out/step16-O1-baseline.json` ve baseline klasöründeki kaynak raporu /
  dependencies kopyaları geri dönüş bilgilerini korur.
- Yeniden açılıştan önceki cihaz CSV/raporu `out/step16-before-*` olarak alındı.
  Oyun/firmware/kurulum verisi silinmez veya tekrar aktarılmaz.

## Derleme doğrulaması

- 70 SPU birimi O2 ve iPhoneOS platformunda başarıyla derlendi; diğer 13
  object'in SHA'ları O1 ile eşit. Üretilmiş kaynak SHA'ları aynı.
- 14.020 üretilmiş global fonksiyon sembolü O1/O2 destek arşivlerinde aynı;
  eksik üretilmiş fonksiyon yok. Bu, oyun semantiğinin bütününün eşitliğini
  ispatlamaz; cihazda boot/oynanış regresyonu ayrıca gereklidir.
- O1 arşivi 43.986.816, O2 arşivi 38.647.064 bayt. Boyut küçülmesi tek başına
  hızlanma kanıtı değildir.
- `out/step16-O2-app-build.log`: gerçek iPhoneOS `BUILD SUCCEEDED`, tek iş.
  `cmake` yeniden configure edildi; paket **0.3/build 16**.
- `codesign --verify --deep --strict` normal sandbox'ta güven deposuna
  erişemedi (`CSSMERR_TP_NOT_TRUSTED`); sistem erişimiyle aynı paket kontrolü
  başarılı (exit 0). `out/step16-signature-verification.log` son sonucu tutar.
- O2 UUID **EAAF75EF-AF0F-36C6-BEC8-80D1820E4987**; tam Mach-O bu UUID'nin
  `build/bces01229/symbols/` klasörüne korundu. Hash `out/step16-O2-binary.json`.
- `tools/test_spu_variant.py`: yalnız O seviyesi/output değişikliği ve belirsiz
  komutların reddi, 2 test PASS. Profil analiz regresyonları 3 test PASS.

## Cihaz karşılaştırması

O1 uygulama `--boot` ile yeniden açıldı. Kullanıcı menüde beklemeden yeni oyunu
başlattığını bildirdi; ilk `out/step16-O1-menu.csv` dosyası bu yüzden sabit menü
benchmark'ı değildir. Etiketi açılış/karma sahne olarak tutulur. Oynanışa
gelince sabit kamera penceresi ayrıca alınacak; sonra O2 kurularak aynı sahne
tekrarlanacak. Oturum başındaki sıcaklık daha önceki 15. adımla aynı değildi;
eski 3 FPS ölçümünden tek başına yüzdelik kazanç çıkarılmayacak.

O1 iki kez dünya geçişinde kapandı: 19:00:28 ve 19:04:23 kayıtlarının UUID'si
O1 binary ile eşleşir. İkisinde de `com.apple.AGXMetal.CodeHeap` üzerinde
`failed to create IOGPUResourceRef` allocation abort'u var. İkinci kaydın son
telemetrisinde footprint 816.974.816 bayt, ek bellek payı 2.723.017.760 bayt,
bellek uyarısı 0, pipeline 434/434/0. Bunlar sistemin kesin hata anındaki
ölçümü değil, çökmeden önce kaydedilmiş son saniyelik örnektir. Baseline
oynanış penceresi tamamlanamadı; bu yüzden kontrollü A/B kazancı henüz yok.

O2 paketinin kurulumu ve `--boot` açılışı başarılı:
`out/step16-O2-install.json`, `out/step16-O2-launch.json`.
17,80 GB oyun verisi yeniden taşınmadı; aynı bundle ID'nin Documents alanı
korundu. Bu oturumda da `--seconds` kullanılmadı. Oynanış regresyon sonucu
ayrıca kaydedilecek; O2'nin eski Metal allocation hatasını düzelttiği
varsayılmıyor.

İlk cihaz raporu `support_build_variant=spu-O2`, `link_validation_passed=true`,
`bundled_ELF_verified=true`, `inputs_ready=true`, eksik/uyumsuz dosya 0 ve
`CPU_JIT=false` doğruladı. DualSense Wireless Controller raporda tanındı.
Kullanıcı yeni oyunu başlatıp giriş anlatımına ulaştığını bildirdi. Bu,
menü/girdi/başlangıç regresyon kontrolüdür; dünya yükleme ve sabit oynanış
ölçümünün yerini tutmaz. Kanıt `out/step16-O2-boot-report.json`;
derleme/kaynak/cihaz kimlik özeti `out/step16-verification.json`.

## O2 oynanış sonucu

Kullanıcı Cole'u kontrol edebildiğini ve kumandayı bıraktığını bildirdi.
Ardından 45 saniye beklendi ve aynı PID 10373 / `spu-O2` oturumunun CSV/raporu
alındı. Son 45 saniyelik pencere 45 satır, ilk/son örnek arası 44 saniyedir.
Yeni fiziksel ekran görüntüsü alınamadı; bu aşamanın sahne doğrulaması kullanıcı
bildirimine dayanır. Kamera eşitliği önceki O1 görüntüsüyle doğrulanmadı.

| Ölçüm | O2 sabit oynanış |
| --- | --- |
| FPS medyanı / min–max | 3,5 / 3–4 |
| Ortalama kare aralığı medyanı | 284,95 ms |
| Süreç CPU medyanı | %457,73 |
| Sunum komut tamponu GPU süresi medyanı | 23,24 ms |
| Fiziksel footprint medyanı | 987.663.496 bayt, yaklaşık 942 MiB |
| Örneklenmiş fiziksel tepe | 1.016.761.480 bayt, yaklaşık 970 MiB |
| Ek bellek payı medyanı | 2.552.329.080 bayt, yaklaşık 2,55 GB |
| Bellek uyarısı | 0 |
| Isınma sınıfı | serious, pencerenin tamamı |

Kanıtlar `out/step16-O2-stationary-performance.csv`,
`out/step16-O2-stationary-bces-device-report.json` ve
`out/step16-O2-stationary-summary.json`. Son noktada Metal errors 0,
pipeline 1.020/1.020/0. Kullanıcı menüden yeni oyunu DualSense ile başlattı ve
oynanış kontrolünü doğruladı. O2 için ses/görüntü doğruluğunun ayrıntılı regresyon
incelemesi veya uzun süreli kararlılık testi yapılmadı.

15. adımdaki başarılı O1 kaydı 3 FPS, 319,51 ms, CPU %550,94 idi. O2 gözlemi
daha iyi görünür; bu iki ayrı oturumdan kontrollü kazanç yüzdesi çıkarılmadı.
Her ikisinin thermal sınıfı serious olsa da aynı sınıf aynı işlemci frekansı /
sıcaklık demek değildir. Bu oturumda yeni O1 dünya ölçümü çökmeden dolayı
alınamadı. 3 → 3,5 FPS gözlemi büyük/oynanabilirliği değiştiren artış değildir.

Bu denemede O2 dünya geçişi başarılı oldu; bu, önceki AGX heap hatasının
çözüldüğü anlamına gelmez. Telemetri/CSV kaydı korunarak O2 uygulama açık
bırakıldı; süre sınırı yok. Sonraki iş, aynı sahnede tekrarlanabilir O1/O2
karşılaştırmasını sağlayan kararlılık araştırması ve oynanış SPU profili.

## Tekrarlanabilir komutlar

Çalışma kökünden:

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
export TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp
python3 tools/test_spu_variant.py
python3 tools/build_bces_spu_variant.py --resume
python3 tools/prepare_bces_ios.py --support-report out/bces-support-compile-iphoneos-spu-O2.json
cmake -S cmake/bces-ios -B build/bces01229/ios
xcodebuild -project build/bces01229/ios/Infamous2BCESIOS.xcodeproj -scheme Infamous2Game -configuration Release -destination id=00008130-001129E00243001C -jobs 1 DEVELOPMENT_TEAM=BJ266NGN3H -allowProvisioningUpdates
xcrun devicectl device install app --device 00008130-001129E00243001C build/bces01229/ios/Release-iphoneos/Infamous2Game.app
xcrun devicectl device process launch --device 00008130-001129E00243001C --terminate-existing dev.infamous2.iosprobe --boot
```

O1'i derleme yapılandırmasına geri seçmek için `tools/prepare_bces_ios.py`
argümansız çalıştırılıp CMake configure/build tekrarlanır. Hemen önceki imzalı
paketi kurmak için baseline `.app` yolu `devicectl install app`'e verilebilir;
profil geçerlilik süresi yine uygulanır. Aynı bundle ID üzerine kurulum
Documents verilerini korur; uygulama silinmez.

O2 açılış/menü/oynanış görüntüsü, ses, DualSense ve kararlılık sınanmadan bu
varyant kesin “başarılı optimizasyon” sayılmaz. Başlangıç/girdi/oynanış smoke
testi geçti; ses/görüntü ayrıntıları ve uzun süreli kararlılık hâlâ açık.
FPS artmazsa veya doğruluk bozulursa
baseline'a dönülecek; sıradaki hedef oynanış fonksiyon profili ve SPU dispatch
maliyeti olacak. Önceki Metal allocation çökmeleri ayrıca açık kalıyor.
