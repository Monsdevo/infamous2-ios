# Optimizasyonun yeniden değerlendirilmesi

27 Ekim 2026 — mevcut kayıtların ve kaynak kodunun derin incelemesi.
Kapsam: BCES01229 iOS build42; karşılaştırma kayıtları ilk oynanış sahnesinden.

**Sonuç:** Edge, skinning ve culling pahalı CPU işleriydi. Bunların kareyi en çok
geciktiren işler olduğu kanıtlanmamıştı. Buna rağmen uygulama önceliğini ve FPS
beklentisini bu yönde kurduk. Bu, önceliklendirme hatasıydı. Şimdi en güçlü yön,
tek thread üzerinde ilerleyen **renderer komut/veri hazırlama zinciri** ve onun
tamamlanmasını etkileyen runtime maliyetleridir. Yeni bir küçük skinning/culling
Metal varyasyonu ilk önerim değil.

Bu rapor için iPhone'a bağlanılmadı, oyun açılmadı, yeni profil/benchmark
alınmadı, uygulama kodu/ayarları değiştirilmedi. Kaydedilmiş CPU örnekleri UUID'si
eşleşen eski binary ile yeniden sembolleştirildi; mevcut zaman izleri ve build42
sonuçları çevrimdışı analiz edildi. Yeni çıktılar yalnız `out/optimization-audit-20261027/`
altındadır. Bu klasör Git dışındadır.

## 1. Edge seçimini hangi kanıt destekliyordu?

İkinci teşhiste yaklaşık toplam CPU dağılımı SPU %75,3, renderer %12,3,
PPU %11,0 idi. Edge modülü tek başına doğrudan CPU payının %16,14'ünü
oluşturuyordu. Sonraki kayıtta %15,74 bulundu: gerçekten büyük ve belirli bir
iş kümesiydi.

Fakat skinning için %43,48, culling için %19,38 değerlerinin paydası **örneklenen
Edge job'larının CPU süresiydi**. Bunlar ekran karesinin %43 ve %19'u değildi.
Bu oranlar driver işlevinin %90,97'sine de eklenemez; driver diğerlerini içeriyor.

Üç farklı ölçütü ayırmamız gerekiyor:

| Ölçüt | Anlamı | FPS hakkında söyleyebildiği |
|---|---|---|
| Toplam CPU payı | Birçok thread'in tükettiği CPU zamanındaki pay | Pahalı işi gösterir; son kareyi kimin geciktirdiğini tek başına göstermez |
| Toplanmış çağrı duvar süresi | Her çağrının giriş/çıkış arası geçen süresinin toplamı | Paralel çağrılar ve scheduler beklemesi içerir; kareden doğrudan çıkarılamaz |
| Nedensel kritik yol | Karesi yetişmeyen tüketicinin gerçekten beklediği üretim/tamamlama zinciri | Bu zinciri kısaltmak doğrudan kare süresini azaltabilir |

Edge için ilk iki konuda kanıt topladık. **Edge job-chain kimliğini PPU'nun
beklediği son üreticiyle bağlama işi tamamlanmadı.** Eski notlarda bu açıkça
yazılıydı; bunu kararımızda yeterince belirleyici yapmadık.

Üstelik iki eski izde Edge job duvar aralıklarının birleşimi kare başına
medyanda 48,85 / 43,44 ms; GPU çalışmasıyla kesişimi 30,63 / 25,00 ms idi.
İşin önemli bölümü başka işlerle aynı anda yapılıyordu. Bu medyanları çıkarıp
"geriye kesin şu kadar ms kaldı" diyemeyiz, ama bunlar büyük CPU tasarrufunun
aynı büyüklükte FPS kazancı olmayabileceğine güçlü uyarıydı.

Kaynak: [ikinci teşhis](</Volumes/monssd/Infamous2-iOS/docs/diagnosis2-tr.md:103>),
[Edge paydaları](</Volumes/monssd/Infamous2-iOS/docs/edge-flow-diagnosis-tr.md:137>),
[örtüşme](</Volumes/monssd/Infamous2-iOS/docs/edge-flow-diagnosis-tr.md:170>),
[tamamlanmamış kritik-yol bağlantısı](</Volumes/monssd/Infamous2-iOS/docs/edge-flow-diagnosis-tr.md:217>).

## 2. Build42'de ne değişti, ne değişmedi?

Gerçek sunum olaylarından hesaplanan sonuçlar:

