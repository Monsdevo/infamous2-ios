# Edge job / veri akışı teşhisi — build 38

26 Ekim 2026. Amaç yeni hızlandırma açmak değil, ARM64 ve Metal arasında karar
verecek süre ve veri bağımlılığı kanıtını toplamak. Önceki üç bloklu Edge
deneyi varsayılan kapalı; Metal aydınlatma/SSAO ve depth sınır temizliği korunur.

## Kaynakta doğrulanan akış

`jobmods_manifest.json` Edge modül girişini **E2A0** olarak verir. Bu fonksiyon
job giriş register'larını saklayıp callback tablosunu kurar; **E364** normal
çıkışta register'ları geri yükleyip SPU_RET yapar. Aradaki C fonksiyonlarının
çoğu yalnız birer lifted basic block'tur: C `return`, job'un bittiği anlamına
gelmez. İşlev sürelerini yalnız ilk basic block'un etrafından ölçmek eksik olur.

`prepare_edge_flow.py:instrument`, türetilmiş Edge kaynağına giriş/normal çıkış
kaydı ekler. Ayrıca özgün **çağrı + spu_drain_call** çiftinin tamamını 16 çağrı
yerinde ölçer. Hedefler: 5740, D0A8, A798, 6E08, 7860, 7570, 76C0, 7B70,
6A40, 83C8, AD48. D0A8 çevresinde önceki D808/D8A8/DA28 matris/ağırlık
döngüleri vardır; diğer adreslerin hepsine kanıtsız skinning/culling adı verilmez.
5740 girdisi r7 üzerinden +44/+48 gibi descriptor alanlarını okur; ilk sekiz
5740 çağrısında bu pointer'dan ham 128 baytlık LS penceresi kaydedilir.
Bu ham veri henüz çözümlenmiş descriptor şeması değildir.

Her kapsam için CLOCK_MONOTONIC tabanlı wall süre ve aynı native thread'in
CLOCK_THREAD_CPUTIME_ID süresi ayrı tutulur. CPU süresi alt çağrıları ve o
thread'deki interrupt işlerini içerir; farklı native thread'e taşınan işi
ölçtüğü varsayılmaz. İç içe çağrı süreleri toplanmaz. Job wall sürelerinin
frame içindeki birleşimi, **nedensel kritik-yol gecikmesi** diye sunulmaz.

## Bellek üreticisi / tüketicisi

`prepare_frame_diagnostics.py` yalnız derived DMA header'ında başarılı normal
MFC GET/PUT aktarımının sonuna hook koyar. List transfer'lar aynı leaf aktarımı
kullandığından elemanları da görülür. Hook yalnız aynı TLS/context'te başlayan
Edge job ve kayıt epoch'u içinde çalışır. Job-manager'ın bu kapsam dışında
yaptığı aktarım, bütün PPU erişimleri ve tüm diğer writer'lar takip edilmez.
Normal DMA/koherens/kilit/notification sırası değiştirilmez; hook sonunda çalışır.

Renderer'da vertex planı ve iki index okuma yolu, mevcut guest-memory callback'i
koruyan wrapper kullanır. Gerçek host pointer'ı `vm_base` içine düşüyorsa EA
aralığı kaydedilir. Bunlar **CPU renderer'ın aralık istekleridir**, bir GPU
okumasının zamanı veya byte eşdeğerliği değildir. Analiz yalnız önceki zamanlı
Edge PUT ile yarı açık aralık çakışmasını arar. Başka writer'ın araya girmediği
veya tek tüketicinin renderer olduğu ispat edilmez. Eşleşmeyen çıktı da kullanılmıyor
veya GPU-only anlamına gelmez.

Kaynakta mevcut renderer yolu şudur:

1. `rsx_draw_engine.c` index/remap ve vertex fetch planını hazırlar.
2. `rsx_vertex_compact.c:rsx_vertex_fetch_all` guest vertex biçimlerini CPU'da
   açıp/değiştirip `dc.verts` dizisine yerleştirir.
