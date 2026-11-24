# Geometri cihaz karşılaştırması — build41 / 26 Ekim 2026

Gerçek iPhone15Pro, aynı süreç PID2820 ve kullanıcı teyitli ilk oynanış. Karakter/kamera sabit. Uygulama yeniden başlatılmadı. Metal aydınlatma ve Metal SSAO bütün turlarda açık; yalnız skinning/culling yolu değiştirildi. Ağır CPU/Metal profiler yok. Örneklenen termal durumların tamamı0 (Normal).

## Sonuç

**Bu paketle geometri hızlandırmasını etkinleştirmiyoruz.** ARM64/ARM64 bu sahnede anlamlı FPS kazancı göstermedi. Mevcut Metal yolları belirgin derecede yavaş. Özgün SPU yollarına dönünce performans toparlandı; uygulama bu durumda açık bırakıldı.

Etiket sırası Skinning / Culling. Süre sütunu pencere süresi/kare sayısıdır; özellikle az kareli GPU turlarında yaklaşık bir throughput ölçüsüdür.

| Yol | Süre (s) | Kare | FPS | Yaklaşık ms/kare |
| --- | ---: | ---: | ---: | ---: |
| SPU / SPU · ilk | 32.00 | 199 | 6.219 | 160.8 |
| ARM64 / ARM64 | 32.00 | 195 | 6.094 | 164.1 |
| Metal / Metal | 32.00 | 4 | 0.125 | 8000.0 |
| ARM64 / Metal | 31.00 | 5 | 0.161 | 6199.9 |
| Metal / ARM64 | 32.00 | 15 | 0.469 | 2133.4 |
| SPU / SPU · tekrar | 32.00 | 195 | 6.094 | 164.1 |

SPU başlangıç6,219 ve tekrar6,094FPS; ARM64/ARM646,094FPS. Küçük farkla ARM64 yolu daha iyi veya kalıcı olarak daha kötü diye karar verilemez; gözlenen referans değişimi aynı büyüklükte. Varsayılan özgün yol korunuyor. Metal turlarında yalnız4,5,15 kare var: kesin jitter/p95, %1 low veya hassas hız oranı iddiası yok. Ancak 6FPS referansına karşı çok büyük yavaşlama açıktır.

## Doğruluk ve gerçekten seçilen yol

ARM64 doğruluk penceresinde11,000s: 36.223 skinning ve36.223 culling karşılaştırması; Metal doğruluk penceresinde11,000s: 766 skinning ve767 culling karşılaştırması. Tam mimari çıktı karşılaştırmalarında uyuşmazlık/hata yok. Bunlar aynı sahnedeki sınırlı girdilerdir; bütün oyun/görsel eşdeğerlik testi değildir.

Metal kaynak/PSO ilk kez arka planda hazırlandı. Hazırlık sırasında özgün SPU fallback çalıştı; bu bölüm FPS karşılaştırmasına alınmadı. Deneysel performans pencerelerinde doğru route, doğrulama kapalı ve validation delta0; Metal kullanılanlarda state2. İlk SPU referansında anahtar açıktı ama route0 üzerinde karşılaştırma çalışmaz; bu referansta da validation delta0. Her iki işte mismatch/failure/blocked0; pencere içi fallback delta0. Eski hazırlık fallback sayıları kümülatif sayaçta durur ve performans turlarının fallback yaptığı anlamına gelmez.

Bütün performans kayıtlarında guest kare artışı ile Metal presented/completed artışı eşit. FPS HUD ortalamasından değil bu sayaç farkı / cihaz monotonic zaman farkından hesaplandı.

## Donmuş görüntü ve maliyet kanıtı

Metal/Metal seçiliyken kullanıcı donma bildirdi. Rapor zamanı ve iş sayaçları ilerliyordu;32s içinde4 gerçek kare üretildi. Tam kilitlenme sonucu yazılmadı: mevcut yol kare başına yaklaşık8s sürerek donmuş görüntü izlenimi verdi. SPU dönüşünde6,094FPS toparlanması aynı süreçte doğrulandı.

Metal/Metal penceresinde2.320 skinning +2.320 culling çağrısı/4 kare, yani işlem başına yaklaşık580 çağrı/kare vardı. Skinning GPU zaman aralıkları toplam7.353ms, culling22.457ms: yaklaşık3,17ms ve9,68ms/çağrı. Tek GPU kuyruğundaki bu aralıklar toplamı32s pencerenin yaklaşık%93ünü kapsıyor. Bu, iki işlevin bu sınırda GPUya aktarılmasının neden pahalı olduğuna güçlü kanıt.

`src/platform/GeometryKernels.mm::MetalState::run` her çağrıda çalışma LS/GPR tamponlarını kopyalıyor, compute komutunu veriyor, `waitUntilCompleted` ile CPU sonucunu bekliyor; ortak mutex kaynak kullanımını seri tutuyor. `tools/geometry_parallel.py` skinning döngülerini paralelleştiriyor fakat çağrılar hâlâ yüzlerce küçük iş halinde gönderiliyor. Culling Metal çekirdeği seri doğruluk referansı; paralel culling hızlandırması değil.

Bu kayıtlar saf shader ALU, tampon kopyası, submit, mutex beklemesi ve commit maliyetlerini ayrı ayrı ölçmez. GPU skinning/cullingin daha iyi bir tasarımla yararlı olamayacağı sonucu çıkarılmaz. Mevcut prototipin seçilen sınırda yararlı olmadığı ölçülmüştür. Yeni GPU denemesinden önce boş/küçük çağrıları CPUda bırakma, yalnız ağır işleri toplu gönderme ve cullingin gerçek paralel kernel tasarımı değerlendirilmelidir. Bunlar henüz uygulanmadı ve kazanç garantisi verilmez.

ARM64 zamanları da tek kareden çıkarılacak tasarruf değildir. `bces_geometry_execute` içindeki `trial_ms` giriş kopyası + hesap/beklemeyi kapsar; son dirty-LS/GPR commitinden önce kapanır. Birden çok SPU işinin wall süreleri örtüşür. Kesin karar için bu oturumda uçtan uca FPS esas alındı.

## Tekrar üretme ve kayıtlar

`out/geometry41-device-tests/result.json` birleşik sonuç. Her tablolu turun alt klasöründe ham cihaz JSONları ve `summary.json` bulunur. İlk kurulum öncesindeki rapor/CSV `preinstall/` altında korundu. Kontrol ve test kayıtları Git dışında.

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
python3 tools/capture_device_window.py --device 00008130-001129E00243001C --output out/geometry-next-window --seconds 30 --scene first-gameplay-fixed-user-confirmed --max-thermal-state 0 --geometry-pair 1 1
# Doğrulama turunda --geometry-check validation eklenir; route0 SPU,1 ARM64,2 Metal.
```

Komuttan önce sahne/kamera teyidi gerekir. Preset ve doğrulama seçimi panelden yapılır; shader hazırlığı ve ilk8 zorunlu karşılaştırma pencereden önce bitmelidir. Araç yanlış route, aktif doğrulama, yeni hata/uyuşmazlık, blocked yol, hazır olmayan Metal veya sıcaklık artışında performans sonucunu reddeder.

Son durum: skinning SPU, culling SPU, aydınlatma/SSAO Metal, sürekli geometri doğrulaması kapalı. Oyun açık; yeni optimizasyon veya yeni build uygulanmadı.
