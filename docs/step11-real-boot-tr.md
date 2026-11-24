# 11. adım — tam BCES hedefi ve ilk gerçek boot

24 Ekim 2026. Amaç, BCES01229 / 01.00 kodunu firmware ve oyun varlıklarıyla
birlikte önce macOS karşılaştırma hedefinde başlatmak. iPhone'daki önceki
uygulama sentetik tanı olarak kalıyor; bu Mac hedefinin sonucu iPhone
performansı veya cihazda oyun çalışması sayılmaz.

## Disk ve girdiler

Arşiv, ISO, oyun, geçici dosyalar, derleme, sanal disk, kayıt ve loglar
`/Volumes/monssd/Infamous2-iOS` altında tutuluyor. `TMPDIR=build/tmp` mutlak
yoluyla ayarlanıyor. Bu, macOS'un sistem diskindeki swap'ını taşımaz.
8 GB RAM için tam title derlemesi **`-j1`** ile yapıldı.

`tools/extract_bces_game.py::main()`, önceden CRC kontrolü geçmiş yerel 7z'den
ISO'yu tek işçiyle çıkarır. Kesilmiş ISO'yu yeniden akışı okuyup mevcut
önekle byte byte karşılaştırarak sürdürebilir. Tam ISO:

- Boyut: **15.327.297.536 bayt**, CRC32 **245D231E**.
- SHA-256: `00bb94036457251dc3809ea3ec825f486c8663a42df32491c28888444f914000`.
- 7-Zip otomatik UDF görünümünde `Headers Error` ve 110.592 bayt trailing
  veri bildiriyor. Bu hata başarılı kabul edilmedi. Aynı ISO'nun **ISO9660
  görünümü `-tiso` ile exit 0** veriyor; iki görünümdeki **194 oyun dosyasının
  yolları ve boyutları birebir aynı**. Çıkarma açıkça ISO9660 kullanıyor.

Dosyalar önce `data/staging/BCES01229-disc` içine çıkarılır. Boyutları ISO
listesiyle, PARAM.SFO ve EBOOT.BIN hash'leri BCES profiliyle karşılaştırılır;
ardından `data/game/BCES01229` doldurulur. Var olan kullanıcı dosyasının
üzerine yazılmaz. PSARC paketleri kapalı tutulur; içlerindeki her sıkıştırılmış
girdinin sağlamlığı henüz bağımsız doğrulanmış değildir.

Oyun dosyalarının toplamı **15.057.198.876 bayt (14,02 GiB)**. Kullanıcının
bildirdiği iPhone boşluğu 23 GB; tam kurulum/önbellek ve güncelleme alanı
ölçülmeden yeterlilik garantisi verilmez. Cihaz sorgusu toplam kapasiteyi
verdi, kullanılabilir boşluğu vermedi. Oyun henüz telefona taşınmadı.

## Gerçek hedef ve akış

`tools/prepare_bces_host.py::main()` 164 title PPU kaynağını üretim
manifestine, kaynak commit'ini kilide, macOS bağımlılıklarını önceki başarılı
tanının SHA-256 kaydına karşı doğrular. Upstream dosyaları değiştirmez.
`build/bces01229/title` altında ayrı main ve GPU hook overlay'leri oluşturur.
Light/SSAO image numaraları BCES için **221/225** olur; hook gövdeleri korunur.

`cmake/bces-host/CMakeLists.txt` ayrı **Infamous2BCES** executable'ını bağlar:
164 gerçek title PPU parçası, 83 birimlik SPU/firmware destek arşivi,
tam ortak runtime, SDL/shader bağımlılıkları ve GPU hook'ları.
PPU loader/HLE/FS/sysprx birimleri BCES header'ıyla yeniden derlenir.
Bu hedefe sentetik `FullRuntimeProbe`/PPU fixture object'leri girmez.
Constructor ile kayıt olan modüller `-force_load` ile korunur.
Bu hedef **macOS'a özeldir**; arşivleri iOS'a bağlanamaz.

`cmake/bces-title/CMakeLists.txt` aynı 164 PPU kaynağını ayrı iPhoneOS
konfigürasyonunda `libbces_title.a` olarak derler. **164/164 birim PASS**;
her object `vtool` ile IOS/minimum 17.0/SDK 27.1 olarak doğrulandı.
Arşivde **30.918 farklı tanımlı title fonksiyonu** var; undef referanslar
fonksiyon sayısına katılmadı. Arşiv **103.713.312 bayt**. Bu bir uygulama
link'i veya cihazda gerçek oyun denemesi değildir.