| Yol | FPS | Ortalama kare aralığı | Skinning çağrı duvar toplamı / kare | Culling çağrı duvar toplamı / kare |
|---|---:|---:|---:|---:|
| SPU/SPU — önce | 6,079 | 164,50 ms | 104,78 ms | 45,83 ms |
| ARM64/ARM64 | 6,258 | 159,80 ms | 37,88 ms | 21,64 ms |
| SPU/SPU — sonra | 6,456 | 154,88 ms | 93,16 ms | 40,53 ms |

ARM64 yolunda skinning+culling için toplanan çağrı duvar süreleri ilk referansa
göre yaklaşık %60,5 azaldı. Bu yerel bir hızlanma belirtisi; **90 ms seri kare
tasarrufu veya %60 daha az CPU enerjisi ölçmüş olmadık**. Bu sayaç
`steady_clock` kullanıyor; CPU'dan düşürülme/bekleme de kapsama giriyor.

Kare aralığı ARM64 turunda yalnız 4,69 ms azaldı. Son SPU referansı ise ilkinden
9,61 ms hızlı çıktı. İki SPU kontrolünün süre/kare sayıları birleştirildiğinde
tanımlayıcı referans 6,271 FPS; ARM64 6,258 FPS. Bu bir drift modeli değil;
yalnız mevcut farkın referans değişkenliğinin içinde kaldığını gösteriyor.
**Tekrarlanabilir bir FPS kazancı kanıtımız yok.**

Buna iki açıklama uyuyor: hızlandırılan işlerin çoğu kritik yol dışında
örtüşüyordu; geometri rahatlayınca başka seri aşama sınır oldu. Mevcut kayıtlar
ikisinin kesin payını ayıramıyor. Son build42 için yeni CPU zaman çizelgesi
bulunmadığından bunu kesin bir güncel darboğaz dağılımı gibi sunamam.

Bir başka önemli ayrıntı: build42 performans pencerelerinde **kabul edilmiş
geometri GPU batch sayısı sıfırdı**. Metal profilleri maliyet kontrolünden sonra
CPU'da yürüdü. Dolayısıyla dört hazır profil, dört gerçek ARM64/GPU performans
kombinasyonu üretmedi. Aynı süreçte bu kabul kararları korunurken profilleri yeniden ölçmek, gerçek
GPU karşılaştırması üretmeyecek.

Kaynak: [ham ilk tur](</Volumes/monssd/Infamous2-iOS/out/geometry42-sweep1-normal/summary.json>),
[zamanlayıcının tanımı](</Volumes/monssd/Infamous2-iOS/src/platform/GeometryKernels.mm:33>),
[çevrimdışı karşılaştırma](</Volumes/monssd/Infamous2-iOS/out/optimization-audit-20261027/geometry-comparison.json>).

## 3. Aydınlatma ve SSAO neden daha iyi sonuç verdi?

Orada yalnız sıcak CPU işlevi bulunmamıştı. RSX'in beklediği label değeri,
onu gerçekten yazan DMA ve o yazıyı hazırlayan job zinciri eşleşmişti:

- `0x870` → aydınlatma job'unun `5A40` tamamlaması.
- `0x890` → tiled SSAO job'unun `49C8` tamamlaması.

Yani çizim tüketicisi gerçekten bu sonuçları bekliyordu. Önemli iş GPU yoluna
alındığında o bağımlılık erken tamamlandı. Pilotlarda aydınlatma yaklaşık
3,97→4,97 FPS; SSAO 4,84→6,16 FPS verdi. SSAO karşılaştırmasında ortalama kare
206,45→162,30 ms, yaklaşık 44,14 ms değişti. Bunlar da sınırlı sahne/ardışık pilot
sonuçlarıdır; bütün oyun için garanti değildir. Fakat etkileri küçük referans
kaymasından belirgin büyüktü ve belirli bir beklemenin üreticisiyle ilişkiliydi.

Edge için aynı nedensellik düzeyine ulaşmadan daha fazla uygulama yaptık.

Kaynak: [gerçek label yazıcıları](</Volumes/monssd/Infamous2-iOS/docs/step21-label-dependency-tr.md:101>),
[aydınlatma karşılaştırması](</Volumes/monssd/Infamous2-iOS/docs/optimization-phase1-device-tests-tr.md:165>),
[SSAO karşılaştırması](</Volumes/monssd/Infamous2-iOS/docs/ssao-device-measurement-tr.md:66>).

