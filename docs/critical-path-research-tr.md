# Anlamlı optimizasyon araştırması — devam ediyor

27 Ekim 2026. Amaç: büyük CPU yüzdesi bulmanın ötesinde, gerçek iPhone'da anlamlı kare süresi kazancı sağlayan bir müdahaleyi doğrulamak. **Amaç henüz tamamlanmadı.** GitHub çalışması kapsam dışında. Sonraki bölümlerde build44 cihaz hatası, build45 düzeltmesi ve doğrulama durumu ayrı kaydedilir.

## Doğrulanan girdiler ve REA

Orijinal BCES01229/01.00 EBOOT.elf: SHA256 `e7aa498258def0c7d651df92dcbb6feaf3230f4486b874170c074e7ca9238be6`, 10.159.776 byte, ELF64 big-endian `EM_PPC64` (21). Başlık kaydı: `out/critical-path43/original-elf.json`.

REA resmi npm sürümü 6.8.0, yalnız SSD'deki `build/analysis-tools/rea/` altına `--ignore-scripts` ile kuruldu; genel ajan yapılandırması değiştirilmedi. Bundled Node 24.22.1 kullanıldı. Gerçek ELF için şu komut yürütüldü:

```sh
PATH=/Users/bartuyilmaz/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH \
  build/analysis-tools/rea/node_modules/.bin/rea analyze \
  /Volumes/monssd/Infamous2-iOS/data/inspection/bces01229/selected/PS3_GAME/USRDIR/EBOOT.elf \
  --provider ghidra --format json
```

Sonuç `unsupported_target / unsupported ELF architecture / file_format_rejected`. Kanıt `out/critical-path43/rea-original-elf.json`. Kurulan sürümün `GhidraPowerPcProfile.js` kodu da yalnız ELF32 yolunu kabul ediyor. Bu, Ghidra'nın kendisinin PPC64 desteklemediği iddiası değildir; REA kabul sınırıdır. Bu girdinin REA ile decompile edildiği söylenemez.

Mevcut pinned PowerPC64 disassembler ve aynı ELF'ten üretilmiş C++ üzerinden doğrudan orijinal oyun kodu incelemesi sürdü. `0x00504DF0`, nesnenin işaret ettiği ilerleme satırındaki 16 bit lane değerlerinin minimumunu hedefle karşılaştırıyor. `0x0037062C` ise `0x005054F0` kontrolünü çağırıp syscall 141 ile 1 mikro-saniyelik uyku/kontrol döngüsüne giriyor. Bu kontrolleri silmek üreticiyi hızlandırmaz.

Orijinal byte'lardan ELF PT_LOAD adres eşlemesiyle çıkarılmış talimatlar: `guest-progress-check.ppc.txt`, `guest-progress-wait.ppc.txt`. Üretilmiş C++ karşılıkları `ppu_recomp_079.cpp:14695`, `ppu_recomp_033.cpp:10220` altında. Kaynakta semantik türetim, çalışma süresinin kanıtı değildir.

## Güncel gerçek cihaz zaman çizelgesi

Build 43, UUID `E23215F7-09F9-32A0-B980-E69D7AF6B452`; PID 6948. Metal aydınlatma/SSAO açık, geometri SPU/SPU, RSX yeni yol açık. `--diagnose-frame` ile aynı uygulama açıldı; kullanıcı ilk oynanış/sabit kamera teyidi verdi.

10 saniyelik kayıt: 86.296 olay, düşen olay 0, termal örnekler normal (0). UUID aynı binary ile kontrol edildi. 56 iç guest flip aralığında medyanlar:

| Ölçü | Medyan |
| --- | ---: |
| Guest flip istekleri arası | 167,78 ms |
| FIFO drain aralıkları birleşimi | 142,30 ms |
| Ölçülen GPU yürütmesi birleşimi | 52,37 ms |
| CPU'nun GPU'yu bekleme aralıkları birleşimi | 18,12 ms |
| Present çağrısı birleşimi | 7,38 ms |
| Readback birleşimi | 3,42 ms |
| RSX acquire beklemesi birleşimi | 0 ms |

