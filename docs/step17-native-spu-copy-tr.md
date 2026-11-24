# 17. adım — SPU işlevinde yerel toplu kopyalama deneyi

24 Ekim 2026. Bu adım GPU aydınlatma/SSAO'yu açmaz. İlk sınırlandırılmış
işlev deneyi, önceki CPU örneğinde görülen image 2 / `0x11C8` kopyalama
döngüsü ve aynı modülün `0x0F94` döngüsüdür. Başlangıç örneğinde görünmesi,
oynanışın başlıca darboğazı olduğunu kanıtlamaz; kullanım ve FPS ayrı ölçülür.

Sonradan ELF32 big-endian section tablosundan `.note.spu_name` okundu:
`ps3_retail/bink.spu.elf`. Kanıt `out/step17-spu-image-name.json` (ELF SHA,
section offset/size ve ham note). Bu, 15. adımın başlangıç örneğindeki yoğun
modülün Bink programı olduğunu belirler; her fonksiyonun semantiğini tek başına
kanıtlamaz. Kopya deneyi video/anlatım yolunda kullanıldı; açık dünyanın
ana hesaplarının hızlandırıldığı veya bu modülün oynanışta baskın olduğu
iddia edilmez. GPU aydınlatma/SSAO işi bu adımda hâlâ değiştirilmedi.

## Korunan davranış

`src/game/BCESSpuCopy.c` yalnız hizalı, çakışmayan, LS sınırını aşmayan,
en az 128 baytlık kopyaları ve image 2 / policy_mode=0 durumunu hızlandırır.
LS debug hook'ları açıkken, küçük/çakışan/hizasız/sarmalanan adreslerde veya
özellik kapalıyken doğrudan özgün fonksiyon çalışır.

N adet 16 baytlık yinelemenin yalnız ilk N−1'i `memcpy` ile yapılır; gerekli
register vektörleri aynı modüler tamsayı miktarıyla ilerletilir. Son yineleme
ve bütün kuyruk kodu **özgün üretilmiş fonksiyonda** kalır. Son yüklenen vektör,
128 register, LS baytları, artık bayt sayısı, pc ve `tramp_fn` korunur.
LS yardımcıları her word'ü okuyup yazarken ters çevirdiğinden, bu okuma/yazma
çifti arasında değişmeyen baytlar ham kopyalanabilir. Kesişen kopyaların sıraya
bağlı davranışı memcpy'ye verilmez. Yeni FP matematiği/fast-math yok.

DMA, event/interrupt, stack ve senkronizasyon protokolleri değiştirilmez.
Bu döngülerin özgün içinde de her yinelemede dispatcher/interrupt çağrısı yoktur;
hızlandırma mevcut fonksiyonun sınırlarında kalır.

## Bağlama

`spu_replace_function` yalnız registry lookup yolunu değiştirir; üretilmiş
kodun doğrudan `tramp_fn=fonksiyon` atamalarını yakalamaz. Bunun için
`tools/build_bces_spu_copy.py`, doğrulanmış O2 kaynağından ayrı bir TU türetir:
yalnız iki **tanım adı** `bces_reference_copy_11c8` / `bces_reference_copy_0f94`
olur. Tüm çağrılar, transferler ve kayıt tablosu eski public isimleri tutar;
bu iki ismi kendi C wrapper'ımız tanımlar. Böylece her iki çağrı yolu kapsanır.
Orijinal üretilmiş kaynak ve O1/O2 arşivleri değiştirilmez. 83 birimin 82'sinin
object SHA'sı önceki O2 ile aynıdır. Yeni arşiv
`build/bces01229/support-compile/iphoneos-spu-O2-copy/libbces_support.a`.

Hazırlayıcı kaynak/object/arşiv üyelerini ve native kaynak/header SHA'larını
denetler. CMake yalnız bu varyantta native C dosyasını O2 ile bağlar;
eski O1/O2 hedeflerinde header'ın boş adaptörü kullanılır. Ana PPU/runtime
ve renderer davranışı aynı kalır. Paket build 17, varyant `spu-O2-copy`.

## Doğruluk ve mikro ölçüm

