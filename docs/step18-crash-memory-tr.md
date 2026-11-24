# 18. adım — sinematik allocation çökmesinin tanısı

24 Ekim 2026. Son normal build 21 sinematikten gerçek oynanışa geçti ve aşağıdaki ölçüm boyunca kapanmadı. Uzun süreli oyun testi henüz yapılmadı; FPS kazancı iddiası yok.

## Ölçülen hata

Build 18, native SPU kopyası kapalıyken sinematikte çöktü. iPhone shader kaydı
406. çeviride, stage=1, 6095 bayt HLSL için yalnız **6376 bayt** `operator new`
isteğinin başarısız olduğunu kaydetti. `os_proc_available_memory` o anda
2720592928 bayttı. Son rapor fiziksel footprint 818793440 bayt; fast copy=0.
`out/step18-crash-195923.ips` aynı binary UUID
9EAE7103-894A-35BC-8659-07BCCD561871 ile eşleşti. VM özeti malloc 3,6 GiB,
stack 3,6 GiB, guard 385 GiB. Guard/virtual size fiziksel RAM tüketimi değildir.

Aynı HLSL, sabitlenmiş host glslang / SPIRV-Tools / SPIRV-Cross arşivleriyle
başarıyla MSL üretti (`out/step18-captured-replay.log`). Host MSL platformu
macOS; çöküş SPIR-V üretiminde olduğundan bu geçiş kaynak girdisinin tek başına
hata verdiği iddiasını desteklemiyor. Bu test iOS GPU çalıştırma testi değildir.

`src/platform/ShaderDiagnostics.cpp` yalnız `--diagnose-shaders` ile son HLSL'yi
ve begin/end kayıtlarını saklar. `BCES_TRACE_NEW_FAILURES=ON` ayrıca diagnostic
operator new kullanır; başarısız malloc'u allocation yapmadan kaydedip standart
new-handler/bad_alloc akışını korur. Varsayılan OFF; kalıcı pakette kapatılmalıdır.
`tools/tests/shader_diagnostics.cpp` hata yolunu doğrular.
`src/host/shader_replay.cpp` host tekrarında tek allocation için 64 MiB güvenlik
sınırı koyar; bu sınır iOS oyununda kullanılmaz. Hiçbir shader atlanmadı ve
shader optimizasyon geçişi devre dışı bırakılmadı.

## Sanal adres alanı hipotezi ve deneme

Fiziksel bellek payı, sanal adres alanı kullanılabilirliğini göstermez.
Apple DTS açıklaması: https://developer.apple.com/forums/thread/826325 .
Oradaki JSC kaynaklı örneğin aynı kök neden olduğu varsayılmıyor.

Extended Virtual Addressing yetkisi denendi. Xcode açıkça Personal Team için
desteklenmediğini söyledi (`out/step18-va-build.log`). Varsayılan
`BCES_EXTENDED_VA=OFF`; destekleyen bir ekip için ayrı seçenek ve
`src/ios/GameEntitlements.plist` tutuldu. Increased Memory Limit eklenmedi.

Build 19 denemesi: `src/platform/BCESGuestMemory.h` aynı 0xE0000000 bayt aralığı
MAP_PRIVATE|MAP_ANON, PROT_READ|PROT_WRITE ile doğrudan mmap eder. Sıfır başlangıç
ve demand paging korunur; büyük arena malloc zone'undan çıkar. Başlangıç sınaması
aynı yardımcıyı kullanıp munmap ile bırakır. Gerçek runner dönüşümü
`tools/prepare_bces_ios.py` içinde tam bir kaynak eşleşmesiyle yapılır; sabitlenmiş
upstream main.cpp değiştirilmez. Gerçek oyun arenası süreç ömrü boyunca kalır.
256 MiB thread stack değerleri bu ilk deneyde değiştirilmedi.

`tools/tests/bces_guest_memory.cpp`: aralığın alt/üst uçları ve seyrek adresler,
yazma/okuma, munmap ve ikinci ayırmanın sıfırlanması PASS. Bu host doğruluk testi,
iPhone üzerindeki kaynak tükenmesini çözdüğünün kanıtı değildir.
`GamePerformance.mm` JSON raporuna `virtual_size_bytes` eklendi; CSV biçimi korunur.