**Satırlar örtüşür; toplanmaz veya medyanlar birbirinden çıkarılarak kesin CPU bütçesi kurulmaz.** Drain ölçümü FIFO kilidini bekleme ve backend/GPU beklemelerini de kapsar. Önceki ayrı CPU kaydı renderer'da yaklaşık 0,61 çekirdek eşdeğeri iş gösteriyordu; ayrı pencere olduğundan bu tablonun tam CPU bütçesi değildir.

GPU yürütme aralıklarının tüm pencereye oranı yaklaşık %31; donanım utilization sayacı değildir. 181 commit/yürütme, 61 flip isteği kaydedildi. Aydınlatma/SSAO acquire beklemesi bu kayıtta artık belirgin sınır değil. Seri renderer hazırlık/işleme yolu güçlü araştırma hedefi; hangi alt parçanın kaldırılmasının ne kadar FPS kazandıracağı ayrıca sınanmalı.

Ana PPU thread'i 10 saniyenin yaklaşık 4,07 saniyesinde syscall/uyku aralıklarındaydı. Sıcak noktalar `0x370694/3706BC/37110C/371138` gibi ilerleme kontrolleri. Bunlar başka işler ve renderer ile örtüşüyor. Bekleme süresini bütünüyle yeni optimizasyon kazancı saymıyoruz.

Kayıt ve analiz: `out/critical-path43/timeline-1/`. CLI `tools/capture_frame_trace.py`, tamamlanmayı/token/süreç kimliğini kontrol eder ve bitince kontrol dosyasını idle yapar. Profiler açık zaman çizelgesi, profiler kapalı FPS benchmark'ı değildir.

## Önce elenen dar deneme

Sık kullanılan SNORM16x3 vertex açma döngüsüne yerel NEON prototipi yazıldı. Her üç bileşende 65.536 değerin tamamı, sıralı ve permütasyonlu referanslarla özgün kodla byte düzeyinde eşleşti. ASan/UBSan denemesi geçti. FMA ile alternatif katsayı denemesi de aynı sınırlı değer testini geçti. Bu test, bütün vertex biçim/stride/frequency/default/bounds kombinasyonlarını kapsamaz.

M3 üzerinde, sentetik üç SNORM16x3 attribute'lu ve tekrar kullanılan girdilerde, ilk soğuk tur dışında çoğu ölçüm yaklaşık %8–15 yerel fark verdi. Gerçek cihaz veya uçtan uca kazanç değildir. Salt bu dar döngü için yeni iPhone sürümü kurulmadı; büyük FPS kazanımı beklemek için yeterli kanıt yok.

Prototipler `build/bces01229/vertex-prototype/`, çıktılar `out/critical-path43/vertex-*-host*.txt`. Hedeflenen oyun/runtime kaynakları değiştirilmedi.

## Sıradaki karar verdiren kayıt

Debugger üzerinden tanı sayacını açma girişimi canlı hedef belleği okumaya uygun bir attach kuramadı. Belleğe yazılmadı; ilk bellek okuması yerel dosya okuması olabileceği için tanı kanıtı sayılmadı. Sonraki girişim süreç durumunu kontrol etti; bu yol bırakıldı.

Aynı build mevcut `PS3RECOMP_ENG_DRAWSTATS=1` seçeneğiyle yeniden açıldı (PID 7017). Kullanıcı aynı ilk oynanış ve sabit kamera teyidi verdi. Gerçek vertex/attribute biçimleri, taşınan MB, fetch/remap/texture/pipeline aşama süreleri alınacak. Bu kayıttan veri dönüşümü/kopyalama, tekrarlı içerik doğrulaması veya komut hazırlığından hangisinin büyük ve kaldırılabilir payı olduğu seçilecek. Basit matematik hızlandırmasını bütün vertex yoluna eşitlemiyoruz.

Süreç seçimi/ham kayıtlar ve yeniden üretilebilir komutlar `out/critical-path43/` içinde korunuyor. Oyun/firmware ve büyük çıktılar Git dışı.

## Build 44: gerçek girdi byte'ları doğrulanan yeniden kullanım deneyi

