# RSX çizim hazırlığı ve Metal gönderimi

Build 63, iPhone 15 Pro üzerinde kayıtlı bataklık iskelesinde çalıştırıldı.
`scene-C` oyun yüzeyini doğruladı. Aynı süreçte üç ayrı bir saniyelik iz
alındı. A, B2 ve C2 sırasıyla 398.576, 406.134 ve 366.889 olay içeriyor.
Üçünde de olay kaybı sıfır ve kayıt sırasında termal kategori 1.
İlk B denemesinde dosya kanalı kayıt başlamadan kapandı. B2 tekrarında
aynı süreç doğrulandı. Cihazda test süreci kayıtlar kapatıldıktan sonra
sonlandırıldı. Son raporda termal kategori 2 görüldü.

`RendererStageTrace.h` FIFO gövdesini, çizim hazırlığını, vertex açmayı,
doku hash'ini, Metal staging'i, senkron gönderimi ve guest writeback'i
aynı zaman çizelgesinde işaretliyor. CPU ölçüsü işi çalıştıran thread'in
saati. Metal komutları mevcut commit ve tamamlanma kimlikleriyle eşleniyor.
Sınır olarak ardışık sunum komutlarının gönderimleri kullanıldı. Her izde
dört tam pencere ve kare başına üç backend gönderimi doğrulandı.

| Kare başına medyan, ms | A | B2 | C2 |
| --- | ---: | ---: | ---: |
| Sunum gönderimleri arası | 108,52 | 115,79 | 127,42 |
| FIFO gövdesi thread CPU | 66,45 | 65,98 | 66,25 |
| Çizim hazırlığı thread CPU, iç aşamalar dahil | 46,02 | 45,48 | 46,09 |
| Vertex hazırlığı thread CPU, açma dahil | 21,37 | 21,45 | 21,91 |
| `rsx_vertex_fetch_all` thread CPU | 12,16 | 12,72 | 13,20 |
| Vertex açmanın Metal kuyruğu boşken geçen duvar süresi | 11,10 | 9,66 | 13,11 |
| Bu açmanın ilk gönderimden önceki boşluğa düşen kısmı | 4,24 | 3,28 | 7,39 |
| Doku hash'i thread CPU | 4,44 | 4,66 | 5,01 |
| Metal staging thread CPU | 4,48 | 4,34 | 4,47 |
| Senkron CPU–GPU beklemelerinin birleşimi | 17,18 | 16,70 | 18,83 |
| Bu beklemelerin ölçülen GPU işiyle örtüşen kısmı | 13,52 | 13,72 | 13,81 |
| İki tam yüzey geri okumasının birleşimi | 3,51 | 3,55 | 3,43 |

Satırlar iç içe ve paralel kapsamlar içeriyor. GPU kuyruğu boşluğu,
izlenen backend komutlarının son tamamlanması ile bir sonraki gönderim
arasından hesaplandı. Vertex örtüşmesi yalnız kuyruğu besleyen seri FIFO
thread'indeki vertex açma kapsamlarından hesaplandı.
Zaman damgası aynı olan iç içe vertex kapsam çiftleri ayrıştırılamadı
ve dışarıda bırakıldı. Her izde bu çakışmaların tekil duvar aralığı
toplamı 1,13–1,29 ms; tam karelere giren açma kapsamları 43.537 adet.
Çağrı başı iz maliyeti ve kısa pencereler nedeniyle tablo FPS
karşılaştırması olarak kullanılmaz.

## İlk aday

`sink_end → dc_fetch → rsx_vertex_fetch_all` seri CPU yolunda kalıyor.
`rsx_fetch_source`, her vertex ve attribute için kaynak elemanı yeniden
hesaplıyor. `RSX_FETCH_LOOP` guest biçimini 16 baytlık host attribute'a
açıyor. `eng_draw` daha sonra genişletilmiş vertex verisini Metal
staging'e kopyalıyor. İlk aday, eşdeğerliği doğrulanabilen düzenli ve
çözülmüş kaynak aralıklarında CPU'nun tam float açmasını atlayan
kompakt vertex yolu. Dar prototipte seçilen biçim Metal vertex
aşamasında açılabilir; index eşlemesi, restart, byte sırası ve varsayılan
bileşenler korunmalı. Seçilebilen biçimlerin gerçek cihaz kapsamı ve
GPU'ya eklenen süre, özgün yol ile A/B'de ölçülmeli. Eski vertex memo
denemesiyle aynı tasarım kullanılmıyor.

Geri okuma hâlâ ayrı bir aday. `nv3089_blit` ve
`rsx_draw_engine_write_back_to` üzerinden renk ve derinlik geri dönüşleri
devam ediyor. Beklemenin 13,5–13,8 ms'si izlenen GPU çalışmasına
denk geliyor; kopya kaldırılınca o GPU işinin de yok olacağı varsayılmadı.
Özgün SPU fallback ve derinlik tüketimi için önce güvenli sahiplik
kanıtı gerekir.

## Tekrar üretme

`prepare_bces_ios.py --support-report out/bces-support-critical62.json
--renderer-stages` ile türetilmiş kaynaklar, Release iPhoneOS ve
`-jobs 1` ile imzalı build hazırlandı. `--diagnose-frame` ile açılıp
`capture_frame_trace.py --seconds 1` ile kayıt alındı. Derleme,
kurulum ve ham kayıtlar `out/ios-render63` altında.

```sh
PYTHONPATH=tools python3 tools/analyze_renderer_stages.py \
  out/ios-render63/trace-A/frame-trace.csv --output out/ios-render63/trace-A/stages.json
```

İki mevcut zaman çizelgesi testi ve sentetik sunum eşlemesi, iç içe
bekleme birleşimi ve GPU boşluğu denetimi geçti.
