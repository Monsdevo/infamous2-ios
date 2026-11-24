# Mac üzerinde en az yaklaşık %40 FPS hedefi — devam ediyor

29 Ekim 2026. Kullanıcı küçük bir kazançta durulmamasını istedi. Referans,
uzak ışık elemesi açık mevcut en iyi Mac yoludur; önceki kazanım yeniden
sayılmaz. Oyun mantığı, senkronizasyon, ışık/gölge, asset ve 1280x720 çözünürlük
korunur. iPhone ve GitHub bu çalışmada değiştirilmez.

`gain40-01/initial-best-baseline`: 13,32497 FPS /75,04707ms. Hedef en az
18,65496FPS /53,60505ms. Profilsiz gerçek GPU-completion olaylarından45s
pencere; cihaz ekran FPS'si değildir. Aynı sahneye gerçek CROSS/RY/RX girdisi
ve görüntü/OCR ile ulaşıldı.

## Depth-only v1: başarısız performans deneyi

Renk yazımı tamamen kapalı, alpha testi kapalı ve HLSL'de discard/clip,
derinlik/coverage çıkışı veya storage/atomic etkisi olmayan RSX fragment
shader'ları için nil fragment PSO adayı eklendi. Referans PSO ve aynı vertex,
depth/stencil state korunur. Ayrı Mac hedefinde opt-in `depth_only` kontrolü
ve gerçek çizim sayaçları vardır.

48 gerçek M3 GPU fixture'ında renk/depth/stencil byte'ları aynı. 8 fixture
derinliği,40 fixture stencili gerçekten değiştiriyor; yalnız boş çizim testi
değil. Uygunlukta color mask/alpha/discard/depth/coverage/UAV ret kontrolleri
geçti. Ancak gerçek oynanış A/B/A sonucu13,368 /13,228 /13,313FPS
(74,806 /75,598 /75,113ms): kazanç yok. Üç pencere de termal1, shader derlemesi
ve profiller kapalı; aynı süreç18743. Uygun yol kare başına yalnız yaklaşık
bir çizime ulaştı. Bu aday hedefi karşılamaz ve varsayılan kapalıdır.

Süreçler kendi süre sınırında kapandı; `gain40-02` returncode−9,3600s sınırı
sonrası launcher temizliğidir, oyun çökmesi kanıtı değildir. Aynı handle'lar
terminal olarak doğrulandı; eski işlem varmış gibi yeniden beklenmedi.

## Güncel araştırma

Uygunluk alpha enable bitini tek başına reddediyordu. GL_ALWAYS (0x0207)
piksel atamaz; yeni sürümde yalnız gerçek alpha elemesi ret sebebidir.
Shader'ın kendisindeki clip/discard kontrolü ayrıca korunur. Ağır geçişin
bu yeni yola gerçekten girip girmediği sayaçla ölçülecek.

Önceki GPU probe render aşamalarını kapsıyor, ışık maskesinin compute encoder'ını
kapsamıyordu. Probe'a mevcut compute encoder descriptor'ü üzerinden iki
zaman damgası eklendi; render pass bölme veya yeni GPU fence yok. FPS ölçümünde
probe kapalı kalır. Gerçek M3 native testi render piksel eşitliğini, clear-only
sıfır damgalarını ve compute off/on çıktı eşitliği + pozitif zaman damgasını
geçti. Üç saf analiz testi compute aralığının vertex olarak sayılmadığını,
clear-only aşamanın epoch0 maliyeti üretmediğini ve ters zaman damgasının
reddini sınar. Süreler örtüşebilir; shader maliyetleri diye toplanmaz.

Kontrol noktası `out/host-research/gain40-state.json`; tüm kaynak/ham ölçüm
kanıtları `gain40-01/`, `gain40-02/`, `gain40-counter-test/` altında.
**%40 hedefi tamamlanmadı.**

## Sonraki gerçek kayıtlar

`gain40-03` compute kaydı: ışık maskesi encoder aralığı16,033ms. Büyük iki
fragment aralığı bu compute aralığıyla örtüşüyor;16+14+14 toplanmaz. Genişletilmiş
GL_ALWAYS denemesi hâlâ yaklaşık1uygun çizim/kareye ulaştı ve kazanç göstermedi.
Sonraki uygunluk, bu Metal engine yolunda alpha testinin yalnız üretilmiş HLSL
içindeki discard ile temsil edildiğini esas alır; color mask0 ve shader'da
discard/clip/depth/coverage/UAV olmaması şartları korunur. Guest enable biti
tek başına optimize edilen programın yan etkisi değildir.

