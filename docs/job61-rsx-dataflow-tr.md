# SPU sonuçlarının RSX'e ulaşması

Build 61 gerçek iPhone 15 Pro'da, kayıtlı bataklık iskelesinde nötr girişle
çalıştırıldı. Oyun yüzeyi üzerinden sahne doğrulandı. Aynı süreçten iki ayrı
1 saniyelik iz alındı. İz A 467.432, iz B 418.650 olay içeriyor. İkisinde de
olay kaybı ve yarım veri grubu sıfır. Termal durum 1, yani `fair`. Ölçüm
bittiğinde kayıtlar `idle` durumuna döndü ve test süreci kapatıldı.

Build 60'taki ilk iz kapasiteyi aştı ve reddedildi. Build 61, seçili işlerin
PUT'larını tutuyor, GET'leri bu işlerin dokunduğu sayfalarla sınırlıyor ve
FIFO'da yalnızca 32 bayta hizalı gerçek 4 baytlık okumaları kaydediyor.
Rapor bu örnekleri tüm FIFO okumalarına oranlamıyor.

| Üretici ve gözlenen tüketici | İz A | İz B |
| --- | ---: | ---: |
| `867e` PUT'larından `1774dd` GET'iyle örtüşen ayrı aktarımlar | 320 | 288 |
| `43398b` PUT'larından `1774dd` GET'iyle örtüşen ayrı aktarımlar | 157 | 142 |
| İlk sözcüğü gerçek RSX okumasıyla eşleşen ayrı `1774dd` PUT'ları | 2.101 | 1.875 |
| `867e` verisini okuyan ve RSX tarafından doğrulanan çıktı yayımlayan `1774dd` çağrıları | 1.261 | 1.091 |
| `43398b` verisini okuyan ve RSX tarafından doğrulanan çıktı yayımlayan `1774dd` çağrıları | 1.261 | 1.091 |

Son iki satır her üretici için ayrı sayıldı. Aynı `1774dd` çağrısının hem
önceki tamponu DMA ile okuduğunu hem de renderer'ın okuduğu bir komut
bloğunu yayımladığını gösteriyor. Bir DMA tamponunun her baytının hesapta
kullanıldığı sonucunu çıkarmak için yerel veri akışının da incelenmesi gerekir.

## Kaynak bağlantısı

- `867e`, `0x4B70` ve `0x4C08` dönüş adreslerinde, `43398b` ise `0x4568`
  ve `0x4608` dönüş adreslerinde 512 baytlık kayıtlar ve değişken boylu
  ek bloklar yayımlıyor.
- `1774dd` içinde `0x43D0` kayıt sayısını 512 ile çarpıyor ve `0x18D60`
  DMA yardımcısını çağırıyor. Dönüş adresi `0x4418`. Her iki üreticinin
  kayıtları bu GET'lerin okuduğu aralığa giriyor. `0x130A0` ikinci okuma
  noktası olarak görüldü. İki üreticinin oyun içi adları henüz bilinmiyor.
- `1774dd` içinde `0x13BC8`, `0x14388` üzerinden `0x143C0` DMA yazısına
  ulaşıyor ve 4 KiB komut bloğunu yayımlıyor. İkinci sık dönüş adresi
  `0x14190`. `cellGcm_rsx_process_fifo` bu bloklardan gerçek komutlar
  okuyor. Eşleşen başlıklarda `0x1EFC` vertex sabiti yükleme ve `0x181C`
  index dizisi adresi ayarı görüldü. Adlar pinned `rsx_commands.h` ile eşlendi.

Ham ELF eşlemesi `867e` için `0x007D0A80`, `1774dd` için `0x007D7B80` ve
`43398b` için `0x0085EE80` adreslerini gösterdi. Bu adresler modül kayıt
referanslarını doğrular. Yanlarındaki OPD girdilerine tüketici adı verilmedi.

## Zamanlama ve karar

Her PUT için ilk gözlenen `1774dd` GET'ine kadar medyan `867e` için
5,68–5,80 ms, `43398b` için 4,35–4,69 ms. Doğrulanmış komut bloğunun PUT'u
ile ilk örneklenmiş eşleşen FIFO okuması arasındaki medyan 83,83–92,71 ms.
Bunlar verinin hazır olmasıyla gözlenen okuma arasındaki aralıklardır.
Ana thread'in veya FIFO'nun üreticiyi beklediği süreyi ölçmek için
ayrıca bekleme giriş/çıkışının ve yayımlanan kaydın eşlenmesi gerekir.
Her iki kısa izde örneklenen tam kare pencerelerinde RSX acquire süresi
sıfırdı. Bu ölçüm, başka bekleme türlerini kapsamaz.

Arada gözlenen DMA yazıları en son yazılan aralığı belirlemek için
kullanıldı. Çakışan yazılar ve ilk sözcüğü tutmayan 558 FIFO aday eşleşmesi
çıkarıldı. PPU ve GPU yazıları ile atomik yazıların tümü izlenmedi. PPU skaler
okuma noktalarında bu çalışmada eşleşme çıkmadı. FIFO sözcük doğrulaması
yalnızca kaydedilen dört baytı kapsar. Ölçüm araçlarının maliyeti nedeniyle
kare aralıkları teşhis içindir.

Bir sonraki hedef `1774dd` komut üretiminde `0x43D0 → 0x18D60` veri alma
aşamasını ve `0x13BC8 → 0x143C0` komut yayımlama aşamasını ayrı ölçmek.
Bu ayrım yoğun maliyetin girdi toplama, komut hazırlama veya kuyruk beklemesi
tarafında olup olmadığını gösterecek. Üreticinin gerçekten geciktiği kare
gösterilebilirse optimizasyon denemesi o aşamaya odaklanabilir.

## Tekrar üretme

Build 59'un doğrulanmış SPU arşiviyle `tools/prepare_bces_ios.py`
`--support-report out/bces-support-critical59.json --job-flow` çalıştırıldı.
Xcode Release iPhoneOS hedefi `-jobs 1` ile derlendi ve imzalandı.
Derleme, kurulum ve açılış kayıtları `out/ios-job61/` altında. Açılışta
mevcut birleşik ayarlar yanında `--diagnose-frame --diagnose-job-flow`
kullanıldı. Gerçek cihazda `tools/capture_frame_trace.py --seconds 1` ile
iz alınır. `tools/analyze_job_flow.py` tam izi okuyup aralık eşleşmesini
ve FIFO ilk sözcük doğrulamasını yapar.

```sh
export PYTHONPATH=tools
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
python3 tools/analyze_job_flow.py out/ios-job61/trace-A/frame-trace.csv \
  --binary build/bces01229/baselines/job61-flow/Infamous2Game.app/Infamous2Game \
  --output out/ios-job61/trace-A/job-flow.json
```

Native ASan/UBSan kapsam testi, 17 mevcut analiz testi ve kısmi/örtüşen
DMA üzerine doğrudan eşleştirme kontrolleri geçti. Her iki cihaz izi
aynı PID ve binary UUID ile doğrulandı.