## 4. "SPU yerine ARM64/Metal" açıklamasını düzeltelim

Uygulamadaki SPU referansı zaten statik olarak ARM64 makine koduna derleniyor.
Pinned runtime, integer/shuffle ve floating-point işlemleri için ARM NEON
yollarına da sahip. Bu, iPhone'da PS3 işlemcisinin fiziksel olarak çalıştırılması
veya bütün hesabın yavaş bir yorumlayıcıda yapılması demek değil.

Örneğin mevcut float yardımcıları uygun durumlarda iki `f64x2` NEON yarısı,
SPU yuvarlama düzeltmeleri ve gerekli lane'lerde exact fallback kullanıyor.
Yeni özel RZ yolu belirli saf bölgelerde bunu `4×f32` donanım hesabı ve kontrollü
fallback ile değiştiriyor. "ARM64" anahtarı özel alternatif uygulamayı seçiyor;
özgün yolun ARM64 olmadığı anlamına gelmiyor.

Statik yeniden derleme ISA çözümleme yükünü azaltır; PS3'ün register dosyası,
local-store/DMA, endian ve job senkronizasyon sözleşmeleri ise hâlâ kodda
yaşar. Bu nedenle sonuç, kaynak kodundan iOS'a göre yeniden tasarlanmış bir
oyun motorunun veri düzeniyle aynı değildir. Büyük kazanç, bu sınırların bir
bölümünü doğru sonuç korunarak kaldırmayı gerektirebilir.

Metal de işi otomatik olarak daha hızlı yapmaz. CPU'nun onlarca mikrosaniyede
bitirdiği bir döngü için GPU komutu oluşturmak, göndermek, beklemek ve sonucu
yeniden CPU sözleşmesine koymak daha pahalı olabilir. Üstelik SPU sayısal
davranışını koruyan shader, sıradan tek bir float FMA kadar ucuz değil.

Kaynak: [mevcut NEON float yardımcıları](</Volumes/monssd/Infamous2-iOS/upstream/infamous2-recomp/ps3recomp-fork/runtime/spu/spu_helpers.h:620>),
[özel RZ matematiği](</Volumes/monssd/Infamous2-iOS/src/game/BCESSpuRZ.h:42>),
[GPU yuvarlama yardımcıları](</Volumes/monssd/Infamous2-iOS/src/platform/GeometryRZ64.h:84>).

## 5. Küçük Metal batch'lerinin kaybetmesinin mevcut kanıtı

Telefondaki kayıtlı kalibrasyon sayaçlarından:

| Kalibrasyon toplamı | Skinning: 18 batch | Culling: 9 batch |
|---|---:|---:|
| Giriş kopyası | 0,160 ms | 0,100 ms |
| Gönderim | 1,399 ms | 0,835 ms |
| GPU'nun gerçek yürütmesi | 3,642 ms | 3,389 ms |
| CPU'nun GPU sonucunu beklemesi | 17,623 ms | 16,084 ms |
| Çıktı kopyası/kontrolü | 0,198 ms | 0,099 ms |

Bekleme GPU yürütmesini de içerir; sütunlar toplanmaz. Batch başına giriş
kopyası yaklaşık 9–11 µs, CPU beklemesi yaklaşık 0,98–1,79 ms. Karşılaştırılan
CPU döngüleri boyuta göre yaklaşık 6–120 µs. Sorun yalnız bellek kopyası değil;
**gönderim/bekleme sınırı ve çok küçük iş birimi** önemli.

Yeni backend hâlâ her uygun döngü için ayrı command buffer/encoder oluşturuyor,
commit ediyor, CPU tail durumunu hesaplıyor, `waitUntilCompleted` sonrası
çıktıyı kontrol ederek LS'ye uyguluyor. Birleşik bellek bu senkronizasyonu
ortadan kaldırmıyor. Culling'in sıralı paketleme kısmı CPU'da kaldığından GPU
sonucunun CPU'ya geri gelmesi de mevcut sözleşmenin parçası.

Maliyet kabul testi hakkında da sınır var: yalnız üç örnek, ilk kullanımın
tembel kaynak kurulumunu içerebilmesi, kalibrasyonun ılık koşulda yapılması,
CPU kontrolünün önceden kopyalanmış sıcak LS üzerinde undo-backup olmadan
çalışması. Bu **koruyucu bir kabul testi**; kapsamlı steady-state GPU throughput
benchmark'ı değil. Güncel küçük offload'ları açmamak için yeterli kanıtımız var;
"skinning GPU'da hiçbir zaman kazanamaz" sonucu için yok.