Başlangıç akışı:

1. Pinned `main.cpp::main()` guest adres alanını ayırır ve `ppu_load_elf()`
   gerçek BCES EBOOT.elf'in PT_LOAD segmentlerini yükler.
2. `ppu_recomp_register()` title fonksiyon tablosunu kaydeder.
   `ps3_load_prx_modules()` BCES WWS region eşlemesini kaydeder. Üretilmiş
   firmware/SPU kayıt birimleri constructor'larıyla kullanılabilir image ve
   fonksiyon tablolarını kaydetmiştir. HLE, dosya sistemi ve lv2 syscall
   tabloları kaydedilir.
3. `ppu_loader.cpp::ppu_run()` içinde `lv2_prx_boot_liblv2()` gerçek firmware
   başlangıcını seçer; title entry OPD'si r11 ile firmware'e verilir.
   Firmware'in bu girişe gerçekten ulaşması ayrıca boot iziyle kanıtlanmalıdır.
4. `main.cpp::frame_clock()` guest FIFO'yu `cellGcm_rsx_process_fifo()` ile
   boşaltır. Guest FLIP hazırsa `present_guest_frame()` ortak Metal backend'e
   sunar. Isınma/boş ekran present'leri guest kare sayılmaz; guest FLIP de
   tek başına görünür ve doğru oyun görüntüsü kanıtı değildir.

## Sınırlı boot denemesi

`tools/run_bces_boot.py` tamamlanmış girdileri doğrular. Monssd APFS olduğu
için `cp -cR` ile oyun verisinden VFS disc görünümüne COW clone oluşturur;
başlangıçta ikinci 15 GB fiziksel kopya gerekmez. Yazılan bloklar ayrışabilir.
`PS3_HDD0_ROOT`, `PS3_DEV_FLASH`, `PS3_GAMEDATA_ROOT` ve çalışma dizini
monssd'ye yönlendirilir. Gerçek kullanıcı kayıtları kullanılmaz.

`src/host/BCESBootDiagnostics.cpp::bces_boot_watchdog()` yalnız
`BCES_BOOT_SECONDS` ayarlanınca başlar. Her saniye Mach `task_info()` ile
sanal boyut, resident boyut ve fiziksel footprint loglanır. Varsayılan
2.048 MiB footprint sınırında exit **125**, süre sonunda exit **124** olur.
Bunlar tanının kendi durdurmalarıdır; oyunun başarılı kapanışı sayılmaz.
Pinned main'in 3,5 GiB calloc arena'sı ve thread/stack yaklaşımı ilk karşılaştırma
için korunur. Arena boyutu doğrudan fiziksel RAM tüketimi diye sunulmaz.

İlk BCES denemesi, NPUA'ya ait sabit GPU buffer adreslerini tahmin ederek
kullanmaz. GPU light/SSAO hook'ları derlenmiş olarak korunur; etkinleştirme
adresleri gerçek BCES izinden doğrulanmalıdır. NPUA fragment shader atlama
listesi de başlangıç ölçümünde uygulanmaz. CPU JIT eklenmez.

Her deneme ayrı `out/step11-boot-<etiket>/boot.log` ve `report.json` üretir.
Log 16 MiB'ı veya dış süre sınırını geçerse yalnız kendi process grubu
durdurulur. Metal capture mevcut renderer'ın her 120 sunumda bir PPM yazma
yolunu kullanır; yakalanan görüntü ayrıca incelenmeden oyun karesi denmez.

## Tekrar üretme

Önceki 9–10. adımlarda kaynak, codegen, firmware ve SDK'ya uygun arşivler
hazır olmalıdır. Bu komutlar tüm bağımlılıkların sıfırdan kurulumu değildir.

