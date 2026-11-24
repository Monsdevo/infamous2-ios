# Optimizasyon Aşaması 1 — Metal aydınlatma ve SSAO

25 Ekim 2026. Güncel durum: **build 27 deneysel Metal pilotu ölçüldü; doğruluk ve termal A/B kabul kapıları henüz geçilmedi, SSAO kapalı**.
[Cihaz testleri ve sonraki doğrulama işi](optimization-phase1-device-tests-tr.md).
Aşağıdaki iş paketleri başlangıç planını ve kabul ölçütlerini korur.
[İlk paket](optimization-phase1-experiment1-tr.md).

Kullanıcının istediği yeni numaralandırma:

- **Deneme 1: yalnız aydınlatmayı Metal'e taşıma.**
- **Deneme 2: kabul edilen aydınlatma yolunun üzerine SSAO'yu Metal'e taşıma.**

Önceki denemeler bu serinin deneme sayısına katılmıyor. Mevcut kaynak/kararlılık
çözümleri ve teşhis kanıtları korunuyor; geçmiş notlar silinmiyor. 20/21. adım
numaraları geliştirme günlüğünün geçmişidir, bu serinin optimizasyon numarası değildir.
Bu plan uygulamayı, açık oyun sürecini veya ayarlarını değiştirmez.

## 1. Amaç ve dayanak

Oyunla aynı ışık/SSAO sonucunu daha az CPU işi ve daha kısa gerçek kare süresiyle
üretmek. Efekt kapatma, kalite/örnek sayısı düşürme veya çözünürlük değiştirme bu
denemenin yöntemi değil. Ekran oranı/FOV ayrıca ele alınacak.

Gerçek iPhone 15 Pro / BCES01229 01.00 teşhisi:

| Gösterge | Gözlem | Yorum sınırı |
| --- | --- | --- |
| Kare aralığı | yaklaşık 266 ms, 3,8 FPS | Önceki sıcak cihaz sahnesi; yeni A/B baz kaydı yerine geçmez |
| RSX acquire / kare | yaklaşık 135–137 ms | Bekleme, tek job'un CPU çalışma süresi değil |
| 0x870 | aydınlatma c6e7...5A40 yazıyor | Native çağrı zinciri/değer/zaman ile eşleşti |
| 0x890 | tiled SSAO e6fe...49C8 yazıyor | Aynı şekilde eşleşti |
| Yazıdan sonra RSX kontrolü | birkaç ms | 135 ms'yi tek başına açıklamıyor |
| Ortak 10 s CPU ancestry | light %22,61; SSAO %22,10 | Sampled CPU maliyeti; FPS yüzdesi/job wall-time değil |
| Kapsanan GPU işi | yaklaşık 36 ms/kare | Donanım utilization ölçümü değil; offload bunu artırabilir |

Hipotez: bu iki işin piksel/tile hesaplarını Metal'e taşıyıp gereksiz SPU
çalışmasını azaltmak, renderer'ın veri beklemesini azaltabilir. Deneme 1 yalnız
aydınlatma hipotezini sınar. 5–6 FPS önceki konuşmadaki koşullu bir senaryodur;
kabul eşiği veya vaat edilen sonuç değildir. Sıfır/negatif kazanç da geçerli sonuçtur.

## 2. Kaynaktan doğrulanan başlangıç noktaları

| Dosya/fonksiyon | Kullanım |
| --- | --- |
| src/ios/GameApp.mm:startGame | Şu an LIGHT/SSAO env değerlerini boşaltarak GPU yollarını kapatıyor |
| profiles/BCES01229-01.00.json:spu_hooks | Light image 221, tile 0x4AC8, walk 0x4578; SSAO image 225, walk 0x4330 |
| tools/prepare_bces_ios.py | Pinned GPU hook kaynaklarını BCES image id'leriyle build altında türetiyor |
| infamous2-lle/gpu_light.c:light_tap_constants, light_tile_gpu, light_skip_4578, infamous2_gpu_light_install | Aynı light constants; tile/iş yürütme değiştirme başlangıcı |
| infamous2-lle/gpu_ssao.c:ssao_tap_frame, ssao_skip_4330, infamous2_gpu_ssao_install | SSAO pass constants ve iş yürütme başlangıcı |
| ps3recomp-fork/libs/video/rsx_draw_engine.c:eng_gpu_light_blit | Normal/derinlik snapshot'ları ve CPU writeback kararı |
| Aynı dosya:rsx_draw_engine_gpu_light_data, eng_gpu_light_texture | Parametre aktarımı ve composite'e GPU sonucu bağlama |
| Aynı dosya:rsx_draw_engine_gpu_ssao_data, eng_gpu_ssao_texture | SSAO parametreleri/çıktısı |
| rsx_metal_backend.m:eng_light_pass, eng_light_fs | Metal aydınlatma ve diffuse/specular çıktıları |
| Aynı dosya:eng_ssao_pass | Beş SSAO pass'inin Metal karşılığı |
| src/platform/FrameTrace.cpp, tools/analyze_frame_dependencies.py | Label üretici ve GPU/CPU bağımlılığı doğrulaması |

