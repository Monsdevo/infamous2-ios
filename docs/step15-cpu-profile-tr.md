# 15. adım — cihaz ölçümü ve CPU darboğazı araştırması

24 Ekim 2026. BCES01229 / 01.00, gerçek iPhone 15 Pro. Bu adımda FPS
artışı sağlayan bir optimizasyon henüz uygulanmadı; ölçüm ve çökme tanısı eklendi.
Mac karşılaştırma hedefi ve sabitlenmiş runtime korunuyor.

## Doğrulanan oynanış ölçümü

Kullanıcı oynanabilir bölüme ulaştıktan sonra kamerayı/kumandayı sabit bıraktı.
`out/step15-stationary-gameplay.png` incelendi: Cole, iskele ve gerçek dünya
görüntüsü var. Bu boş Metal ekranı veya yalnız menü testi değil.
`out/step15-stationary-gameplay.csv` son 45 saniyesi, 46 ölçüm satırı:

| Ölçüm | Sonuç |
| --- | --- |
| FPS medyanı | 3,0 (örnek aralığı 3–3,5) |
| Ortalama kare aralığının medyanı | 319,5 ms |
| Süreç CPU medyanı | %550,9; %100 bir çekirdek |
| Ekran sunum komut tamponu GPU süresi medyanı | 23,27 ms |
| Fiziksel footprint medyanı | 908,55 MiB |
| Örneklenmiş fiziksel tepe | 917,21 MiB |
| OS'nin bildirdiği ek bellek payı medyanı | 2.587.308.944 bayt (2,59 GB) |
| Bellek uyarısı | 0 |
| Isınma sınıfı | serious / “Sıcak”, bu pencerenin tamamı |

Kaynak ve hash'ler `out/step15-stationary-summary.json` içinde.
Değerler saniyelik örneklerin medyanlarıdır; rolling p95'lerin medyanı bütün
oturumun p95'i değildir. GPU ölçümü ayrı offscreen/compute tamponlarını kapsamaz;
23 ms'den bütün karenin GPU maliyeti veya GPU kullanım yüzdesi çıkarılamaz.
Render döngüsünün yaklaşık 7,8 ms değeri de guest'in bütün karesi değildir.
USB bağlıydı; ısınma ve şarj koşulları sonraki A/B ölçümünde eşit tutulmalı.

Bu ölçümde bellek sınırına dayanıldığına dair bulgu yok. Increased Memory Limit
entitlement eklenmedi. Bu entitlement daha fazla allocation payı sağlayabilir;
işlemcinin aynı işi daha hızlı bitirmesini sağlamaz. Metal allocated size ile
physical footprint örtüşebilir; bunlar toplanmaz. `recommendedMaxWorkingSetSize`
ise uygulamanın kesin RAM limiti değildir. Büyük sanal arena ve thread stack
rezervasyonları fiziksel kullanım gibi raporlanmaz.

## Gerçek fonksiyon örnekleri ve sınırı

Instruments Time Profiler hem Wi-Fi hem USB ile denendi. `devicectl` cihazı
bağlı/wired görürken `xctrace list devices` Offline gösterdi; kayıtlar
bağlanma zaman aşımıyla bitti. Kullanılabilir bir `.trace` oluşmadı.
DDI servisleri `isUsable=true`, `contentIsCompatible=true`; bu sonuçtan
“Xcode kesin uyumsuz” çıkarımı yapılmadı. Eşleşme/cihaz durumu sıfırlanmadı.

Alternatif olarak iOS'un kendi `cpu_resource` Microstackshots kaydı alındı:
`Infamous2Game.cpu_resource-2026-10-24-172948.ips`.
Örnekleme aralığı **17:27:43–17:29:42 İstanbul**, menü/yükleme dönemi;
yukarıdaki sabit oynanış penceresi değildir. 56 örnek, 22 kayıp örnek vardır.
Bu seyrek kayıt Time Profiler'ın yerini tam olarak tutmaz ve tüm oynanışın
kesin yüzdelerini vermez. `Action taken: none`; cpu_resource olayı tek başına
OS'nin uygulamayı kapattığı anlamına gelmez.

Kaydın UUID'si **82DF04B1-E453-3CB0-8DFE-6AF4E40D348B** ile Mach-O UUID'si
eşleştirildi. Tam o executable `build/bces01229/symbols/UUID/Infamous2Game`
altında korundu; hash `out/step15-binary.json` içinde. Eski sürümlerin
adresleri bu binary ile yorumlanmadı. 189 farklı uygulama offset'i `atos`
ile fonksiyon adına çevrildi. `tools/analyze_cpu_resource.py` UUID eşleşmezse
durur; iç içe çağrıların inclusive ağırlıklarını üst üste toplamaz.

