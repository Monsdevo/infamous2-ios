# 10. adım — BCES SPU ve firmware destek kodu

17 Ekim 2026. Native iOS hedefi, macOS karşılaştırma hedefi ve sabit runtime
korundu. **Tam oyun executable'ı bağlanmadı, cihazda oyun başlatılmadı;
game_frames=0.** Önceki iPhone uygulaması sentetik tanı olarak kalıyor.

## Firmware girdisi ve araç davranışı

Resmî 4.93 PUP, RPCS3'ün `--headless --installfw` yolu ile açıldı. Sabit
RPCS3 commit'indeki `main_window.cpp::HandlePupInstallation` PUP başlığını,
boyutunu ve entry hash'lerini denetliyor. Log, **“Successfully installed PS3
firmware version 4.93”** yazıyor; `version.txt` de `release:04.9300` diyor.
Bu, Sony imza güven zincirinin bağımsız doğrulanması değildir.

**Araç kapanışı temiz değil:** işlem, başarı logundan sonra global typemap
yıkımında `Emulation object is unavailable (process teardown)` ile **134**
döndü. `out/step10-rpcs3-firmware-installer.log` başarıyı, ayrı install logu
kapanış hatasını saklıyor. Bu nedenle exit 0 veya kusursuz kurulum denmiyor.
Çıktılar dosya hash'leri ve PRX ELF başlıklarıyla ayrıca doğrulandı.

Önceki portable varsayımı düzeltildi: bu RPCS3 binary'si executable yanındaki
`portable/` dizinini kullanmadı. Kendi dosyalarını şu kullanıcı dizinlerine
yazdı; mevcut dosyalar silinmedi:

- `~/Library/Application Support/rpcs3/dev_flash`
- `~/Library/Caches/rpcs3`

1075 dosyalık `dev_flash`, yerel `data/firmware/dev_flash/` içine kopyalandı.
`sys/external` altındaki liblv2/libsysmodule/libsre SPRX'leri
`data/firmware/prx/` içine alındı ve çözüldü. RPCS3, **her dosya için ayrı
`--decrypt`** istiyor; bu seçenek zaten headless modu seçiyor. Host aracı
iOS'a eklenmiyor. Hiçbir PS3 veya iPhone sistem yazılımı güncellenmedi.

`tools/prepare_firmware_inputs.py::main()` PUP, sürüm, SPRX/PRX hash'lerini
ve ELF64 big-endian PPC64 PRX türünü doğrular. Var olan farklı girdinin
üzerine yazmaz. Kimlikler `profiles/firmware-4.93.json` içinde.

`tools/prepare_firmware_lle.py::main()`, pinned `lift_prx.py::Prx` ile
relocation uygular; ardından `ppu_lifter.py` ve `gen_prx_module.py` çalışır.
Upstream wrapper'ın varsayılan çoklu iş sayısı yerine **`--jobs 1`** kullanır.

| Modül | Guest base | Üretilen fonksiyon sayısı |
| --- | --- | --- |
| liblv2 | `0x30000000` | 335 |
| libsysmodule | `0x30180000` | 220 |
| libsre | `0x30100000` | 440 |

Bu sayılar keşif/üretim sayısıdır; tüm girişlerin gerçek fonksiyon olduğu
veya firmware başlangıcının çalıştığı iddia edilmiyor. Üretilmiş firmware
PPU kodundaki TODO'lar da incelenmiş veya güvenli sayılmadı.

**Üretici hatası gerçekten yakalandı ve düzeltildi.** İlk native kayıt
tanısında üç modülün de function table adres kontrolü başarısızdı. Pinned
`ppu_lifter.py::main()`, `--raw --base ... --code-end ...` kullanıldığında
`code_lo` değerini sıfır bırakıyor; `PPULifter.generate_mid_function_entries()`
bu aralığın dışındaki gap hedeflerini de fonksiyon yapabiliyordu. Başlangıç
tablolarında liblv2/libsysmodule/libsre için 101/82/500 aralık dışı kayıt vardı.

