# İkinci optimizasyon teşhisi — 26 Ekim 2026

Amaç: build 32 Metal aydınlatma + Metal SSAO sonrasında kalan maliyetleri
ölçmek; bu oturumda yeni oyun/runtime optimizasyonu uygulanmaz. Aynı kurulu
binary UUID 3C9D35C1-C8FD-3974-9654-6FBF77B10BFB kullanılır. Native copy kapalı,
SPU half-depth ve input writeback'leri korunur.

Önceki karşılaştırma: 4,84→6,16 FPS (+%27,2 SSAO ek kazancı), normal termal
sınıf ve harici soğutmayla tek C/B pilotu. Bu teşhis o kazancı yeniden vaat
etmez; eski aydınlatma/SSAO öncesi CPU dağılımı güncel kabul edilmez.

Mevcut CPU profili önce out/diagnosis2-preexisting-cpu-profile-20261026.csv'ye
korundu. Eski komutlar idle yapıldı. Aynı paket --profile-cpu ve
--diagnose-frame ile açıldı; kayda yalnız ilk oynanış/kamera teyidinden sonra
başlanır. Yeni derleme/kurulum veya oyun dosyası aktarımı yok.

Kayıt sırası: normal termal seviyede 30 s hafif FPS penceresi → ayrı 30 s CPU
örnekleme → ayrı 10 s bekleme/GPU izi → örnekleyici kapalı son FPS penceresi.
Profiler penceresinin FPS'si benchmark sayılmaz. CPU CSV ve trace UUID/token,
hata/kesilme/drop ve sıcaklık kontrol edilir. CPU exclusive PC sıralaması
birincil; unsuspended FP ancestry yalnız yardımcı, inclusive süreler toplanmaz.

Çıktı: işlev/dosya düzeyinde güncel maliyet dağılımı; CPU işi, GPU işi ve
beklemenin ayrılması; kanıt düzeyine göre sıralanmış optimizasyon adayları.
Bilinen pahalı işlerin toplam CPU payı FPS kazancı değildir. Kareyi bitirmeyi
engellediği henüz kanıtlanmayan bir adaya doğrudan FPS tahmini verilmez.

## Önce sinematik donması yakalandı

İlk teşhis süreci PID 14762 oynanış öncesi dondu. Guest frame 4519'da kaldı;
4544 Metal submitted/completed, in-flight 0; Metal/SSAO fault 0, CPU yaklaşık
%17,9, footprint 803212616 byte ve thermal normal. Yeniden başlatmadan 10 s
CPU örneği (1839 satır, errors=0, truncated=0) ve ayrı 5 s iz alındı. İzde
flip/Metal commit/GPU execution 0. Bu kayıtlar performans benchmark'ı değildir.

Main native stack: func_003374C8 → sys_timer_usleep; kaynakta obj+0x318'in
4 olmasını bekliyor. Logical PPU9 izinde LR0x337470, 5 s'nin yaklaşık 4,999 s'si
usleep. Kaynak func_00337414/func_0033704C state machine ile ilişkili. SPU'ların
çoğu kanalda bekliyor; audio/reloc işleri az miktarda devam ediyor.

Kapanıştan sonra korunmuş runtime günlüğünde FIFO resync **unmapped-JUMP**
0x0057ED08 → put0x00010058 görüldü. Bu build31'de kapatılan self-JUMP timeout
recovery'sinden farklı bir yol. Tetikleyici/ilk bozuk komutun kök nedeni
henüz kanıtlanmadı; Metal SSAO'nun sebep olduğu varsayılmıyor. Kalıcı kararlılık
hâlâ ayrı öncelikli iş. Dosyalar out/diagnosis2-hang-*20261026*.

İlk yeniden açılış PID vermedi; ikinci deneme aynı binary/ayarlarla PID 14770
olarak açıldı. Kullanıcı yeniden ilk oynanışa ilerliyor. Oyun kodu değiştirilmedi.

