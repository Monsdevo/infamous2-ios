# Geometri yollarını ve ölçümü düzeltme — build 42

27 Ekim 2026. Build41'in GPU sonucu başarılı bir hızlandırma değildi.
Skinning yaklaşık129 dispatch/çağrı ve tüm SPU grafiğini taşıyordu;
culling seri GPU yürütülüyordu. CPU yolunda da her çağrı tüm256KiB local-store
kopyasını içeriyordu. İki Metal yolunun kötü sonucu GPU potansiyeli hakkında
kesin hüküm vermez. Özgün SPU referansı zaten ARM64'e statik derlenmiş koddur.

## Yapılan değişiklikler

- `src/platform/GeometryExecution.h`, `tools/prepare_geometry_kernels.py`:
  ARM64 normal yürütmesi canlı, thread'e özel LS üzerinde çalışır. İlk yazılan
  16-byte quad undo günlüğüne alınır. Desteklenmeyen dal/interrupt/stop
  durumunda yazılar geri alınır, özgün fonksiyon çalışır. GPR/PC yalnız başarılı
  çağrı sonunda güncellenir. Tam LS kopyası yalnız doğruluk denemesinde kalır.
- `tools/geometry_batches.py`, `src/platform/GeometryBatch.h`:
  bağımsız skinning döngüleri D800/D5B0/DA28/DCE0/DF20/7030 ve culling
  A650 transform/clip aşaması GPU adayı. AAF8 sıralı pack/scan CPU'da kalır;
  bu bütün culling'in GPU'ya taşındığı anlamına gelmez.
  CPU adres planlayıcı önce read-after-write bağımsızlığını kanıtlar.
- `src/platform/GeometryMetalBatches.mm`:
  her uygun döngü için tek paralel dispatch; tüm128-register GPU kontrol akışı
  yerine çıktıya gerekli işlemler. Son iterasyonun GPR/ABI durumu CPU'da,
  GPU işiyle örtüşerek hesaplanır. Girişte yalnız gerekli4KiB sayfalar ve küçük
  seed/prefix durumu aktarılır. GPU canlı LS'ye yazmaz; adresleri ve hash'i
  denetlenen sıralı çıktılar journal üzerinden uygulanır.
  Worker başına kaynak/queue, en fazla iki GPU işi; kapasite dolunca bekleyen
  genel mutex yerine CPU yolu. GPU komutunun kendi sonucu yine beklenir.
- `src/platform/GeometryRZ64.h`, `GeometryMathProbe.c`:
  SPU sayı davranışı için exact64-bit yardımcılar. Güvenli normal aralıkta
  GPU float işlemi+yuvarlama düzeltmesi; özel sayılarda integer fallback.
  Metal Safe+Precise derleme. Her cihaz açılışında4096 giriş/24.576 sonuç ve
  RNE tie kontrolü; geçmezse integer-only shader yeniden hazırlanır.
- `src/platform/GeometryKernels.mm`:
  PC ve iş boyutu başına üç tam çıktı karşılaştırması ve maliyet ön denemesi.
  GPU toplam planlama/aktarım/submit/bekleme/commit maliyeti CPU hesabının
  %85'inden küçük değilse aday reddedilir. Bu muhafazakâr bir kabul eşiğidir;
  ilk kullanım/çakışma maliyeti küçük bir kazancı gizleyebilir. Kalibrasyon
  FPS örneği değildir. Yeni girdide bağımlılık varsa CPU'ya dönülür.
  İlk8 çağrı zorunlu karşılaştırılır; isteğe bağlı sürekli karşılaştırma var.
  Uyumsuzlukta özgün çıktı korunur ve ilgili yol süreç boyunca durdurulur.
- `src/platform/GameTelemetry.*`, `src/ios/GamePerformance.mm`:
  sunum sayacı ve son sunum zamanı aynı kilit altında alınır. Bounded8192
  gerçek sunum olayı; FPS/median/p95 bu olayların farkından hesaplanır.
  `total_ns` tüm çağrı, reference/fallback ve commit'i içerir.
  Ayrıntılı CPU bölümleri1/64 örneklenir. Eşzamanlı thread/GPU süreleri
  toplanıp kare kazancı gibi sunulmaz. Gerçek GPU batch, kalibrasyon,
  CPU-only ve reddetme sebepleri ayrı sayaçlardır.
- `src/platform/GeometryControl.*`, `src/ios/GameApp.mm`:
  yalnız `--geometry-control` geliştirme açılışında oturuma özel nonce/token
  komutları. Her böyle açılış SPU/SPU başlar; eski dosya yeni süreci etkilemez.
  Hazır profiller korundu; Metal+CPU hibrit kapsamı panelde açıklanır.
- `src/platform/SkinningCapture.c`:
  SPU/SPU'dan iki türde en fazla64 stratified gerçek giriş/çıkış yakalaması.
  Yalnız saf GPR/PC/image/host-depth ve LS kopyalanır; asenkron host durumu
  kopyalanmaz. Dosyalar özel oyun türevi tanı verisidir; `out/` ve cihaz
  Documents dışında dağıtılmaz. Oyun/firmware kaynakları Git'e eklenmez.

## Yerel doğrulama

- `out/geometry42-transaction-test.log`:8 türetilmiş golden fixture;
  GPR/PC/tüm LS ve undo/unsupported geri alma geçti.
- `out/geometry42-rz64-test.log`:12milyon bağımsız CPU oracle kontrolü.
- `out/geometry42-gpu-arithmetic-test.log`:12.582.912 exact GPU kontrolü.
- `out/geometry42-gpu-native-math-test.log`:12.582.912 guarded nativefloat
  ve cancellation/özel sayı sonucu bağımsız128-bit oracle ile aynı.