`gain40-04` gerçek HLSL uygunluğuyla108 PSO'ya ulaştı; D penceresinde2.060.323
uygun çizim gerçekten hızlı PSO'dan geçti. Görüntü normal fakat13FPS civarı
kontrollerine göre anlamlı kazanç yok: depth D12,774FPS /78,287ms; sonraki
kapalı E12,650FPS /79,054ms. Önceki kapalı C76,960ms olduğundan bu farkla
başarı iddiası kurulmadı; depth-only varsayılan kapalı kaldı.

Tamamen background tile'ını erken eleme adayı: mask A13,061FPS /76,567ms,
B13,340FPS /74,964ms, C12,994FPS /76,960ms. Yaklaşık%2,4 FPS; hedefe yetmez.
72 gerçek M3 fixture'ında112 kabul+176ret tile'ın bütün mask byte'ları aynı.

Ortak erken bitiş varyantı da aynı72 fixture'da byte eşitliğini geçti. Derinlik
bitinin grup genelinde varlığı önceden bilinir; herhangi bir thread'in gerçek
üyelik bulması sonucu kesinleştirir. Atomik OR monotondur: erken bitiş yalnız
gerçek üyelikten sonra olur. Kaçırılan atomik güncelleme en fazla fazladan
özgün iş yapar. Bu varyantın gerçek oyun FPS'si henüz ölçülmedi.

Sonraki sürümde mode2, iki maskeyi de aynı gerçek girdide hesaplar, bütün
tile'ları GPU'da karşılaştırır ve oyun için daima özgün maskeyi kullanır.
Karşılaştırılan tile sayısı da GPU'dan doğrulanır; eksik dispatch veya uyuşmazlık
adayı kapatır. Mode2 ve readback sırasında FPS sonucu kabul edilmez.
`mask-input-request.txt` tek seferlik depth/param fixture'ı çıkarır; FPS
pencereleri capture state/geçişlerini reddeder. Kaynaklar Mac hedefindedir.

Çizim PSO cache slot'u yeniden kullanıldığında alternatif PSO artık ayrıca
sıfırlanır; release/reset yolu da alternatif referansını bırakır. Bu lifecycle
düzeltmesi bir FPS kazancı diye sayılmadı.

## Ortak erken bitiş ve konservatif interval adayı

`gain40-05` ortak erken bitiş A/B/A/B/A: 12,170 /12,344 /12,277 /12,663 /12,191 FPS. Gerçek sahnede GPU doğrulaması 25.200 tile karşılaştırmasında uyuşmazlık0. İzole gerçek girdi replay'inde özgün maske yaklaşık3,96ms, ortak erken bitiş2,26ms; oyun içindeki16ms encoder aralığı yalnız hesap süresi değildir.

Yeni `LightMaskInterval.metal`, pinned SPU integer işlemleriyle tile'ın bütün konumlarını kapsayan sınır kurar; kesinlikle ulaşamayacak ışıkları piksel döngüsünden önce eler. Sıfırdan geçen w sınırı tüm ışıkları korur. Gerçek59ışıklı girdide720 mask byte sonucu aynı, bütün720tile'da her piksel sınırın içinde. Genişletilmiş576GPU fixture'ında2304tile aynı;2232tile containment,72konservatif fallback. İzole replay yaklaşık3,9→1,7ms; **oyun FPS kazancı değildir**. `gain40-06` gerçek oyunda doğrulama ardından30s A/B/A/B/A ölçümünü yürütür; probe/capture kapalı, far-light açık.

Sonraki araştırma adayı önceki üç Edge bloğunun tekrarından daha geniştir: yoğun `jobmod_d0d15ec83992_ea2a0` modülündeki46saf hesap bloğunda mevcut doğrulanmış `BCESSpuRZ.h` aritmetiği. Kanal/DMA/scheduler/double/harici çağrı kapsam dışı; FPCR ve FPSR her çıkışta restore edilir. Bu kaynak yalnız Mac araştırma hedefinde; henüz test/performans sonucu yok.