Önemli sınırlamalar:

1. Pinned upstream image id'leri light 219 / SSAO 226; BCES'te 221 / 225. Hash ve
   işlev adresi kontrolü olmadan hook kurulmayacak; çalışma anındaki image=100
   kaydı gerçek iş kodunun SPURS bağlamında çalışabildiğini gösteriyor.
2. Upstream env örneklerindeki buffer adresleri BCES için ölçülmüş sayılmayacak.
   Guest EA, RSX IO offset ve local VRAM offset birbirine karıştırılmayacak.
3. `PS3RECOMP_ENG_GPU_LIGHT_SPU=1` SPU işini korur, fakat composite yine GPU
   sonucunu kullanır. Tek başına gerçek gölge doğrulaması değildir.
4. Normal/derinlik kopyalarını SSAO CPU'da okur. Aydınlatma tek başına taşınırken
   ikisinin de guest writeback/readback'i korunacak; NOWB kullanılmayacak.
   Kaynak notlarında stale normals ile yakın dövüş sonrası takılma bildirilmiş.
5. SSAO env'i açılınca upstream kod writeback'i otomatik atlayabiliyor. İlk birleşik
   deneyde bu atlama da ayrıca kontrol altında tutulacak; diğer CPU okuyucularının
   kalmadığı gösterilmeden otomatik olarak kabul edilmeyecek.
6. `have_params`, `in_seq/out_seq`, paylaşılan parametre ring'i ve texture ömrü
   aynı kareyle ilişkilendirilmeli. Önceki karenin matrisi/ışık listesi yeni
   normal/derinlik görüntüsüyle eşleşmemeli. Sekiz ring slotunun yeterliliği gerçek
   in-flight kullanımına göre doğrulanacak; rastgele yeni GPU wait eklenmeyecek.
7. `rsx_draw_engine.c` şu an runtime arşivinden bağlanıyor. Build altında duran
   overlay C dosyasını değiştirmek tek başına uygulamayı değiştirmez. Bu dosyada
   düzenleme gerekirse `rsx_draw_engine.o` türetilmiş arşivden çıkarılıp iOS overlay
   birimi aynı seçeneklerle derlenecek; tek tanım ve gerçek link/dependency kontrolü
   yapılacak. Özgün doğrulanmış runtime arşivi korunacak.
8. Mevcut env seçimleri ve fonksiyon değişimleri başlangıçta cache'leniyor.
   İlk sürümde mod değişimi yeniden başlatmada uygulanacak. Çalışan SPU'ların
   fonksiyonlarını menüden anlık değiştirme planlanmıyor.

## 3. Deneme 1'in iş paketleri ve geçiş kapıları

### 1A — Baz sürüm ve deney modları

- Build 25 binary/UUID, profil/pin/derleme seçenekleri ve oyun verisi kimliği
  kaydedilecek. O anki süreç belleğini kaydetmek veya başka binary'ye aktarmak
  mümkün varsayılmayacak. Aynı bundle update'i Documents verilerini koruyacak.
- Aynı deney binary'sinde başlangıçta seçilen üç mod tasarlanacak: **SPU referansı**,
  **doğrulama** (GPU yan çıktı üretir, ekranda SPU sonucu), **Metal aydınlatma**.
  Bunlar henüz var olan CLI/ayarlar değildir. Varsayılan SPU olacak.
- Bütün modlarda aynı O2 destek arşivi, memory/stack düzeltmeleri, renderer,
  native copy-off, çözünürlük, FOV ve diğer ayarlar kullanılacak.
- Hook/parametre/format hatası SPU hesabı atlanmadan önce yakalanırsa referans
  yolu korunacak. SPU işi zaten atlanmışken hata çıkarsa eski/boş texture'ı
  başarı sayan sahte fallback yapılmayacak; deney başarısız raporlanıp güvenli
  SPU başlangıç moduna dönülecek. Aynı kareyi tekrar SPU'da yürütme, ancak ayrıca
  doğrulanırsa kullanılabilir; otomatik var sayılmıyor.