Gerçek büyük GPU dönüşümü, çok sayıda job'u birlikte göndermek,
skinning→culling→vertex çıktısını mümkün olduğunca GPU'da tutmak ve doğrudan
çizime bağlamak olurdu. Bu, birkaç matematik fonksiyonunu çevirmekten büyük
bir veri akışı/ABI projesi. Şu an ilk pratik adım olarak önermiyorum.

Kaynak: [batch yürütme/gönderim/bekleme](</Volumes/monssd/Infamous2-iOS/src/platform/GeometryMetalBatches.mm:64>),
[kabul testi](</Volumes/monssd/Infamous2-iOS/src/platform/GeometryKernels.mm:52>),
[kalibrasyon yeniden analizi](</Volumes/monssd/Infamous2-iOS/out/optimization-audit-20261027/geometry-comparison.json>).

## 6. Yeni önemli bulgu: seri renderer önceki yüzde tablosunda gizlenmiş

Kaydedilmiş build32 CPU örnekleri yeniden çözüldü. Renderer thread'i 30,01
saniyelik kayıtta **17,49 thread CPU-saniyesi** tüketmiş. Yaklaşık bir çekirdeğin
%58'i. Edge38 kaydında aynı rol 15 saniyede 9,29 CPU-saniyesi, yaklaşık %62.

Renderer'ın toplam CPU payı %12–14 çünkü payda birçok thread'in yaklaşık
4,5–4,7 çekirdek eşdeğeri işi. İşin kendisi büyük ölçüde tek `frame_clock`
thread'inde seri ilerliyor. Buna karşılık SPU işleri altı worker'a dağılıyor.

Bu ölçüyü ayrı bir ~6 FPS penceresine kabaca bölersek renderer için kare başına
95–100 CPU ms mertebesi çıkar. **Bu ölçülmüş kesin kritik-yol bütçesi değil**;
CPU profili ile FPS penceresi aynı zaman aralığı değil. Fakat araştırma
önceliğini değiştirmek için güçlü kanıt: toplam CPU yüzdesi küçük görünen seri
renderer, Edge'in daha büyük toplam yüzdesinden daha önemli olabilir.

Renderer thread'inin kendi CPU dağılımı:

| İş | Renderer CPU'sundaki yaklaşık pay |
|---|---:|
| Sistem/çözülemeyen leaf | %23,28 |
| `rsx_vertex_fetch_all` | %19,57 |
| `eng_texture_content_hash` | %10,20 |
| `rsx_process_method` | %10,02 |
| `rsx_dispatch_method` | %5,38 |
| `rsx_vertex_remap_build_range` | %4,64 |
| `cellGcm_rsx_process_fifo` | %4,45 |
| `sink_end` | %4,27 |

Vertex fetch/remap/index/topoloji hazırlığı birlikte yaklaşık **%27,27 renderer
CPU'su**. Sistem leaf'lerinin yardımcı ancestry'sinde Metal encode/commit ve
readback yolları görülüyor; bu %23'ü tümüyle bir oyun işlevine atayamayız.

Eski GPU izinden yeniden çıkarılan diğer somut bulgular:

- 57 iç karede medyan **8.540 backend record/kare**.
- Her karede üç submission.
- CPU encode duvar aralıklarının kare içi birleşimi medyan **13,32 ms**.
- GPU commit→start medyan yaklaşık **0,81 ms**.

Record sayısı draw-call sayısı değildir; clear/copy/lighting/SSAO gibi kayıtları
da içerir. Yine de büyük bir seri komut/veri hazırlama yükü bulunduğunu gösterir.

Kaynak: [renderer CPU yeniden analizi](</Volumes/monssd/Infamous2-iOS/out/optimization-audit-20261027/renderer-cpu-breakdown.json>),
[renderer zaman izi yeniden analizi](</Volumes/monssd/Infamous2-iOS/out/optimization-audit-20261027/renderer-trace-breakdown.json>).

## 7. Öncelik 1 — gereksiz ikinci RSX durum işleme yolunu ayırmak

Kaynakta doğrudan görülen bir tekrar var:

1. FIFO komutu aktif `rsx_draw_engine_method` yoluna gidiyor.
2. Aynı standart 3D komut `rsx_process_method(&s_state, ...)` ile eski durum
   modeline de gönderiliyor.