İki opt-in yol hazırlandı; henüz cihaz FPS kazancı doğrulanmadı. `RendererMemo.c`,
anahtar ve bütün girdi byte'ları `memcmp` ile eşitse önceki saf işlev sonucunu
kullanır. Hash yalnız set seçer; hash/pointer eşitliği içerik kabulü değildir.
Yeni girdiler önce sahipli snapshot'a kopyalanır, özgün decoder/hash tam olarak
bu snapshot üzerinde çalışır; böylece önbellekteki girdi ve sonuç aynı veriye
aittir. Kaynak/yazıcı generation kapsamına dair varsayımla kontrol atlanmaz.
Girdinin bir byte'ı değişirse özgün hesap yeniden yapılır.

`VertexFetchMemo.c`: yalnız tamamı stabil mapping içinde olan referanslar kabul
edilir; normal/frequency/modulo/base-index ve default değerleri anahtardadır.
Interleaved aralıkların birleşimi bir kez tutulur. Eksik mapping/inline, geçersiz
attribute veya büyük girişler özgün yola gider. `bces_vertex_fetch_borrow` çıktı
sahipliğini değiştirmeden backend'in staging kopyasına immutable pointer verir;
sonraki vertex fetch'e kadar geçerlidir. `dc.verts`in realloc/free sahipliği
korundu. Metal backend staging kopyası tamamlanmadan yeni vertex batch başlamaz.
Texture memo ayrı depodur; aradaki texture işlemleri vertex çıktısını silemez.

`TextureHashMemo.c`: mevcut sekiz lane'li hash algoritması/değeri korunur.
Değişmemiş byte'larda daha önceki aynı hash döner; yeni hash algoritması veya
kirli sayfa/yazıcı kapsamı varsayımı getirilmedi. Fonksiyon kimliği de anahtardır.

Metadata dahil her depo 128 MiB ile sınırlı; LRU eviction/malloc başarısızlığında
referans yolu korunur. Cihazın fiziksel footprint'i ayrıca ölçülecek; depo byte
sayısı RSS ile eş tutulmayacak. Sınır toplam 256 MiB; gerçek tutulan miktar
sahne girdilerine bağlı. Shader/oyun asset'i veya firmware Git'e eklenmedi.

Mod 0 referans, 1 byte-validated reuse, 2 doğrulama. Mod 2 her çağrıda canlı
özgün sonucu üretip oyun için onu kullanır; aday çıktıyla karşılaştırır. Uyuşmazlık
aday yolu süreç boyunca kapatır. Normal başlatmada iki yol kapalı; geliştirme
komutları `--geometry-control --renderer-memo-control` ve süreç nonce'u ister.
A/B arası cache belleği tutulur, ancak her kullanım girdiyi yeniden doğrular.

ASan/UBSan altında 3.242 decoder karşılaştırması, mutasyon, guard page, alignment,
fonksiyon kimliği, bellek sınırı, LRU ve uyuşmazlıkta geri dönüş geçti. Yeni
renderer adaptasyonu SDK'nın mock backend testlerinde mod 0/1/2 ile çalıştırıldı;
her modda aynı dört bilinen fixture uyuşmazlığı kaldı, yeni hata/sanitizer uyarısı
yok. Doğrulama modunda 1.063 vertex ve 1.031 hash karşılaştırması uyuşmazlıksızdı.
Bu testler gerçek Metal görüntü eşdeğerliğinin yerine geçmez.

Sentetik M3 testinde (8.500 draw × 100 vertex, üç karışık attribute) ısınmış
referans yaklaşık 5,0–5,2 ms, borrowed memo yaklaşık 2,0 ms. 73,8 MB depo,
çoğu çağrıda içerik eşleşmesi. Bu, gerçek oyunun birebir girdi replay'i veya
iPhone FPS sonucu değildir; yalnız yerel fizibilite kapısıdır.

Build 44 iPhoneOS Release/jobs1 derlendi ve imzalandı, aynı bundle'a güncellendi.
UUID `895E0A43-035E-3541-ACD6-B801714607F3`; kayıt
`out/critical-path43/memo44-build-result.json`. Orijinal decoder tek tanım halinde
renamed referans olarak bağlı, normal API korunuyor. macOS hedefi değiştirilmedi.
Build 43 geri dönüş uygulaması `build/bces01229/baselines/renderer44-app/` altında.
Kaynak yedeği tümüyle build43 snapshot'ı değildir: bazı altyapı dosyaları deney
sırasında kopyalandı; uygulama yedeği build43 hash'iyle doğrulanabilir.

