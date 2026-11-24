# 9. adım — BCES01229 girdisi, statik üretim ve iPhoneOS object kontrolü

17 Ekim 2026. Kullanıcı **BCES01229 / APP_VER 01.00** ile devam etmeyi
seçti. iOS altyapısı ve sabit runtime korunuyor; NPUA profili referans olarak
ayrı tutuluyor. **Oyun bağlanmadı/başlatılmadı; oyun karesi 0.**

## Gerçekleştirilen işler

- `tools/extract_bces_probe.py`, arşivin yalnız ilk **128 MiB** ISO çıktısından
  SFO ve tam **10.162.208 baytlık EBOOT.BIN** alıyor. Kaynak arşiv değişmedi.
  Seçili dosyaların SHA-256 değerleri profille eşleştiriliyor; tam arşiv/ISO
  CRC'si ve oyun varlıklarının bütünlüğü **henüz doğrulanmadı**. Eksik ISO
  üzerinde 7zz exit 2 / EOF beklenir; tam seçili dosya kabulü hash'e bağlıdır.
- Resmî RPCS3 ARM64 aracı proje içindeki `upstream/host-tools/` altına alındı.
  Arşiv SHA-256 değeri resmî GitHub release digest'iyle eşleşti; sürüm ve URL
  `sources.lock.json::host_tools` içinde. `--headless --decrypt` ile gerçek
  EBOOT çözüldü. Bu **host aracı** iOS uygulamasına eklenmedi, oyun çalıştırmadı.
  Executable yanında portable klasörü oluşturuldu; **10. adımda bu sürümün
  onu kullanmadığı, kullanıcı Library dizinlerine yazdığı görüldü**. Önceki
  portable varsayımı geçerli değil. Sandbox'ta macOS servis erişimi başarısız
  olduğundan dönüşüm sistem bağlamında tamamlandı.
- `tools/analyze_bces.py`, ELF/SFO hash'ini doğrular; pinned loader ve SPU
  çıkarıcılarını çalıştırır. Magic/imza tarayıcılarını import ederek blob
  envanteri çıkarır. File offset → guest adresi **ELF PT_LOAD eşlemesinden**
  hesaplanır; başka sürümün sabit offset'i kullanılmaz.
- `profiles/BCES01229-01.00.json`: doğrulanmış yerel input hash'leri, entry/TOC,
  executable section sınırı, iki kritik SPU hook eşlemesi ve açık kalanlar.
  `game_boot_enabled=false`. `check_inputs.py` varsayılanı bu profildir;
  `--profile profiles/NPUA80638-reference.json` eski referansı korur. Hash/metadata
  kabulü runtime uyumluluğu anlamına gelmez.

| ELF bulgusu | BCES değeri |
| --- | --- |
| ELF SHA-256 | `e7aa498258def0c7d651df92dcbb6feaf3230f4486b874170c074e7ca9238be6` |
| Entry OPD / code / TOC | `0x94dd38` / `0x10230` / `0x973528` |
| Executable section üst sınırı | **`0x6eb2b0`**, exclusive; NPUA'nın `0x742e18` değeri kullanılmadı |
| İlk loader keşfi | 13.472 unique OPD fonksiyonu; 257 import / 19 kütüphane |
| Lifter'ın son çıktısı | **30.918 fonksiyon, 164 C++ parçası**, yaklaşık 265 MiB |
| SPU envanteri | 2 gömülü ELF, **27 jobmod, 5 datamod, 30 relocmod** |

OPD sayısı ile son fonksiyon sayısı farklı aşamalardır: lifter çağrı/hedef
keşfi ve ek girişler üretir. 30.918 sayısı doğruluk veya boot başarısı değildir.
PPU üretimi **1 iş**, native derleme en fazla **2 iş** kullandı; CPU JIT yok.

## Korunabilen iki kritik modül ve gerçek fark

| Hook | Referans semboldeki içerik imzası | NPUA image ID | BCES image ID |
| --- | --- | --- | --- |
| GPU light | `jobmod_c6e7383dc013_e5400` | 219 | **221** |
| GPU SSAO | `jobmod_e6fe749031f8_e2060` | 226 | **225** |

12 haneli SHA-1 içerik önekleri referans kaynak sembolleriyle eşleşti.
Yerelde NPUA binary bulunmadığı için tam byte karşılaştırması yapılmadı.
Image ID'ler `lift_jobmods.py` sıralı modül kayıt kuralı ve üretilen kayıt
dosyasıyla doğrulandı; eski ID'ler körlemesine taşınmadı.

`tools/check_bces_compile.py`, pinned `gpu_light.c` ve `gpu_ssao.c` kaynaklarından
yalnız image define'larını değiştirerek **ayrı build overlay'leri** üretir.
Kaynak commit ve kaynak bytes, Git HEAD ile kontrol edilir. NPUA dosyaları
değiştirilmez; job iç protokol veya math sadeleştirilmez. Bu hook'ların
**oyun sırasında doğru çalıştığı henüz doğrulanmadı**.

## Gerçekten derlenenler ve açık kontroller