3. Aktif Metal dispatch yolu eski render backend vtable'ını bağlamıyor.
4. Bu yerel `s_state`in başka okuyucusu bulunmuyor.

**Oyun iki kez çizilmiyor.** Tekrar, eski 3D durumunun çözülüp yazılması.
Eski işlemcinin kendisi renderer CPU'sunun yaklaşık %10,02'si; dolayısıyla
kaynakta bulunan tekrar, gerçek CPU örnekleriyle de destekleniyor.

Önerilen dar müdahale: dispatch engine aktif **ve eski backend yokken** eski
yoldan yalnız zorunlu yan etkileri yürütmek. Legacy backend/debug yolu korunur.
Semaphore release, byte-swap, reference fence, report, user command, flip ve
gerekli milestone davranışları aynen kalır. `rsx_process_method` çağrısını
koşulsuz silmek yanlış olur.

Bu adayın avantajı: yeni GPU ABI'si veya oyunun algoritmasını çözmek gerekmiyor;
seri yol üzerinde ölçülmüş bir tekrar var. Eski işlemcinin bütün %10'u ücretsiz
olmayacak ve bu **%10 FPS vaadi değildir**. Fakat kapsam/kanıt oranı yeni küçük
skinning shader'ından daha iyi. Sonraki ilk uygulama deneyi olarak bunu seçiyorum.