3. Draw engine bu diziyi `g.be->draw` ile iletir.
4. Metal backend `eng_draw` / `eng_stage_copy` vertex verisini staging'e kopyalar.

Edge çıktıları bu yola bağlanırsa mevcut tasarımda CPU tüketimi vardır. GPU
skinning'i doğrudan çizime bağlamak için bu dönüşüm/upload akışını da ele almak
gerekebilir. Henüz belirli bir Edge çıktısının bu yola bağlandığı cihaz kaydı
olmadan kabul edilmez; bu paragraf kaynak mimarisini anlatır.

## Güvenlik ve sınırlamalar

`--diagnose-edge-flow` açık **ve** frame trace kaydı aktif değilse kayıt yoktur.
Özgün çıktılar/dispatch/IRQ/DMA veya culling kararları değişmez. Giriş/çıkış
eşleşmesi için aynı context/epoch gerekir; yarım kalmış kayıtlar ve ring drop
sayısı analizde ayrıca raporlanır. FrameTrace'in mevcut 500.000 kayıt sınırı
korunur; İlk build37 kayıtları bir saniyede dahi kapasiteyi aştı ve reddedildi. Build38 örneklemeyle bu hacmi sınırlar. Trace maliyeti mevcut olduğundan kayıt sırasındaki FPS bir
optimizasyon A/B ölçümü değildir. Üretimde normal flag'siz başlatma kayıt açmaz.

## Test ve derleme

`tools/test_edge_flow.py` gerçek kayıt kodunu ASan/UBSan ile çalıştırır:
bağlamın değişmediği, job/child CPU+wall kaydı, LS sınırında saran ham pencere,
GET/PUT/vertex aralıkları, kapalı/bitmiş/epoch kontrolleri doğrulanır. Analiz
testleri gelecekteki PUT'a eşleştirmeyi, yalnız sınırdan dokunan aralıkları,
GET'i output sanmayı engeller; eksik metadata ve dropped capture reddedilir.
Önceki 6.144 Edge karşılaştırması iki binary'de tekrar geçti.

Build38 iPhoneOS derlendi ve strict imzası doğrulandı; cihaz güncellendi.
UUID `EAA388B7-94DE-3CF5-8133-AA55011719DD`. Geri dönüş build36 paketi
`build/bces01229/baselines/step27-edge-flow-build36/Infamous2Game.app`.
Oyun verileri tekrar aktarılmadı. Host testleri cihazda job kaydı alınmış
olduğunu göstermez; cihaz sonuçları aşağıya ayrıca eklenecek.

```sh
python3 tools/test_edge_flow.py
python3 tools/test_edge_geometry.py
python3 tools/prepare_bces_ios.py --support-report out/bces-support-compile-iphoneos-spu-O2-copy.json
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer /opt/homebrew/bin/cmake -S cmake/bces-ios -B build/bces01229/ios
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp xcodebuild -project build/bces01229/ios/Infamous2BCESIOS.xcodeproj -scheme Infamous2Game -configuration Release -destination 'generic/platform=iOS' -jobs 1 DEVELOPMENT_TEAM=BJ266NGN3H -allowProvisioningUpdates
```

Başlatma argümanları: `--boot --diagnose-edge-flow --diagnose-frame --profile-cpu`.
Kayıt komutu: `Documents/frame-trace-control.txt` içine `start BENZERSIZ_TOKEN 3`.
CPU örnekleyicisi ayrı tutulur ve bu ilk iz sırasında kapalı kalır.

```sh
python3 tools/analyze_edge_flow.py out/edge38-gameplay-flow2.csv --output out/edge38-gameplay-flow2-analysis.json
python3 tools/analyze_frame_trace.py out/edge38-gameplay-flow2.csv --output out/edge38-gameplay-frame2-analysis.json
```

