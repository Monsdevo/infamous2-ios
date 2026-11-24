# Büyük SPU işlerinin süre ve bağımlılık teşhisi — 5 Kasım 2026

Kullanıcı optimizasyon eklemeden, büyük hesap ve gerçek kare bağımlılığını
ölçmeyi istedi. Telefon üzerinde ölçüm; Mac native testleri yalnız doğruluk.
Oyun/firmware ve çalışan pinned runtime değiştirilmedi. Build jobs1.

## Build57: önceki aday alt çağrı zinciri

`638a73` modülündeki `8648→6B90 + spu_drain_call(...866C)` bütünü, ayrıca
68D8 ve örneklenen1/16 5A98 alt çağrıları braketlendi. Uygulama gerçek iPhone'a
kuruldu, kayıtlı bataklıkta aynı iskele konumu iki gerçek yüzeyle doğrulandı.
Yalnız nötr giriş gönderildi. İlk3s iz201.288 olay/dropped0/thermal1;
ortak kayıt15,016sCPU +3strace194.735 olay/dropped0/thermal2.
CPU7.269satır/662tick/error0/truncated0. UUID4A04FCB1-9E95-3CB1-BD98-5733410838AF.

İlk izde295tam6B90çağrısı: wall medyan0,058ms, CPU medyan0,054292ms;
toplam CPU23,002279ms /3s. 21tam guest-frame penceresinde bütün worker'ların
root wall union medyan0,865ms; kare aralığı medyan112,325ms.
291nitelikli tek-geride-özel-lane PPU poll'unda bu dar alt ağ aktif değildi.
İkinci kayıtta rootCPU23,012242ms /3s ile küçük bütçe tekrarlandı.
Bu alt ağ, bu sahnede büyük kazanım hedefi olarak desteklenmedi.
Bu sonuç modülün tamamı veya ilk liman sahnesi hakkında etkisizlik kanıtı değil.

CPU ancestry dağılımı, duvar/kare süresi değildir: Edge modülü doğrudan%16,39;
1774dd modülü ancestry%7,10, 867e%5,94, 43398%5,64. İlk legacy issuer/CPU
korelasyonunda yalnız10eşleme/1tek-geride-lane vardı; aday seçmek için zayıf.
Bu yüzden dağıtıcı seviyesinde tüm işlerin tam süresi hedeflendi.

## Build58: host çağrı braketinin eksikliği

WWS31F8dolaylı çağrı +3218drain dönüşü etrafına C-scope eklendi. Native
call/drain testi geçti, gerçek3s iz249.815olay/dropped0/thermal3 aldı.
27.163begin fakat yalnız2.957end var. Interior unclosed koruması analizi
reddetti; bu veri tam iş bütçesi olarak kullanılmadı. Eksik eşleşmenin tam
kök nedeni izole edilmedi; normal host devamına bağımlı C-scope güvenilir
mantıksal iş sınırı sayılmadı. Ölçüm araçları bunu başarı gibi sunmadı.

## Build59: gerçek guest iş giriş/dönüşü

27kayıtlı jobmod kaynağında gerçek ELF entry fonksiyonuna başlangıç,
her modülün tek `int_enable=0; SPU_RET` CRT çıkışına bitiş eklendi.
Yalnız guest LR3218sözleşmesi olan işler kabul edilir. Kalıcı thread-local
context/slot token'ı host continuation terk edilse bile yaşar. Yeni giriş eski
kapsamı kapatmadan gelirse418cancellation kaydı olur; bu işler tamamlanmış
CPU/ms bütçesine eklenmez. Scopeclass0xC0000000|entry; native-depth değişimi
mantıksal işte normal host-call eşitliği gibi zorlanmaz. Guest register/LS
ve hesap/senkronizasyon algoritmaları değiştirilmez.

27SPUbirimi yeniden O2/iPhoneOS derlendi; kalan56nesne byte olarak korundu.
Özgün arşiv değiştirilmedi. CMake/header kimliği ve iPhoneOS platformu denetlenir.
Native ASan/UBSan: gerçek dönüştürülmüş wrapper +deferred5msdrain, CPU/wall,
read-onlycontext/LS,1/16örnekleme, paralel writer, epochstop/replay, setjmp/
longjmpilemantıksal ömür ve cancellation geçti. Kuyruk modu2 her PPU poll'unun
braketini ve ayrıca zamanlanmış POST-poll snapshot'ını kaydeder; eski0/1modu
korunur. Son doğrulamada kuyruk ve tam-iz analizinin 17 testi geçti.

İlgili kaynak ve araçlar:
`CriticalJobTrace.{h,c}`, `prepare_critical_job.py`,
`build_bces_critical_job.py --logical-jobs`, `analyze_critical_job.py`.

## Build 59: tamamlanan gerçek iPhone ölçümü

