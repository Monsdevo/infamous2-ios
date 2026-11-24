# 12. adım — gerçek oyun uygulaması ve iPhone veri aktarımı

24 Ekim 2026. Hedef BCES01229 / 01.00, fiziksel iPhone 15 Pro.

## Doğrulanan durum

- `cmake/bces-ios/CMakeLists.txt` ayrı UIKit/Objective-C++ oyun uygulamasını oluşturur. Gerçek 30.918 PPU fonksiyonlu title arşivi, firmware/SPU destek arşivi ve iPhoneOS runtime bağlandı. macOS hedefi korundu.
- `tools/prepare_bces_ios.py`, sabitlenmiş kaynakları/arşivleri doğrular; macOS başlatıcısından iOS runner ve BCES shader/SPU hook uyarlamalarını üretir. CPU kodu statik yeniden derlemedir; CPU JIT yoktur.
- `src/ios/GameApp.mm`, CAMetalLayer yüzeyi ve Documents/BCES01229 içindeki oyun/firmware/kurulum verilerini kullanır. Varsayılan açılış oyunu başlatmaz. Önce dosya denetimi yapılır.
- `src/game/BCESIOS.cpp` içindeki `bces_ios_validate_link()`, gerçek PPU tablosunu, PRX/SPU kayıtlarını, gerçek BCES SPU leaf fonksiyonunu ve 3,5 GiB sanal alanın birkaç seyrek sayfasını fiziksel telefonda doğruladı. Bu, 3,5 GiB fiziksel RAM tüketimi veya tüm oyunun bellek başarısı değildir.
- Uygulama derlendi, imzalandı, iPhone'a kuruldu. Aynı geliştirme bundle kimliği `dev.infamous2.iosprobe` kullanıldı; Documents korundu.
- İlk cihaz denemesinde Objective-C nesne ömrü nedeniyle çökme oldu. Xcode karma dil hedefinde dil koşullu ARC bayrağı gerçek derlemeye uygulanmamıştı. GameApp/AppleWorkPool ve Metal backend için kaynak bazında `-fobjc-arc` tanımlandı. Pinned runtime arşivi korunup Metal object'i çıkarılmış ayrı türev arşiv ve yeniden derlenen ARC backend kullanıldı. Son build: `out/step12-ios-ready-build.log`.
- iPhone'da **gerçek oyun boot'u henüz yapılmadı; gerçek oyun karesi 0**. Dosya ve bağlantı denetimi renderer/oyun başarısı değildir.
- Kullanıcı Mac'te görünür çalıştırmada oynanabilir dünyaya ulaştığını ve DualSense'in denediği girdilerinin çalıştığını bildirdi. Elle saydığı 35 kare/15 saniye yaklaşık 2,3 FPS'tir; kontrollü benchmark değildir. iPhone performansı bilinmiyor.

## Veri aktarımı ve kesinti

Manifest: `build/bces01229/ios-prepared/resources/bces-inputs.json`.
Toplam 1.318 dosya, 17.801.016.289 byte:

- `data/game/BCES01229` → `Documents/BCES01229/PS3_GAME`
- `data/firmware/dev_flash` → `Documents/BCES01229/dev_flash`
- `data/vfs/BCES01229/dev_hdd0` → `Documents/BCES01229/dev_hdd0`

Oyunun istediği `BCES01143_INSTALL` klasör adı korunur. Mac kayıtları taşınmaz.
Oyun dosyaları, firmware ve büyük çıktılar Git'e eklenmez.

USB aktarımı Mac'in şarj ihtiyacı nedeniyle kullanıcı tarafından durduruldu.
Yalnız bu aktarım ve ekran yakalama süreçleri kapatıldı; kısmi dosyalar silinmedi.

Kablosuz tekrar bağlantıda 46 dosya / 6.709.753.835 byte kaynakla aynı boyutta bulundu. Bu tüm dosyaların hash doğrulaması değildir. Toplam 7.589.921.574 byte görünüyordu; aradaki veriler kısmi/uyumsuz dosyalardı. Güncel uygulama raporu 1.253 eksik, 19 uyumsuz dosya ve 16.218.653.468 byte kullanılabilir alan gösterdi.

16 MiB rastgele dosya Wi-Fi üzerinden 2,143 saniyede gönderildi: komut ek yükü dahil yaklaşık 62,64 Mbps. Geri okunan dosyanın SHA-256 özeti eşleşti (`out/step12-wifi-probe.json`). Bu internet hattı veya sürekli büyük aktarım benchmark'ı değildir.