`prepare_firmware_lle.py::bounded_lifter()`, checksum'u kontrol edilen kaynaktan
**yalnız yerel build overlay'i** üretir: raw alt sınırını `base_addr` yapar,
gap üretiminde `_outside_code()` denetimi uygular. Ortak fork ve title PPU
üreticisi değişmez. `tools/check_ppu_bounds.py`, bize ait iki komutluk PPC
örneğinde aynı hatayı pinned üreticide yeniden oluşturur; bounded üreticide
yalnız tek doğru kayıt kaldığını ve üç firmware tablosunun da artık image
aralığında olduğunu doğrular. **683 hatalı kayıt üretim sırasında engellendi**;
başarısız native testin kontrolü gevşetilmedi. İlk hata logu
`out/step10-support-host-unbounded.log`, regresyon kanıtı
`out/ppu-bounds-validation.json` içinde. Bu koruma, modül içindeki tüm
kod/veri ayrımını veya firmware davranışını çözmüş sayılmaz.

`tools/prepare_firmware_spu.py::main()` libsre image hash'ini, SPU gövde
pointer/size slotlarını ve doğrudan dalları kontrol eder. İki SPU ELF
image 100–101; üç raw gövde image 102–104 olarak üretildi. 4.93 image'ındaki
üçüncü gövdenin boyut slotu **0x3e30** diyor; README'deki **0x3da0** körlemesine
alınmadı. Kod uzunlukları `0x2110 / 0x1c00 / 0x3cf0`; gövde verileri ELF'de
kalır. Tüm dolaylı dallar kanıtlanmış veya kernel çalıştırılmış değildir.

## BCES WWS eşlemesi

`tools/prepare_bces_spu.py::checked_elf()` ELF hash'ini ve PT_LOAD eşlemesini
kullanır. `validate_wws()` aşağıdaki gerçek kod/veri ilişkilerini sınar:

- Guest **`0x887100`**, ham **0x2e30** bayt; DMA için 128'e yuvarlanmış
  **0x2e80 = 11904** bayt. LS base/entry `0xa00`, resume `0xa2c`, image **3**.
- TOC `0x973528` içindeki slot `0x96bd7c` pointer'ı, `0x96bd80` boyutu taşır.
- Getter **`0x505fe8`** pointer'ı yükler. **`0x505ff0`** boyutu yükleyip
  128'e yuvarlar. `0x504ff0 / 0x504ffc` çağrıları ve register taşımaları
  pointer'ı r6'ya, boyutu r7'ye hazırlar.
- **`0x505050`**, **`0x6e95b0`** import stub'ına çağrıdır; import listesi bu
  stub'ı **`_cellSpursWorkloadAttributeInitialize` / NID `0xefeb2679`** olarak
  tanımlar. Sadece imza taramasıyla yer seçilmedi.

`build/.../title/stubs.cpp` ayrı BCES overlay'idir:
`ps3_load_prx_modules()` içindeki region adresi `0x887100` olur.
NPUA'nın `0x8e5b00` kaynağı değişmedi. Wrapped ELF, EBOOT içinde bir ELF olarak
bulunamadığından workload generator uyarısı beklenir; raw region bu hook ile
kaydedilir. `profiles/BCES01229-spu.json` statik kanıt ve sınırları tutar.

## Kod/veri sınırları ve kalan işler

27 jobmod yeniden üretildi. Beş modüldeki önceki **108** unsupported işareti
veri kuyruğu nedeniyle oluşuyordu. `validate_boundary()` içerik hash'ini,
veri başlangıcını ve doğrudan/manual/switch hedeflerini kontrol eder;
`lift_jobmods.CODE_END` yalnız yerel Python çağrısı içinde genişletilir.
Pinned kaynak dosyası değiştirilmez. Gerçek son helper'lar korunur; ham
veriler çıkarılmaz. **27 jobmod'un yeni unsupported sayısı 0.**

5 datamod ve 30 relocmod da üretildi. Her blob'un guest/file adresi PT_LOAD
ile doğrulandıktan sonra pinned extractor'ın `--va-offset 0x10000` kuralı
kullanıldı. İki kritik light/SSAO job ve GPU hook kaynakları korunuyor.