Kaynak: [aktif engine'e gönderim](</Volumes/monssd/Infamous2-iOS/build/bces01229/ios-prepared/diagnostic_cellGcmSys.c:2149>),
[eski modele ikinci gönderim](</Volumes/monssd/Infamous2-iOS/build/bces01229/ios-prepared/diagnostic_cellGcmSys.c:2173>),
[Metal backend seçimi](</Volumes/monssd/Infamous2-iOS/build/bces01229/ios-prepared/renderer-overlay/libs/video/rsx_metal_backend.m:5025>),
[korunacak semaphore yan etkileri](</Volumes/monssd/Infamous2-iOS/upstream/infamous2-recomp/ps3recomp-fork/libs/video/rsx_commands.c:356>).

## 8. Öncelik 2 — seri vertex hazırlama ve tekrar kopyalama zinciri

Bugünkü yol kabaca şöyle:

`Edge çıktısı / guest vertex → CPU index/remap → CPU endian/format açma → dc.verts → Metal staging kopyası → GPU`

Skinning'i hızlandırmak, bundan sonraki seri vertex hazırlığını kaldırmıyor.
`rsx_vertex_fetch_all` attribute/vertex başına veriyi açıyor; `eng_draw` oluşmuş
vertex/index dizisini staging'e tekrar kopyalıyor. Metal descriptor'ı bütün
attribute'ları `Float4` olarak beklediğinden daha kompakt guest biçimleri önce
CPU'da genişletiliyor.

Dar ilk hedef: ardışık/dense `float3` gibi doğrulanmış biçimlerde toplu
byte-swap/pack; mümkün olan durumlarda doğrudan nihai staging alanına üretim.
Böylece yalnız talimatı hızlandırmak yerine ikinci geçiş/kopya azaltılır.
Endianness, default lane, stride, remap, instancing/frequency ve primitive-restart
kuralları aynen korunmalıdır. Bazı vertex tüketicileri CPU'da olabilir;
staging'e doğrudan yazma bütün durumlara körlemesine uygulanmamalıdır.

Daha büyük kazanç yönü: packed vertex binding / vertex pulling veya renderer
batch'inde GPU decode. Bu, eski API/Float4 sözleşmesi ve guest tamponlarının
ömrünü değiştirdiğinden daha yüksek kapsamlıdır. Pointer bazlı cache güvenli
değildir; aynı adrese Edge DMA/PPU/RSX tekrar yazabilir.

Kaynak zaten format-özel döngü, dense remap ve bazı state/constant optimizasyonları
içeriyor. Bunları yeni öneri gibi tekrar saymıyorum. Hedef, kalan veri zinciridir.

Kaynak: [CPU vertex açma](</Volumes/monssd/Infamous2-iOS/upstream/infamous2-recomp/ps3recomp-fork/libs/video/rsx_vertex_compact.c:383>),
[fetch/remap hazırlığı](</Volumes/monssd/Infamous2-iOS/build/bces01229/ios-prepared/renderer-overlay/libs/video/rsx_draw_engine.c:1877>),
[ikinci staging kopyası](</Volumes/monssd/Infamous2-iOS/build/bces01229/ios-prepared/renderer-overlay/libs/video/rsx_metal_backend.m:3814>),
[Float4 sözleşmesi](</Volumes/monssd/Infamous2-iOS/build/bces01229/ios-prepared/renderer-overlay/libs/video/rsx_metal_backend.m:3514>).

## 9. Öncelik 3 — texture değişim takibi ve CPU/GPU besleme düzeni

**Texture hash:** bir cached texture o karede yeniden kullanıldığında, ilk
kullanımında bütün mip/cube span'ı okunup hashleniyor. Bu iş renderer CPU'sunun yaklaşık %10,20'si.
Hash zaten sekiz bağımsız lane kullanıyor; öneri yeniden aynı SIMD fikri değil.
Asıl fırsat, gerçekten değişmeyen veriyi tekrar okumamaktır.

Güvenli yön: tam yazıcı kapsamı olan dirty/generation takibi; kapsam dışında
kalan aralıkta mevcut hash fallback'i. PPU store, SPU DMA, HLE/direct memcpy,
local-memory/RSX writeback gibi yazıcılar atlanırsa eski texture gösterilir.
Texture upload/hash byte adetleri mevcut cihaz kayıtlarında yok; buradan GB/s
veya kesin kaç MB tasarruf çıkarmıyorum.

**Besleme:** `eng_encode_and_commit`, biriken kayıtları encode edip gönderiyor;
ara flush yolu senkron bekleyebiliyor. Bağımsız record parçalarını erken
göndermek veya CPU hazırlığıyla GPU yürütmesini daha iyi örtüştürmek daha büyük
bir mimari aday. Ancak kaynakta olasılık görmek, bekleme boşluğunun tamamının
kaldırılabilir olduğunu kanıtlamaz. Readback/reference/ara yüzey bağımlılıkları
korunmalıdır. Daha çok küçük command buffer açmak da overhead'i artırabilir.

Kaynak: [tam-span hash ve mevcut sekiz lane](</Volumes/monssd/Infamous2-iOS/build/bces01229/ios-prepared/renderer-overlay/libs/video/rsx_draw_engine.c:850>),
[cache kontrolü](</Volumes/monssd/Infamous2-iOS/build/bces01229/ios-prepared/renderer-overlay/libs/video/rsx_draw_engine.c:1049>),
[encode/commit/senkron flush](</Volumes/monssd/Infamous2-iOS/build/bces01229/ios-prepared/renderer-overlay/libs/video/rsx_metal_backend.m:4646>).

## 10. Ortak runtime ve PPU: geometri dışındaki kapsamlı adaylar

### SPU dispatch/reset/drain

Son geniş CPU profilinde `spu_check_stack_reset` %4,34,
`spu_indirect_branch_slow` %3,03, `spu_drain_call` %2,15: yaklaşık %9,51 toplam
CPU payı. Birçok job'u etkilediğinden tek Edge alt fonksiyonundan daha geniş
kapsama sahip olabilir. FPS üzerindeki kritik payı henüz bilinmiyor.

Somut kaynak fırsatı: BCES dört stack-reset giriş PC'si kaydediyor
(`0x808/818/838/848`), fakat reset kontrolü dispatch sırasında çok sık çağrılıyor.
Registration'dan türetilen küçük PC aralık/bitset ön kontrolü, çoğu job PC'sini
out-of-line handler'a girmeden eleyebilir. Gerçek image/function/TLS eşleşmesi,
longjmp, IRQ/overlay/restart davranışı aynen kalmalı. Bazı resolver yollarındaki
çift kontrol de yalnız eşdeğerliği kanıtlanan kapsamda ayrılabilir.

Bu fonksiyon host stack sınırı sorgusu değildir; `pthread` stack cache'i
eklemek ilgili maliyeti hedeflemez. Lookup da zaten hash-indexlidir; "lineer
aramayı hash yapalım" mevcut durumu yanlış anlatır.

Kaynak: [reset kontrolü](</Volumes/monssd/Infamous2-iOS/upstream/infamous2-recomp/ps3recomp-fork/runtime/spu/spu_channels.c:1911>),
[BCES'in dört kaydı](</Volumes/monssd/Infamous2-iOS/build/bces01229/lle_spu/libsre_spu_register.c:34>).

### PPU store / koherens / bekleme

Edge38 CPU penceresinde ana PPU thread'i 15 saniyede yaklaşık 6,23 CPU-saniyesi
tüketmiş. Mevcut örneklerde `barrier_watch_hit`, `vm_write64`,
`spu_coh_is_reserved` ve progress bekleme yolları görülüyor.
`vm_write64` normalde kapalı diagnostic watch için iki çağrı yapıyor.
Diagnostic-off hızlı yol, bounds/null, atomiklik, raw-SPU register ve reservation
koherensini koruyarak sadeleştirilebilir. Load tarafı zaten inline, endian
dönüşümü ve doğrudan `vm_base+ea` kullanıyor; burada gizli büyük bir software
MMU veya CPU JIT maliyeti varsaymıyorum.

`0037062C/00371054 → 005054F0/00504DF0` yolları gerçek worker ilerlemesini
bekliyor. Sonuncusu birden çok ilerleme sözcüğünün minimumunu hedefle
karşılaştırıyor. Kontrolü/uykuyu silmek işi erkenden bitirmez; üretici tamamlanmadan
ilerleme hatası yaratabilir. Hangi chain'in son bitirdiğini mevcut argüman kaydı
belirlemiyor. Başka bir job'u yeni "en büyük FPS hedefi" ilan etmeden önce bu
bağlantı gerekir.

Kaynak: [PPU örneklerinin yeniden analizi](</Volumes/monssd/Infamous2-iOS/out/optimization-audit-20261027/ppu-main-edge38.json>),
[PPU store yardımcıları](</Volumes/monssd/Infamous2-iOS/upstream/infamous2-recomp/ps3recomp-fork/runtime/ppu/ppu_loader.cpp:2059>),
[chain beklemesi](</Volumes/monssd/Infamous2-iOS/build/bces01229/recompiled/ppu_recomp_033.cpp:10220>),
[per-worker ilerleme kontrolü](</Volumes/monssd/Infamous2-iOS/build/bces01229/recompiled/ppu_recomp_079.cpp:14695>).

### Başka saf SPU hesapları

1774…, 867e…, 3c40… ve reloc008ae480 modüllerinde sıcak vector/shuffle/matris
benzeri bölgeler var. Bazılarının oyun içi rolü henüz kanıtlanmış değil.
Guarded ARM64 RZ/block fusion buralarda da toplam işi azaltabilir. Ancak tekrar
yalnız CPU yüzdesine bakıp sırayla hepsini çevirmek aynı öncelik hatasını
tekrarlar. Önce seri bağımlılığa bağlantı aranmalı. FPCR kapsamı channel/DMA/
native callback/interrupt sınırına taşmamalıdır.

## 11. Büyük kazanç için gerçekçi bütçe

160 ms civarı bir kareyi örnek alalım. Aşağıdaki tablo yalnız aritmetiktir;
bir adayın sağlayacağına dair tahmin değildir:

| Gerçekten seri kare yolundan kaldırılan süre | Yeni kare süresi | FPS |
|---:|---:|---:|
| 0 ms | 160 ms | 6,25 |
| 10 ms | 150 ms | 6,67 |
| 30 ms | 130 ms | 7,69 |
| 60 ms | 100 ms | 10,00 |
| 126,7 ms | 33,3 ms | yaklaşık 30 |

30 FPS için mevcut seri gecikmenin yaklaşık %79'unun kaldırılması gerekir.
Tek bir %10 renderer-CPU adayından böyle bir sıçrama beklemek gerçekçi değil.
Büyük ilerleme muhtemelen birden çok seri veri/komut maliyetini azaltıp
CPU/GPU örtüşmesini iyileştiren birleşik bir yol gerektirecek.

Eski build32 izinde GPU komut tamponlarının yürütme aralıkları birleşimi
medyan 51,84 ms/kare; normal oyun
lighting/SSAO aynı renderer kuyruğunda bu kapsama dahil. Bu bile 33,3 ms
bütçesinden büyük. CPU besleme sorunu azaltıldıktan sonra GPU pass/shader,
overdraw veya kontrollü iç çözünürlük çalışması da gerekebilir. Bundan
"kesin tavan 19 FPS" çıkarmıyorum: eski build, clock/termal/load ve farklı
pencere/medyanlar var. GPU pencere çalışma birleşimi de donanım utilization
sayacı değil. `163−52=111 ms CPU` hesabı geçerli değildir.

Ek bellek entitlement'ı, yeni shader cache veya rastgele QoS/spin/çözünürlük
ayarları bu kanıtın gösterdiği ilk müdahaleler değil. Eski sabit sahne
pencerelerinde yeni shader dalgası/hata yoktu. Frame-clock'taki 4 ms polling ve
16 ms tick pacing'i ayrıca adaydır; yalnız immediate flip'ten beş kat kazanç
beklenemez, uyku yerine spin koymak worker'ları daha da sıkıştırabilir.

Kaynak: [mevcut GPU/CPU iz özeti](</Volumes/monssd/Infamous2-iOS/out/diagnosis2-gameplay-trace-analysis-20261026.json>),
[frame-clock pacing](</Volumes/monssd/Infamous2-iOS/upstream/infamous2-recomp/infamous2-lle/main.cpp:175>).

## 12. Bundan sonraki çalışma önerim

| Sıra | İş | Neden | Karar ölçütü |
|---|---|---|---|
| 1 | Aktif dispatch yolundaki gereksiz eski RSX state işlemeyi ayır | Ölçülmüş seri maliyet + somut tekrar + dar kapsam | Sync/reference/report çıktıları aynı; renderer işi ve gerçek kare süresi azalıyor mu? |
| 2 | CPU vertex hazırlığı → nihai staging zincirini kısalt | Renderer CPU'sunda büyük pay; source'ta dönüşüm/ikinci kopya var | Format/vertex/index byte eşdeğerliği; tek geçişin tüm çağrı maliyeti |
| 3 | Güvenli texture dirty/generation takibi veya renderer encode/submit düzeni | Seri tekrar okuma ve geç GPU besleme olasılığı | Yazıcı/ömür kapsamı eksiksiz; güncel veri ve sıra korunuyor |
| 4 | Ortak SPU dispatch/reset ve PPU store hızlı yolları | Geometri dışındaki birçok işi kapsayan ölçülmüş overhead | Overlay/IRQ/reservation doğruluğu ve seri bağımlılığın tamamlanması |
| 5 | Büyük batch / GPU'da kalan geometri veri akışı | Küçük offload sınırını kökten değiştirebilir | CPU geri dönüşü az, gerçek GPU kapsamı ve uçtan uca kazanç |

3 ve 4'ün uygulama sırası, dar kapsamlı fizibiliteye göre değişebilir. Bunları
beş ayrı garanti FPS paketi gibi değerlendirmiyorum. **İlk uygulanabilir aday
1; büyük mimari potansiyel 2/3 ve daha sonra 5.**

Şimdilik geometri varyant matrisini genişletmeyi, CPU'da kalan üç Metal profilini
tekrar tekrar açıp kapatmayı ve başka işlevleri yalnız sıcaklık sırasına göre
Metal'e taşımayı durdurmayı öneriyorum. Mevcut ARM64 ve referans yolları korunur.
Yeni bir uygulamaya ancak kendi doğruluk ve uçtan uca süre hedefiyle başlanır.

İleride telefon hazır olduğunda tek bir aday için karar verdiren kısa A/B gerekir;
bu raporda yeni ölçüm yapılmadı. Son build42'nin tam güncel kritik yolu halen
ölçülmüş değil; bu sınırı saklamıyorum. Rapordan çıkan fark, yeni denemeyi daha
iyi gerekçelendirebilmemiz ve neyi kanıtlamadan ilerlemememiz gerektiğinin artık
çok daha somut olmasıdır.

## 13. Çevrimdışı analizi tekrar üretme

```sh
cd /Volumes/monssd/Infamous2-iOS
python3 out/optimization-audit-20261027/analyze_renderer_cpu.py
python3 out/optimization-audit-20261027/analyze_renderer_trace.py
python3 out/optimization-audit-20261027/analyze_geometry_history.py
```

Ana PPU tekrar üretimi ayrıca
[komut notunda](</Volumes/monssd/Infamous2-iOS/out/optimization-audit-20261027/ppu-main-replay.md>) yer alır.

Bu komutlar yalnız mevcut CSV/binary'yi okur. Kaynak SHA/UUID, örnekleme ve
çözülemeyen adres sınırları çıktı JSON'larında yer alır. CPU profili eski build32,
Edge akış izi build38, yeni geometri FPS sonucu build42'dir; bunlar tek bir
eşzamanlı güncel kayıt gibi birleştirilmedi. Profil/screenshot/ham oyun verisi
Git'e eklenmedi; kaynak pinleri ve çalışan macOS hedefi değişmedi.