## Başarılı oynanış kaydı

İkinci açılış PID 14770 ilk oynanışa ulaştı; kullanıcı sabit karakter/kamera
teyidi verdi. CPU örnekleyicisi kapalı ilk pencere: 30,999561 s / 183 guest
frame = **5,903309 FPS**. Son pencere: 31,000813 s / 190 frame = **6,128872 FPS**.
Her iki pencere thermal normal, yeni pipeline 0, Metal/SSAO fault 0, SSAO
fallback 0; GPU geçiş/binding/skip sayaçları artıyor. Aradaki ~%3,8 fark
optimizasyon kazancı değildir: kod değişmedi, sahnenin zamanlaması değişebilir.

CPU kaydı: 30,007916 s, 15098 satır, 1340 tick, errors=0, truncated=0, token
`diagnosis2cpu20261026`, doğru build32 UUID. Yaklaşık 141,837 aggregate CPU
saniyesi gözlendi; birden çok thread paralel olduğundan bunu kare duvar
süresine çevirmiyoruz. Örnekleyici nominal 50 Hz hedefler, gerçek tick yaklaşık
44,65 Hz. FPS benchmark'ı bu pencereye ait değil.

| Yaklaşık CPU rolü | Gözlenen toplam CPU payı |
|---|---:|
| SPU | %75,27 |
| Renderer | %12,31 |
| PPU | %11,01 |
| Diğer/atanamayan rol | %1,41 |

Rol atfı yardımcı ancestry'ye dayanır. Exclusive PC'lerin %14,21'i sistem/
çözülemeyen adrestir; bu satırdaki pay, başka bir tabloda verilen %1,41 rol
payıyla aynı şey değildir. Inclusive değerler birbirini kapsar, toplanmaz.
`spu_interp_run_until/spu_step` ancestry'sinin ~%54 görünmesi, talimatların
%54'ünün yorumlandığı anlamına gelmez: wrapper'lar üretilmiş native işlevleri
de çağırır. Gerçek interpreter oranı için instruction/dispatch sayacı gerekir.

Host analiz aracı tam exclusive dağılımı modül bazında toplamak için genişletildi
(`tools/analyze_native_profile.py`). Modül exclusive toplamı ana CPU toplamıyla
sayısal olarak doğrulandı. Üç mevcut analiz testi ve py_compile geçti. Cihaz
uygulaması, optimizasyon anahtarları ve binary değişmedi.

## CPU/GPU zaman çizelgesi

CPU örnekleyicisi bittikten sonra ayrı 10 s iz: 57 iç kare, medyan **162,776 ms**,
p95 **197,047 ms**. GPU execution union medyan **51,844 ms/kare**; CPU GPU wait
union **17,294 ms**, readback union **3,498 ms**, RSX drain union **142,729 ms**.
Bunlar örtüşür: drain süresi saf CPU hesaplama değildir, GPU/wait sütunlarıyla
toplanmaz. GPU'nun kendi kapsanan işi tek başına ~163 ms'yi açıklamıyor;
yeni adayları CPU işi ve bağımlılıklarla birlikte seçmek gerekiyor.

0x870 bekleme medyanı 0, 48/57 karede bekleme yok. 0x890 bekleme medyanı 0,
40/57 karede bekleme yok, p95 32,122 ms. Önceki gibi her karede ~70 ms süren
tek bir SSAO etiket beklemesi artık yok; kalan maliyet farklı işlere dağılmış.
28 acquire'dan 27'si tek kaydedilmiş label yazısıyla eşleşti. Bir acquire iz
başlangıcından 4,513 ms önce başlıyor ve 0,589 ms sonra bitiyor; yazıcısı capture
öncesinde kalmış. Bu olay saklanan iç kare aralıklarının dışında; eksik DMA
grupları 0, GPU commit/execution kaybı 0.

## Adaylar — büyüklük ve kanıt

