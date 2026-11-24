# Otonom Mac araştırma ve ölçüm oturumu

28 Ekim 2026. Kullanıcının yeni tercihi: günlük testler Mac üzerinde otonom
ilerler. Anlamlı, tekrarlanan Mac kare süresi kazancı doğrulanınca iPhone'da
kısa doğrulama istenir. Mac kazancı iPhone için garanti olarak sunulmaz.

## Karşılaştırma hedefi

Eski çalışan `Infamous2BCES` ve iOS hedefi korundu. Ayrı
`cmake/bces-research` hedefi `Infamous2Research` executable'ını üretir.
164 doğrulanmış macOS PPU object'i ve yalnız macOS bağımlılıkları kullanılır;
iOS object/arşivi bağlanmaz. 70 SPU birimi ayrıca macOS SDK ile O2 derlenir,
diğer13 firmware/kayıt nesnesi korunur. Güncel doğrulanmış Metal
lighting/SSAO ve SSAO depth sınırı kaynakları aynı türetilmiş metinlerden
snapshot alınır. Native stack/fiber yolu macOS'un kendi yoludur.

`tools/prepare_host_research.py` kaynak hash'lerini, arşiv hash'lerini,
164 PPU nesnesinin MACOS platformunu ve değiştirilen runtime member
envanterini kontrol eder. `host-research-prepared/manifest.json` kaynak ve
nesne kimliklerini kaydeder. Eski reference runner/runtime dosyaları değişmez.

## Girdi ve serbest oynanış

Runtime `cellPad.c::pad_poll_file` zaten `PS3_PAD_FILE` üzerinden CROSS ve
`LX/LY/RX/RY=0..255` kabul eder; 128 nötrdür. `host_research_control.py`
dosyayı atomik değiştirir. Girdiler özgün `cellPadGetData` yolundan oyuna
ulaşır; öğretici kodu veya dünya donması atlanmaz.

Başlangıç menüsünde CROSS verilir ve bırakılır. Oynanıştaki yukarı bakış
ve sola bakış talimatları sırayla gerçek sağ analog girdileriyle tamamlanır.
Görüntülerden her aşama kontrol edilir. Yalnız dünya çizilmiş olması veya
bir miktar süre geçmesi öğreticinin bittiği kanıtı değildir.
`scene-ready.json` aynı PID/session için iki talimatın ve serbest oynanışın
doğrulamasını taşır; ölçüm aracı bu kanıt olmadan çalışmaz.

## Ölçümün anlamı

Ekran dışı Metal renderer'da yalnız gerçek oyun present command buffer'ının
tamamlanma callback'i kare sayılır. Döngü/sunum isteği sayılmaz; yeni GPU
beklemesi/readback eklenmez. Bu metrik ekran scanout'u veya iPhone FPS'si
değildir. Callback zamanlarından ham interval CSV çıkarılır.

Kapalı/açık/kapalı pencerelerinde kamera ve karakter sabittir. CPU profili,
zaman izi, frame capture ve yeni shader derlemesi ölçümü geçersiz yapar.
Termal sınıf, düşük güç, GPU/compute hataları ve log cap geçişi kontrol edilir.
Her pencere en az45 saniye ve240 interval ister; süreç/session değişirse
reddedilir. Ham olaylarla snapshot sürelerinin eşitliği ayrıca kontrol edilir.
Tek pencere farkı başarı ilanı için yeterli değildir.

## Yeniden üretim

```sh
python3 tools/build_bces_spu_variant.py --sdk macosx --resume
python3 tools/prepare_host_research.py
cmake -S cmake/bces-research -B build/bces01229/host-research -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_ARCHITECTURES=arm64
cmake --build build/bces01229/host-research --parallel 1
python3 tools/run_host_research.py --label unique-session --seconds 1800
```

Komutlar `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer` ve
`TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp` ile yürütülür. Oturum VFS'si
oyuna salt okuma amacıyla symlink verir; hdd/gamedata ve kayıtlar oturuma özel
SSD dizinindedir. Mevcut kullanıcı kayıtları kullanılmaz. Log32MiB'de kapanır;
geçiş ölçüm penceresine gelirse pencere reddedilir. Süre ve2.500MiB fiziksel
footprint sınırı vardır. Bu sınır normal oyun RAM ihtiyacı ölçümü değildir.

İlk aday build47'nin WWS dispatch ve konservatif reset-page kontrolüdür.
Henüz cihaz veya Mac FPS başarısı iddia edilmiyor. REA6.8.0'ın gerçek ELF64
PPC64 girdiyi reddettiği önceki kanıt geçerli; analiz mevcut statik lift ve
orijinal talimatlar üzerinden sürer.

## Gerçek ilk sonuçlar

`dispatch47-02` oturumunda PID8510, UUID
`FF94DB32-6857-381B-9AE1-B07CEFFF42B6`. Makro ×, RY=0, RX=0
sırasını görüntü/OCR ile tamamladı. Son görüntüde “Kargaşaya doğru ilerle”
görev hedefi var; kamera öğreticisinin donmuş dünyası kullanılmadı.

A/B/A/B/A pencereleri45 saniye, ham GPU-completion interval CSV ile ölçüldü.
İlk A15,20FPS idi fakat kendi dört çeyreği12,64/12,61/17,02/18,61FPS
ile belirgin değişkenlik gösterdi. B12,292; C12,180; D12,223; E12,183FPS.
Son dört pencerede sıcaklık sınıfı1, yeni shader/hata/profil/capture yok.
Bu sonuç dispatch adayına anlamlı kazanç göstermiyor; varsayılan kapalı.
İlk A'yı kullanıp %20 gerileme veya kazanç iddiası kurulmadı.