Yeni üretilen diğer SPU gruplarında **901** unsupported işareti var:
`relocmod_00898900` 640; `relocmod_008bd580` 7; gömülü SPU ELF'lerde 213 ve
37; WWS'de 4. **Bunlar henüz güvenli sınıflandırılmadı.** Bazıları veri
aralıklarında görünüyor; WWS'deki dört adres bir iç veri adasında. 108 jobmod
düzeltmesinin tüm SPU sorunlarını çözdüğü söylenmiyor. Liste ve LS adresleri
`out/bces-spu-preparation.json` içinde. CPU JIT eklenmedi; pinned SPU
interpreter fallback yolu da tüm olası işleri statik kapsama aldığımızın
kanıtı sayılmıyor.

## Derleme ve kontroller

`tools/check_bces_support_compile.py`, **en fazla 2 compiler işi** ile
83 destek TU'sunu derler: 65 oyun SPU modülü + 4 kayıt birimi, 7 firmware
PPU/kayıt birimi, 5 firmware SPU gövdesi + kaydı ve BCES stubs overlay'i.
Her object'in SDK platformu `vtool` ile, üretilmiş fonksiyonlar arası eksik
semboller `nm` ile kontrol edilir. `libbces_support.a` yalnız yerel çıktıdır.
Bu arşiv tam title PPU kodunu, GPU hook overlay'lerini veya varlıkları içermez.

**iPhoneOS: 83/83 PASS**, arm64/iOS 17 minimum/SDK 27.1; eksik üretilmiş
fonksiyon sembolü 0. İlk denemede üç PRX kayıt biriminde `prx_loader.h` include
yolu eksikti; `runtime/prx` eklenip bu birimler yeniden derlendi. Yalnız
constructor taşıyan bazı TU'lar için libtool'un “no symbols” uyarısı beklenir;
constructor section'ları vardır. Gerçek executable entegrasyonunda bunların
arşivden alınması için `-force_load` gerekir.

Önceki sınır düzeltmesinden önce 84 TU vardı. Yeni firmware üretimi bir C++
parçasını gereksiz kıldığı için son sayı **83**; eski object dosyaları yeni
arşivin açık kaynak listesine alınmaz.

`tools/check_bces_static.py`: **16/16 PASS**. NPUA adresi, değiştirilmiş SPURS
NID/çağrısı, unmapped adres, beş modülde veri kuyruğuna sentetik gerçek çağrı
ve erken return sonrasında gerçek helper'ı kesecek sınır reddedildi.
Mevcut macOS runtime/Metal regresyon grubu: **12/12 PASS**.

**macOS: 83/83 PASS**, eksik üretilmiş fonksiyon sembolü 0. Native kayıt/leaf
tanısı **11/11 PASS**; firmware tablo sınırları, WWS entry/resume, light/SSAO ve
firmware SPU girişleri bulundu. Gerçek BCES SPU leaf'i r3'e **-10** yazıp
beklenen return PC'ye döndü. Son CTest grubu yeni tanıyla **13/13 PASS**.
macOS derleme/kayıt tanısının son sonucu `out/bces-support-compile-macosx.json`
ve `out/step10-support-host.log` içinde tutulur. Host tanısı, mevcut sentetik
PPU sağlayıcısıyla destek kodunu bağlar; gerçek title PPU başlangıcını veya
firmware start rutinini çağırmaz. iPhone FPS/oyun performansı ölçümü değildir.

Tanı hedefinin CMake configure işlemi, shader bağımlılıklarında geniş bir
yeniden derleme planladı. Yalnız bu oturumun Ninja işlemi SIGINT ile durduruldu;
kütüphane kaynakları değiştirilmedi. `tools/run_bces_support_host.py`, aynı
CMake hedefinin Ninja kurallarından **yalnız yeni compile/link komutlarını**
argv olarak alır ve önceden test edilmiş bağımlılık arşivleriyle çalışır.
Kullandığı arşiv/object SHA-256 değerlerini kaydeder. Soğuk veya bağımlılıkları
değişmiş build'de normal `cmake --build` gerekir.

