# Build45 — görüntü düzeltmesi ve önbellek denemesi

27–28 Ekim 2026. Gerçek iPhone15Pro; aynı PID7392 ve ilk oynanışta sabit
karakter/kamera. **Anlamlı FPS kazancı bulunmadı; araştırma amacı sürüyor.**
GitHub'a değişiklik gönderilmedi.

## Görüntü kapısı

Build44, iki aday kapalıyken bile sinematikte renkli şekillere bozuldu. Bu
sürümün FPS ölçümü yapılmadı. Build45 çalışan runtime arşivindeki
`rsx_vertex_compact.o` nesnesini byte olarak aynen korur; kapalı modda özgün
decoder ve sahipli vertex tamponu kullanılır. İki değişken beraber geri
alındığından tek kök nedenin izole edildiği iddia edilmiyor.

Build45 UUID: `BB5566B3-8B31-3B3E-BD10-A00609538BBD`.
Binary SHA256: `69f28ba792f8bbf69b0f775d90e5bb4799c85472570a823b325a150ef0d1729d`.
iPhoneOS Release/jobs1 derlendi, imzası doğrulandı ve aynı bundle'a kuruldu.
Oyun dosyaları/kayıtlar silinmedi. Geri dönüş build43 uygulaması
`build/bces01229/baselines/renderer44-app/Infamous2Game.app` içinde duruyor.

Kullanıcı oynanışın normal olduğunu teyit etti. Gerçek cihazdan token ile
alınmış kareler `out/critical-path43/45-gameplay-reference/frame.png`,
`45-vertex-visual/frame.png`, `45-texture-visual/frame.png` altında. Yeni kare
alma aracı yalnız açık istek gönderildiğinde GPU fence/readback yapar; FPS
pencerelerinde kullanılmadı ve sonrasında en az8s beklenildi.

## Doğruluk ve gerçek FPS