Ayrı tanı: 15 saniye CPU,4942 örnek,613 tick, hata0; 1 saniye iz170129
olay, düşen0. CPU örneklerinde SPU43,68 çekirdek-saniye, renderer6,44,
PPU6,47 görülüyor; paralel CPU süreleri kare bütçesi olarak toplanmaz.
Tam içerilen5 flip aralığında medyan81,56ms; GPU span birleşimi59,65ms,
CPU-GPU bekleme birleşimi38,38ms, drain71,73ms. GPU span birleşimi tüm
pencerenin%72,94'ü; bu bir donanım utilization sayacı değildir. Bu kısa
profil FPS benchmark'ından ayrıdır. İlk tanı penceresinin başında sembol
binary'si kopyalandı; küçük CPU ayrıntıları için daha temiz tekrar gerekir.

Mac'in GPU sınırlaması iPhone'a genellenmedi. Sonraki adım GPU geçişlerini
ayırmaktır. M3 yetenek sorgusu stage-boundary timestamp desteği olduğunu,
draw/dispatch-boundary örneklemenin desteklenmediğini doğruladı.
`MetalPassProbe.m`, render pass'leri bölmeden veya yeni GPU fence eklemeden
bir tam guest karede dört aşama zaman damgası toplar. VS/FS ve pass span'leri
örtüşebilir; süreler toplanmaz. Compute ve gerçek blit encoder süreleri bu
araçta ayrı ölçülmüyor. Normal FPS pencerelerinde araç kapalı olmalı.

Küçük gerçek Metal testinde off/on piksel byte'ları64,128,191,255 olarak
aynı kaldı, zaman damgaları geçerli çıktı. Gerçek intro renderer smoke kaydı
da2 pass ile geçti. Bu sonuç optimizasyon veya oynanış başarısı değildir.
Sonraki `gpu-pass-01` oturumu yalnız önceki **kurulum önbelleğini** APFS COW
ile aldı; kullanıcı/oyun kayıtları kopyalanmadı. Bu oturumda `PS3_VERBOSE=0`
kullanılıyor; eski oturumla mutlak FPS karşılaştırması yapılmayacak.

## GPU ayrıştırması ve uzak ışık adayı

`gpu-world-A/B/C` kayıtlarında110 render encoder ölçüldü. Bazı clear-only
geçişler için fragment zaman damgaları0/0; ilk ham rapordaki `span_ms` bu
satırlarda epoch0'dan hesaplanmıştı. Bu alanlar kullanılmadı. Ham kayıtlar
korunarak `tools/analyze_gpu_passes.py` ile yeniden hesaplandı. Yeni native
probe ve clear-only GPU regression testi bu durumu düzeltiyor. VS/FS arası
kuyruk boşluklarını shader hesap süresi saymamak için aşamalar ayrı sıralanır.

Aydınlatma fragment aşaması üç kayıtta17,19 /7,91 /17,32ms; bazı guest
geçişleri yaklaşık14ms,8ms ve6ms seviyesinde. Bu değişken tek-kare kayıtları
kazanç veya kesin kare bütçesi değildir. İlk doğrudan aday aydınlatma shader'ı.

`prepare_lighting_far_reject.py` özgün shader'ı korur, ayrı bir fragment
variant üretir. Işığa uzaklık karesi, radius karesinden128 epsilon'dan fazla
uzaksa, scalar/spot parametreleri güvenliyse ve normal sonlu büyüklükler
kullanılıyorsa, özgün attenuation'ın kesin sıfır olacağı light iteration
atlatılır. Küçük/sonlu olmayan/alışılmadık girdiler özgün işlemleri yürütür.
Tile maskesi, alpha tabanı ve RGBM/specular paketleme değiştirilmez. Genel
fast-math veya çözünürlük düşüşü yok. Normal başlatmada aday kapalı.

Dokuz önceki fixture'da referans/aday GPU diffuse+specular byte'ları aynı.
Ayrıca2/8/32/128 ışıklı, bir yakındaki ışık ve kalan uzak ışıklardan oluşan
karışık tile'larda byte eşitliği korundu. Ayrı tanı shader'ındaki atomik sayaç
sırasıyla1.280 /8.960 /39.680 /162.560 gerçek erken eleme saydı. Bu sayaç
oyunun performans shader'ında bulunmaz. Kanıtlar `out/lighting-far-guard/`
ve `out/lighting-far-mixed-test/`. Bu sınırlı girdi testleri tüm oyun doğruluğu
veya uçtan uca FPS kanıtı değildir.

`lighting-far-01` Mac oturumu, varsayılan kapalı aday ve nonce/session
kontrolüyle açıldı. `run_host_light_comparison.py` makro kanıtını bekler,
serbest oynanış sonrası60 saniye ve yeni shader sonrası20 saniye durulma
ister; sonra45 saniyelik kapalı/açık/kapalı/açık/kapalı pencereleri toplar.
Her mod geçişinden sonra10 saniye bekler. Renderer memoları/dispatch adayı
kapalıdır. Gerçek seçilen PSO'nun pass sayacı ve faults alanı da kontrol edilir.
Henüz FPS kazancı sonucu yok; iPhone kurulumu/testi yapılmadı.