- GPU PSO/kaynak hazır olması, doğru hook adresi ve desteklenen girdi koşulları
  atlama açılmadan doğrulanacak. Aydınlatmanın gerçek shader yolu çalışması ayrı
  sayaçla gösterilecek; yalnız label'ın daha erken gelmesi başarı değil.

**Çıktı:** varsayılanı aynı davranan deney binary'si, kayıtlı baz kimliği,
mod/etkin hook/readiness sayaçları ve gerçek sunulan karelerin zaman kaydı.

### 1B — BCES/iPhone referans girdilerini yakalama

- GPU yolu kapalıyken normal/derinlik girdileri, boyut/pitch/format, light matrix,
  ışık listesi, ölçek, ilgili buffer eşlemeleri ve SPU diffuse/specular çıktısı
  sınırlı sayıda karede alınacak. Girdi ve çıktı aynı frame/label generation
  ile etiketlenecek. Girdi capture'ı SPU aynı buffer'ı değiştirmeden yapılacak.
- Copy/command-buffer sırası ve immutable capture kaynakları kullanılacak;
  bütün guest thread'lerini güvenilir biçimde pause edebildiğimiz varsayılmayacak.
- Başlangıç için 3–5 sınırlı fixture: ilk sabit sahne, farklı ışık koşulu,
  yansımalı/ışık sınırı olan yüzey. Zero light, uzak depth, tile sınırları,
  farklı ışık türleri ve desteklenen ışık sayısı sınırı ayrıca anlamlı sentetik
  girdilerle sınanacak. Desteklenmeyen sayıyı sessizce kırpmak kabul edilmeyecek.
- Varsa mevcut kayıt/Devam et kullanılacak; yoksa yeni oyun üzerinden aynı
  konum ve kamera tarif edilecek. Yeni kayıt/checkpoint desteği kapsamı büyütmek
  için eklenmeyecek; bunu eksiksiz ölçüm tekrarlanabilirliği diye sunmayacağız.
- Texture/readback senkronizasyonunun capture maliyeti FPS ölçümüne katılmayacak.
  Çıktı Git dışında monssd'de; telefonda sınırlı tanı klasörü, ilk hedef üst sınır
  200 MB. Gerçek boyut manifestte kontrol edilecek; oyun verileri taşınmayacak.

**Kapı:** bir fixture'da girdi/parametre/SPU çıktısı aynı kareye bağlanamıyorsa
shader doğruluğu hakkında karar verilmeyecek.

### 1C — Aynı girdide Metal/SPU çıktı karşılaştırması

- Eksik scratchpad harness'inin repoda bulunduğu varsayılmayacak. Gerekli küçük
  replay aracı yakalanmış fixture'ları kullanacak; tüm oyun boot'u gerekmeden
  hatalar incelenebilecek. iPhone GPU sonucu gerçek A17 Pro üzerinde doğrulanacak.
  Mac replay teşhise yardımcı; cihaz doğrulamasının yerine geçmez.
- `eng_light_fs` aynı girdi ve parametrelerle çalıştırılacak; önce ara
  diffuse/specular buffer'ları, sonra composite sonucu karşılaştırılacak.
- Kanal sırası, 24 bit depth çözümü, matris/piksel koordinatları, half/big-endian
  parametreler, normal normalize, gloss/specular, clamp/sqrt/quantization kontrol
  edilecek. Özellikle sıfır uzunluklar ve sınır değerler incelenecek.
- Hedef bit eşitliği. Sayısal fark varsa kanal başına max/ortalama hata,
  değişen piksel oranı, histogram ve fark görüntüsü üretilecek. Açıklanamayan
  fark geçmez; “%99 benziyor” otomatik kabul değildir. Yuvarlamadan kaynaklanan
  kaçınılmaz bir tolerans gerekiyorsa kapsamı/görsel etkisi açıkça raporlanıp
  kalite kararına dönüştürülecek; sessiz kalite kaybı olmayacak.
- Integer label/değer/sıra ve scheduler state'inde tolerans yok.
- Ekranda SPU sonucunu koruyan doğrulama modunda aynı karenin GPU yan çıktısı
  alınacak. Mevcut SPU=1 bayrağını bu modun yerine kullanmayacağız.

**Kapı:** fixture eşlemesi + açıklanmış sayısal sonuç + kareler arasında
flicker/ghosting/stale veri bulunmaması. Bu adımın yavaş olması sorun değil;
ikisini birden çalıştıran moddan FPS kazancı beklenmeyecek.

### 1D — Yalnız aydınlatmanın SPU işini azaltma