`gain40-06` son kontrollü sonuç: özgün12,8355FPS /77,9090ms; interval13,9047FPS /71,9184ms; **+%8,33FPS,−5,99ms**. Aynı PID35907, termal1, beş geçerli pencere. Açık tur14,062/13,745FPS, kapalı12,824/12,744/12,936FPS. Gerçek oyun doğrulaması66pass /47.520tile /0uyuşmazlık. Bu faydalı fakat%40hedefini karşılamayan Mac sonucudur; iPhone sonucu değildir.

ARM64 kapsam denemesi:21döngüsüz bloğun2.688tam-context/256KiBLS karşılaştırması geçti; internal/externalLS, iki dönüş biçimi, FZ0/1, FPCR/FPSR korunumu sınandı. Geri kalan25döngülü blok, rastgele sayaçla sonsuz döngü riski nedeniyle bu sentetik koşumda çağrılmadı; gerçek oyun girdisinde mod2ile ayrıca karşılaştırılacak. Altı aritmetik işlemin mevcut9,6milyon lane/op referans testi korunuyor. Varsayılan yol0(özgün).

`gain40-07` gerçek oynanışta ARM64 mod2:1.368.183tam register/LS karşılaştırması,0uyuşmazlık;46bloğun19'u görüldü (kesin liste `math-comparison/validation.json`). İlk FPS turu ek sanitizer derlemesiyle çakıştı; A açıkça geçersiz sayıldı, B yüzey capture korumasıyla reddedildi. Bu turlardan performans sonucu çıkarılmayacak. Yeni `measurement-inhibit.json` işareti, araştırma derleme/testi aktifken FPS pencerelerini reddeder.

`gain40-07/math-clean` altı geçerli pencerede özgün11,9308FPS, maske12,6762FPS, birleşik12,9935FPS: CPU adayının ek kazancı%2,50, birleşik%8,91. A/F kontrolleri11,745/12,113; B/Dmaske12,611/12,741; C/Ebirleşik13,021/12,966. Termal1, profiller/capture/derleme kapalı. Bu hâlâ%40hedefini karşılamaz. Sonraki alt aday aynı46bloğun register değerlerini yerel değişkenlerde tutar; LS/GPR alias durumunda özgün yola döner, her çıkışta bütün yazılmış register'lar publish edilir. Henüz ölçülmedi.

Birleşik yol görsel kontrolünde şehir/karakter tutarlı. Ölçüm dışı son15sCPU+1siz kaydı `gain40-07/diagnostics-math-combined`; aynıUUIDbinary `build/bces01229/symbols/6AEDDDBB-BDAA-3545-BE09-99A93EEB9F57/`. TekGPUkarede render-stage union36,06ms, compute-span7,31ms, timestamp extent79,31ms; bunlar toplanabilir bağımsız iş süreleri değildir. Yoğun modülün RZ blokları hâlâ sıcak; register yerelleştirme adayı bu nedenle ayrıca denenecek. Yeni adayın21döngüsüz bloğu2.688tam-context/LS karşılaştırmasını geçti.

`gain40-08` yerel register adayı gerçek oyunda1.464.994doğrulama/0uyuşmazlık. Altı pencere: özgün12,0182FPS, maske12,6934FPS, birleşik13,0196FPS. CPU ek kazancı%2,57; önceki%2,50ile hemen hemen aynı, register yerelleştirme için ek FPS başarısı yok. Sonra aynı oturumda, değişen GPU iş yükü altında mevcut doğrulanmış dispatch yolunun beş kontrol penceresi başlatıldı.

Ölçüm altyapısında yeni bir karıştırıcı tespit edildi: HostSpuMath'ın deney sayacı saniyede yaklaşık2milyon çağrıda bütün worker'ların aynı cache satırını güncelliyordu. Mevcut dispatch sayaçları zaten128byte/SPU ayrılmışken yeni deney sayacı böyle değildi. Yeni kaynak aynı API/değerleri koruyup SPU-slot başına128byte sayaç kullanıyor; henüz derlenmedi/ölçülmedi. Bu varsayımsal maliyet azaltımı%40başarısı diye sayılmayacak. Eski07/08 sonuçları, ortak sayaçlı araştırma binary'sine aittir.