Cihaz sırası: aynı ilk sahne → mod2 doğruluk → mod0 referans → tek aday → mod0
kontrol → diğer aday → mod0 → gerekirse birleşik aday. Her pencere aynı termal
sınıfı, aynı log-capped durumunu, aktif shader/profiler olmamasını ve gerçek
sunum olaylarını kontrol eder. Kazanç aynı koşuldaki kontrol tekrarlarından
büyük ve tekrar edilebilir olmadıkça amaç tamamlanmış sayılmayacak.

```sh
python3 tools/test_renderer_memo.py
python3 tools/test_renderer_memo_engine.py
python3 tools/geometry_device_control.py --device 00008130-001129E00243001C --output out/memo-control-unique --vertex-memo 2 --texture-memo 2
python3 tools/measure_renderer_memo.py --device 00008130-001129E00243001C --modes 2 2 --correctness-only --seconds 15 --thermal-state 1 --output out/memo-validation-unique
```

Son komutlar örnektir; gerçek o anki termal sınıf ve yeni çıktı klasörleri seçilir.

## Cihaz görsel kapısı: build44 reddedildi

Kullanıcı ilk sinematiğin birkaç saniyesinden sonra dünyanın renkli şekillere
bozulduğunu, bozulmanın oynanışta sürdüğünü bildirdi. Rapor PID7249, iki memo
modu0, iki cache çağrı/hit/allocation sayısı0; Metal/lighting/SSAO hata sayaçları0.
Dolayısıyla cache hit çıktısı bu bozulmayı üretmiş olamaz; kapalı referans
entegrasyonu güvenilir değil. **Build44 için FPS karşılaştırması yapılmadı.**
Logda iki anlamsız texture descriptor bind hatası bulunuyor; önceki43 kayıtlarında
aynı hatalar görülmedi. Bu, tek başına kök nedeni tanımlamaz.

Çalışan runtime'ın compact nesnesi44'te SDK kaynağından yeniden derlenmişti.
Build45 bu değişikliği geri alır: `rsx_vertex_compact.o` doğrulanmış orijinal
runtime arşivinden byte olarak aynen korunur (SHA256
`a38a783205f6f0c037aae5eb694396dc481748265b924df09b14c1ac1bf2c746`).
Kapalı modda orijinal decoder ve `dc.verts` aktarımı doğrudan kullanılır;
texture hash'in özgün işlevi de kapalı mod için metin olarak aynen bırakılır.
Bu iki değişken birlikte geri alındığından düzeldiğinde bile tek başına kesin
kök neden ilan edilmeyecek. Önce cihazda temiz referans görüntü gereklidir.

Build43 kurtarma paketi aynı uygulamaya geri kuruldu; oyun dosyaları/kayıtlar
silinmedi. Reddedilen44 app'i `baselines/memo44-rejected/` içinde korundu.
Kontrol ve loglar `memo44-corruption-*`, geri dönüş `recovery43-install.json`,
nesne korunumu `memo45-reference-check.json` dosyalarında.

45 host testleri 3.244 decoder karşılaştırması ve renderer mod0/1/2 regresyon
kontrollerinde yeni hata göstermedi. Bu kez farklı yuvarlama modları cache'e
alınmaz. Host testinin geçmesi cihaz görsel kapısının yerine konulmayacak.

Yeni opt-in display capture, yalnız token'lı request dosyası olduğunda gerçek
oyun yüzeyini PPM'e okur; token/header/payload tamlığı hostta doğrulanır. FPS
pencerelerinde request gönderilmez. Böylece sonraki görsel incelemede cihazın
ürettiği kareyi doğrudan görmek mümkün olacak; simülatör çıktısı değildir.

Build45 iPhoneOS Release derlendi, imzası doğrulandı ve cihazdaki aynı bundle’a
kuruldu. UUID `BB5566B3-8B31-3B3E-BD10-A00609538BBD`, binary SHA256
`69f28ba792f8bbf69b0f775d90e5bb4799c85472570a823b325a150ef0d1729d`.
İlk launch iOS tarafından **Locked / FBSOpenApplicationErrorDomain7** ile
reddedildi. Dosya servisindeki önceki PID7249 raporu build44’e aittir; build45
çalışmış gibi değerlendirilmedi. İlk one-shot capture isteği bu nedenle
tamamlanmadı. Kullanıcıdan yalnız kilidi açık tutması istendi; yeni oynanış
turu/performans kaydı henüz başlatılmadı.

