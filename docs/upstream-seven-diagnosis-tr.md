# macOS ve Linux kaynaklı yedi başlığın Mac teşhisi

30 Ekim 2026. Optimizasyon uygulanmadı, yeniden derleme yapılmadı. iPhone'a kurulum yapılmadı. Yalnız mevcut araştırma uygulaması çalıştırıldı; yeni çıktılar ve bu not yazıldı. Oyun oturumu analizden önce kapatıldı.

## Kaynak ve ölçüm kimliği

- Bizim port: `b76ecda525b2b02bb1ca59aca63024fdebb78d06`; runtime `770660a3971b87a453677e46125e5e01ac7891c0` + kilitli yama + mevcut yerel platform katmanları.
- Güncel macOS referansı: `erikomis/infamous2-recomp`, `a69a0525b91e4b22f4ed0e3d6452c95159060643` (25 Ekim). Güncel kurulum da aynı runtime commit'ine dayanıyor; değişiklikler büyük birleşik yamada. Yeni runtime HEAD'i ile değiştirmek gerekmiyor.
- Linux referansı: `ThiagoFraga761/infamous2-pc`, `1ab02e702c37247ad4f53ac0b361d92e8b3269bc` (26 Ekim). BCUS98125, x86/Vulkan ve HLE sistem modülleri; bizim BCES01229/LLE/ARM64/Metal hedefimizin doğrudan eşdeğeri değil.
- GitHub API commit kayıtları, o commit'lerden indirilen notlar ve macOS yaması: `out/host-research/upstream-seven-audit/`. Web önbelleğinin raw/main ile HTML sayfasında farklı eski içerikler gösterebildiği görüldü; değerlendirmede sabit SHA ile indirilen içerikler kullanıldı. Yama uygulanmadı.
- Etkin kaynakların SHA256 listesi: aynı klasörde `input-hashes.json`.
- Gerçek Mac oturumu: `out/host-research/upstream-seven-01`, PID51007, binary UUID `19FC7BFA-A4FC-3A78-85B3-74DA20CA5BD9`.
- CROSS, sağ çubuk yukarı, sağ çubuk sola girdileri görüntü/OCR ile doğrulandı. `scene-ready.json` kamera öğreticisinin tamamlandığını ve serbest oynanış görev yazısını belgeliyor. Kamera sabit.
- Metal aydınlatma/SSAO, SSAO temizliği, uzak ışık elemesi ve mevcut interval maske açık; deneysel SPU matematik/dispatch/vertex/texture memo kapalı. Yeni yol eklenmedi.
- Termal1, düşük güç kapalı; profil öncesi/sonrası shader sayısı1162, GPU/ışık/SSAO fault0. DRAWSTATS/RESOLVE_LOG açık. Bu kayıtlar tanıdır, profilsiz FPS karşılaştırması değildir.
- CPU18,008s /6226satır /hata0 /truncated0. Zaman izi15s /1.271.927olay /dropped0. Ayrı bir karede111GPUencoder kaydı, geçersiz0. Mevcut örnekleyici unsuspended best-effort ancestry kullanıyor; işlev atıfları istatistikseldir.

## Yedi başlık