Host ASan/UBSan:3.244 decoder karşılaştırması; renderer fixture mod0/1/2'de
yeni hata yok (SDK'nın aynı dört bilinen fixture uyuşmazlığı korunuyor).

Sinematik doğruluk turunda168.155vertex/31.506hash, ayrı oynanış doğruluk
penceresinde649.494vertex/54.685hash karşılaştırması: uyuşmazlık0. Doğrulama
modu özgün sonucu çizer; bu pencereler FPS benchmark'ı değildir. Kontroller
bu sahneleri kapsar, bütün oyunun test edildiği anlamına gelmez.

FPS kayıtları ham drawable sunum olaylarından; profiler/trace ve doğrulama
kapalı, Metal aydınlatma/SSAO açık, geometri SPU/SPU, RSX hızlı yol açık.
Termal sınıf bütün geçerli örneklerde2(sıcak); bu, eşit çip frekansı garantisi
değildir. Yeni shader, renderer hatası ve bellek uyarısı geçerlilik kapıları
kontrol edildi. İki aday arasında ayrı kapalı kontroller alındı.

| Tur | Vertex/texture modu | Gerçek aralık | FPS | Ortalama ms | Log sınırı |
| --- | --- | ---: | ---: | ---: | --- |
| A | 0/0 | 196 | 6,139 | 162,895 | Kapalı |
| B | 1/0 | 187 | 6,029 | 165,854 | Kapalı |
| C | 0/0 | 188 | 5,859 | 170,691 | Kapalı |
| D | 0/1 | — | Geçersiz | — | Pencere içinde değişti |
| E | 0/0 | 192 | 5,810 | 172,106 | Açık |
| F | 0/1 | 185 | 5,795 | 172,558 | Açık |
| G | 0/0 | 181 | 5,837 | 171,329 | Açık |

0=özgün,1=tüm girdi byte'ları eşleşirse önbellek,2=özgün sonuçla doğrulama.
Log sınırı açık, uygulamanın16MiB sonrasında log yazmayı kapattığını ifade eder.
D reddedildi; farklı log durumundaki pencereler birleştirilmedi.

Yanlardaki kontrollerin toplam frame/toplam sunum süresi ile:

- Vertex:A+C **5,998FPS**; B6,029FPS, fark+%0,517 (~0,858ms).
  %88,98 çağrı isabeti anlamlı uçtan uca kazanç vermedi.
- Texture:E+G5,823FPS; F5,795FPS, fark−%0,481 (~0,829ms daha uzun).
  %95,50 çağrı isabeti kazanç vermedi.

Bu küçük farklar normal değişkenlik içinde. Birleşik yol için kazanım varsayılmadı.
İki deney normal başlatmada kapalıdır. A/B sırasında tahsis edilmiş önbellekler
kapalı turda da tutuldu; her adayın metadata dahil sınırı128MiB. FPS pencereleri
fiziksel footprint'i yaklaşık1,26–1,28GB gördü; en son tanı araçlarıyla1,36GB.
Önbellek byte sınırı fiziksel RAM veya bütün uygulamanın sınırı değildir.

Ham kayıtlar ve birleştirme sonucu `out/critical-path43/45-perf-*/` ve
`memo45-ab-result.json` içinde. Hiçbir aday varsayılan olarak etkinleştirilmedi.

## Neden FPS artmadı: ek tanı kanıtı

UUID eşleşen ayrı15s CPU kayıtlarında renderer thread CPU süresi kapalı8,360s,
vertex açık7,657s. İstatistiksel exclusive PC atfında decoder1,444s→0,188s;
yeni arama/kontrol işlevlerinin de maliyeti var. Bu ayrı pencerelerden kesin
bir kare bütçesi çıkarılmıyor; sistem leaf ancestry ek CPU gibi toplanmıyor.

Ayrı10s zaman çizelgelerinde her tur55tam flip aralığı ve düşen olay0:

| Aynı saatli trace medyanı | Kapalı | Vertex açık |
| --- | ---: | ---: |
| FIFO drain birleşimi | 152,397ms | 141,960ms |
| GPU yürütme birleşimi | 54,880ms | 53,861ms |
| Ana PPU kısa bekleme birleşimi | 63,943ms | 69,302ms |
| Ana PPU kısa beklemelerinin drain dışında kalan kısmı | 0ms | 9,938ms |

Son satır bağımsız medyanların farkı değildir: **her karede aralık kesişimleri**
hesaplanıp sonucun medyanı alınır. Drain; mutex/GPU beklemesi ve scheduling de
içerir, exclusive CPU sayılmaz. Usleep aralığı scheduling de içerebilir.

Drain dışında kalan bekleme en çok `0x370694`/`0x3706BC` çağrı noktalarında.
Özgün `func_0037062C`, `func_005054F0` üzerinden iş kuyruğu/ilerleme kontrolü
yapıyor; `func_00504DF0` ise yedi16bit ilerleme lane'inin minimumunu karşılaştırıyor.
Bu bulgular renderer'ın daha erken ilerlemesiyle başka bir üretici bağımlılığının
görünür hale gelmesiyle uyumlu; geciken SPU işi veya kesin üretici henüz belirlenmedi.
Beklemeyi silmek, eksik sonucu tamamlanmış saymak veya doğrudan bir Edge işine
suç atmak için kanıt yok.

Sıradaki araştırma: bu kuyrukta geciken gerçek ilerleme lane'ini ve yazıcısını
bağlamak; sonra o üreticinin ağır işini seçmek. Yeni kör Metal/ARM64 denemesi
yapılmadan önce bu bağımlılık kanıtlanmalı.

## Tekrar üretme araçları

Çalışma klasörü `/Volumes/monssd/Infamous2-iOS`; her yeni kayıt için benzersiz
çıktı klasörü seçilir. Cihaz kontrolleri aynı süreç nonce'unu doğrular.

```sh
python3 tools/capture_device_frame.py --device 00008130-001129E00243001C --output out/yeni-kare
python3 tools/geometry_device_control.py --device 00008130-001129E00243001C --output out/yeni-mod --vertex-memo 1 --texture-memo 0
python3 tools/measure_renderer_memo.py --device 00008130-001129E00243001C --modes 1 0 --thermal-state 2 --output out/yeni-fps
python3 tools/analyze_progress_overlap.py out/critical-path43/45-timeline-on/frame-trace.csv --output out/yeni-overlap.json
python3 -m unittest tools/tests/progress_overlap.py
```

Son kontrol:PID7392 aynı, iki memo modu0, iki uyuşmazlık sayacı0, Metal hata0.
Profiler/trace kayıtları tamamlandı ve kontrol dosyaları idle yapıldı; oyun açık.