- `tools/tests/bces_spu_copy.c` özgün kaynak dosyasından alınan gerçek iki
  fonksiyon gövdesiyle karşılaştırır. Test devam fonksiyonlarını yürütmez;
  atanmış gerçek devam hedefinin eşitliğini ve bütün context alanlarını sınar.
- 2.200 vaka: rastgele LS / tüm register lane'leri, artık baytlar,
  ileri/geri çakışma, aynı adres, hizasız adres, LS sarılması, küçük kopya,
  başka image/policy, debug ve kapalı özellik. 200 native, 2.000 fallback.
  LS ayrı allocation olduğu için hem tüm LS içerikleri hem pointer farkı
  normalize edilmiş context karşılaştırılır.
- Normal ARM64 host testi ve AddressSanitizer+UBSan PASS. İlk test düzeninde
  LS pointer'ı ayrılmadığı için null store vardı; sanitizer ile bulunup
  **cihaz kurulumundan önce** düzeltildi. Bu bir oyun runtime çökmesi değildi.
- 128–32.768 bayt mikro testinde native yol daha hızlı çıktı. Son normal
  32 KiB örneği 11C8 için 10,01×, 0F94 için 6,24×; ölçümler Mac M3 üzerinde,
  sıcak cache ve sentetik bağlamladır. iPhone FPS kazancı değildir.
- `bces_spu_copy_selftest`, oyun thread'leri başlamadan 32 sentetik tam LS /
  context vakasını iPhone'da gerçek bağlı referans fonksiyonlarla karşılaştırır.
  32 native çağrıya gerçekten girildiğini de kontrol eder. Başarısızlık boot'u
  durdurur. Canlı SPU context'i gölgelenmez veya geri yazılmaz.

Kanıtlar `out/step17-copy-test.log`, `out/step17-copy-test-asan.log`,
`out/step17-static-checks.json`. `out/step17-app-build.log`: gerçek iPhoneOS
BUILD SUCCEEDED; tek iş. İmza strict doğrulaması PASS; dört public/reference
sembolün her biri binary'de bir kez tanımlı. UUID
`49DE00B4-D88B-355B-80E9-ED1A379D9801`, SHA/korunan Mach-O yolu
`out/step17-binary.json` içinde.

## Cihaz ve açık/kapalı kontrolü

Build 17 aynı bundle ID üzerine kuruldu; oyun verileri korunur. İlk rapor
PID 10401, `support_build_variant=spu-O2-copy`, `inputs_ready=true`,
`link_validation_passed=true`, `game_booted=true`, DualSense tanındı.
Bu PASS 32 cihaz doğruluk vakasını da kapsar. İlk oyun ölçümünde 38 native
çağrı / 154.400 hızlandırılmış bayt görüldü; bu FPS başarısı olarak yorumlanmaz.

CSV 27 sütundur: önceki 23'e `spu_copy_enabled`, `spu_copy_fast_calls`,
`spu_copy_fallback_calls`, `spu_copy_bytes` eklenir. Sayaçlar birikimlidir;
byte sayısı native prefix'i kapsar, özgün son 16 baytı içermez. Başlangıç
selftest sayaçları sıfırlanır; oyun kapsamına karışmaz.

Normal açılış native yolu açık kullanır. `--spu-copy-off` başlangıçta kapatır.
Yalnız `--spu-copy-control` argümanıyla Documents/spu-copy-control.txt dosyası
saniyede bir okunur. `on` / `off` atomik enable bayrağını değiştirir; her
fonksiyon çağrısı seçimini bir kez yapar, devam eden kopya yarıda değiştirilmez.
Bu tanı argümanı normal açılışta dosya okuma yükü eklemez. Kontrolün `off`
durumunda da aynı wrapper/sayaçlar bulunur; tam eski binary ile eşit değildir.

İlk kurulumda `--boot --spu-copy-control` kullanıldı, `--seconds` yok.
Ölçümde kullanıcı aynı kamerada bekler; açık–kapalı–açık pencerelerinde ilk
geçiş saniyeleri dışlanır. Sahne, PID, CSV enable bayrağı, ısınma ve sayaç
deltaları doğrulanmadan kazanç açıklanmaz. Önceki Metal CodeHeap hatasının
bu değişiklikle çözüldüğü varsayılmaz.