- SSAO özgün SPU yolunda kalacak. Önce doğrulanmış Metal aydınlatma sonucu
  composite'e bağlanacak; ardından eşdeğer GPU işinin varlığına bağlı olarak
  SPU tile piksel hesabı ve gereksiz tile yürütme/DMA yolu kaldırılacak.
- `light_skip_4578` referans tile iterator/claim/completion/yield davranışıyla
  karşılaştırılacak. Light constants aktarımı, son label135 değeri/adedi,
  WWS dönüşü ve PPU tamamlanma işaretleri korunacak. 5A40'a erken return veya
  sahte label yazımı yapılmayacak.
- Label hazır işaretinin CPU'da görünmesiyle GPU'nun fiziksel bitişi aynı şey
  değil: snapshot → light pass → composite GPU komut sırası doğru kurulacak.
  CPU'ya her kare yeni waitUntilCompleted ekleyerek doğruluk sağlanmış sayılmayacak.
- Normal ve depth guest kopyaları SSAO için korunacak. Kamera hareketi, yakın
  dövüş/efekt ve bölüm geçişinde CPU okuyucularının doğru veriyi gördüğü sınanacak.
- GPU iş süresi, hook hits/tap/pass/composite sayıları, input/output generation
  ve label protokolü kaydedilecek; callback kuruldu diye etkin optimizasyon
  iddiası yapılmayacak.

**Kapı:** gerçek oyun görüntüsü + işin Metal'de çalıştığının kanıtı + atlanan SPU
çalışmasının kanıtı + state/label doğruluğu. Ardından FPS karşılaştırması yapılacak.

### 1E — Performans, kararlılık ve kabul

A = SPU referansı. B = Metal aydınlatma, SPU SSAO. Aynı binary, farklı başlangıç modu.

1. Aynı kamera/konum/çözünürlük, güç bağlantısı, düşük güç modu ve ekran ayarı.
   Pipeline sayısı sabit ve boot shader derleme dalgası bitmiş olacak. Normal/fair
   thermal tercih; yalnız serious durumda test mümkünse sonuç ayrı bir sıcak
   cihaz testi diye raporlanacak. Critical=3 olursa performans testi duracak.
2. İlk pilot A/B'de 30 s'lik gerçek game-frame/present zamanları alınacak. HUD'ın
   basamaklı 3,5/4 FPS değerlerinin medyanı temel performans metriği olmayacak.
   Ortalama FPS gerçek kare/zaman ile; medyan ve p95 raw kare aralıklarından.
3. Heavy trace, CPU profiler ve GPU readback/diff kapalı; hafif sayaçlar iki modda
   aynı. Neden analizi için ayrıca kısa 10 s trace alınacak; benchmark'a karıştırılmayacak.
4. Doğru çalışan ve potansiyel kazanç gösteren pilot tekrar edilecek: en az üç
   A/B çifti, sıra A/B ve B/A dengelenecek. Her launch intro gerektirebilir;
   anlık toggle veya yeniden başlatmasız A/B vaat edilmiyor. Aynı bazın baş/son
   medyanı %5'ten çok kayarsa veya thermal/power/scene eşleşmezse o karşılaştırma
   geçersiz/inconclusive sayılıp koşullar düzeltilmeden tekrarlanmayacak.
5. Birincil kabul hedefi **eşleşen çiftlerde tekrar eden en az %10 medyan kare
   süresi azalması**; örneğin 266→239 ms veya daha iyi. Bu mühendislik eşiği,
   beklenen kazanç değil. p95'te %5'ten fazla kötüleşme, düzenli yeni takılma,
   görüntü veya protokol bozulması varsa genel başarı denmeyecek. Küçük/dağınık
   kazanç varsayılanı değiştirmek için yeterli sayılmayacak.
6. Başarılı adayda 5–10 dk hareket/kamera/efekt testi; menü–sinematik–oynanış,
   ses ve controller kontrolü; memory/Metal error/warning ve kaynak büyümesi.
   Süreli kararlılık denemesi, uzun dönem kararlılık garantisi değildir. Isınmış
   sürdürülebilir performans ayrı raporlanacak; soğuk FPS ile birleştirilmeyecek.

**Sonuç seçenekleri:** kabul / görüntü-state hatası nedeniyle ret / yavaşlama
nedeniyle ret / ölçüm koşulları nedeniyle belirsiz. Kazanç yoksa önce GPU-pass,
readback/encode ve kalan bağımlılık incelenecek; ikinci rastgele ayar eklenmeyecek.
Her koşuda UUID, mod, sahne, oyun profili, ayarlar, thermal/power, süre, kare adedi,
FPS, medyan/p95, CPU, bütün kapsanan GPU işleri, label wait ve bellek kaydedilecek.