Arşivin tamamında `7zz t -mmt=1` **exit 0 / Everything is Ok** verdi:
iki entry, ISO **15.327.297.536** bayt, ISO entry CRC `245D231E`.
İçindeki readme çalıştırılmadı. `out/bces-archive-validation.json` ayrıca
arşiv SHA-256 değerini tutar. Bu, ISO'nun 7z içinde kayıtlı CRC'sine uyumdur;
PSARC içeriklerinin doğrulanması, dosyaların kaynağının onayı veya oyun
varlıklarının entegrasyonu değildir. SFO/EBOOT dışındaki oyun dosyaları
henüz çıkarılmadı; `check_inputs.py` bu nedenle hâlâ exit 1 verir.

## Tekrar üretme

```sh
cd /Volumes/monssd/Infamous2-iOS
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
PY=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12
python3 tools/setup_sources.py
# PUP mevcut değilse önce 9. adımın resmî kaynak/hash kaydını kullan.
# İlk firmware açma: RPCS3 kullanıcı Library dizinlerine yazar; bilinen
# teardown 134 hatasında çıktıların doğrulamasını atlama.
upstream/host-tools/rpcs3-arm64/RPCS3.app/Contents/MacOS/rpcs3 \
  --headless --installfw data/incoming/PS3UPDAT.PUP
# İlk kez modülleri kopyalarken --installed-flash için şu yol da kullanılabilir:
# "$HOME/Library/Application Support/rpcs3/dev_flash"
# Bu oturumda tam flash data/firmware/dev_flash altına ayrıca kopyalandı.
$PY tools/prepare_firmware_inputs.py --installed-flash data/firmware/dev_flash
$PY tools/prepare_firmware_lle.py
$PY tools/prepare_firmware_spu.py
$PY tools/prepare_bces_spu.py
$PY tools/check_bces_static.py
$PY tools/check_ppu_bounds.py
$PY tools/check_bces_support_compile.py --sdk iphoneos
$PY tools/check_bces_support_compile.py --sdk macosx
# Sonraki tekrarda --resume değişmeyen başarılı object'leri kullanabilir.
cmake -S . -B build/host \
  -DBCES_SUPPORT_ARCHIVE="$PWD/build/bces01229/support-compile/macosx/libbces_support.a"
cmake --build build/host --target bces_support_host -j2
build/host/bces_support_host
# Bağımlılıklar zaten test edilmiş/güncelse, bu oturumda kullanılan kısa yol:
$PY tools/run_bces_support_host.py
ctest --test-dir build/host -j1 --output-on-failure
python3 tools/check_inputs.py --game-dir data/inspection/bces01229/selected/PS3_GAME
# Son komut şu anda yalnız game_archives eksikliği nedeniyle exit 1 verir.
7zz t -mmt=1 'data/incoming/inFamous 2 (Turkey).7z'
```

**Sonraki somut adım:** tüm oyun varlıklarını yerel arşivden çıkarmak ve
PSARC/kurulum yollarını BCES düzenine göre bağlamak; eksik 162 title PPU
parçasını sınırlı paralellikle derleyip ayrı BCES executable link'ini
tamamlamak. Önce macOS boot logunda ilk çalışma zamanı engelini bulmak,
ardından aynı title çekirdeğini iOS uygulamasına bağlamak. Açık kod/veri ve
dolaylı girişleri boot izleriyle ele almak gerekir. Menüye/bölüme ulaşma,
ses/kayıt ve FPS optimizasyonu bundan sonra ölçülebilir. Oyun/firmware ve
büyük çıktılar Git dışında kalır.

Toplu doğrulama: `out/step10-verification.json`. Title'ın mevcut 30.918 PPU
kaydında da executable pencere dışına çıkan adres bulunmadı
(`out/bces-title-ppu-range-audit.json`); bu, henüz derlenmemiş 162 parçanın
semantik doğruluğu veya tam title derlemesinin geçtiği anlamına gelmez.