## Komutlar

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
export TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp
python3 tools/build_bces_spu_copy.py
xcrun clang -std=c17 -O2 -DBCES_SPU_COPY_ENABLED=1 -fno-strict-aliasing -fwrapv -ffp-contract=off -Isrc/game -Iupstream/infamous2-recomp/ps3recomp-fork/runtime/spu -Iupstream/infamous2-recomp/ps3recomp-fork/include -Ibuild/bces01229/support-compile/iphoneos-spu-O2-copy tools/tests/bces_spu_copy.c src/game/BCESSpuCopy.c build/bces01229/support-compile/iphoneos-spu-O2-copy/test_reference.c -o build/bces01229/spu-copy-test
build/bces01229/spu-copy-test
# Sanitizer için aynı komuta -g -fsanitize=address,undefined -fno-omit-frame-pointer ekle.
python3 tools/prepare_bces_ios.py --support-report out/bces-support-compile-iphoneos-spu-O2-copy.json
cmake -S cmake/bces-ios -B build/bces01229/ios
xcodebuild -project build/bces01229/ios/Infamous2BCESIOS.xcodeproj -scheme Infamous2Game -configuration Release -destination id=00008130-001129E00243001C -jobs 1 DEVELOPMENT_TEAM=BJ266NGN3H -allowProvisioningUpdates
xcrun devicectl device install app --device 00008130-001129E00243001C build/bces01229/ios/Release-iphoneos/Infamous2Game.app
xcrun devicectl device process launch --device 00008130-001129E00243001C --terminate-existing dev.infamous2.iosprobe --boot --spu-copy-control
```

Canlı kontrol: yerel bir dosyaya `on\n` veya `off\n` yazıp
`devicectl device copy to --domain-type appDataContainer --domain-identifier
dev.infamous2.iosprobe --source DOSYA --destination Documents/spu-copy-control.txt`
ile aktar. Cihaz `--device` seçeneği yine yukarıdaki UDID'dir. Üretilmiş büyük
dosyalar, oyun ve firmware Git'e eklenmez.

Geri dönüş paketi `build/bces01229/baselines/step17-O2/Infamous2Game.app`.
Saf O2'yi yeniden derlemek için 16. adımın support report'u seçilir ve CMake
configure/build tekrarlanır. İlk O1 baseline da korunur.

## İlk sinematik çökmesi

Kullanıcı anlatım sonrası sinematikte kapanma bildirdi. 19:33:24 kaydının
UUID'si build 17 ile eşleşir. Bu kez `operator new` / `std::vector<spv::Instruction*>::resize`
→ `spv::Builder::createVariable` → `glslang::GlslangToSpv` →
`rsx_hlsl_to_msl` → `eng_function` → `eng_pipeline_create` zincirinde
yakalanmamış allocation exception / SIGABRT var. Önceki AGX CodeHeap
`IOGPUResourceRef` mesajı yok; aynı kök sebep varsayılmaz. İstenen allocation
boyutu kayıtta yok; büyük SPIR-V isteği, kaynak baskısı veya bozulmuş durum
arasında henüz ayrım yapılamaz. Native kopyalamanın zamanlamaya etkisi de
bu tek kayıttan dışlanamaz.

Çökmeden önceki son saniyelik örnek: 924 native çağrı, 631.523 fallback,
2.170.176 native prefix baytı; pipeline 462/462/0, memory warning 0,
footprint 865.602.600 bayt, ek pay 2.674.389.976 bayt. Bu değerler kesin hata
anını değil son kaydedilmiş örneği gösterir. Başlangıçtaki hızlandırma kapsamı
küçüktür; bu sayıdan oynanış FPS kazancı çıkarılmaz.

Kanıt `out/step17-crash-193324.ips`, `out/step17-crash-performance.csv`,
`out/step17-crash-bces-device-report.json`. Aynı binary `--spu-copy-off` ile
ve kontrol dosyası `off` yapılarak yeniden başlatıldı. Sıradaki kontrol,
oynanışa özgün yol açıkken ulaşılması; ulaşılırsa aynı süreçte native yolu
açıp kapatarak karşılaştırmadır. Hata kendiliğinden kaybolmuş sayılmaz.

## Kapalı kontrolün sonucu ve kalan engel

İkinci deneme de sinematikte kapandı (19:38:27). Aynı build/UUID, yeni PID
10411. Son rapor `spu_copy_enabled=0`, native çağrı **0**, native bayt **0**,
fallback 632.447 doğruladı. Bu kez yakalanmamış allocation exception
SPIRV-Tools `Instruction::Clone` / `InlinePass` / `InlineExhaustivePass`
yolundadır. Önceki açık denemenin glslang SPIR-V üretiminden farklı alt aşama;
her ikisi shader çeviri zincirinde bellek ayırırken sonlanır. Tam istek boyutu
ve kök neden belirlenmedi. Yeni toplu kopyanın çalışması bu ikinci çökmenin
oluşması için gerekli değildir; zamanlama/başka bellek sorunları bütünüyle
dışlanmış değildir. Telemetri headroom'u başarısız allocation'ın boyutunu
veya kullanılabilir en büyük kesintisiz alanı göstermez.

Son kapalı örnek footprint 764.267.488 bayt, ek pay 2.775.725.088 bayt,
bellek uyarısı 0, pipeline 230/230/0. Kanıtlar
`out/step17-off-crash-193827.ips`, `out/step17-off-final-performance.csv`,
`out/step17-off-final-bces-device-report.json`.

**Sonuç:** İşlev hızlandırması derlendi, doğruluk testlerinden geçti, iPhone'da
gerçek oyun sırasında çalıştı. Açık–kapalı–açık oynanış benchmark'ı çökme
yüzünden tamamlanamadı; **iPhone FPS kazancı açıklanmıyor**. Son cihaz süreci
çökerek kapandı, uygulama hâlâ kurulu. Bu bir kararlılık/oynanış başarı iddiası
değildir. Tekrarlanan yeni oyun denemeleri burada bırakıldı.

Öncelikli sonraki iş, başarısız shader'ın HLSL/SPIR-V girdisini ve allocation
isteğini yakalamak; glslang/SPIRV-Tools büyümesi, kaynak baskısı ve bozulmuş
girdi ayrımını yapmak. Legalization geçişlerini körlemesine kapatmak veya
shader'ı atlayıp eksik görüntüyü başarı saymak doğru değil. Ardından gerçek
oynanış CPU profiliyle grafik/SPU işleri seçilmeli. Bu Bink kopya deneyi
genel oynanış hızlanmasının yerine geçmez.

## Kullanıcının aşama bazında ek gözlemi

24 Ekim, denemeler sonrası kullanıcı bildirimi; bu değerler cihaz CSV'siyle
zaman olarak eşleştirilmiş yeni bir benchmark değildir. Bildirimin native
açık/kapalı denemelerden hangisini kapsadığı kesinleştirilmedi:

- Başlangıç anlatımı büyük ölçüde 29–32 FPS, yaklaşık sabit 30 FPS.
- Zaman zaman 5–15 FPS'e kısa düşüşler; anlatım sonuna doğru 5–20 FPS aralığı
  daha sık görülüyor.
- Oynanıştan önceki ilk sinematik yaklaşık 5,5 FPS; bir süre sonra oynanışa
  geçmeden uygulama kapanıyor.

Bu gözlem anlatım ile ilk 3D sinematiğin aynı performans aşaması gibi
toplanmaması gerektiğini pekiştirir. 30 FPS, oynanışın 30 FPS olduğu veya
native kopyalamanın bu artışı sağladığı anlamına gelmez. Düşüşlerin shader
çevirisi, asset akışı veya başka bir maliyetle çakışıp çakışmadığı henüz
ölçülmedi. Bilinen allocation crash kayıtları shader çeviri zincirindedir;
bütün FPS düşüşlerinin aynı sebepten geldiği çıkarılmaz.