## 4. Deneme 2 — SSAO, Deneme 1 sonucundan sonra

- Deneme 1 kabul edilmeden birleşik optimizasyon denenmeyecek; başarısız Deneme 1
  üzerine SSAO ekleyerek hatanın kaynağı karıştırılmayacak.
- B (yalnız Metal aydınlatma) yeni SSAO bazıdır. C = Metal aydınlatma + Metal SSAO.
  C/B SSAO'nun ek kazancı; C/A toplam kazançtır. Karşılaştırmalar ayrı raporlanacak.
- BCES pass descriptor'ları ve datamod eşlemeleri kaynak NPUA adreslerinden
  kopyalanmadan gerçek girdilerden çıkarılacak. Beş pass ayrı doğrulanacak:
  linear depth/downsample → SSAO → yatay blur → dikey blur → bilateral upsample.
- Her ara buffer ve final AO aynı SPU fixture'ıyla karşılaştırılacak. Sadece
  son ekran görüntüsüne bakıp hangi pass'in farklı olduğunu gizlemeyeceğiz.
- `ssao_skip_4330`, tile claim/completion/barrier/yield ve label136/137 değer-sıra
  davranışını korumalı. GPU üzerinde pass sırası ve composite tüketimi doğrulanmalı.
  Sample sayısı, kernel, çözünürlük ve efekt şiddeti bu deneyde düşürülmeyecek.
- İlk C doğrulamasında guest writeback'ler korunacak. İki GPU yolu çalıştıktan sonra
  kalan SPU/PPU okuyucuları incelenecek; ancak gereksizliği kanıtlanan kopyalar
  ayrı C alt karşılaştırmasında kaldırılacak. Upstream'in SSAO env'ine bağlı
  otomatik skip'i bu aşamalı kontrolü atlamak için kullanılmayacak.
- Deneme 1'le aynı doğruluk, %10 ek medyan hedefi, p95, thermal ve kararlılık
  kuralları B/C için uygulanacak. Ek kazanç küçükse birleşik yol varsayılan olmaz.
- Sonunda yeni CPU/GPU/label profili alınarak kalan darboğaz çıkarılacak.
  Eski CPU yüzdelerinin optimizasyondan sonra aynı kalacağı varsayılmayacak.

## 5. Kaynak sınırları ve geri dönüş

- Pinned fork/commit/yamalar ve macOS karşılaştırma hedefi korunacak. Gereken
  değişiklikler kontrol edilen iOS overlay ve port adaptörlerinde; lock hash'leri
  değişiklik gerekçesiyle güncellenecek. Genel runtime güncellenmeyecek.
- CPU statik yeniden derlenmiş kalacak. Metal shader derlemesi CPU JIT değildir.
  Mevcut iOS bağımlılıkları ve bellek entitlement'ları bu deneyde değişmeyecek.
- Derleme `-jobs 1`; build/temp/capture monssd'de. Telefona oyun verisi yeniden
  gönderilmeyecek. Capture, oyun/firmware ve büyük üretilmiş çıktılar Git dışında.
- Mevcut üç noktalı panele deney modunun görünmesi eklenebilir; menü kapsamı
  büyütülmeyecek. Başlangıç modu/uygulanan mod açık olacak. Genel kullanıcıya
  doğrulanmamış bir seçeneği sessiz varsayılan yapmayacağız.
- Geri dönüş SPU referans başlangıç modu ve saklanan imzalanabilir baz kaynak/
  binary üzerinden; aynı bundle ile Documents korunacak. Yeni profil gerekirse
  yeniden imzalama olağan kurulum işidir, oyun verisinin silinmesi değildir.
- Her alt iş sonunda kısa durum ve devam komutu kaydedilecek. Uzun tek turn'de
  doğruluk, cihaz testi ve A/B'yi bitirme zorunluluğu varsayılmayacak.

## 6. İlk uygulama oturumunun somut kapsamı

**Deneme 1 / ilk iş paketi: baz modu güvenceye almak, BCES buffer/parametre
capture'ını hazırlamak ve aynı girdinin SPU çıktısını kaydetmek.** Sonraki paket
Metal replay/gölge karşılaştırması. Bunlar geçmeden SPU piksel/tile işi atlanmayacak.

Bu plan turunda hiçbir uygulama kodu/ayar değiştirilmedi, build veya cihaz testi
başlatılmadı. Yukarıdaki kabul ölçütleri önerilen çalışma sözleşmesidir; sonuç
olarak elde edilmiş test veya desteklenen yeni komut gibi sunulmaz.