## Tekrar üretme

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
export TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp
python3.12 tools/prepare_bces_ios.py --support-report out/bces-support-compile-iphoneos-spu-O2-copy.json
cmake -S cmake/bces-ios -B build/bces01229/ios -DBCES_EXTENDED_VA=OFF -DBCES_TRACE_NEW_FAILURES=ON
xcodebuild -project build/bces01229/ios/Infamous2BCESIOS.xcodeproj -scheme Infamous2Game -configuration Release -destination id=00008130-001129E00243001C -jobs 1 DEVELOPMENT_TEAM=BJ266NGN3H -allowProvisioningUpdates
clang++ -std=c++20 -O2 -Isrc/platform tools/tests/bces_guest_memory.cpp -o build/bces01229/guest-memory-test
build/bces01229/guest-memory-test
```

Aynı bundle ID üzerine kurulum Documents içindeki oyun verilerini korur.
Deneme argümanları: `--boot --spu-copy-off --diagnose-shaders`. Süreli kapanma yok.
Cihaz sonucu ve sabit oynanış FPS penceresi aşağıya eklenecek.

Build 19 imza strict kontrolü PASS, yalnız team/application/get-task-allow yetkileri
var; Extended VA yok. Binary UUID 1B3CB078-A9B5-3780-B017-3727E0C6F8D3,
`out/step18-mmap-binary.json`. iPhone PID 10469, başlangıç ve 32 SPU doğruluk
kontrolü PASS. Canlı kayıtta önceki başarısız 406 shader sınırı aşıldı, 538 shader
çevirisi başarılı ve pipeline sayısı daha sonra 991'e ulaştı. Henüz kullanıcının
oynanış teyidi ve sabit sahne penceresi alınmadı; bunlar oynanış sonucu sayılmaz.

## İlk cihaz geçişi: build 19

Kullanıcı Cole'u kontrol edebildiği oynanışa ulaştığını doğruladı. Ölçüm başlangıcı
`out/step18-mmap-gameplay-start.json`, monotonic 135874.1542. Bundan sonraki
45 örnek / 44 saniye pencere 135908.1538–135952.1547: medyan **4 FPS**, min/max
3,5–4; medyan kare aralığı 254,2 ms; rolling p95 medyanı 270,9 ms. CPU %546
(%100 bir çekirdek), fiziksel bellek medyanı 952699968 bayt (908,6 MiB),
headroom medyanı 2587292608 bayt, memory warning=0, thermal state=2 (serious).
Sunum command buffer GPU medyanı 23,2 ms; bu bütün oyun GPU süresini kapsamaz.
SPU native kopyası OFF. Özet `out/step18-mmap-gameplay-summary.json`; ham CSV
`out/step18-mmap-gameplay-performance.csv`. Aynı kamera için dokunmama talimatı
verildi; otomatik kamera doğrulaması yok. Bu ölçüm eski farklı oturumlara göre
kontrollü hız artışı iddiası değildir.

Aynı diagnostic allocator ile calloc sürümü çökerken mmap sürümü oynanışa ulaştı;
güçlü deneysel kanıt büyük arena / malloc kaynak baskısına işaret eder. Kesin
kernel adres alanı sınırı veya zone içi mekanizma henüz ölçülmüş değildir.

Normal allocator doğrulama sürümü build 20 derlendi ve strict imza kontrolü geçti.
UUID 8103469F-F84E-33EF-9F16-EF814BDADA03, SHA ve sembol kontrolü
`out/step18-final-binary.json`. Binary'de diagnostic operator new/new[] tanımı
yok; BCES_TRACE_NEW_FAILURES=OFF, Extended VA=OFF. Shader tanı kaydı başlatma
argümanı verilmezse kapalıdır. Oyun mantığı / shader geçişleri / stack boyutları
bu düzeltmede değiştirilmedi.

## Karşı kanıt: build 20 yine çöktü

Normal allocator sürümünde kullanıcı sinematikte yeniden kapanma bildirdi.
`out/step18-final-crash-201637.ips`, UUID 8103469F-F84E-33EF-9F16-EF814BDADA03:
SPIRV-Tools `DefUseManager::AnalyzeInstUse` / dead function elimination içinde
sistem `operator new` bad_alloc. Malloc rezervasyonu 128,8 MiB'ye inmiş olsa da
stack 3,6 GiB kaldı. **mmap tek başına çözüm değildir**; ilk geçiş başarı oranı
veya kalıcı çözüm kanıtı değildir. Diagnostic allocator ile farklı allocation
örüntüsü de mümkün; global new override kalıcı çözüm olarak bırakılmadı.

## İkinci düzeltme denemesi: host stack rezervasyonu

Build 21: guest PPU thread host stack'leri ve GameApp ana PPU worker host stack'i
256 MiB yerine 64 MiB ayırır. Guest stack alanı, register'lar ve guest adresleri
aynı kalır. 64 MiB hâlâ büyük bir host stack'tir; derin yeniden derlenmiş çağrı
zincirleri nedeniyle 512 KiB/1 MiB varsayılanına dönülmedi. SPU / frameclock stack
boyutları değiştirilmedi. Süreçte tutulan rezervasyon miktarı azaltılır; fiziksel
RAM kazancı eşit miktarda varsayılmaz.

`tools/prepare_bces_ios.py` doğrulanmış yamalı `sys_ppu_thread.c` dosyasından
ayrı `ppu_thread.c` üretir; orijinal full-runtime arşivinden yalnız bu üye ek
olarak çıkarılır ve uygulamada aynı O2 seçenekleriyle yeniden derlenir. Sabitlenmiş
fork'a önceden uygulanmış dört ftrace eklemesi korunur, kaynak SHA'sı
`sources.lock.json:ios_ppu_host_stack` ile sabitlenir. Upstream kaynak değişmez.

`src/platform/HostStack.c` PPU girişinde thread'in kendi stack sınırını kaydeder;
1 Hz telemetry thread_get_state ile gerçek ARM64 SP derinliğini örnekler. Rapor
`performance.host_stacks`: registered/sampled, toplam reserved_bytes,
peak_sampled_used_bytes, minimum_sampled_margin_bytes. 128 slotla sınırlı; Mach
send right'ları başarısız/bitmiş thread örneklemesinde bırakılır. Başka thread'in
pthread pointer'ı üzerinden yarışmalı sınır okuması yapılmaz. Örneklenmiş tepe,
gerçek bütün-zamanların yüksek su işareti değildir; kısa derin çağrılar kaçabilir.
`tools/tests/host_stack.cpp` 64 MiB thread üzerinde 256 KiB gerçek stack derinliği,
iki thread'in okunması ve biten thread'in temizlenmesini doğruladı. İlk testte
compiler sparse volatile array'i küçülttü; buffer escape eklenince gerçek 256 KiB
frame korundu. pthread_join ile kernel port ölümü arasındaki kısa gecikme testte
beklenir. PASS: `out/step18-host-stack-test.log`.

Build 21 normal allocator ile, shader tanısı kapalı ve native copy OFF denenir.

Build 21 gerçek iPhoneOS derlemesi ve strict imza kontrolü PASS.
UUID DFFB5769-11BA-3D1A-A7A3-18350FBC0263; `out/step18-stack-binary.json`.
İlk canlı rapor PID 10481: 23/23 PPU stack örneği geçerli; toplam host rezervasyon
1543786496 bayt (1,4375 GiB), örneklenmiş en derin kullanım 34080 bayt,
en küçük örneklenmiş marj 67087072 bayt. Bu erken anlatım örneğidir; henüz
açık dünya yüksek su işareti sayılmaz. Başlangıç doğruluk kontrolleri PASS.

Build 21 kullanıcı tarafından gerçek oynanışta doğrulandı; ölçüm başlangıcı
`out/step18-stack-gameplay-start.json`, monotonic 136885.006966. Aynı anda
23/23 stack örneği geçerli, toplam rezervasyon 1543786496 bayt; örneklenmiş tepe
34144 bayt ve minimum marj 67087008 bayt. Pipeline 1027/1027, failure=0;
physical footprint 955420000 bayt, headroom 2584572576 bayt. Normal sistem
operator new kullanılıyor; shader girişlerinin dosyaya yazılması kapalı.
Bu testte native SPU kopyası özellikle OFF (fast_calls=0). Bu nedenle sonuçlar
native copy FPS etkisi olarak yorumlanamaz.

Host stack ölçümünü tekrar üretmek için:
```sh
clang -O2 -Isrc/platform -c src/platform/HostStack.c -o build/bces01229/host-stack-test.o
clang++ -std=c++20 -O2 -Isrc/platform tools/tests/host_stack.cpp build/bces01229/host-stack-test.o -o build/bces01229/host-stack-test
build/bces01229/host-stack-test
```
Son normal derlemede `-DBCES_TRACE_NEW_FAILURES=OFF` kullanılır.

## Son normal sürüm ölçümü

Kullanıcının oynanış teyidinden sonraki başlangıç 136885.006966, son rapor/CSV
136978.006558; yaklaşık 93 saniyelik kayıt sırasında PID 10481 korundu. Son
45 örnek / 44 saniye pencere **136934.007141–136978.006558** tamamen bu teyitten
sonradır. Kaynak `out/step18-stack-gameplay-performance.csv`, SHA256
ca7b4b636da8b18dafb3f4620178d34baf95404e697113cad44e523021308b80.
Özet `out/step18-stack-gameplay-summary.json`.

| Ölçüm | Son 45 örneğin medyanı |
|---|---:|
| FPS | 4,0 (min 3,5 / max 4,0) |
| Kare aralığı ortalaması | 254,2 ms |
| Rolling kare p95 | 266,7 ms |
| CPU | %545,6 (%100 = bir çekirdek) |
| Sunum command buffer GPU | 23,3 ms (bütün GPU işi değildir) |
| Fiziksel footprint | 955714912 bayt ≈ 911,4 MiB |
| Fiziksel allocation headroom | 2584277664 bayt ≈ 2,41 GiB |
| Bellek uyarısı | 0 |
| Isı durumu | 2 / serious |

Son rapor pipeline 1027/1027, failed=0, Metal errors=0; 23/23 PPU stack ölçümü
geçerli. Rezervasyon 1543786496 bayt ≈ 1,44 GiB, örneklenmiş tepe stack kullanım
34144 bayt, minimum örneklenmiş marj 67087008 bayt. Bu toplam yalnız kayıtlı PPU
thread'lerine aittir; SPU, frameclock ve sistem thread stack'lerini kapsamaz.

```sh
python3.12 tools/analyze_performance_csv.py out/step18-stack-gameplay-performance.csv --label 'build21 normal allocator; verified gameplay; native copy OFF' --last-seconds 45 --output out/step18-stack-gameplay-summary.json
```

Sonuç: mmap tek başına başarısız oldu; host stack rezervasyonunun da düşürüldüğü
normal sürüm hatalı geçişi ve bu ölçümü tamamladı. Önceki küçük allocation
hataları, dev rezervasyonlar ve bu sonuç sanal bellek kaynak baskısını güçlü
aday yapar; kesin kernel limit/tag mekanizması kanıtlanmış değildir. Sistem
allocator korumaları kapatılmadı, shader atlanmadı, SPIRV optimizer pass'leri
korundu. Uzun oyun, yeni bölgeler/ek shader'lar, arka plan ve yeniden açma
sonrasında kararlılık ayrıca sınanmalı. Tek yeni başlatma geçişi uzun dönem
çökme oranını belirlemez. FPS hâlâ CPU çalışması açısından ciddi optimizasyon
ister; video/Bink yerine gerçek oynanış CPU/SPU işi üzerinden ölçülmelidir.
Uygulama açık bırakıldı, otomatik kapanış argümanı yok. Bu çalışma sonunda
kurulu sürüm build 21; çalışan denemede native copy OFF, tanı allocator OFF,
shader dosya kaydı OFF, Extended VA OFF. Normal kullanıcı başlatmasında native
copy'nin önceki varsayılanı değişmedi; bu FPS sonucu onun etkisini ölçmez.

Son canlı rapor: `out/step18-final-live-report.json`, aynı PID, oynanış ölçüm başlangıcından 165 saniye sonra hâlâ güncelleniyor; Metal/pipeline hata sayaçları 0/0.
