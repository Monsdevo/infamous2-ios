# 19. adım — oynanış profiline göre optimizasyon

24 Ekim 2026. Çalışma sürüyor; ilk sıralama gerçek sabit oynanış penceresinden
alınacak. Video/menü örnekleri kararın temeli değildir.

## Ölçüm yolu

Instruments bu oturumda da gerçek iPhone'u Offline gösterdi; `out/step19-crash-list`
içindeki son cpu_resource kaydı eski 17:29 oturumuydu. Tekrarlı bağlantı sıfırlama
yerine kendi sürecimize sınırlı CPU örnekleyicisi eklendi.

`src/platform/CPUProfile.cpp`: yalnız `--profile-cpu` ile yapılandırılır.
Mevcut 1 Hz UI tick'i `bces_cpu_profile_poll` çağırır; kontrol dosyasında
`start UNIQUE_TOKEN 30` görünce ayrı sampler thread 30 saniye örnek alır.
Normal başlatmada kontrol dosyası okunmaz, sampler başlamaz. Aynı token tekrar
başlatmaz. Süre 1–60 saniye, 50000 satır ve 16 frame ile sınırlıdır. Thread'ler
durdurulmaz. task_threads portları ve VM dizisi her tur bırakılır; sampler kendi
thread'ini hariç tutar. RUNNING thread PC'leri alınır. İkincil FP zinciri doğrudan
pointer dereference yerine vm_read_overwrite kullanır; değişen stack nedeniyle
zincir eksik/tutarsız olabilir. Asıl exclusive sıralama birincil PC'ye dayanır.
Mach API dayanağı: https://developer.apple.com/documentation/kernel/1418576-thread_get_state .
İlk iOS derlemesinde SDK'nın mach_vm.h desteği olmadığı görüldü; SDK'nın kendi
64-bit vm_address_t / vm_read_overwrite arayüzüne geçildi.

Çıkış `Documents/cpu-profile.csv`: executable UUID, ASLR base/end, monotonic
başlangıç/bitiş, kayıt/tick/hata/kesilme sayıları ve thread başına kümülatif CPU
sayaçları. `tools/analyze_native_profile.py` binary UUID eşleşmezse durur.
Adresler atos --offset ile bu binary üzerinden çevrilir. Her thread'in gözlenen
CPU farkı kendi örnek sayısına bölünerek exclusive/inclusive ağırlık üretilir;
inclusive değerler toplanmaz, recursive frame aynı örnekte bir kez sayılır.
Bu yaklaşık bir CPU örnek profilidir; kesin fonksiyon kronometresi veya kernel
stack profili değildir. Sadece RUNNING thread'ler seçildiği ve PC/CPU state farklı
Mach çağrılarıyla alındığı için örnekleme yanlılığı olabilir. Atıf belirsiz kalan
sistem frame'leri açıkça unresolved tutulur.

Profiler çalışırken FPS benchmark'ı yapılmaz. Açık/kapalı FPS karşılaştırması
sampler bittikten sonra aynı sahnede yapılmalıdır.

## Doğrulama ve ilk paket

Host test `tools/tests/cpu_profile.cpp`: iki saniye bilinen yoğun CPU işlevi,
bounded capture, dosya oluşması, bitiş ve aynı token'ın yeniden başlamaması PASS.
`out/step19-profile-test-analysis.json`: known_cpu_work exclusive CPU ağırlığı
%99,98; yanlış UUID'li iPhone binary'siyle analiz ValueError ile reddedildi.

Build 22 iPhoneOS Release -jobs 1 derlendi; aynı bundle ID üstüne kuruldu.
UUID 9FC44D98-4F35-3C0E-ABAE-AC661AFB6B8C, korunan executable yolu ve hash
`out/step19-profile-binary.json`. 18. adım mmap + 64 MiB PPU host stack değişikliği
korundu. Native Bink kopyası kapalı; CPU JIT yok; shader/allocator tanısı kapalı.