Build 59 iPhoneOS için derlendi ve aynı uygulama kimliğiyle iPhone 15 Pro'ya
kuruldu. PID 5387, UUID `C0F83632-21D5-314A-AA9B-EAE2BD4B5F9C`.
Kayıtlı **bataklıktaki tahta iskele** sahnesi kullanıldı; ilk yeni oyun limanı
değil. Nötr giriş korundu. Başlangıç ve bitişte gerçek oyun yüzeyi incelendi:
`out/ios-job59/scene-{1,2,final}/frame.png`. Sahne normal görünüyor.

İlk 3 saniyelik kayıtta 500.000 olay kapasitesi doldu, 81.968 olay düştü;
`trace-A` **reddedildi**. Kabul edilen kayıtlar:

| Kayıt | Süre | Olay | Tam mantıksal iş | Tam kare penceresi |
| --- | ---: | ---: | ---: | ---: |
| trace-B | 1 s | 189.089 | 9.163 | 4 |
| joint-C/trace | 2 s | 372.957 | 18.108 | 14 |
| trace-D | 2 s | 395.815 | 18.112 | 13 |

Sonuç: **5 saniye / 45.383 tamamlanmış iş / 31 tam kare penceresi**.
Kabul edilen üç izde dropped=0; iptal edilmiş veya açık kalmış kapsam yok.
Pencere sınırını aşan 8 tamamlanmış kapsam süre bütçesine katılmadı.
20 farklı kayıtlı modül gerçekten çalıştı; eşlenemeyen root yok.
27 modüle araç eklenmesi bütün oyun işlerinin eksiksiz ölçüldüğü anlamına
gelmez: o pencerede çalışmayan veya başka uygulamaya yönlendirilen işler
bu kapsamlarda görünmeyebilir.

Telefon üç kayıtta da **kritik (3)** termal durum bildirdi. Harici soğutma
istenmedi. Bu kayıtlar iş kimliği, iş maliyeti ve gözlenen bağımlılık teşhisidir;
normal sıcaklık performansı veya optimizasyon açık/kapalı FPS karşılaştırması
değildir. Ölçüm araçlarının kendi maliyeti de vardır.

### Ağır CPU işleri ve gerçek bekleme ayrımı

Aşağıdaki birim **1 saniye duvar süresinde bütün worker'ların toplam CPU
milisaniyesidir; kare başına milisaniye değildir**. İşin içindeki runtime,
alt çağrı ve interrupt maliyeti dahildir. Paralel işler ve alt kapsamlar
toplanarak kare süresi veya kazanılabilir süre çıkarılamaz.

| Modül | Üç kayıtta CPU ms / duvar saniyesi |
| --- | ---: |
| Edge `d0d15ec83992` | 876,48–876,67 |
| `1774dd41c4e8` | 483,99–488,20 |
| `867e5d2348b3` | 334,32–349,95 |
| `43398b961dfa` | 269,47–283,27 |
| SSAO işinin kalan CPU yolu `e6fe749031f8` | 90,14–105,17 |
| `638a73a6476e` bütün mantıksal iş | 17,63–18,62 |

`1774dd`, `867e`, `43398b` için fizik/animasyon/decompression gibi bir ad
henüz kanıtlanmadı. Hex kimlikleri korunuyor. `638a73` içindeki önceki dar
alt zincir küçük çıktı; bütün modül ölçümü de bu sahnede büyük bir bütçe
göstermedi. Bu, başka sahnelerde aynı olacağı iddiası değil.

Kare pencerelerinde medyan aralık 97,27 / 99,14 / 99,35 ms; RSX FIFO drain
87,39 / 88,22 / 88,44 ms; ölçülen GPU yürütme union'ı
61,17 / 61,47 / 61,77 ms. **Bunlar iç içe ve paralel sürelerdir.** Drain
salt CPU hesabı değildir; GPU, senkronizasyon ve zamanlama da içerebilir.
Ana PPU kısa uykularının drain dışındaki medyanı yalnız
1,64 / 1,32 / 0,55 ms; uykuların çoğu drain ile örtüşüyor.
Bu gözlem tek başına “SPU darboğaz değil” veya “drain'in tamamı silinebilir”
sonucunu vermez.

Üç izde 812 / 1.322 / 2.648 ilgili ana-PPU kuyruk poll'u var. Kesin tek
geride özel lane, değişmeyen gözlenen değerler ve benzersiz üretici
koşullarını yalnız 21 / 69 / 133 poll sağladı. Bu, poll sayısının yaklaşık
%2,6 / %5,2 / %5,0'ı. Bunların iş kapsamıyla eşleşen union süresi
tüm pencerede 0,665 / 4,995 / 9,716 ms. Güvenle sınıflandırılan kapsam dar:
eşlenmeyen beklemeler sıfır maliyet sayılmadı ve kalan süreye oranlanmadı.
Dolayısıyla büyük bir SPU işinin kareyi 30–50 ms durdurduğuna henüz kanıt yok;
bu az sayıdaki eşleşme böyle bir işin olmadığını da kanıtlamıyor.