CPU payları tek sahnede yaklaşık aggregate CPU payıdır, kare ms'si veya vaat
edilen FPS artışı değildir. Bu sıralama bütün oyun için kesin sıralama sayılmaz.

| Aday | Kanıt | İlk gerekli çalışma |
|---|---|---|
| **Edge geometri kümesi d0d15ec83992** | Doğrudan modül CPU %16,14; ancestry %19,92. D8A8 %3,35, DA28 %2,06, AAF8 %1,85, D808 %1,75, A650 %1,61 | Bir job'un girdilerini/çıktılarını ve tüketicilerini yakala; native ARM64 kernel ile Metal seçeneğini veri aktarımı dahil karşılaştır |
| **SPU dispatch / stack kontrolü** | `spu_check_stack_reset` %3,86 + `spu_indirect_branch_slow` %3,28 + `spu_drain_call` %2,32 = doğrudan %9,46 | Çağrı yeri/lookup/reset/TLS maliyetini ayır; overlay, IRQ, stack, stop ve yield doğruluğu korunarak küçük deney |
| **CPU'da kalan SSAO işi** | SSAO job ancestry %6,61; AO modülü doğrudan %3,13. Native stack aşağıda | Özgün derinlik çalışmasını yalnız pass E ile sınırla; half-depth ve iki label/iterator doğrulamasından sonra A/B |
| **Diğer WWS job 1774dd41c4e8** | Modül doğrudan %4,15; ancestry %10,40 | Önce işin amacını ve tüketicisini tanımla; kanıtsız fizik/ses/zlib adı verilmedi |
| **Renderer vertex hazırlığı / texture hash** | Renderer toplam %12,31. `rsx_vertex_fetch_all` %2,41; `eng_texture_content_hash` %1,26 | Kare başına vertex/format/dönüşüm/hash byte sayısı; tekrar kullanım, geçersizleştirme ve ARM64 vektörleştirme adayları |
| **Writeback/readback** | Readback medyan ~3,5 ms; flush beklemeleri ayrıca örtüşüyor | CPU tüketicilerini belirlemeden kopya kaldırma. Yalnız readback bütün ~163 ms'yi açıklamaz |

**En büyük belirli iş kümesi geometri.** Job binary'sinde EDGE/culling/blend
shapes/skinning mesajları var; pinned ROADMAP de aynı job'u Edge geometry olarak
tanımlıyor. Bu, her sıcak işlevin kesin skinning olduğu anlamına gelmez.
D8A8/DA28 çevresinde FMA, shuffle, ağırlık/indeks ve LS okumaları yoğun.
Kaynak: `build/bces01229/spu/jobmod_d0d15ec83992_ea2a0/spu_recomp.c`.
Metal'e taşımadan önce üretilen veriyi PPU'nun mı GPU'nun mı tükettiği çözülmeli;
CPU'ya geri okuma gerekiyorsa GPU taşıması kazancı tüketebilir. ARM64 üzerinde
birkaç sıcak kernel'i hızlandırmak daha küçük bir ilk deney olabilir.

Runtime kaynakları `runtime/spu/spu_channels.c:spu_check_stack_reset,
spu_indirect_branch_slow` ve `spu_drain.c:spu_drain_call` (pinned fork).
Kontrolleri kapatmak önerilmiyor: özellikle mevcut donma ve overlay/IRQ
protokolleri nedeniyle bu genel değişikliğin doğruluk riski yüksek.

Renderer kaynakları pinned `libs/video/rsx_vertex_compact.c:rsx_vertex_fetch_all`
ve `rsx_draw_engine.c:eng_texture_content_hash`. Dönüşüm/hash toplamları kernel
süreleriyle çifte sayılmadan ele alınmalı. GPU kalitesini düşürmek bu teşhisin
önerdiği ilk adım değil.

## Özgün AO neden hâlâ CPU profilinde?

Somut örnek native stack:

