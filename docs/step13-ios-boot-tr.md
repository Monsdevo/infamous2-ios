# 13. adım — ilk gerçek iPhone boot denemeleri

24 Ekim 2026. iPhone 15 Pro, kablosuz CoreDevice (`localNetwork`). Oyun ve firmware dosyaları cihazın kendi uygulama alanında; Mac yalnız derleme/kurulum/tanı için kullanılıyor.

## Renderer geçişi

`src/game/BCESRenderGate.cpp`: renderer zaten beklerken hızlı resume/pause, mevcut idle onayını kaybettiriyordu. Onay artık yalnız `bces_ios_frame_begin()` yeni bir batch kabul edince geçersizleşir. `bces_ios_set_active()` yalnız admission durumunu değiştirir. `tools/tests/bces_render_gate.cpp`, hızlı geçişi, çalışan CPU batch'ini ve GPU completion beklemesini sınar; PASS.

Bu yalnız renderer/GPU admission kontrolüdür. Tüm PPU/SPU thread'leri kooperatif olarak durdurulmuş değildir.

## İlk iki fiziksel cihaz denemesi

`out/step13-first-final-report.json`: 60 saniyelik gerçek PPU boot'u, 3.585 Metal sunumu, 0 Metal hatası, yaklaşık 95,7 MiB fiziksel footprint. Oyun SPURS, gerçek firmware ve GCM'yi başlattı, ancak `cellGameDataCheck()` sonrasında `NOSPACE_EXIT` yoluna girdi. Sunum sayacı gerçek oyun görüntüsü değildir; boş siyah yüzey sunuluyordu. Bu değerlerden oyun FPS'i çıkarılamaz.

`GameApp.mm::startGame()` içindeki mutlak iOS container yolu ile `BCES01143_INSTALL` birleşimi 128 karakter; runtime `cellGame.c` host path tamponu NUL dahil 128 byte. Bu nedenle mevcut kurulum klasörü kesiliyordu. Uygulama artık kendi VFS klasörüne `chdir()` yapar; `PS3_VFS_ROOT=.`, `PS3_HDD0_ROOT=dev_hdd0`, `PS3_DEV_FLASH=dev_flash`, `PS3_GAMEDATA_ROOT=saves`. UIKit'in mutlak URL'leri ve guest PS3 yolları korunur. EBOOT ELF yine mutlak bundle yolundan yüklenir.

İkinci 120 saniyelik denemede `DataCheck` mevcut kurulumu buldu, `GetSizeKB` çağrıldı, ancak yine `NOSPACE_EXIT`. `statvfs` gerçekten yaklaşık 2,23 GB boş alan bildirdi; NSURL important-usage kapasitesi yaklaşık 5,80 GB idi. Bunlar aynı ölçüm değildir; boş alan uydurulmadı.

İkinci rapor `out/step13-vfs-button-report.json`: 7.185 Metal sunumu, 0 Metal hatası, renderer stop onayı 1. Fiziksel ekran `out/step13-vfs-first-screen.png` incelendi: siyah yüzey ve kendi tanı HUD'ımız, **oyun görüntüsü yok**.

## Kurulum boyutu HLE düzeltmesi

Pinned `cellGameGetSizeKB()` stub'ı her zaman 0 yazıyordu. Bu, mevcut 2,55 GB kurulumu yok sayıp yeniden tüm kurulum için alan istemesine yol açıyordu. `src/game/BCESGameStorage.c` pinned cellGame implementasyonunu içerir, yalnız boyut stub'ını gerçek dizin ölçümü ile değiştirir. Mevcut check oturumunun HDD içerik klasörü sayılır; dosya boyutları ayrı ayrı KiB'a yuvarlanır, sonuç guest big-endian belleğe yazılır. Symlink takip edilmez, okuma/erişim hataları bildirilir, derinlik ve s32 sınırı korunur. Eksik klasörün boyutu 0'dır.

Semantik karşılaştırma için [RPCS3 cellGameGetSizeKB](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/Cell/Modules/cellGame.cpp) incelendi: mevcut içeriğin dizin boyutunu hesaplar. RPCS3 kaynak kodu kopyalanmadı; kendi pinned HLE üzerine POSIX dizin sayımı yazıldı.