- `out/geometry42-concurrent-batch-test.log`:73 batch /8 tüm fonksiyon
  çıktısı; A650 dahil PC-mask0x6d, declined0. ASan/UBSan temiz. Bilinçli
  alias reddi geçti. Dört worker testi15 gerçek GPU işi/17 nonblocking busy
  dönüşüyle doğru. D5B0/DF20 mevcut fixture'larda çalışmadı; canlı veri kapsamı
  ayrıca denetlenmeli. Bu test Mac GPU'sundadır; iPhone performansı değildir.
- `out/geometry42-release-batch-test.log`: aynı8 fixture ve4-worker kontrolü
  Release Mac binary ile de geçti; sanitizer olmayan host süreleri ayrıca kayıtlı.
- `out/geometry42-final-runtime-test.log`: üretim adaptörü, bütün çiftler,
  sürekli doğrulama açık/kapalı, shared-LS fallback ve enjekte edilmiş
  uyuşmazlıkta özgün çıktı/route block kontrolleri.
- Telemetri eşzamanlılık/ring-wrap ASan/UBSan, komut ayrıştırıcı ve ham kare
  istatistik/bozulmuş pencere reddi testleri geçti.
- `out/geometry42-build-final.log`: Release iphoneos **BUILD SUCCEEDED**;
  jobs1, TMPDIR SSD. İmza sistem güven deposuyla doğrulandı. Test hata enjeksiyonu
  sembolü üretim binary'sinde yok. Build42 mevcut kimliğe güncellendi;
  `out/geometry42-install.log`. Oyun dosyaları yeniden aktarılmadı.

## Cihaz ölçüm sırası ve tekrar üretim

Cihaz `00008130-001129E00243001C`, bundle `dev.infamous2.iosprobe`.
Her ilk oynanış/aynı kamera kullanıcı tarafından doğrulanır. Metal lighting/SSAO
iki tarafta açık; LPM kapalı, foreground, panel kapalı, termal0.

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
export TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp
python3 tools/prepare_bces_ios.py --support-report out/bces-support-compile-iphoneos-spu-O2-copy.json
xcodebuild -project build/bces01229/ios/Infamous2BCESIOS.xcodeproj -scheme Infamous2Game -configuration Release -destination 'generic/platform=iOS' -jobs 1 -derivedDataPath build/bces01229/DerivedData DEVELOPMENT_TEAM=BJ266NGN3H
xcrun devicectl device process launch --device 00008130-001129E00243001C --terminate-existing dev.infamous2.iosprobe --boot --geometry-control
```

1. SPU/SPU'da capture aç, kısa sabit sahne ardından kapat ve pending0 bekle.
   GPU'yu ayrıca prepare et. `geometry_device_control.py --help` alanları açıklar.
2. `fetch_geometry_captures.py --device … --output out/benzersiz-klasor`
   yalnız geçerli süreç dosyalarını indirir. `batch-check-asan --allow-unsupported
   out/…/*.bin` CPU/Metal çıktısını device goldeni ile denetler; unsupported
   grafikte rollback doğrulanır, bu durum hesaplamanın doğrulandığı sayılmaz.
3. `qualify_geometry.py --device … --pair 1 1 --output out/benzersiz-klasor`
   ve2/2,1/2,2/1: doğrulama açık. Hata, gerçek GPU kapsamı ve gate maliyetleri
   ayrı raporlanır. CPU'ya ayrılan profil GPU performans başarısı değildir.
4. Doğrulamayı kapat; kalibrasyon/compilation durmuş, yeterli ısınma kareleri
   geçmiş olsun. `measure_geometry.py --device … --pair 1 1 --scene first-gameplay
   --output out/benzersiz-klasor` en az120 gerçek kare aralığı/30s toplar.
   Termal artış, LPM, yeni shader, capture, config/process değişimi veya
   karşılaştırma/failure artışı pencereyi geçersiz kılar. Route2'de sıfır gerçek
   GPU batch varsa Metal FPS sonucu olarak kabul etmez.
5. SPU dönüş kontrolü ve uygulama yeniden açılmış ikinci tur. Adaylar sırayla
   ters çevrilir. Yeniden açılışta aynı sahne tekrar doğrulanır.

## Bu oturumun cihaz durumu

Build42 kuruldu ve PID3408 ile `--boot --geometry-control` açıldı.
`out/geometry42-ready-report.json`: Metalstate2/stage20, native_math1;
cihazın24.576 aritmetik sonucu/RNE kontrolü geçti. Renderer/lighting/SSAO
hataları0; SPU/SPU, captureOFF/pending0, aktif uygulama. Rapor termal1
(ılık) gösterdiğinden performans penceresi başlatılmadı. Kullanıcıya ilk
oynanış/sabit kamera teyidi soruldu; henüz yanıt alınmadı. Gerçek çağrı
fixture yakalama ve dört kombinasyonun cihaz doğrulaması/FPS tekrarları
bekliyor. Yerel testlerin geçmesi gerçek oynanış eşdeğerliğini kanıtlamaz.

Yeni cihaz doğrulama/FPS karşılaştırması henüz tamamlanmadı. Build41'in
`docs/geometry-device-measurement-tr.md` sonuçları eski prototipe aittir.
Pinned toolkit/runtime ve çalışan macOS karşılaştırma hedefi değiştirilmedi.

## Güncel devam noktası

İlk gerçek cihaz doğrulaması ve altı normal termal profil penceresi tamamlandı.
Yeniden açılmış süreçte ikinci tur henüz başlamadı. Kullanıcı telefonu şu an
soğutamayacağı için yeni ölçüm başlatılmadı. Sonuçlar ve kalan komutlar:
[build42 ilk tur](geometry42-results-tr.md). Önceki “bekliyor” durumunun yerini bu kayıt alır.