```
datamod_00821080...07320
spu_drain_call
datamod_00821080...06E68
spu_drain_call
jobmod_e6fe749031f8...056B0
spu_drain_call
ssao_skip_4330
```

Build32 ilk paketi half-depth çıktısını korumak için pass0'da özgün `5258`
adımını çağırıyor (`tools/prepare_metal_ssao.py:hook`). Ancak özgün `5840`
tamamlaması `46D0` ile pass'i ilerletip callback sıfır dönerse `5328` claim
loop'una geri dönebiliyor. Dolayısıyla bu çağrı tek depth tile'ıyla sınırlı değil;
AO işlerine de devam edebilmesi hem kaynak akışında hem örnekte görülüyor.
Metal SSAO gerçekten çalışıyor; buna ek olarak bazı CPU AO işleri kalıyor.
Ölçülen %6,61 job ancestry'nin tamamının kaldırılabilir olduğu varsayılmıyor.

**Önerilen küçük ilk uygulama deneyi:** bu yolun sınırını düzeltmek; özgün
half-depth, tag/barrier/yield, label136/137 değer ve sıra, son iterator state'i
referansla karşılaştırmak. Ardından tek değişkenli FPS testi. Bu oturumda
uygulanmadı. En büyük kapsamlı sonraki aday ise geometri kümesidir.

## Önkoşullar ve devam sırası

1. Kaydedilen aralıklı sinematik donması ayrı kararlılık önceliği. Geçersiz
   FIFO atlamasının tetikleyicisi kanıtlanmadan genel recovery kapatılmayacak.
2. SSAO gerçek ara çıktı/tam görüntü eşdeğerliği açık kalır. Performans kanıtı
   piksel doğruluğu kanıtı değildir.
3. Küçük, ölçülebilir ilk deney: CPU'da kalan AO yolunu pass sınırında ayırmak.
4. Geometri girdisi/çıktısı yakalama ve sıcak kernel prototipi; sonra ölçüme
   göre native ARM64 / Metal seçimi. Eşzamanlı birçok optimizasyon açılmayacak.
5. Runtime/diğer WWS/renderer adayları aynı yöntemle sırayla daraltılacak.
   Daha yoğun sahne ve kamera hareketinde sıralama ayrıca kontrol edilmeli.

## Kanıt ve tekrar üretim

`out/diagnosis2-result-20261026.json` birleşik özet. Ham CPU,
CPU analizi, ham trace, trace analizi, dependency analizi ve pre/post FPS
pencereleri `out/diagnosis2-*20261026*` altında ayrı. Yeni oyun binary'si yok;
yalnız host analiz aracı/dokümantasyon değişti. Ölçüm komutları idle yapıldı,
CPU state/trace state completed; oyun aynı süreçte açık bırakıldı.

```sh
python3 tools/analyze_native_profile.py out/diagnosis2-gameplay-cpu-20261026.csv --binary build/bces01229/symbols/3C9D35C1-C8FD-3974-9654-6FBF77B10BFB/Infamous2Game --label 'Diagnosis2 fixed first gameplay; profiler ON' --output out/diagnosis2-gameplay-cpu-analysis-20261026.json
python3 tools/analyze_frame_trace.py out/diagnosis2-gameplay-trace-20261026.csv --output out/diagnosis2-gameplay-trace-analysis-20261026.json
python3 tools/analyze_frame_dependencies.py out/diagnosis2-gameplay-trace-20261026.csv --binary build/bces01229/symbols/3C9D35C1-C8FD-3974-9654-6FBF77B10BFB/Infamous2Game --output out/diagnosis2-gameplay-dependencies-20261026.json
python3 tools/test_profile_analysis.py
```

Build33 güncellemesi: önerilen küçük SSAO sınır temizliği uygulandı.
[Ayrı uygulama ve cihaz doğrulama notu](ssao-depth-cleanup-tr.md); eski
profil verileri tarihsel teşhis olarak korunur.