Telefon açıldıktan sonra build45 PID7392 olarak başlatıldı. İlk siyah karelerin
ardından çizgi roman (`45-current-world/frame.png`) ve iki ayrı sinematik
karesi (`45-cinematic-check/frame.png`, `45-after-validation/frame.png`) gerçek
iPhone yüzeyinden alındı. Karakter/şehir görüntüsü tutarlı; önceki renkli şekil
bozulması bu karelerde görülmüyor. Oynanış görsel kapısı henüz bekleniyor.

Sinematikte yalnız doğruluk denemesi yapıldı: mod2/2, 168.155 vertex ve 31.506
texture-hash karşılaştırması, iki türde de uyuşmazlık0. Vertex117.518hit,
texture30.991hit; bunlar çağrı sayılarıdır, tasarruf edilen iş miktarı değildir.
Tutulan depo yaklaşık128MiB vertex+52,5MiB texture; toplam fiziksel footprint
yaklaşık1,26GB. Sonunda iki memo modu0’a geri getirildi. Kayıt
`45-cinematic-validation/summary.json`. Bu tur bir FPS karşılaştırması değildir.

Capture isteği renderer tarafından hemen tüketilip silindiğinde CoreDevice
post-copy stat işlemi “file node missing” diyebiliyor. Host aracı bu hatayı
kaydeder, yalnız aynı benzersiz token ve tam piksel yükü taşıyan çıktı oluşursa
başarı kabul eder; hatayı doğrudan başarıya çevirmiyor.

Kullanıcı build45’te ilk oynanışın normal olduğunu ve karakter/kamerayı sabit
bıraktığını teyit etti. Cihaz yüzeyi de `45-gameplay-reference/frame.png` ile
görüldü. Bu, build44 regresyonunu gideren cihaz görsel kapısıdır; tek kök neden
izole edilmiş değildir. Aynı oynanışta ek649.494vertex+54.685hash doğrulaması
yapıldı, uyuşmazlık0; iki yol tekrar kapatıldı. Vertex reuse açıldığında
`45-vertex-visual/frame.png` de aynı konumda tutarlı görüntü üretti.

İlk kapalı referans32s/196gerçek sunum aralığı:6,1389FPS,162,895ms ortalama,
166,701ms medyan,200,041ms p95. Termal2(sıcak), düşük güç modu kapalı, yeni
shader/renderer hatası yok. Sonraki açık/kapalı kontrol pencereleri olmadan
bu sayıdan kazanç sonucu çıkarılmayacak.

## Build45 sonucuyla araştırmanın güncellenmesi

Aynı PID7392 ilk oynanışta görsel kapıyı geçti. Kontrollü A/B/A kayıtlarında
vertex+%0,517 ve texture−%0,481: anlamlı FPS kazanımı yok. İki aday kapalı
bırakıldı; amaç tamamlanmadı. Ayrıntılar, geçersiz log-geçiş turu ve gerçek
sunum sayıları `docs/memo45-device-results-tr.md` içinde.

Ek CPU ve aynı saatli trace incelemesi, vertex reuse açıkken decoder işinin
azaldığı fakat ana PPU'nun drain dışında yaptığı kısa beklemelerin medyanının
0’dan9,938ms’ye çıktığını gösterdi. Bu, başka üretici bağımlılığını araştırmak
için somut bir işaret; henüz hangi SPU işinin sonlandığı kanıtı değildir.
Sonraki odak0x370694/0x3706BC üzerinden sorgulanan iş kuyruğunda gerçek
geciken lane/yazıcı ilişkisi. Bir başka genel önbellek veya Metal taşıması
seçilmeden bu bağlantı kurulacak.

`tools/analyze_progress_overlap.py` aynı-kare aralık kesişimlerini tekrar
hesaplar; üç anlamlı aralık/boundary testi geçti. Binary değiştirilmedi.
Son cihaz raporu `45-final-device-report.json`: iki memo kapalı, uyuşmazlık0,
Metal hata0, profiler/trace tamamlanmış; süreç açık.
