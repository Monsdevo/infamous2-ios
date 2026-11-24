# 7. adım — ayrı PPU/renderer thread'leri ve yaşam döngüsü

Amaç iPhone'un kendi CPU/GPU'sunda, tek uygulama sürecinde çalışmaktır. Mac
bu aşamada derleme, yükleme ve rapor alma için kullanılır. Bu testte oyun
verisi/kodu yoktur; lifter ABI'sine uygun sentetik ELF programı kullanılır.
**Oyun karesi 0.** Kaynak pin'leri ve title SPU/light/SSAO yamaları korunur.

## Değişen akış

- `RuntimeCoordinator.cpp::runtime_renderer_start()` **16 MiB** stack isteyen
  joinable pthread oluşturur. UIKit'in başlattığı PPU pthread'i **256 MiB**
  stack istemeye devam eder. Backend init, FIFO drain, draw, sunum, GPU bekleme
  ve backend shutdown yalnız renderer sahibinde çalışır. TID'ler loglanır;
  renderer ile PPU'nun farklı olduğu kontrol edilir.
- `FullRuntimeProbe.cpp::graphics()` gerçek GCM NID/context/IO/label yolunu
  korur. `render_call()` işi renderer'a devreder; `ppu_gcm_pump()` ve gerçek
  OPD callback'leri PPU'da kalır. Önceki doğru piksel, flip sınırı ve semaphore
  kontrolleri iki thread arasında da yürütülür.
- **Tek bekleyen batch** vardır. Mutex/condition-variable devri guest bellek
  yazılarının görünürlüğünü sağlar. PPU, renderer aynı VM/register alanını
  tüketirken üzerine yazmaz. Bu aşama çok sayıda eşzamanlı PPU/SPU FIFO
  üreticisi veya performans amaçlı çok kareli pipeline değildir.
- `full_runtime_set_active(false)` yeni iş kabulünü kapatır.
  `runtime_ppu_checkpoint()` PPU'yu güvenli noktada park eder; renderer
  mevcut işi bitirip GPU flush yapar. `full_runtime_wait_quiescent()` ancak
  **PPU park + renderer/GPU idle** olduğunda onay verir. Aktif GPU işi zorla
  kesilmez. Flush/teardown da PPU güvenli noktasını bekler; GCM setup ve
  callback kodu renderer state'ine erişirken kaynaklar serbest bırakılmaz. Stop, condition wait'lerini uyandırır; bekleyen iş varsa iptal
  edilir, çalışan iş bitirilir, GPU kapanır ve renderer join edilir.
- `RuntimeApp.mm::append()` raporu NSLock altında senkron kaydeder; UIKit
  güncellemesi asenkrondur. Böylece main thread'in pause onayı beklerken
  worker loglarıyla kilitlenmesi önlenir. Scene will-deactivate pause ister;
  main thread en fazla **1 saniye** quiescence bekler. Timeout başarı sayılmaz.
  Background durumunda idle, geri dönüşte iş sayısının sabit kaldığı doğrulanır.
  UI'da Duraklat/Sürdür/Durdur düğmeleri bulunur.
- `AppleWorkPool.m` renderer batch/idle/shutdown işlemlerini ayrı
  `@autoreleasepool` içine alır. Native pthread'in UIKit run loop'u yoktur;
  geçici Metal/Foundation nesneleri iş başında/sonunda sınırlanır. Worker'ın
  rapor yazımı da çağrı başına pool kullanır; tüm oturumu beklemez.
- Son sıra: **GPU işi bitir → backend shutdown → renderer join → PPU dönüşü
  → outer PPU join → main thread'de layer detach**. Stop sonucu `STOPPED`,
  doğal bitiş `PASS`, doğrulama hatası `FAIL` olarak ayrılır. `STOPPED`, bütün
  istenen karelerin çizildiği anlamına gelmez.

## Anlamlı kontroller

Mac CTest **12/12 PASS**. Önceki seri test ayrı süreçte korunur; yeni gerçek
Metal testleri pause/resume ve pause sırasında stop'u sınar. Ek koordinatör
stres testinde 200 payload devri, 20 hızlı pause/resume, çalışan işte stop ve
100 startup/stop yarışı ve PPU park edilmeden flush/teardown yapılmaması kontrol edilir. Aynı test **ThreadSanitizer ile PASS**,
veri yarışı bildirimi yok.

Stres testi ilk sürümde hızlı resume→pause geçişinde idle onayının kaybolduğunu
buldu. İş kabulünün değişmesi GPU işi sayılmaz; idle durumu artık ancak gerçek
renderer işi başladığında geçersiz kılınır. Başlangıç onayı da kısa süreli
renderer-running flag'i yerine kalıcı thread-started flag'iyle beklenir.

Gerçek **iPhone 15 Pro / A17 Pro / iOS 27.2** üzerinde son imzalı sürüm:

| Senaryo | Sonuç |
| --- | --- |
| Otomatik pause/resume | **98 kontrol PASS**, 12/12 GPU karesi sunuldu; 300 ms pause boyunca iş sayısı sabit |
| Pause sırasında stop | **36 kontrol PASS**; 2 kare sonrası `STOPPED`, PPU ve renderer join, layer detach başarılı |
| Ayarlar'a geçiş ve aynı sürece dönüş | **1226 kontrol PASS**, 200/200 kare, 0 GPU hatası; background quiescent=1 |