`prepare_bces_ios.py` artık doğrulanmış iPhoneOS runtime'ın kopyasından `rsx_metal_backend.o` ve `cellGame.o` çıkarır; Metal ve storage birimleri oyun hedefinde yeniden derlenir. Orijinal arşiv değiştirilmez. Türev her hazırlamada yeniden oluşturulur; eski cache'in yalnız dosya adına güvenilmez. Hazırlama raporuna adapter hash'i yazılır. macOS hedefi ve pinler değiştirilmedi.

`tools/tests/bces_game_storage.c`: iç içe dosya ölçümü, KiB yuvarlama, big-endian yazma, NULL argüman, eksik/boş klasör, dizin olmayan içerik hatası ve symlink izlemeden sayım PASS.

## DualSense

Gerçek cihazda SDL iki joystick gördü: iOS Accelerometer (gamepad değil), DualSense Wireless Controller (`mapped=1`). iOS `GCController.controllers` da DualSense'i gördü. Kullanıcının yaklaşık 3 saniyelik × basışı ikinci raporda `controller_button_seen=true` oldu. Bu, iOS'un tuş basışını gördüğünü doğrular; gerçek oyun henüz menüye ulaşmadığından oyun içindeki tüm eşlemeler/analoglar doğrulanmış değildir. Mevcut runtime `cellPad.c` SDL yolunu korur.