3 saniye iOS smoke (oynanış benchmark'ı değildir): 524 satır, 130 tick, errors=0,
truncated=0; app UUID doğru, SPU/PPU adresleri çözüldü. Dosyalar
`out/step19-ios-smoke-profile.csv` / `out/step19-ios-smoke-analysis.json`.

## Komutlar

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
export TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp
cmake -S cmake/bces-ios -B build/bces01229/ios -DBCES_TRACE_NEW_FAILURES=OFF -DBCES_EXTENDED_VA=OFF
xcodebuild -project build/bces01229/ios/Infamous2BCESIOS.xcodeproj -scheme Infamous2Game -configuration Release -destination id=00008130-001129E00243001C -jobs 1 DEVELOPMENT_TEAM=BJ266NGN3H -allowProvisioningUpdates
# Uygulama argümanları: --boot --spu-copy-off --profile-cpu
# Yalnız oynanış teyidinden sonra Documents/cpu-profile-control.txt: start gameplay_TOKEN 30
python3.12 tools/analyze_native_profile.py out/step19-gameplay-profile.csv --binary build/bces01229/symbols/9FC44D98-4F35-3C0E-ABAE-AC661AFB6B8C/Infamous2Game --label 'user-confirmed stationary gameplay' --output out/step19-gameplay-analysis.json
```

Profil bulgusu, seçilen işlev, doğruluk testi ve sampler kapalı FPS A/B sonucu
çalışmanın devamında eklenecek. Oyun/firmware/çıktılar Git'e eklenmez.

Kullanıcı yeni sürümde gerçek oynanışa ulaştığını bildirdi. Kontrol tokenı `gameplay-baseline-01`, süre 30 saniye ile kayıt başlatıldı. Ölçüm bitince bu pencereye ait fonksiyon sıralaması kullanılacak. Build 22 geri dönüş paketi `build/bces01229/baselines/step19-profile/Infamous2Game.app` altında korunuyor.

## Tamamlanan gerçek oynanış profili

Kullanıcının Cole'u kontrol ettiğini teyidinden sonra `gameplay-baseline-01` ile
30,004 saniye kayıt alındı: monotonic 138044.638943–138074.642764; 10798 satır,
1339 tick, errors=0, truncated=0. UUID build 22 ile eşleşti. Ham veri
`out/step19-gameplay-profile.csv`, çözümlenmiş sonuç
`out/step19-gameplay-analysis.json`. Bu pencere FPS benchmark'ı değildir.

Yaklaşık CPU ağırlığı: SPU %83,3; PPU %9,4; renderer %6,3; diğer %0,9.
En yoğun exclusive uygulama işlevleri:

| İşlev | Yaklaşık CPU ağırlığı |
|---|---:|
| datamod_00821080_spu_func_00007320 | %7,54 |
| datamod_00820480_spu_func_00006F80 | %4,26 |
| jobmod_c6e7383dc013_e5400_spu_func_00009248 | %3,96 |
| spu_check_stack_reset | %2,89 |
| relocmod_008ae480_spu_func_00002AF8 | %2,40 |

Sistem/unresolved exclusive ağırlığı %12,34; bu ayrı bir oyun fonksiyonu değildir.
Interpreter/dispatcher inclusive değerleri yüksek, fakat altında yürütülen
üretilmiş işlevleri de içerir. Inclusive %63'ü "CPU'nun %63'ü interpreter
komut çözümlemesine gidiyor" diye yorumlamak veya diğer değerlerle toplamak yanlış.

Seçilen fonksiyon image 234; `datamods_register.c` kaynak EA 0x00821080,
LS tabanı 0x6C00, span 0x1510. 0x7320 işlevi 577 kaynak satırı ve saf LS/math
hesaplaması içerir; loop sayacı r6 dörder azalır. Semantik görevini yalnız bu
verilerle fizik/ışık/animasyon diye adlandırmıyoruz. Bu Bink kopyalama işlevi değil.

## İki host deneyi

`tools/prepare_bces_hot_kernel.py` doğrulanmış O2 kaynak SHA'sından işlevi alır;
original/generated kaynak ve kurulu arşiv değişmez. Çıkış
`build/bces01229/hot-kernel/kernels.c`; kendi baseline/ref ve aday gövdeleri ayrı.

1. Register dosyasını fonksiyon içi local alana alma: 1000 tam context + bütün
   256 KiB LS karşılaştırması PASS. 1/8/64 döngü mikro ölçümleri 0,974× / 0,909× /
   1,147×. Küçük ve tutarsız olduğundan cihaz entegrasyon adayı olarak seçilmedi.
2. ARM64 RZ: `src/game/BCESSpuRZ.h` yalnız bu yaprak işlevin içinde FPCR rounding
   alanını sıfıra doğru yuvarlamaya ayarlar, çıkıştan önce eski FPCR'yi geri koyar.
   Native fadd/fsub/fmul/fmla işlemleri volatile asm ile FPCR yazımlarıyla sırada
   tutulur; compiler fast-math yok. SPU exponent-zero girdi/çıktıları +0 olur;
   exponent 255 girdiler ve IEEE overflow/max-finite sınırı özgün integer exact
   SPU hesabına döner. Yaklaşık reciprocal veya shader/CPU JIT eklenmez.

`tools/tests/bces_spu_rz.c`: altı işlemde 9,6 milyon lane/op bit karşılaştırması,
sınır değerler + rastgele bitler, flush-to-zero kapalı/açık PASS; eski FPCR'nin
korunduğu her vakada kontrol edilir. `out/step19-spu-rz-test.log`.
`tools/tests/bces_hot_kernel.c`: özgün işlev ile RZ işlevinin 1000 tam context ve
bütün LS karşılaştırması PASS; 1–8 döngü ve iki host_depth dönüş biçimi,
FPCR geri yükleme kontrolü. İlk host mikro ölçümünde 1/8/64 döngü için
1,244× / 1,652× / 2,010× görüldü (`out/step19-hot-rz-test.log`).
Bunlar iPhone FPS ölçümleri değildir; sentetik, normal finite girdili M3 ölçümü.

## Toplantı için karar sınırı

Tek fonksiyonun %7,54 ağırlığıyla iki kat hızlanması aggregate CPU-work modelinde
ancak yaklaşık %3,9 kazanç verir; tamamen ücretsiz olması bile yaklaşık %8,2
sınırındadır. Bu bir FPS tahmini değildir: kritik yol, SPU paralelliği ve
senkronizasyon sonucu değiştirebilir. `out/step19-planning-bounds.json`.

Dolayısıyla bu tek işlevden büyük FPS sıçraması beklenmemeli. Toplantıda asıl karar,
bit-eşdeğer matematik yolunu profildeki başka uygun yaprak hesaplama işlevlerine
genişletmek ile dispatcher/DMA ortak maliyetlerini hedeflemek arasında verilmeli.
Interpreter inclusive yüzdesi tek başına bir yorumlayıcı darboğazı kanıtı değildir.

RZ adayı **deneyseldir, uygulamaya bağlanmadı ve telefonda etkinleştirilmedi**.
Cihazda native RZ işlevi doğruluğu/coverage ve aynı sahnede sampler kapalı A/B
henüz yok; FPS kazancı iddia edilmiyor. Entegrasyon önce debug/fallback gate,
fonksiyon tanımı ile doğrudan trampoline çağrılarının kapsanması ve runtime
feature toggle gerektirir. Yeni test oturumu toplantı öncesinde başlatılmadı.

## Kesinti sonrası kapanış — 25 Ekim 2026

Ek kontroller tamamlandı: tam işlev karşılaştırması AddressSanitizer ve UBSan
ile PASS (`out/step19-hot-rz-asan.log`). Sanitizer altında çıkan mikro süreler
performans karşılaştırması için kullanılmaz. RZ/ref/local gövdeleri gerçek
iphoneos SDK ve arm64-apple-ios17.0 hedefiyle object olarak derlendi; vtool
platform IOS doğrulaması PASS. SDK/macOS arşivleri karıştırılmadı.
`out/step19-candidate-ios-object.json` komut, object SHA ve
EXPERIMENTAL_NOT_LINKED_IN_APP durumunu saklar. Bu bir uygulama link/kurulum
veya cihazda RZ yürütme testi değildir. Kurulu son paket build 22 CPU profiler
sürümü olarak kaldı. RZ için cihaz A/B işi açık; adayın etkin olduğu bir FPS
sonucu yok. Oyun/firmware ve büyük çıktılar Git'e eklenmedi.

Güncel doğrulamaları tekrar üretmek için:
```sh
python3.12 tools/prepare_bces_hot_kernel.py
clang -std=c17 -O2 -fno-strict-aliasing -fwrapv -ffp-contract=off -Isrc/game -Iupstream/infamous2-recomp/ps3recomp-fork/runtime/spu -Iupstream/infamous2-recomp/ps3recomp-fork/include tools/tests/bces_spu_rz.c -o build/bces01229/spu-rz-test
build/bces01229/spu-rz-test
clang -std=c17 -O2 -fno-strict-aliasing -fwrapv -ffp-contract=off -fsanitize=address,undefined -fno-omit-frame-pointer -Isrc/game -Iupstream/infamous2-recomp/ps3recomp-fork/runtime/spu -Iupstream/infamous2-recomp/ps3recomp-fork/include tools/tests/bces_hot_kernel.c build/bces01229/hot-kernel/kernels.c -o build/bces01229/hot-kernel-test-asan
build/bces01229/hot-kernel-test-asan
# iPhoneOS object komutu, SDK yolu ve platform doğrulaması:
cat out/step19-candidate-ios-object.json
```
