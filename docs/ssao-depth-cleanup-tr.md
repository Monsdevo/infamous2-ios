# SSAO derinlik geçişi sınırı — build 33, 26 Ekim 2026

## Sorun ve değişiklik

İkinci teşhiste Metal SSAO açıkken özgün AO modülü CPU'da yaklaşık %3,13
exclusive CPU payı gösterdi. Korunan derinlik yolu `ssao_skip_step` içinden
özgün `5258` işlevini çağırıyordu; bu işlev pass E tamamlandıktan sonra da
`5328 → 4A50` ile sonraki AO tile'larını sahiplenebiliyordu.

`tools/prepare_metal_ssao.py:depth_reference_source` doğrulanmış BCES SPU
kaynağından ayrı `ssao_spu_reference.c` üretir. Yalnız `4AAC` atomic claim
akışına, GETLLAR snapshot'ı okunduktan ve PUTLLC yapılmadan önce bir sınır
kontrolü eklenir. GPU yolunun derinlik çağrısı aktifse ve snapshot'taki pass
1..4 ise claim yapılmaz; özgün `4BF0` devamı 0xFFFE döndürür. Böylece özgün
IRQ/stack epilogue'u ve dış GPU döngüsünün retry protokolü kullanılır.

Kontrol konumu önemlidir: başka SPU pass'i GETLLAR sonrasında ilerletirse eski
PUTLLC başarısız olur; yeniden GETLLAR'dan okunan yeni pass sınırda durdurulur.
Claim öncesinde sıradan bir guest-memory okuması aynı yarışa dayanmazdı.
Pass0 derinlik ve 0xFFFF terminal davranışı değiştirilmez. Derinlik datamod'u,
DMA output, completion `46D0`, label136/137 ve shader'lar değiştirilmedi.

`src/platform/SSAODepthBoundary.c` scope'u host thread/context/state EA ile
bağlar. Yalnız GPU yolunun synchronous özgün derinlik çağrısı bu scope'a girer;
tam özgün SPU fallback scope dışında kalır. Nested scope geri yüklenir. Yeni
SSAO girişinde eski scope temizlenir; halt/longjmp sonrası fallback'e sızmaz.

Pinned kaynak/arşivler değişmez. Doğrulanmış support arşivinin build kopyasından
özgün SSAO object çıkarılır; türetilmiş source O2 ve aynı SPU dispatch tanımıyla
ayrı derlenir. Lighting overlay ve macOS hedefi korunur. Build32 app geri dönüş
kopyası `build/bces01229/baselines/step24-ssao-build32/Infamous2Game.app` altında.

## Karşılaştırma ve göstergeler

Normal açılışta temizlik açık. `--ssao-depth-boundary-off` eski davranışı seçer.
Yalnız `--diagnose-ssao-depth` ile configure edilen UI kontrolü
Documents/ssao-depth-control.txt içinde `off TOKEN` / `on TOKEN` komutlarını
bir kez uygular. Aynı token tekrarlanmaz. Anahtar gelecekteki claim'leri etkiler;
önceden alınmış iş normal tamamlanır, completion iptal edilmez. Geçişten sonra
birkaç saniye beklenip raporda mode doğrulanır, sonra FPS penceresi başlatılır.
Normal kullanımda bu dosya okunmaz. İlk pakette ürün paneline yeni ayar eklenmedi.

Rapor alanları: `ssao_depth_cleanup_enabled`, `ssao_depth_original_calls`,
`ssao_depth_boundary_blocks`. Host FPS aracı pencere içinde mode değişirse
kaydı reddeder. CPU örnekleri/FPS/zaman izi ayrı pencerelerde tutulur.

SSAO depth label136 (0x880), mevcut 0x870/0x890 filtreli DMA yazı izine eklendi;
yalnız kısa trace aktifken provenance kaydı alınır. Normal frame akışına GPU
beklemesi veya readback eklenmedi.

## Tamamlanan doğrulama

- Production lifted GETLLAR/PUTLLC akışıyla **416 durum**, ASan/UBSan PASS.
  Pass0 success/barrier ve terminal için kapalı yolun tam context/bellek
  eşitliği; pass1..4'te claim yapılmaması; tam fallback eşitliği; 16 farklı
  state-line offset'i ve iki IRQ durumu; deterministik reservation kaybı yarışı.
- TLS/thread isolation, nested scope, state binding, stale scope reset ve
  tanı komutunun token/replay kontrolü geçti.
- Bu harness'te başarılı claim sonrasındaki descriptor hazırlığı stub'dır;
  atomik claim ve özgün epilogue gerçek lifted koddur. Bu **tam oyun job'u veya
  görüntü eşdeğerliği testi değildir**. Gerçek half-depth bitmap/whole-job
  karşılaştırması bu testten çıkarsanmaz; cihaz davranışı ayrıca kontrol edilir.
- Üç-label tam-word/big-endian/provenance/flush testi PASS; iki mevcut dependency
  analiz testi PASS; Python py_compile PASS.
- iPhoneOS Release -jobs1 BUILD SUCCEEDED. Build33 UUID
  **4D38A65C-6575-364A-9439-6409EFCD0907**, strict imza kontrolü geçti.
  Final binary'de claim ve guard tek tanım; derived support içinde eski SSAO
  object yok. Kurulum tamamlandı, oyun dosyaları tekrar aktarılmadı.