| # | Başlık | Bizdeki durum ve gerçek kanıt | Çıkarılabilecek sonuç |
|---|---|---|---|
| 1 | macOS SPU doğrudan dallanma / tail-call | Etkin `spu_context.h` ve üretilen SPU kodunda `SPU_DIRECT` yok. Kod, `g_spu_trampoline_fn` ayarlayıp dönüyor. CPU örneklerinde yalnız `spu_drain_call`'ın kendi çalışması yaklaşık2,264CPU-s; gözlenen SPU CPU toplamı61,781CPU-s olduğundan yaklaşık%3,66. Launch/reset kontrolleri ayrıca iş tüketiyor. | Uygulanabilir aday. Bu oran kare süresi veya garantili FPS kazancı değildir. Çağrıların altındaki gerçek oyun hesabını da kapsayan55,25CPU-s inclusive drain süresi, kaldırılabilir maliyet sayılamaz. |
| 2 | macOS dolaylı adres önbelleği + sade DMA | `PS3_SPU_IBCACHE`/`PS3_SPU_DMA_LEAN` etkin kaynaklarda yok. `spu_indirect_branch_slow`+`spu_indirect_branch`+`spu_lookup` exclusive tahmini4,108CPU-s (~%6,65 SPU CPU). `mfc_do_transfer`+`spu_overlay_note_get`+`mfc_submit_body`+`mfc_for` yaklaşık3,934CPU-s (~%6,37). DMA kaynağında her PUT yükünü tarayan poison tanısı var. | İki ayrı aday; gelecek deneylerde ayrı ölçülmeli. Bütün resolver/DMA işi kaldırılamaz. Önceki bizim dispatch denememiz, bu yeni cache+generation mekanizmasının eşdeğeri değil. Linux'un x86 fence kaldırması ARM64'e aynen taşınamaz. |
| 3 | macOS framebuffer fetch | Etkin renderer/çeviricide `rsx_fp_apply_fbfetch` yok. Okunmayan texture birimlerini atlama ise zaten var. GPU kaydında111encoder var; genel kopya/resolve sayaçları hangi kopyaların framebuffer-fetch için uygun olduğunu belirtmiyor. | Gerçek aday, fakat mevcut araçlarla aday decal kopyalarının özel ms bütçesi belirlenemedi. macOS'un1080p kazancını720p'ye taşımak geçersiz. GPU stage süreleri örtüşüyor; bunlar kopya maliyeti diye toplanamaz. |
| 4 | Linux G-buffer'ı CPU/guest belleğine geri taşımama | Temel fork'ta atlama var, fakat **etkin** `host-research-prepared/renderer-overlay/.../rsx_draw_engine.c` içindeki `eng_gpu_light_blit` yolunun sonunda koşulsuz `return 0` var: iOS katmanı SPU fallback için iki guest writeback'i koruyor. Gerçek15s kayıtta456adet1280x720readback,228present çağrısı: yaklaşık2readback/kare. Medyan readback wall1,268ms/kare. CPU GPU-wait union20,086ms/kare; iki ara flush beklemesi/kare, kaynak satırı4902. | En somut mimari aday. Readback ve senkron gönderim zinciri mevcut. Fakat20,086ms'nin tamamı kopya maliyeti değil: öncesindeki zorunlu GPU işini de bekliyor. Kopyayı kaldırmak GPU işini yok etmez; gönderim sırası ve fallback/diğer tüketiciler doğrulanmalı. Kesin20ms kazanç deneme yapılmadan söylenemez. |
| 5 | Linux uniform/descriptor ring dolması | Vulkan'ın16MiB uniform ring'i yerine Metal'de384MiB üst sınırlı staging arena + paylaşılan MTLBuffer slotları var. Son altı drawstats grubunda vertex35,4–35,6MB, index8,2MB, constant16,0–16,5MB/kare. Toplam yaklaşık60MB;384MiB eşiğinin oldukça altında. Oturumda staging-slot bekleme uyarısı0. Mevcut trace arena taşmasına özel benzersiz reason vermiyor. | Bu sabit sahnede Vulkan'daki ring-boyutu çözümünü kopyalamayı destekleyen kanıt yok. Yaklaşık60MB, headroom/diğer staging kullanımının tam sayacı olmadığı için mutlak taşma-yok ispatı değildir. Ölçülmüş kazanç0 deneme sonucu yok; teşhis önceliği düşük. |
| 6 | Linux küçük SPU bloklarını birleştirme | Bizim üretilen kodda D8A8 gibi bloklar ayrı C işlevleri ve trampoline dönüşleriyle bağlı. Birleştirme yok. #1 ile aynı drain/dispatch/register yükünün bir bölümünü hedefliyor; bağımsız bir kazanç havuzu değil. | Aday; #1 ile alternatif veya kısmen örtüşen uygulama olarak ele alınmalı. %kazançları toplanamaz. Interrupt/reset, overlay, iç giriş noktaları ve host stack davranışı korunmalı. Yeni derleme olmadan gerçek etkisi ölçülemez. |
| 7 | Ana PPU'nun beklediği son işi bulma | Bu bir hızlandırma değil, doğru işi seçme yöntemidir. Yeni kayıtta220tam kare penceresinde main usleep poll union medyan2,701ms; bunun2,656ms'si RSX drain ile örtüşüyor. Drain dışındaki poll medyan0ms, p95 0,313ms. İlerleme/CPU eşlemesinde1841örtüşenSPUörneğinin52'si kabul edildi;29tek-geride-lane örneğinin21'i `jobmod_638a73a6476e_e60c0`. Önceki kayıttaki14/20 bulgusunu yön bakımından tekrarlıyor. | 638a73 yine aday, ancak21/29 oranı kare zamanı yüzdesi değildir. `8648 -> 6B90 + spu_drain_call` alt ağının tam inclusive wall/CPU süresi mevcut kayıtlarda yok. Yeni begin/end ölçümü olmadan bu alt ağın kaç ms kısaltılabileceği dürüstçe hesaplanamaz. Bu tur kod değiştirilmeyerek sınır korundu. |

## Bütçeyi okuma

Zaman çizelgesinde220kare aralığının medyanı64,278ms, p95 73,842ms. Bu tanı penceresindeki istek aralığıdır; ekrana sunum veya profilsiz performans sonucu değildir. GPU işgal birleşimi medyan41,155ms, RSX drain54,577ms, CPU GPU beklemesi20,086ms, readback1,268ms. Bunlar örtüşür; toplamları bir kare bütçesi değildir.