Trace ve ham LS penceresi oyun kaynaklı veri içerir; ignored `out/` altında
saklanır, Git'e veya halka açık paketlere eklenmez.

## Kayıt hacmi düzeltmesi

Build37 teknik kontrolü: 1 saniye, 500.000 retained / 90.175 dropped;
ilk kullanıcı teyitli oynanış kaydı: 500.000 retained / 817.410 dropped.
İki kayıt da **geçersiz**: bu pencerelerden FPS, kritik yol veya tüm-job
performansı sonucu çıkarılmaz. 128 baytlık ilk ham descriptor pencereleri
ayrıca özel tanı verisi olarak saklandı; oynanıştaki tüm girdilerin şeması
çözülmüş sayılmaz.

Build38 bütün üst Edge job'larının wall/thread-CPU kayıtlarını ister.
Alt çağrı ve DMA ayrıntıları ilk sekiz job, ardından deterministik hash ile
~1/16 job'dan alınır. Renderer aralık istekleri ilk sekiz istek, ardından
~1/64 oranında örneklenir. Kaydedilen root metadata'sı ayrıntı seçimini işaretler.
Bu nedenle alt çağrı/DMA/reader adetleri toplam adet veya kapsama yüzdesi
olarak sunulmaz; eksik eşleşme GPU-only sonucu değildir. Amaç yeterli sayıda
**pozitif** üretici/tüketici örneği ve all-root süre dağılımıdır.

Host yük testinde 1000 root span korundu; 61 iç çağrı ve 10.000 reader isteğinden
159'u kaydedildi. Hiçbir kayıt düşmedi, oyun context'i değişmedi. Bu test
cihazda ring'in dolmayacağı garantisi değildir; cihazda dropped sayısı ayrıca
kontrol edilir. Aralık eşleştirmesine yalnız tamamlanmış, sınırda kırpılmamış
Edge job'u içindeki PUT'lar alınır. Trace ortasından başlayan/yarım job'lar
negatif kanıt olarak kullanılmaz.

## Gerçek oynanış sonuçları

Kullanıcı ilk oynanışta Cole ve kamerayı sabit bıraktığını teyit etti. Build38,
PID15195, aynı süreç. Üç ayrı **1 / 3 / 3 saniyelik** iz: **69.010 / 189.326 /
190.238 satır**, dropped=0, eksik kayıt grubu0. Toplam **5.145 tam, sınırda
kırpılmamış root job** ve 317 ayrıntı örnekli job kaydı. CPU saati unavailable0,
CPU>wall+0,1ms hatası0. Başlangıç/son raporlarında termal durum normal0;
trace içinde sürekli termal kayıt yok. Bu kayıtlar FPS A/B deneyi değildir.

İki 3 saniyelik kayıtta toplam 4.390 tam root job var. Ayrıntı seçilmiş
root job'ların CPU süreleriyle ağırlıklandırılan, **iç içe kapsayıcı** paylar:

| İşlev yolu | İlk 3 s | İkinci 3 s | Birleşik |
|---|---:|---:|---:|
| D0A8 — skinning | %43,48 | %43,49 | **%43,48** |
| A798 — culling | %19,30 | %19,46 | **%19,38** |
| 5740 — bu aşamaları da içeren driver | %91,00 | %90,94 | %90,97 |

5740 satırı diğerlerini **içerir**, bunlar toplanmaz. Payda oyunun bütün CPU
veya kare süresi değil, ayrıntı örneklenen Edge root job CPU süresidir.
Alt çağrı sayısı/örnek sayısı tüm oyuna ölçeklenmez. D0A8/A798 süreleri bütün
logical call + drain akışını kapsar; önceki üç basic-block aritmetik denemesiyle
aynı kapsam değildir.

### Skinning ve culling adları nasıl doğrulandı?