| Ayrık çağrı yolu | Örnek |
| --- | --- |
| SPU thread'leri (`spu_exec_thread_proc`) | 47 / 56 (%83,9) |
| PPU başlangıç/host thread'leri | 6 / 56 |
| Renderer `frame_clock` | 3 / 56 |

CPU tarafından örneklenen bu ağırlıklar, duvar saatinin aynı oranda bölündüğü
veya yalnız bu kod hızlanınca toplam FPS'in aynı oranda artacağı anlamına gelmez.
Sistem/kernel alt çağrıları atalarının yoluna dahildir.

Öne çıkan zincir:

```text
spu_exec_thread_proc → spu_lifted_thread_run → spu_run_with_halt
 → spu_0001_at_0085E400_spu_func_00000124
 → spu_drain_call → ...00000290 → ...00000640 → ...00000A50
 → ...0000BC08 → diğer statik SPU fonksiyonları
```

`build/bces01229/spu/spu_workloads.c`, bu modülü image id 2 altında
`spu_0001_at_0085E400` adıyla kaydeder; ELF entry `0xD0`, içerik EA `0x86E500`,
LS tabanı `0x80`, boyut `0x184F0`. Üretilmiş fonksiyonlar aynı adlı alt klasörde
`spu_recomp.c` içindedir. `...BC08` inclusive olarak 17 örnek taşır; bu kendi
başına 17 örneklik maliyeti olduğu anlamına gelmez. Exclusive en yüksek tek
fonksiyon `spu_check_stack_reset`, 5 örnektir; 56 örnekle ince sıralama kesin değil.
Modülün semantik görevini henüz “fizik/ışık/geometri” diye adlandırmıyoruz.

Pinned runtime içinde `runtime/spu/spu_drain.c:spu_drain_call`, üretilmiş
fonksiyonların devam adreslerini/trampoline akışını yürütür. Her aktarımda
`spu_task_launch_check` çağrılır. `runtime/spu/spu_channels.c:spu_check_stack_reset`,
guest stack'ini değiştiren girişlerde doğru host stack'e dönülmesini sağlar.
Bunlar çıkarılabilir gereksiz beklemeler değildir; kaldırmak doğruluğu bozabilir.
Yalnız profilde görünmesi, o kontrolün tüm yavaşlığın nedeni olduğunu kanıtlamaz.
Üretilmiş PPU/SPU destek kodu şu an `-O1` ile derleniyor
(`tools/check_bces_compile.py`, `tools/check_bces_support_compile.py`).

## Çökmeler ve yeni tanı

Üç ayrı kayıt korundu, tek sebepmiş gibi birleştirilmedi:

- 16:58:03: UIKit form sheet gölge bitmap'i oluştururken assertion/SIGABRT.
  `GamePerformance.openSettings` sunumu OverFullScreen olarak değiştirildi;
  oyun view/layer'ı altta kalır. Yeni sunum biçiminin cihazda panel açılarak
  tekrar sınanması hâlâ gerekli; bu yüzden kesin “çözüldü” denmiyor.
- 17:11:59: AGXMetal.CodeHeap üzerinde “failed to create IOGPUResourceRef”
  heap allocation abort'u. Bu bir jetsam kanıtı değil; allocation'ın neden
  başarısız olduğu henüz belirlenmedi.
- 17:15:20: Metal PipelineFunctionObjects yolunda objc allocation/instantiate
  abort'u. Önceki Metal kaydıyla yakın bir alanda, aynı hata mesajı değil.

`src/ios/GamePerformance.mm` artık `os_proc_available_memory`, bellek uyarısı
sayısı, Metal allocation ve pipeline sayaçlarını raporlar. Ayarlarda
“Bellek sınırına kalan pay” anahtarı var. CSV 17'den 23 sütuna çıktı.
`GameTelemetry.cpp:game_telemetry_pipeline` begin/success/failure sayar.
`patches/ios-metal-surface.patch` içindeki `ios_profiled_pipeline`, mevcut
8 pipeline oluşturma yerini sarar; shader/descriptor davranışını değiştirmez.
Yalnız `--profile-pipelines` verilince ayrı `Documents/pipeline-events.csv`
oluşur (20.000 satır sınırı, olay başına flush). Normal açılışta bu dosya IO'su yok.