Arka planda durulan iş sayısı **35**; dönüşte aynı kaldı, sonraki kareler devam
etti. Session satırı iki raporda aynıdır: yeni process boot'u resume sayılmadı.
Son koordinatör sayacı normal 200 karede **401 submitted / 401 completed**,
renderer_running=0, ppu_finished=1; outer pthread join ve layer detach 0.
Stop senaryosundaki 2 kare kısmi sonuçtur; 12 karenin tamamlandığı söylenmez.

Renderer istenen **16777216**, bildirilen **16789504** bayt stack; PPU
istenen **268435456**, bildirilen **268447744** bayt. Sanal rezervasyon fiziksel
kullanım değildir. Son fiziksel footprint örnekleri 12 karede **86,22 MiB**,
200 karede **84,02 MiB**; UIKit/log/Metal önbelleklerini de içerir. Bunlar oyun
belleği veya stack'in tamamına yazma testi değildir. SDL controller init hâlâ
başarılı; ses ve gerçek kontrolcü eşlemesi bu aşamada doğrulanmadı.

Son kaynaklar macOS, iPhoneOS ve Simulator SDK'sıyla derlenip bağlandı.
iPhone bundle imzası doğrulandı; AppKit, Homebrew veya TSAN dylib'i bağlanmıyor.
Her SDK'da 14 bağımlılık arşivi denetlendi: macOS **597**, IOS ve IOSSIMULATOR
**598** object doğru platformda. Simulator **çalıştırılmadı**. Bilinen dört
upstream draw-engine beklenti farkı önceki baseline karşılaştırmasında korunur.

Kanıtlar Git dışında `out/step7-device-{resume,stop,background,foreground,background-final}-report.txt`,
`step7-verification.json`, `step7-host-tests.log`, `step7-host-test-details.log`,
`step7-coordinator-tsan.log`, `step7-ios-final-sign.log`,
`step7-simulator-final-build.log` ve `step7-*-archives.json` dosyalarında.
`*-before-pools.txt` önceki ara denemenin raporudur; güncel sonuç sayılmaz.

## Tekrar üretme

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
tools/build_probe.sh host       # 12 test
tools/build_probe.sh ios        # iPhoneOS; 2 iş
tools/build_probe.sh simulator  # ayrı SDK; simülatörü açmaz
# İmzalama ve kurulum kök README'deki Infamous2FullRuntime komutlarıyla.
xcrun devicectl device process launch --device "$PROBE_DEVICE_ID" \
  --terminate-existing dev.infamous2.iosprobe -- --lifecycle-test
# Raporu aldıktan sonra yeni süreçte pause durumunda stop:
xcrun devicectl device process launch --device "$PROBE_DEVICE_ID" \
  --terminate-existing dev.infamous2.iosprobe -- --stop-paused-test
# Uzun tanı: çalışırken Ayarlar'a geç, sonra aynı sürece geri dön.
xcrun devicectl device process launch --device "$PROBE_DEVICE_ID" \
  --terminate-existing dev.infamous2.iosprobe -- --background-test
xcrun devicectl device process launch --device "$PROBE_DEVICE_ID" com.apple.Preferences
xcrun devicectl device process launch --device "$PROBE_DEVICE_ID" dev.infamous2.iosprobe
xcrun devicectl device copy from --device "$PROBE_DEVICE_ID" \
  --domain-type appDataContainer --domain-identifier dev.infamous2.iosprobe \
  --source Documents/threaded-runtime-report.txt --destination out/threaded-runtime-report.txt
```

Her senaryonun raporunu bir sonraki süreci başlatmadan önce farklı adla al.
`--serial` önceki 6 karelik testi çalıştırır ve `gcm-runtime-report.txt` yazar.
Varsayılan yeni mod 12 kare; background-test 200 kare; her karede tanı amaçlı
GPU readback ve 100 ms bekleme vardır. **Bunlardan oyun FPS'i çıkarılamaz.**
TSAN'ı yalnız hafif koordinatörde çalıştırmak için:

```sh
xcrun clang -fobjc-arc -fsanitize=thread -c src/platform/AppleWorkPool.m \
  -o build/host/apple-work-pool-tsan.o
xcrun clang++ -std=c++20 -O1 -g -fsanitize=thread -Isrc/full \
  src/full/RuntimeCoordinator.cpp src/host/coordinator_main.cpp \
  build/host/apple-work-pool-tsan.o -framework Foundation \
  -o build/host/runtime_coordinator_tsan
build/host/runtime_coordinator_tsan
```

## Açık sınırlar ve sonraki iş

Bu protokol sentetik PPU'nun belirlenmiş güvenli noktalarını kontrol eder;
keyfi oyun fonksiyonunu zorla durdurmaz. Gerçek SPU/SPURS/fiber işlerinin,
sesin ve dosya erişimlerinin pause/stop'a katılması henüz doğrulanmadı. Guest
VM/registry'ler korunur; aynı süreçte tam runtime teardown/restart henüz yoktur.
Her boot testi yeni uygulama sürecinde yapılır. Simulator yalnız derlenir;
önceki oturumdaki servis takılması nedeniyle bu aşamada açılmaz.

Son girdi kontrolünde NPUA80638/01.03 PARAM.SFO, çözülmüş EBOOT.elf, oyun
arşivleri ve liblv2/libsysmodule/libsre PRX seti hâlâ yok. Bir sonraki gerçek
oyun adımı bu girdileri doğrulamak, aynı pin ile macOS referans boot'unu
kurmak, title'ın üretilmiş PPU/SPU/LLE kodunu iOS hedefiyle birleştirmektir.
Oyun verileri iPhone'un yerel uygulama alanında bulunacak; Mac'ten yayın yok.
