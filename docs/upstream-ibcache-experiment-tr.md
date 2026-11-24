# İkinci aday: SPU fast-resolver sonuç önbelleği (Mac)

30 Ekim 2026. Önceki normal-writeback deneyi kapalı. Yeni aday yalnız Mac araştırma hedefinde; iOS/runtime kilidi değiştirilmedi.

`tools/prepare_host_ibcache.py` mevcut fast resolver'ın seçim sonucunu256entry/native-thread önbelleğinde tutar. Anahtar PC, context kimliği, image, resident overlay/task ve registry generation içerir. Native thread farklı context'e geçtiğinde veya resident-code descriptor tablosunun herhangi bir byte'ı değiştiğinde entries temizlenir. Registry generation, register/replace/reloc-image kayıtlarında ilerler. Task tablolarının kullanıldığı adresler, IRQ/stop/service ve tanı yolları mevcut koşullardan geçer; cache bunları bypass etmez. Reloc seçiminde code_base güncellemesi, resident_task, stack-reset ve tail-call davranışları korunur. Miss ve unsupported durumlar özgün resolver'ı kullanır.

Bu, upstream'in fikrine dayanan fakat context ABI'sini değiştirmeyen bir uygulama. Upstream resident generation alanları yerine daha pahalı, temkinli descriptor `memcmp` kontrolü kullanıyor. Yeni upstream'in bütün runtime'ı ya da aynı uygulaması olarak sunulmuyor; stale-slot düzeltmeleri gibi bağımsız upstream değişiklikleri bu denemeye karıştırılmadı. Daha önceki WWS fast-dispatch anahtarı iki performans kolunda da açık, dolayısıyla onun eski kazancı yeniden sayılmıyor.

Kontrol `ib_cache`:0özgün,1cache,2shadow. Mode2 cache hit'inde özgün seçim yeniden yapılır, fn ve reloc base davranışı karşılaştırılır; yalnız bir işlev çalıştırılır. Uyuşmazlıkta fault sayacı artar, mode0'a dönülür ve özgün sonuç kullanılır. Fault olan kayıttan performans iddiası kurulmaz. Mode2 performans pencerelerinde reddedilir. Per-SPU128byte ayrılmış sayaçlar shared cache-line çekişmesini sınırlar; sayacın kendi maliyeti yine deney maliyetinin parçasıdır.

## Doğrulama ve yeniden üretme

`python3 tools/test_host_ibcache.py`: gerçek transform edilmiş resolver ile özgün resolver nativeASan/UBSan altında stubbed registry/context üzerinde40bin differential dispatch'i geçti. Residency/registry değişimleri, reloc base, task exclusion, stop/IRQ yolları, aynı callback'in bir kere çalışması ve bilinçli yanlış cache sonucu enjekte edilince fault closure test edildi. Bu gerçek SPU iş sonuçlarının bütün oyun boyunca eşdeğerliği kanıtı değildir.

Mac build tek iş ile geçti: `out/host-research/upstream-seven-audit/ibcache-build.log`. Kaynak SHA'ları gerçek oturumda `source-hashes.json` ile saklandı.

```sh
python3 tools/test_host_ibcache.py
# Hazırlık ve build, FPS pencerelerinden önce:
python3 tools/prepare_host_research.py
cmake --build build/bces01229/host-research --parallel 1
# Ayrı terminal/süreçlerde:
python3 tools/run_host_research.py --label upstream-ibcache-01 --seconds 1800 \
 --install-template out/host-research/lighting-far-01
python3 tools/drive_host_gameplay.py --run out/host-research/upstream-ibcache-01
python3 tools/run_host_ibcache_comparison.py --run out/host-research/upstream-ibcache-01
```