## Cihaz denemesi

İlk açılış yalnız karşılaştırma için temizlik kapalı, iki Metal yolu açık.
CPU/GPU iz ve CPU örnekleyicisi hazır ama kayıt, kullanıcı ilk oynanış/kamera
teyidi verene kadar başlamaz. Aynı süreç/sahne içinde temizlik açılarak A/B
alınır; ardından CPU AO kalıntısı ve label136/137 değer/sırası kontrol edilir.

Önceki aralıklı sinematik donması ayrı açık kararlılık sorunudur; bu dar claim
sınırı düzeltmesinin onu çözdüğü iddia edilmez. Görsel kalite değiştirilmedi.
Kazanç, cihaz karşılaştırması olmadan ilan edilmez.

## Kanıt ve komutlar

`out/ssao-cleanup33-*` test/derleme/kurulum/binary kayıtları; oyun/firmware ve
büyük üretilmiş çıktılar Git dışında.

```sh
python3 tools/test_ssao_depth_boundary.py
python3 tools/prepare_bces_ios.py --support-report out/bces-support-compile-iphoneos-spu-O2-copy.json
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer /opt/homebrew/bin/cmake -S cmake/bces-ios -B build/bces01229/ios
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp xcodebuild -project build/bces01229/ios/Infamous2BCESIOS.xcodeproj -scheme Infamous2Game -configuration Release -destination id=00008130-001129E00243001C -jobs 1 DEVELOPMENT_TEAM=BJ266NGN3H -allowProvisioningUpdates
python3 -m unittest discover -s tools -p test_frame_dependencies.py
```

## Gerçek cihaz sonucu — aynı süreç, ılık koşul

Kullanıcı ilk oynanışta sabit karakter/kamera teyidi verdi, ancak telefonu
normal termal seviyeye indiremediğini bildirdi. Bu nedenle normal sıcaklık
benchmark'ı yapılmadı; iki kısa sayaç penceresi fair=1 koşulunda, serious=2
olursa duracak şekilde alındı. Eski normal sıcaklık sonuçlarıyla kıyaslanmaz.

Aynı PID 14877 / aynı kamera, sampler kapalı:

| | Temizlik kapalı | Temizlik açık |
|---|---:|---:|
| Süre | 21,999963 s | 20,999587 s |
| Guest frame | 130 | 129 |
| FPS | 5,909101 | 6,142978 |
| Thermal state | bütün örnekler 1 | bütün örnekler 1 |
| Yeni pipeline | 0 | 0 |
| SSAO fallback / fault | 0 / 0 | 0 / 0 |
| SSAO skipped tile / GPU pass | 232,123 | **245,000** |
| Yeni sınırda durdurulan claim | 0 | 432 |

Dört GPU aşamasının 64+45+40+96=245 tile'ının tamamı açık yolda atlandı.
Kapalı yolda bir kısmı özgün CPU hesabına kaçıyordu. Bu, yeni sınırın gerçek
oyun akışında çalıştığını doğruluyor. Kısa tek off/on çifti **gözlemsel +%3,96**
FPS ve sayaç ortalamasında 6,443 ms/kare fark verdi. Isı sınıfı aynı olsa da
fiziksel sıcaklık/frekans ve sahne zamanlaması birebir aynı değil. Bu küçük
farkı tekrarlanabilir FPS kazancı olarak kabul etmek için normal sıcaklıkta
tekrarlı/dengeli A/B gerekir; bu oturumda böyle bir iddia yapılmıyor.

### CPU ve label doğrulaması

FPS pencereleri dışında 15,014818 s CPU kaydı: 6970 satır, 662 tick,
errors=0, truncated=0, token cleanup33cpuon15 ve build33 UUID eşleşti.
Özgün **AO modülü datamod_00821080 örneklerde görülmedi**; korunan depth
modülü datamod_0081ed00 gözlendi. Önceki profilin farklı koşullardaki CPU
paylarıyla yüzde farkı hesaplanmadı. Sonuç, test edilen GPU yolundaki ek AO
hesabının kalktığını destekler; desteklenmeyen özgün fallback'lerde AO
çalışmaması gerektiği anlamına gelmez.

Ayrı 10 s label izi: 58 label136 ve 58 label137 yazısı; 58 ortak değerin
hepsinde tek yazı ve **depth tamamlanması → AO tamamlanması** sırası doğru,
eşleşmeyen değer yok. Tam half-depth bitmap veya tüm ekran buffer eşdeğerliği
bu kayıttan çıkarsanmaz. Önceki aralıklı sinematik donması ayrı açık konudur;
bu build'in o problemi çözdüğü iddia edilmedi.

Son rapor: PID14877, cleanup=1, CPU/trace completed=3, Metal/light/SSAO
hataları 0, thermal1. Kayıt komutları idle yapıldı; uygulama aynı süreçte,
**temizlik açık** bırakıldı. Usage kesintisi sırasında dosyalar tamamlanmıştı;
kontrol sonrası yeni ölçüm gerektiren eksik kayıt bulunmadı.

Birleşik sonuç `out/ssao-cleanup33-result.json`; CPU analizi,
label-check, off/on-window, install/build/test dosyaları aynı prefix altında.