`tools/transfer_bces_ios.py --resume` cihaz envanterinde boyutu eşleşen dosyaları korur, yalnız eksik/uyumsuz girdilerin hard link'lerini monssd üzerindeki özel staging klasöründe toplar. Kaynak dosyaların mtime'ına dokunmaz. Seçili tüm veri için boş alan + 1 GiB pay ister; kısmi dosyaların hemen yer açacağını varsaymaz. İlk Wi-Fi devamında 1.272 dosya / 11.091.262.454 byte seçildi.

Bütün aşamalar bittikten sonra cihazın tüm envanteri tekrar boyut denetiminden geçmeden `transfer-complete.json` yayımlanmaz. Uygulama ayrıca kritik SFO/SELF ve bundled ELF hash'lerini doğrular. Büyük arşivlerin tamamının cihazda hash'lenmiş olduğu iddia edilmez.

## Tekrarlanabilir komutlar

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
export TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp
xcrun devicectl list devices
xcrun devicectl device process launch --device 00008130-001129E00243001C --terminate-existing dev.infamous2.iosprobe --validate-only
# Uygulamadaki dosya kontrolü bittikten sonra: rapordaki boş alan güncel olmalı.
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -u tools/transfer_bces_ios.py --device 00008130-001129E00243001C --resume
```

Aktarım günlüğü `out/step12-wifi-transfer.log`; durum dosyası `out/step12-asset-transfer/state.json`. Aynı anda ikinci aktarım başlatılmaz. Kablo yeniden takılması gerekirse önce mevcut işlem durdurulur.

## Wi-Fi aktarımının sonucu

Aktarım tamamlandı. Üç fazın komut süreleri toplamı 535,83 saniye (yaklaşık 9 dakika); 11,09 GB seçili verinin bu süreye oranı yaklaşık 166 Mbps. İlk küçük dosya testinden farklı bir ölçümdür; hazırlık ve son kontrol sürelerini içermez.

`out/step12-asset-transfer/state.json`: `complete=true`, `final_inventory_size_mismatches=[]`. Korunan 46 dosyanın kaynakla mtime eşleşmesi de kontrol edildi. `tools/test_transfer_bces_ios.py` içindeki 3 çevrimdışı regresyon geçti: kısmi dosyayı seçip tamamlanmış olanı koruma, yetersiz boş alanda durma, son envanter başarısızsa token yayımlamama.

Uygulama `--validate-only` ile yeniden açıldı. `out/step12-device-ready-report.json` fiziksel cihaz sonucu:

- `inputs_ready=true`, `transfer_complete=true`
- `missing_files=0`, `mismatched_files=0`
- `bundled_ELF_verified=true`, `link_validation_passed=true`
- `available_capacity_bytes=5902991260` (yaklaşık 5,90 GB)
- `game_booted=false`, `guest_present_calls=0`, `Metal_presented=0`

Oyun verileri artık iPhone'un kendi uygulama alanında. Mac'ten dosya akışı veya görüntü aktarımı yapılmıyor. Henüz gerçek oyun boot'u denenmedi; bağımsız oynanabilirlik doğrulanmış sayılmaz.

Tekrar kontrol ve regresyon:

```sh
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 tools/test_transfer_bces_ios.py
xcrun devicectl device copy from --device 00008130-001129E00243001C --domain-type appDataContainer --domain-identifier dev.infamous2.iosprobe --source Documents/bces-device-report.json --destination out/step12-device-ready-report.json --timeout 20
```

## Bu adımdan sonraki işler

Güncelleme: [13. adımda](step13-ios-boot-tr.md) ilk gerçek iPhone menüsü ve giriş anlatımına ulaşıldı; aşağıdaki eski gate yarışı düzeltildi. Gerçek workload altında stop onayı zaman aşımı ayrı bir açık konu olarak kaydedildi.

İlk gerçek oyun boot'undan önce render gate'in hızlı resume/pause durumundaki idle onay yarışını düzeltip anlamlı regresyonla sınamak gerekir. Mevcut gate tüm PPU/SPU thread'lerini kooperatif olarak durdurmaz; eski sentetik lifecycle testi gerçek oyunu kanıtlamaz. Ardından sınırlı süreli fiziksel cihaz boot'u, Metal/CPU/bellek logları ve gerçek ekran görüntüsü. Menü, bölüm, ses ve iOS kontrolcü girdileri henüz doğrulanmadı.