iPhoneOS SDK 27.1 / arm64 / minimum iOS 17 için **6/6 object derlemesi PASS**:

- 164 PPU parçasından **yalnız 2'si**: ilk kod parçası ve function table'ı
  içeren son parça;
- iki kritik gerçek SPU job'ının üretilmiş C kodu;
- iki BCES GPU hook overlay'i.

Her object `vtool` ile **IOS** platformunda doğrulandı. Bu bir executable
link'i, tüm 164 parçanın derlenmesi veya cihaz testi değildir. Önceki iPhone
uygulaması sentetik tanı olarak kalır; bu oturumda yeni oyun uygulaması
kurulmadı. İlk derleme denemesinde eksik runtime/ppu ve title header arama
yolları tamamlandı; son 6 birim geçti. PPU parçasındaki 7 stil uyarısı korundu.

27 SPU job'ı statik olarak üretildi. İki kritik job'ın unsupported sayısı 0;
beş başka job'da toplam **108 `.word` / `spu_unsupported` işareti** var.
Bazıları açıkça metin/veri kuyruğuna benziyor, ancak kontrol akışıyla
sınıflandırılmadan hiçbiri güvenli sayılmadı veya silinmedi. PPU çıktısında da
TODO/veri-as-code işaretleri var; üretim sonucu semantik doğruluk değildir.
WWS ham policy modülünün BCES konumu hâlâ açık; NPUA'nın `0x008E5B00`
adresi otomatik uygulanmadı. Datamod/relocmod'lar bu adımda **envanterlendi**,
henüz lift/compile edilmedi.

## Firmware girdisi

[Sony'nin resmî sayfasının](https://www.playstation.com/tr-tr/support/hardware/ps3/system-software/)
4.93 olarak sunduğu PUP, `data/incoming/PS3UPDAT.PUP` konumuna alındı:
206.197.916 bayt; MD5, sayfanın indirme URL'sindeki kimlikle eşleşiyor.
SHA-256: `158471fd834f8ea8036136b6aab43cd86c7ba73d79ca30e0af3c0fe0001cf365`.
Sayfa HTTP indirme bağlantısı yayımlıyor; HTTPS denemesi hostname sertifika
hatası verdi. TLS denetimi kapatılmadı; sayfada yayımlanan özgün HTTP bağlantısı
kullanıldı. Bu hash/transfer kaydı PUP iç imzalarının doğrulanması değildir.
Firmware açılmadı, liblv2/libsysmodule/libsre çıkarılmadı ve portun sabit
firmware SPU gövdeleriyle uyumu doğrulanmadı. Hiçbir sistem güncellenmedi.

## Tekrar üretme

```sh
cd /Volumes/monssd/Infamous2-iOS
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
PY=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12
T=upstream/infamous2-recomp/ps3recomp-fork/tools
E=data/inspection/bces01229/selected/PS3_GAME/USRDIR/EBOOT.elf
S=data/inspection/bces01229/selected/PS3_GAME/PARAM.SFO
python3 tools/setup_sources.py
python3 tools/extract_bces_probe.py
# Resmî host aracı sources.lock.json::host_tools URL/hash'iyle hazırlanır.
upstream/host-tools/rpcs3-arm64/RPCS3.app/Contents/MacOS/rpcs3 \
  --headless --decrypt data/inspection/bces01229/selected/PS3_GAME/USRDIR/EBOOT.BIN
$PY tools/analyze_bces.py --elf "$E" --sfo "$S"
$PY "$T/ppu_lifter.py" "$E" --functions build/bces01229/analysis/EBOOT.functions.json \
  --hle-stubs build/bces01229/analysis/EBOOT.imports.json --code-end 0x6eb2b0 \
  --max-chunk-lines 30000 --jobs 1 --output build/bces01229/recompiled
$PY "$T/lift_jobmods.py" --jobmods build/bces01229/spu/jobmods \
  --out build/bces01229/spu --register build/bces01229/spu/jobmods_register.c \
  --symbol-prefix infamous2
$PY tools/check_bces_compile.py
python3 tools/check_inputs.py --game-dir data/inspection/bces01229/selected/PS3_GAME
# Son komutta PRX ve PSARC girdileri eksik: exit 1 beklenir.
```

Kanıtlar: `out/bces-analysis.json`, `bces-ios-compile-checks.json`,
`bces-codegen-manifest.json`, `bces-validation-tests.json`,
`bces-spu-unsupported-review.json`, `bces-input-inventory.json`,
`step9-sources-check.log`, `step9-verification.json`, `ps3-firmware-source.json`.
Oyun/firmware, host araçları ve tüm büyük çıktılar Git dışında.

**Sıradaki adım:** firmware modüllerini doğrulayıp çıkarmak; WWS policy
eşlemesini ve 108 SPU işaretinin kod/veri sınırlarını çözmek; datamod/relocmod
üretimini tamamlamak. Ardından tam BCES runtime/title link'i ve önce macOS
boot tanısı, sonra iOS'ta ilk gerçek guest kare denemesi. Bunlar tamamlandı
diye raporlanmıyor; mevcut PPU/Metal altyapısı kullanılmaya devam edecek.