### Aynı sürecin CPU örneklemesi

joint-C: 15,018 saniye, 6.871 satır, 667 tick, errors=0, truncated=0.
Binary UUID, PID ve saat dönüşümü denetlendi; 2 saniyelik iz CPU penceresinin
içinde. CPU dağılımı istatistiksel; exact iş sürelerinin alternatifi değil.
SPU modüllerinin doğrudan örneklenen toplam süreç CPU payı: Edge %16,47,
`43398b` %5,50, `867e` %4,00, `1774dd` %3,22. Ancestry payları farklıdır
ve birbirleriyle toplanmaz.

Renderer thread gözlenen CPU süresi 7,957 s / 15,018 s; 441 running-PC
örneği. Kendi CPU'su içinde `rsx_vertex_fetch_all` %18,82,
`bces_cached_texture_hash` %7,71, `cellGcm_rsx_process_fifo` %6,58,
`rsx_vertex_remap_build_range` %5,44. Sistem/çözülemeyen leaf payı %29,93;
buna belirli bir oyun fonksiyonu adı verilmedi. Bu paylar da doğrudan
kare başına kazanılabilir milisaniye değildir.

### Karar ve sıradaki somut adım

Bu oturum yeni bir hızlandırma algoritması eklemedi. Ağır işler üç kayıtta
tekrarlanabilir biçimde sıralandı; tam iş ile küçük alt fonksiyon farkı
ölçüldü. Sonraki adım `1774dd`, `867e` ve `43398b` işlerinin giriş/çıkış
verisini ve tüketicisini kaynak üzerinden tanımlamak; ardından yalnız adayın
sonuç yayımlama anını PPU/renderer tüketimiyle eşlemek. Çok-geride-lane
beklemeleri, sırf tek üretici seçilemiyor diye dışarıda bırakılmayacak;
belirsiz olarak korunacak. Bütünü bilinmeyen bir işi körlemesine Metal'e
taşımak veya Edge mikro-kernel deneyini tekrar etmek seçilmedi.

Bu eşlemeden sonra hesap ağırlığı yüksek, orijinal sonuçla doğrulanabilen ve
kritik tüketiciyi bekleten **tek** aday için ARM64/Metal prototipi seçilebilir.
Şu anda sayısal FPS kazancı vaat edilemiyor.

## Tekrar üretme ve çıktılar

Ön koşul: aynı pinned kaynaklar, üretilmiş yerel BCES01229 girdileri ve
iPhoneOS bağımlılıkları hazır olmalı. Oyun/firmware bu not veya Git'e dahil
değil. Derleme paralelliği `-jobs 1`; TMPDIR harici SSD'de tutulur.

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
export TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp
export PYTHONPATH=tools
python3 tools/build_bces_critical_job.py --logical-jobs
python3 tools/prepare_bces_ios.py --support-report out/bces-support-critical59.json
xcrun xcodebuild -project build/bces01229/ios/Infamous2BCESIOS.xcodeproj \
  -scheme Infamous2Game -configuration Release -destination generic/platform=iOS \
  -derivedDataPath build/bces01229/DerivedData -jobs 1 \
  CODE_SIGNING_ALLOWED=YES DEVELOPMENT_TEAM=BJ266NGN3H -allowProvisioningUpdates
# Son başarılı derlemenin kaydı: out/job59-build.log (BUILD SUCCEEDED).
# Açılışta --boot --diagnose-frame --profile-cpu --diagnose-critical-job
# ve mevcut güvenilir optimizasyonların kontrol seçenekleri kullanıldı.
python3 tools/capture_frame_trace.py --device 00008130-001129E00243001C \
  --output out/ios-job59/repeat-new --seconds 2
python3 tools/analyze_critical_job.py out/ios-job59/repeat-new/frame-trace.csv \
  --output out/ios-job59/repeat-new/critical-analysis.json
python3 -m unittest tools.tests.critical_job tools.tests.progress_overlap \
  tools.tests.progress_issuer_mapping tools.tests.progress_writers
python3 tools/test_critical_job.py
python3 tools/test_progress_trace.py
```

Son iki komut ASan/UBSan ile gerçek tanı kodunu sınadı; 17 Python testi de
geçti. Native test, oyunun bütün semantiği veya FPS testi değildir.
Ham kayıtlar ve analizler `out/ios-job59/`; birleşik sonuç
`measurement-summary.json`. Kaynak manifesti `source-hashes.json`, son analiz
revizyonu ayrıca arşivlenir. Kontroller sonunda frame_trace_state=3 ve
cpu_profile_state=3 doğrulandı; kayıt kontrol dosyaları idle. Bu oturumun
test süreci ölçümden sonra kapatıldı; uygulama, oyun verileri ve save korundu.