Doğrulanmış BCES job binary'sinin SHA256'sı
`b713689924faad1452b20ae59d4a6b4dcf2c8fa882050bc900a3dcf05daf6a69`.
Job LS tabanı0x4000. D0A8 doğrudan LS0xF440'taki skinning/uniform hata
mesajını referanslar; aynı yolun E15C bloğu F490 skinning uniform sınırına
referans verir. A798'in A80C kolu E9E0 culling/uniform hata mesajını kullanır.
Bunlar `out/edge38-semantic-xrefs.json` ve özel string incelemesinde saklandı.
İşlev rolü bu kaynak kanıtı, matris/ağırlık döngüleri ve gerçek argümanlarla
birlikte adlandırıldı; yalnız adrese bakılarak atanmadı.

İkinci izde D0A8 ve A798 ayrı ayrı 569 ayrıntı örnekli çağrı. D0A8 ortak LS
context pointer'ı, akış pointer'ları ve sayısal parametreler alıyor. A798 aynı
context'i kullanıyor; gözlenen mod girdileri1/2/3. Örnek dönüş sayıları 3'ün
katları; indeks/üçgen çıktısıyla uyumlu, fakat bütün ABI/descriptor şeması
çözülmüş kabul edilmiyor. Kaynak akışında skinning çağrısını culling izliyor.
Bu iki aşamanın paylaştığı bütün LS tamponları henüz alan alan haritalanmadı.

### CPU / GPU örtüşmesi

İki uzun izde ham flip-request aralığı medyanı **154,88 / 158,44 ms**.
Edge root job wall sürelerinin frame içindeki birleşimi medyanda
**48,85 / 43,44 ms**. Edge/GPU çalışma kesişimi medyanı
**30,63 / 25,00 ms**. GPU çalışma birleşimi ilk uzun izde medyan49,92ms;
CPU GPU-wait16,95ms, readback3,35ms, RSX drain127,63ms. Bunlar birbirini
kapsayabilen/örtüşen sürelerdir; toplanmaz, medyanlar çıkarılıp kazanç hesabı
yapılmaz. Edge'in önemli kısmı başka işlemlerle örtüşüyor; CPU tasarrufunun
neden aynı oranda FPS'ye dönüşmeyebileceğine dair bir işaret. **Nedensel kritik
bekleme süresi** veya GPU'ya geçince kazanılacak ms bu kayıttan çıkmaz.
Kanıt: `out/edge38-edge-gpu-overlap.json`.

### Üretici / tüketici

Üç izde sırasıyla17 / 113 / 98 **örneklenmiş aralık eşleşmesi** var; vertex
ve index istekleri iki uzun izde de görülüyor. Bunlar tamamlanmış root job'un
PUT aralığı ile sonraki renderer aralık isteğinin çakışmaları. Örneğin ikinci
izde Edge PUT0xC1A6B180 aralığı vertex isteği0xC1A6B190 ile; başka PUT0xC1BE8680
index isteği0xC1BE8680 ile çakışıyor. Aynı verinin byte eşdeğerliği veya arada
başka yazı olmadığı ispat edilmedi. Örnekleme nedeniyle en yakın *kaydedilmiş*
PUT yüzlerce ms önce olabilir: bu fark **ilk tüketim gecikmesi veya bekleme**
değildir. Eşleşme yüzdesi/çıktı kapsama oranı verilmez.

Mevcut CPU vertex hazırlama yoluna giriş olduğuna dair pozitif kanıt var.
Metal yalnız hesap kernel'i olarak eklenirse sonuç CPU culling/fetch tarafında
tekrar gerekebilir; bunun kesin paylaşım şeması çözülmeden GPU-only veya
readback gereksiz kararı verilmez. Doğrudan GPU çizimine bağlanacak çözümün
vertex biçimlendirme, indeks/remap ve backend staging sözleşmesini de ele
alması gerekir. Bu aşamada Metal compute benchmark çalıştırılmadı.