```sh
cd /Volumes/monssd/Infamous2-iOS
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
export TMPDIR="$PWD/build/tmp"
PY=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12
$PY tools/setup_sources.py
$PY tools/extract_bces_game.py
$PY tools/prepare_bces_host.py
cmake -S cmake/bces-host -B build/bces01229/host -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=27.0
cmake --build build/bces01229/host --target Infamous2BCES -j1
$PY tools/check_inputs.py --game-dir data/game/BCES01229 \
  --eboot data/inspection/bces01229/selected/PS3_GAME/USRDIR/EBOOT.elf
$PY tools/run_bces_boot.py --seconds 20 --label first
# Tekrarda yeni etiket kullan; önceki logun üzerine yazılmaz.
# İlk kurulum kısa sürede bitmez; bu oturumdaki diğer tanılar:
$PY tools/run_bces_boot.py --seconds 120 --label install
$PY tools/run_bces_boot.py --seconds 300 --label startup
$PY tools/check_bces_install.py
# Doğrulama bittikten sonraki ayrı, sakin disk açılışı:
$PY tools/run_bces_boot.py --seconds 90 --label installed
# Gerçek title'ın ayrı iPhoneOS arşivi (macOS archive kullanmaz):
cmake -S cmake/bces-title -B build/bces01229/title-iphoneos -G Ninja \
  -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT=iphoneos \
  -DCMAKE_OSX_ARCHITECTURES=arm64 -DCMAKE_OSX_DEPLOYMENT_TARGET=17.0 \
  -DCMAKE_BUILD_TYPE=Release
cmake --build build/bces01229/title-iphoneos --target bces_title -j1
ctest --test-dir build/host -j1 --output-on-failure
```

## Doğrulama

Tam **164/164 title PPU birimi derlendi ve executable bağlandı**.
Mach-O ARM64, platform macOS, minimum/SDK 27.0; **30.918 title fonksiyon
sembolü** ve `func_00010230` entry sembolü var. İlk executable 116.922.272
bayt. Kaynak pin/yama doğrulaması PASS. Mevcut CTest **13/13 PASS**;
BCES statik kontrolü **16/16 PASS**; firmware fonksiyon sınırı regresyonu
PASS. Bu kontroller oyun boot semantiğinin doğrulandığı anlamına gelmez.

İlk 20 saniyelik tanı (`first`) gerçek liblv2 → libsysmodule/libsre →
**BCES entry `0x10230`** geçişini logladı. Beş SPURS kernel SPU'su image 100
ile başladı. Oyun GCM'yi açtı, 1280×720 display buffer'larını ayarladı ve
gerçek PSARC'ları FIOS üzerinden açtı. **361 guest present**; son capture
siyah. En yüksek saniyelik fiziksel footprint **170,50 MiB**. Süre sonu
exit 124; oyun çökmesi veya oyun başarısı diye sınıflandırılmadı.

120 saniyelik `install` tanısında **1.013 guest present** ve en yüksek
**364,88 MiB** footprint ölçüldü. Son PPM → PNG dönüşümü gözle incelendi:
alt ortada **inFAMOUS 2 logosu** var. **İlk görünür oyun içeriği doğrulandı**;
menü/bölüm, görüntü doğruluğu, ses ve oynanış doğrulanmadı. Bu Mac üzerindeki
headless Metal sonucudur; iPhone karesi/FPS'i değildir.

Oyun, SFO'su BCES01229 olsa da kurulum için gerçek binary'nin istediği
`/dev_hdd0/game/BCES01143_INSTALL/USRDIR` yolunu kullanıyor. Bu yol gözlemden
alındı; SFO'ya bakılarak başka isim tahmin edilmedi. İlk tanıda yazılan
334.476.763 bayt, ikinci tanı sonunda toplam **1.800.386.011 bayt** oldu.
Kurulum dosyaları beklenen boyuta ulaşmadan süre sınırı devreye girdi;
300 saniyelik `startup` denemesi kurulumun tamamlanmasını izler.

`startup` sırasında gerçek installer `ne.bv` bitiş dosyasını oluşturdu;
kurulum thread'i status 0 ile çıktı. Ardından gözle incelenen Metal karesinde
**Türkçe “YENİ BİR OYUNA BAŞLA” menüsü**, “Devam etmek için X butonuna bas”
yazısı, karakter ve yıldırım efektli 3D arka plan görüldü. Kanıt:
`out/step11-boot-startup/progress.png` ve `menu-inspection.json`.
**Menüye ulaşma Mac üzerinde doğrulandı**. Yeni oyun seçilmedi; bölüm,
oynanış, ses çıkışı, kayıt ve iPhone oyun çalışması test edilmedi.
Işıklandırma/renk ve tam görsel doğruluk onaylanmadı; NPUA GPU buffer
adresleri BCES'e körlemesine taşınmadı.