## Tekrarlanabilir kontroller

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
export TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp
xcrun clang++ -std=c++20 -pthread -Isrc/game -Isrc/platform -Iupstream/infamous2-recomp/ps3recomp-fork/libs/video -Iupstream/infamous2-recomp/ps3recomp-fork/include tools/tests/bces_render_gate.cpp src/game/BCESRenderGate.cpp -o build/bces01229/render-gate-test
build/bces01229/render-gate-test
xcrun clang -std=gnu17 -Iupstream/infamous2-recomp/ps3recomp-fork/include tools/tests/bces_game_storage.c -Wl,-dead_strip -o build/bces01229/storage-test
build/bces01229/storage-test
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 tools/prepare_bces_ios.py
cmake -S cmake/bces-ios -B build/bces01229/ios
xcodebuild -project build/bces01229/ios/Infamous2BCESIOS.xcodeproj -scheme Infamous2Game -configuration Release -destination id=00008130-001129E00243001C -jobs 1 CODE_SIGNING_ALLOWED=YES DEVELOPMENT_TEAM=BJ266NGN3H -allowProvisioningUpdates
xcrun devicectl device install app --device 00008130-001129E00243001C build/bces01229/ios/Release-iphoneos/Infamous2Game.app
xcrun devicectl device process launch --device 00008130-001129E00243001C --terminate-existing dev.infamous2.iosprobe --boot --seconds 120
```

Tanı süresi yalnız `--seconds` ile verilir; sonunda renderer gate kapatılıp onay kaydedilir ve süreç 124 ile çıkar. Varsayılan uygulama otomatik boot yapmaz. `game_booted=true`, worker'ın başlatıldığını belirtir; menü veya ilk görüntü kanıtı değildir. Canlı yazılan logu CoreDevice ile okuma bazen socket kapanmasıyla başarısız oldu; süreli denemenin ardından tekrar okuma başarılıydı.

## İlk gerçek oyun görüntüsü — üçüncü deneme

Kurulum ölçümü `installed_KiB=2489025` bildirdi; `NOSPACE_EXIT` aşıldı. Fiziksel ekran görüntüsü `out/step13-storage-screen.png` incelendi: Türkçe **“Yeni bir oyuna başla”** menüsü, Cole ve elektrik efektleri var. Böylece iPhone'da ilk gerçek oyun karesi doğrulandı. Görsel kanıtın SHA-256'sı ve değerlendirme `out/step13-game-image-verification.json` içinde. Uygulamanın kendi `device_game_image_verified` alanı otomatik görsel doğrulama yapmadığından false kalır; manuel görsel kanıt ayrı tutulur.

120 saniyelik denemenin son raporu `out/step13-storage-final-report.json`: 1.311 Metal sunumu/tamamlanması, 0 Metal hatası, renderer stop onayı 1, fiziksel footprint yaklaşık 712 MiB (son örnek, tepe değer değil). Menü ekranı örneğinde yaklaşık 715 MiB. Bu sayılar kontrollü FPS benchmark'ı değildir. Tüm oyun görüntüsü ve bölüm doğruluğu henüz kanıtlanmadı. Audio mixer/portlar başladı; duyulan ses ve kayıt doğruluğu ayrıca denenmeli.

Kullanıcı × basışının menüyü ilerletmediğini bildirdi. SDL ivmeölçeri joystick 0'a, DualSense'i 1'e koyuyordu; `cellPad` joystick indeksini guest portu olarak kullanır, oyun port 0'ı okuyor. `GameApp.mm::startGame()` artık SDL init öncesi `SDL_HINT_ACCELEROMETER_AS_JOYSTICK=0` ayarlar. SDL'nin projede kullanılan header ve `SDL_mfijoystick.m` kaynakları bu ayarı doğruluyor. CPU/oyun koduna tuş simülasyonu eklenmedi.

## Sonuç — dördüncü deneme

`out/step13-pad-runtime.log`: SDL artık yalnız bir joystick görüyor; `joystick[0]=DualSense Wireless Controller mapped=1`. `cellPad` de DualSense'i port 0'da açtı. Kullanıcı yeni oyunu × ile başlatabildiğini ve ses geldiğini doğruladı. `out/step13-pad-screen.png` fiziksel ekranında çizgi roman giriş anlatımı görüldü; görsel olarak incelendi. Sonradan alınan `step13-pad-intro-screen.png` süre dolduktan sonra çekildiğinden oyun görüntüsü kanıtı olarak kullanılmaz.

`out/step13-pad-report.json`: 180 saniyelik tanı sınırı, 1.824 Metal submitted/completed/presented, 0 Metal hatası, son footprint 797.101.048 byte (yaklaşık 760 MiB). Bu tepe bellek veya oynanış FPS ölçümü değildir. `controller_button_seen=false` son raporda kısa basışın 1 Hz tanı örneklemesinde kaçırılabileceğini gösterir; gerçek oyun tepkisi kullanıcı tarafından ve giriş ekranıyla doğrulandı.

**Açık sınır:** son denemede `renderer_stop_acknowledged=0`: 1 saniyelik bekleme içinde idle onayı alınmadı. Önceki iki gerçek denemede onay 1 idi. GPU sayaçları tamamlanmış olsa da bu tüm renderer/CPU işinin park ettiğini kanıtlamaz. Nedeni ayrıca incelenmeli; gerçek oyunun background/pause güvenliği tamamlandı sayılmaz. Süreli test explicit `_exit(124)` ile biter; süreç belleği OS tarafından temizlenir. Normal kullanıcı açılışında tanı süresi verilmez.

Son uygulama `out/step13-ios-pad-build.log` ile tek iş (`-jobs 1`) olarak derlendi, imzalandı, cihazda çalıştırıldı. `out/step13-build-validation.json` son executable ve kaynak SHA-256'larını, IOS Mach-O platform kontrolünü ve Mac framework'lerinin bağlı olmadığını kaydeder. Manifest/token uyumu tekrar doğrulandı; 17,80 GB veri yeniden taşınmadı.

**Sıradaki somut iş:** ilk oynanabilir bölümü kontrollü süreyle yüklemek; bu sırada frame süreleri, fiziksel bellek tepe değeri, input ve sesi ölçmek. Renderer stop onayı zaman aşımını ve gerçek arka plan geçişini ayrıca çözmek/sınamak. Kayıt, tüm DualSense tuşları/analoglar ve dokunmatik kontroller henüz doğrulanmadı. Mevcut uygulama ikonundan açılıp dosya kontrolünden sonra “Oyunu başlat” ile tanı süresi olmadan başlatılabilir; bu kararlı bitmiş port anlamına gelmez. Mac'in oyun çalıştırması veya veri sunması gerekmez.
