# %40 hedefi için sonraki teşhis kapısı

29 Ekim2026; tasarım, henüz uygulanmış kayıt değildir. Önce `gain40-09` sayaç çekişmesi düzeltilmiş gerçek-kare karşılaştırması tamamlanacak. Maske +%8,33, geniş RZ yaklaşık +%2,5, register yerelleştirme ek fark0, dispatch yeni iş yükünde +%2,64 seviyesinde. Bunlar %40 hedefini karşılamıyor.

CPU'da sıcak görünen bir fonksiyonu hızlandırmanın kritik kare zincirini kısalttığı varsayılmayacak. Sonraki kayıt, PPU'nun beklediği ilerleme satırındaki hedefe en son ulaşan SPU'nun o sırada ne yaptığına yoğunlaşmalı. Eski ortak kayıtta yalnız19SPU örneği kabul edildiği için küçük altküme büyük optimizasyon kararı için yeterli değildi.

- `ProgressTrace.cpp` için Mac'te opt-in compact mod: bütün başarılı yazıların mevcut320..326çekirdek olayları korunur. Her yazıda backtrace ve iş-başlığı okumaları çıkarılır. PPU300..305snapshot anlamı aynıdır; başarısız atomikler yazı sayılmaz. iOS varsayılan ayrıntılı yol korunur.
- İlk yazıda SPU/native-thread eşlemesi18kaydı açıkça üretilir; busy worker'ın bir wait'e girmesi beklenmez.
- Mac trace ring2milyon kayıt (yaklaşık80MBüst sınır); iOS500bin korunur.15s trace ile18sCPU kaydı aynıUUID/monotonic kalibrasyonuyla örtüşür. Dropped/truncated kayıt kabul edilmez.
- Aynı row/target için lagging lane, gerçek lane değişimleri, son başarılı publisher ve o native thread'in aradaki CPU örnekleri eşleştirilir. CPU örnekleri iş süresi diye toplanmaz. Bekleme kaydındaki bütün süre kazanç sayılamaz.
- Analizden önce oyun durdurulabilir; böylece büyük CSV/JSON analizi8GBMac'te oyunla RAM paylaşmaz. Ölçüm sırasında başka build, GPU fixture veya yüzey capture yok.

Karar: belirli iş/kuyruk gerçekten kritik zincirde tekrarlandığında onun algoritması veya senkronizasyon aktarımı seçilir. Rastgele yeni ARM64/Metal taşıması bu kaydın yerine konulmaz.

Compact kayıtla korelasyonun uyarlanması gerekir: mevcut `correlate_progress_cpu.py` ownership için her yazıda WWS0x3450native stack kanıtı istiyor. Compact modda bunlar yoksa sonuç boş kalır. Ayrı açık `issuer-only` modu, bütün gerçek lane değişimlerinden SPU/native-thread eşlemesini her(row,lane)için en az50artış ve%99benzersiz issuer tutarlılığıyla kurmalı; ortak lane1 ve belirsiz lane'ler dışarıda kalır. Bu mod yayıncının tam native çağrı zincirini veya belirli job'ın bittiğini kanıtlamaz; rapor bunu açıkça belirtmeli. Eski ayrıntılı yöntem korunur. Sentetik sahiplik/karışık-yazıcı/eksik-thread fixture'ları gerekir.

## Hazırlanan kaynaklar

Compact mod `ProgressTrace.{h,cpp}` içine opt-in olarak eklendi; iOS varsayılanı0, Mac ResearchMain1seçer. Mac ring2milyon, iOS500bin; paylaşılan runtime state struct'ı değiştirilmedi. Kısa nativeASan/UBSan testi çekirdek7DMAolayını, ilk/native18eşlemesini ve dedup'u, ayrıca mevcut read-only/bounds/queue kurallarını geçti. Issuer eşlemesinin dört saf testi, mevcut yazıcı decoder'ının üç testi geçti. `capture_host_diagnostics.py --trace-seconds 15` artık18sCPU+15strace üretir. Gerçek uzun kayıt henüz alınmadı.

Eski bir saniyelik kaydın yeniden incelenmesi, tüm lane değişimlerinin doğrudan sahiplik sayılamayacağını gösterdi: reset/decrease yayınları ve bir publisher'ın birden çok lane'i güncellemesi var. Yeni issuer-only analiz yalnız artışları kullanır; her(row,lane)için benzersizissuer arar, birSPU=birLane varsaymaz. Bir CPU örneğinde aynı publisher'a ait birden fazla lane aynı anda gerideyse örnek belirsiz sayılır. Eşik gevşetilmedi; veri modeli düzeltildi. Dört sahiplik testi bunu kapsıyor. CPU eşlemesi için1msazami snapshot yaşı ve100usazami saat kalibrasyon genişliği seçildi.

## Gerçek kayıt tamamlandı

`gain40-10/critical-progress-clean`:15s1.177.295olay/dropped0,18s6.891CPUörneği/error0;3.082snapshot,149.747tam yazıcı grubu. Beş nativeSPUthread eşlendi.1msveara-lane-değişimi filtreleri sonrası89eşleme;20tek-toplam-geride-lane örneğinin14'ü638a73modülüne ait. Henüz kesin süre bütçesi yok.

Sonraki somut probe:638a73kaynağında8648'in6B90'ı çağırdığı satırda call+`spu_drain_call(ctx,0x866C)` bütünü braketlenmeli. Yalnız6B90Cişlevinin return'ü tüm guest alt ağın dönüşü değildir. Alt çağrılar68D8/693C/5A98 kaynağı incelenecek. İşin resmi adı belirlenmedi; matris/dönüşüm işlemleri açık. Sonra bu alt ağın hızlandırılması için kaldırılabilir bütçe ve doğruluk sınırı kararlaştırılır.