Kurulumdan sonra **49 dosya / 2.548.738.605 bayt** oluştu. Diskteki tam oyun
ile birlikte yaklaşık **17,61 GB** mantıksal veri var; buna uygulama,
firmware ve sonraki cache büyümesi dahil değil. Bu, kullanıcının bildirdiği
23 GB iPhone boşluğuyla karşılaştırılabilir bir ilk ölçüm; cihaz kurulum
alanı yeterliliği veya çalışma RAM'i garantisi değildir.
`tools/check_bces_install.py` kurulu dosyalardan diskte karşılığı olanları
salt okunur olarak byte byte karşılaştırır ve hash kaydeder. `ne.bv` gibi
üretilmiş girdileri ayrı raporlar; completion marker üretmez.

**Kurulum kopyası kontrolü PASS:** 48 kaynak karşılığı / 2.548.738.542 bayt
byte byte aynı. Ayrı raporlanan tek üretilmiş dosya `ne.bv` (63 bayt).
Sakin diskte sonraki 90 saniyelik `installed` açılışında kurulu paketler
doğrudan açıldı; **aynı Türkçe menü yeniden gözle doğrulandı**
(`out/step11-boot-installed/frame.png`). Yazılabilir mount dosya sayısı ve
toplam boyutu değişmedi. **1.518 guest present**, saniyelik örneklerde
en yüksek footprint **825,00 MiB**; ilk kurulumlu 300 saniyelik denemede
**2.159 present / 828,53 MiB**. Bunlar menü/başlangıç ölçümleri; iPhone veya
bölüm FPS/RAM sonucu değildir. Toplam sanal süreç boyutu yaklaşık 511 GB
görünüyor; Apple sistem/GPU rezervasyonlarını da içerdiği için bunu 3,5 GiB
guest arena'nın fiziksel tüketimi diye yorumlamıyoruz.

**Başarısız kısa tekrar da saklandı:** `warm` etiketiyle 60 saniyelik açılış,
aynı SSD'de 2,55 GB kopyanın kaynakla karşılaştırılması sürerken süre sınırına
girdi; title entry görüldü fakat guest present **0** kaldı. Karşılaştırma
bittikten sonraki `installed` denemesi menüye ulaştı. Bu gözlem I/O yükünün
etkisini düşündürür; tek başına kesin kök neden veya performans ölçümü değildir.
Tüm beş tanı native **exit 124** ile kendi süre sınırında kapandı.

Toplu sonuç `out/step11-verification.json`. iPhone 15 Pro bu oturumda
erişilebilir/paired, bağlantısı yerel ağ üzerinden görüldü; yeni oyun app'i
imzalanmadı, kurulmadı ve cihazda oyun test edilmedi. Son gözlemde sistem
diskinde **26 GiB**, monssd'de **172 GiB** boşluk vardı. Büyük girdiler ve
üretilmiş çıktılar `git check-ignore` ile Git dışında doğrulandı.

**Sonraki somut adım:** gerçek title ve 83 birimlik iPhoneOS destek arşivini,
BCES header'ıyla derlenen loader/HLE/FS/sysprx ile UIKit oyun hedefinde
birleştirmek. Sentetik PPU sağlayıcısını gerçek boot sağlayıcısından ayırmak;
VFS'yi uygulama sandbox'ındaki oyun/kurulum/kayıt yollarına bağlamak ve yaşam
döngüsünü çoklu oyun thread'leriyle doğrulamak. Ardından varlıkları cihaza
taşıyıp aynı menüyü gerçek iPhone'da sınamak. Menüden bölüme giriş, giriş/ses/
kayıt desteği ve ölçümlere göre optimizasyon sonraki ayrı doğrulamalardır.

Erken `ne.bv`, ICON0/PIC1 temporary ve xpps dosyaları için ENOENT logları var;
tek başına bu loglar kök neden sayılmadı. Installer ilerlerken paketleri
gerçek diskte oluşturuyor. Dosya sistemi hatalarını gizleyen genel bir
otomatik klasör oluşturma veya kurulum kontrolü atlama yaması eklenmedi.
Kalan **901 SPU unsupported işareti** ve PPU TODO'ları incelenmiş sayılmaz.