Gerçek test önce15s mode2, en az10bin doğrulanmış hit/fault0 şartı; ardından mode0/1/0/1/0, her kolda10s settle +30sprofilsiz GPU-completion aralıkları. Aynı termal kategori, shaderquiet, kamera sabit, normal writeback açık, dispatch1, ışık/SSAO/intervalmask/uzakışık açık. Görüntü alma FPS pencerelerinin dışında. Sonuç yalnız bu Mac sahnesi için yorumlanacak, iPhone kazancı sayılmayacak.

Sıradaki bağımsız aday: DMA PUT yükünün poison tanı taramasını isteğe bağlı kılma, MFC durum aramasını hint ile hızlandırma ve overlay aday taramasını azaltma. Fenceler, atomikler, lock-line ve GPU/PPU senkronizasyon semantiği korunmalı. Her alt değişiklik ayrı ölçülmeli.

## Gerçek Mac sonucu — kazanç kabul edilmedi

Oturum `upstream-ibcache-01`, PID54784. Kamera öğreticisi otomatik tamamlandı. Termal kategori beş kolda da1; GPU/fallback-deneyi hatası yok. Açık/kapalı iki kolun da dispatch1 olması, eski fast-dispatch kazancını bu adaya yazmayı engelliyor. Normal writeback atlama kapalı, derinlik kopyası korunuyor.

Gerçek15s shadow validation:83.041.396hit doğrulandı,10.622.810miss,0fn/base uyuşmazlığı. Bu, yalnız gözlenen resolver seçimlerini doğrular; bütün oyunun doğruluğu iddiası değildir.

| Tur | Cache | FPS |
|---|---|---:|
| A | Kapalı |15,1641|
| B | Açık |14,7417|
| C | Kapalı |14,9826|
| D | Açık |15,0292|
| E | Kapalı |14,8941|

Ham frame interval toplamlarıyla birleşik kapalı15,01363FPS /66,60615ms; açık14,88545FPS /67,17968ms. FPS farkı−%0,8537. B kendi komşu referanslarından düşük, D az yüksek; **tekrarlanan bir üstünlük yok**. Sonuç küçük farkın istatistiksel olarak anlamlı bir gerileme olduğunu kanıtlamıyor; ama optimizasyon başarısı iddiasını desteklemiyor.

Açık iki FPS penceresinde toplam322.309.065cache hit ve41.468.717miss var; yaklaşık%88,6hit oranı. Dolayısıyla 'yol hiç kullanılmadığı için kazanç yok' açıklaması geçerli değil. Her açık penceredevalidated0/fault0; ölçüm sırasında shadow kontrolü çalışmadı. Memcmp/anahtar kontrolü ve sayaç maliyetinin kazancı ne kadar tükettiği ayrıca profillenmedi; neden olarak kesinleştirilemez. Bu temkinli sidecar uygulamasının sonucu, upstream'in generation tabanlı bütün uygulamasının kazanç sağlayamayacağını göstermez.

Açık moddaki kaydedilmiş görüntü gözle incelendi: Cole, iskele, gemi, ışıklar ve çevre anlaşılır, belirgin yeni geometri bozulması yok. Bu yalnız görsel sağlık kontrolüdür; piksel eşitliği testi değil.

Cache tekrar0'a alındı, test launcher'ı Ctrl-C ile sonlandırıldı; session `stopped`, returncode−9 launcher temizliği. Varsayılan kapalı. iPhone kurulumu yapılmadı. Kaynak ve ham sonuçlar `out/host-research/upstream-ibcache-01/` içinde, `ibcache-comparison/comparison.json`, `validation.json` ve her turun `frames.csv` dosyalarında.

**Sıradaki somut adım:** DMA PUT başına yapılan poison tanı taramasını opt-in tanı olarak koruyup normal yoldan çıkarmayı ayrı bir Mac anahtarıyla denemek. Bellek kopyası, fence, reservation/coherency ve tamamlanma işaretleri korunacak. İlk karşılaştırmaya MFC hint ve overlay taraması eklenmeyecek; bunlar ancak ayrı sonraki adaylar olacak.