Başarılı oturumda 1.037 begin ve 1.037 success, 0 failure; açık kalan çağrı yok.
Çağrı süresi medyanı 0,136 ms, en uzunu 144,855 ms; toplam 468,525 ms.
Bu süre shader çevirisi/library oluşturmayı kapsamaz. Son pipeline olayı
monotonic 127309, sabit oynanış raporu 127407; o raporda sayaç hâlâ 1.037.
Bu aralıkta sürekli pipeline yaratımı görülmedi. Başarılı tek oturum önceki
driver allocation çökmelerinin düzeldiğinin kanıtı değildir.

## Derleme ve kontroller

- `out/step15-diagnostic-build.log`: gerçek iPhoneOS `BUILD SUCCEEDED`, `-jobs 1`.
  Aynı bundle ID üzerine kuruldu; oyun verileri/tercihler silinmedi.
- Kurulu yeni executable'ın UUID'si yukarıdakiyle eşleşiyor. Paket etiketi
  hâlâ **0.3/build 14**: kaynak Info.plist 15'e alındıktan sonra CMake configure
  tekrarlanmadığı için eski kopya kullanıldı. UUID ile kod kimliği doğrulandı;
  sonraki paket öncesi configure yapılmalı.
- `tools/tests/game_telemetry.cpp`: pipeline sayaçları, gerçek sunum penceresi,
  stale/NaN örnekler ve bounded/concurrent ring PASS.
- `tools/tests/bces_render_gate.cpp`: hızlı pause/resume, CPU batch/GPU fence
  onayı PASS. Bu tüm guest thread'lerinin pause doğruluğu testi değildir.
- `tools/test_profile_analysis.py`: UUID/architecture mismatch reddi,
  recursive inclusive sayımların çift sayılmaması, CSV zaman penceresi ve
  geçersiz/NaN örneklerin elenmesi: 3 test PASS.
- Cihazda gerçek dünya görüntüsü ve sayaçlar okundu. Süre sınırı yoktu.
  Increased Memory Limit, çözünürlük/FOV ve oyun davranışı değiştirilmedi.

## Tekrarlanabilir komutlar

Çalışma kökünden, mevcut CMake cache'i korunarak:

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
export TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp
python3 tools/test_profile_analysis.py
python3 tools/analyze_performance_csv.py out/step15-stationary-gameplay.csv --label 'Kullanıcı sabit kamera oynanış' --last-seconds 45 --output out/step15-stationary-summary.json
python3 tools/analyze_cpu_resource.py out/step15-cpu-resource-current.ips --binary build/bces01229/symbols/82DF04B1-E453-3CB0-8DFE-6AF4E40D348B/Infamous2Game --label 'Menu/load 17:27:43–17:29:42; not stationary gameplay' --output out/step15-cpu-analysis.json
python3 tools/prepare_bces_ios.py
cmake -S cmake/bces-ios -B build/bces01229/ios
xcodebuild -project build/bces01229/ios/Infamous2BCESIOS.xcodeproj -scheme Infamous2Game -configuration Release -destination id=00008130-001129E00243001C -jobs 1 DEVELOPMENT_TEAM=BJ266NGN3H -allowProvisioningUpdates
xcrun devicectl device install app --device 00008130-001129E00243001C build/bces01229/ios/Release-iphoneos/Infamous2Game.app
# Tanı oturumu; kullanıcı normal açılışında bu argümanlar gerekmez:
xcrun devicectl device process launch --device 00008130-001129E00243001C --terminate-existing dev.infamous2.iosprobe --boot --profile-pipelines
```

Kaynak pinleri değişmedi; kendi renderer patch SHA'sı kilit dosyasında güncellendi.
Oyun, firmware, .ips/CSV ve büyük üretilmiş çıktılar Git'e eklenmez.

## Sıradaki somut iş

Önce oynanış aralığını kapsayan fonksiyon profili alınmalı: Instruments
bağlantısını çözmek veya aynı UUID'li yeni OS kaydı oluşursa tarihini oynanış
ölçümüyle eşleştirmek. Şu anki OS kaydı yalnız başlangıç dönemini kapsıyor.
İlk sınırlı A/B adayı, SPU destek kodunu ayrı bir arşivde daha yüksek derleyici
optimizasyonuyla (`-O2`, fast-math olmadan) denemek; mevcut `-O1` baseline'ını
korumak. Bunun kazanç vereceği henüz ölçülmedi. Gerekirse sonra dispatch/TLS ve
stack kontrol maliyetleri ayrı incelenir. Semantik kontroller silinmez.
Her değişiklik aynı sahne, kamera ve benzer thermal state'te karşılaştırılmalı;
ses, DualSense, world yükleme ve görüntü doğruluğu regresyonu kontrol edilmeli.
Metal allocation çökmeleri ayrı kararlılık konusu olarak açık kalıyor.