### Ayrı CPU profili

İz bittikten sonra ayrı **15,00434 s**, 660 tick / 6.809 satır CPU örneği.
UUID doğru, errors=0, truncated=0. Yaklaşık aggregate CPU payları:
SPU %75,12, renderer %13,62, PPU %9,79, diğer rol %1,47.
Edge modülü doğrudan **%15,74**; yine en büyük belirli job modülü.
`spu_check_stack_reset` %4,34, `spu_indirect_branch_slow` %3,03,
`spu_drain_call` %2,15: doğrudan toplam ~%9,51.
Renderer `rsx_vertex_fetch_all` %2,67, `eng_texture_content_hash` %1,51.
Diğer job modülleri: 1774... %5,06; 867e... %4,61; 3c40... %4,02;
reloc008ae480 %3,82. Amaçları kanıtlanmadan isim atanmadı.
Bunlar **CPU payları**, tek kareden çıkarılabilecek ms değildir.
`<system/unresolved>` %14,47 ayrı exclusive sınıflamadır; diğer rolün %1,47
payıyla aynı tanım değildir. Interpreter ancestry ~%51 görülmesi, %51
instruction'ın yorumlandığı anlamına gelmez; wrapper'lar native lifted kod çağırır.

### Kalan kritik-yol belirsizliği ve önerilen devam

PPU izinde genel job-chain ilerleme beklemeleri var. BCES
`func_0037062C` / `func_003710...` -> `func_005054F0` / `func_00504DF0`
list ve per-SPU ilerleme alanlarını okuyor. Hangi runtime chain pointer'ının
Edge'e ait olduğu bu izde kayıtlı değil. PPU9 LR337470 ve PPU8 LR338D1C
beklemeleri de var; bunlar doğrudan Edge gecikmesi diye etiketlenmedi.
`out/edge38-ppu-waits.json` yalnız gözlenen bekleme yerlerini içerir.

1. **Bütün D0A8 skinning işi** artık ilk referans kernel adayı. Giriş/çıkış
   tamponları ve modları fixture olarak çıkarılıp tam çıktı eşdeğerliği
   sınanmalı; yalnız üç SPU aritmetik helper'ı değiştirmekle yetinilmemeli.
2. **A798 culling** ikinci belirli Edge adayı. Skinning'den hangi tamponları
   tükettiği ve CPU tarafındaki görünür indeks sayısının nerede kullanıldığı
   tamamlanmalı. GPU'ya geçişte bu bağımlılık atlanmamalı.
3. Metal yolu seçilecekse skinning/culling sonucunun CPU'ya dönmesi ve mevcut
   CPU vertex hazırlığı dahil **uçtan uca** maliyet karşılaştırılmalı. Sadece
   shader süresi ile karar verilmeyecek. CPU tüketicileri korunacaksa bütün
   kernel için ARM64 alternatifi de karşılaştırma hedefi olarak tutulmalı.
4. Tam FPS önceliğini belirlemek için Edge chain pointer/handle ile PPU bekleme
   bağı kurulmalı; renderer'ın tek thread vertex/fetch/hash maliyetleri ayrı
   ölçülmeli. Mevcut CPU/GPU örtüşmesi nedeniyle büyük Edge CPU payı tek başına
   onu en yüksek FPS kazancı yapan aday ilan etmeye yetmiyor.

**Yeni hızlandırma etkinleştirilmedi.** Süreç15195 oynanışta açık; Edge hızlı
yolu kapalı, Metal aydınlatma/SSAO açık. CPU/trace completed3; iki kontrol dosyası
idle yapıldı. Son cihaz raporu hata0 / termal0. Önceki aralıklı sinematik
kapanmasının kalıcı çözüldüğü veya uzun oyun kararlılığı kanıtlandığı iddia edilmez.
Birleşik sonuç: `out/edge38-diagnosis-result.json`.