Özellikle `GPU wait20ms` + `GPU41ms` toplanmaz. Wait içinde, GPU'nun gerçekten yapmak zorunda olduğu işler var. Readback'i kaldırdıktan sonra o iş başka bir noktada beklenebilir. Gerçek katkı ancak doğru çıktı üreten alternatif yolla A/B ölçülür. Bu tur hiçbir başlık için yeni FPS kazancı kanıtlanmadı.

Aynı64,278ms aralık yalnız matematik örneği olarak kullanılırsa: gerçekten kritik zincirden10ms kaldırmak18,42FPS,20ms kaldırmak22,58FPS karşılığıdır;30FPS için yaklaşık30,945ms kaldırmak gerekir. Bu örnekler tahmin veya vaat değil, gereken ölçeği gösterir. Yedi başlığın bu miktarı sağlayabildiği gösterilmiş değil.

## Sonraki uygulama sırası için teşhis sonucu

1. #4: Etkin writeback/fallback yolunu ve iki tam çözünürlüklü kopyanın tüketicilerini çözümle. En açık senkronizasyon/kopya adayı. Kullanılmayan guest kopyaları tamamen kaldırmak veya gerektiğinde üretmek, güvenli alternatiflerin konusu olabilir.
2. #2: Cache ve DMA sadeleştirmesini ayrı adaylar olarak değerlendir. Önce kaynakta diagnostic iş yükünü ayır; bellek sıralaması ve overlay invalidation doğruluğunu koru.
3. #1 ve #6: Tek ortak dispatch/lift başlığı olarak planla. Önce küçük bir modülde doğrudan geçiş ya da birleştirmeyi dene; kazançları iki kere sayma.
4. #3: Framebuffer-fetch uygun kopyalarının özel sayacı/zamanı çıkarılmadan büyük kazanç atfetme.
5. #7: 638a73 tam alt ağını braketlemek, sonraki iş hızlandırmasını seçmek için gerekli; bu tur kesin iş ms'si bulunmadı.
6. #5: Bu sahnede düşük öncelik. Başka ağır sahnede gerçek arena taşması gözlenirse yeniden aç.

Yedi maddenin dışında ama aynı kayıtta görülen maliyet: son altı drawstats grubunda vertex fetch/decode7,322–10,857ms (medyan8,706), remap2,877–3,310ms, texture hash4,302–5,315ms. Bunlar instrumented wall süreleridir; texture ve vertex memo denemelerinin neden yeniden değerlendirilebileceğini gösterir, daha önce kazanç göstermemiş bir denemeyi başarıya dönüştürmez.

## Yeniden üretme / ham kanıtlar

```sh
# Mevcut binary; build veya patch yok. Oyun/saves/loglar SSD'de.
env PS3RECOMP_ENG_DRAWSTATS=1 PS3RECOMP_ENG_RESOLVE_LOG=1 \
 DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
 TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp \
 python3 tools/run_host_research.py --label upstream-seven-01 --seconds 1800 \
 --install-template out/host-research/lighting-far-01
python3 tools/drive_host_gameplay.py --run out/host-research/upstream-seven-01
python3 tools/run_host_critical_capture.py --run out/host-research/upstream-seven-01
python3 tools/capture_host_gpu_passes.py --run out/host-research/upstream-seven-01 \
 --output out/host-research/upstream-seven-01/gpu-stages
```

Etiket mevcutsa yeni etiket kullanılır. Macro/OCR ve shader ısınması bitmeden profil başlatılmaz. Profil kaydı sırasında başka build/analiz/GPUfixture çalıştırılmadı. Oyun launcher'ına Ctrl-C ile durdurma verildi; session `stopped`, returncode−9 launcher temizliğinin sonucu, kendiliğinden çökme değil.

Analizler `critical-progress/` altında: `frame-analysis.json`, `category-budgets.json`, `cpu-analysis.json`, `rsx-cpu.json`, `progress-analysis.json`, `critical-correlation.json`, `progress-overlap.json`, `submission-counts.json`, `drawstats-last-six.json`, `drawstats-summary.json`. GPU aşamaları ayrı `gpu-stages/` klasöründe.

## Sınırlar

İki gerçek platform arasında sadece saat hızı farkı yok: işletim sistemi zamanlama/Metal davranışı, CPU çekirdek dağılımı, bellek bant genişliği, GPU kaynakları ve sürdürülebilir termal bütçe farklı. Mac teşhisi aday seçtirir; iPhone kazancını ve sürdürülebilir30FPS'yi kanıtlamaz. Kaynak karşılaştırması ve mevcut tanı yedi başlığı kapsadı; özellikle #3 ve #7 için istenen ayrıntılı ms ayrımı yeni instrumentation olmadan tamamlanamıyor. Bu eksikler tahminle doldurulmadı.