Yeni iş yükünde dispatch A/B/A/B/A sonucu12,7540→13,0904FPS, +%2,64. Hızlı resolver160milyon çağrı ve1,11milyar negatif stack-reset bypass gerçekten çalıştı; büyük FPS kazancı yok. Bu yüzden bu oran da%40hedefinin tamamlanması sayılmadı.

Sayaç düzeltmesi2688tam-context/LS testini geçti; aynı test16SPU-slot için referans/hızlı toplamlarını ve mismatch latch'ini de doğruladı. İzole sayaç throughput testinde5thread×1milyon çağrı ortak sayaç68,215ms, slot'lu2,193ms;8thread125,790→2,319ms. **Bu oyun FPS'si değildir**; yalnız altyapıdaki çekişmenin varlığını gösterir. `gain40-09` yeni binary ile gerçek oyun karşılaştırmasını yapacak. Yerel register varyantı varsayılan seçilmedi; ayrı `--spu-local-registers` seçeneği korunur.

`gain40-09` slot sayaçlarıyla altı temiz pencere: özgün11,9997FPS, maske12,6408FPS, birleşik12,7046FPS. CPUek farkı%0,505: anlamlı başarı sayılmaz; maske+%5,34, birleşik+%5,87. Sayaç microbenchmark'ındaki büyük fark oyun FPS'sine taşınmadı. Bu, altyapı düzeltmesidir; kendimizin eklediği sayaç maliyetini kaldırmayı%40oyun kazancı diye saymıyoruz. Özgün13,32497FPSreferans ve18,65496FPStarget korunuyor. Yeni odak `docs/critical-progress-next-tr.md`: sıcak fonksiyondan daha güçlü, gerçekten son kalan üreticinin kaydı.

## Uzun kritik-ilerleme kaydı

`gain40-10/critical-progress-clean`, PID40273, UUID19FC7BFA-A4FC-3A78-85B3-74DA20CA5BD9:15s/1.177.295traceolayı, dropped0;18s/6.891CPUörneği, error/truncation0. İlk kısa çakışmalı kayıt primary analizden çıkarıldı; temiz tekrar sırasında yalnız oyun/kayıt çalıştı. Sonra oyun RAM için durduruldu; bu normal test temizliğidir, çökme değildir.

Decoder3.082PPUsnapshot ve149.747başarılıyazıcı grubu çıkardı; eksikgrup0. Eşleme her(row,lane)için en az50artış ve%99benzersizissuer, sabit native thread, en fazla1mseski snapshot ve arada hiçbir gözlenen lane değişimi olmaması ister. Değişip eski değere dönme de reddedilir. Reset/decrease sahiplik kanıtı sayılmaz; birSPU=birLane varsayılmadı.

2.389örtüşen CPUörneğinden89tanesine bağlamsal eşleme yapılabildi. Tamamen tek geride kalan lane kohortu20örnek; bunların14'ü **jobmod_638a73a6476e_e60c0** (58F0,5B20,5C08,6118,6210,6368çevresi). Bütün geride-lane örneklerinde1774dd41c4e8daha sık; bu, "genel olarak meşgul" ile "son kalan" ayrımının önemli olduğunu gösterir.20örnek hâlâ sınırlıdır;14/20bir kesin süre bütçesi veya%70FPSkazancı değildir. Tek son-lane listesinde optimize edilenD0DEdge modülü baskın değil.

638a73kaynağında matris/dönüşüm hesabı gözlendi; fizik/animasyon/zlib adı kanıtsız verilmedi. `8648→6B90→68D8/693C/5A98` çağrı ağının tamamı, tek C blok dönüşünden daha uzun bir guest çağrıdır: `spu_drain_call` sonrası gerçek dönüşü ölçmek gerekir. Sıradaki ölçü bu alt ağın gerçek CPU/wall süresini ve kritik beklemeyle örtüşmesini belirleyecek. End-of-window saat kalibrasyonu kullanıldığından15sarası drift ayrıca ölçülmüş değildir; unsuspended native ancestry bağlamsaldır.

**%40hedefi açık; tamamlanmadı.** iPhone'a kurulum veya GitHubpush yapılmadı.
