# İlk uygulama: normal tamponu writeback deneyi (Mac)

30 Ekim 2026. `upstream-seven-diagnosis-tr.md` sırasındaki ilk adayın sınırlı uygulaması.

## Uygulamanın sınırı

Kaynakta SSAO'nun pass0 derinlik işi hâlâ özgün SPU'da çalışıyor (`gpu_ssao.c::ssao_skip_step`, `00005258` çağrısı). Bu iş guest derinlik girdisini okuyor. Bu yüzden iki G-buffer writeback'ini birden kaldırmak mevcut uygulamada güvenli değil. Önce sadece **normal** tamponunun writeback'i deneniyor. Derinlik yolu aynen korunuyor.

`tools/prepare_host_normals_writeback.py`, sadece Mac türetilmiş kaynaklarına uygulanır. `eng_gpu_light_blit` içindeki normal kopyası, 1280x720 GPU kaynakları hazırlanmışsa ve fault yoksa atlanabilir. Varsayılan kapalıdır. Ana iOS hazırlayıcı ve runtime kilidi değiştirilmez.

`src/platform/HostNormalsWriteback.{h,c}` atlanan normal girdisini işaretler. Aydınlatma veya SSAO job'ı özgün SPU fallback'i isterse, eksik guest girdisiyle devam etmek yerine **denemeyi abort ile geçersiz kılar**. Modu kapatmak bu eksik-girdi işaretini silmez; bir sonraki normal kare girdisinin başlangıcı sıfırlar. Bu bir üretim fallback çözümü değildir. Bilinmeyen diğer tüketicilerin yokluğu ve bütün oyun doğruluğu henüz kanıtlanmış değildir. Başarılı pilot bile varsayılanı açmak için yeterli sayılmaz.

Mac kontrol alanı: `normals_nowb=0/1`; raporda enabled ve skipped sayaçları bulunur. `tools/measure_host_research.py` seçilen modu, sayacın ilerlemesini ve diğer mevcut profil/fault/sıcaklık kurallarını doğrular. `tools/run_host_normals_comparison.py`, sabit sahne ve shader ısınması sonrası A/B/A/B/A 30s pencereleri alır; ekran görüntüleri FPS pencerelerinin dışındadır. Görüntüler yalnız görsel sağlık kontrolüdür, bit eşitliği kanıtı değildir.

## Tamamlanan doğrulama

- Mac araştırma hedefi tek paralel iş ile derlendi. Log: `out/host-research/upstream-seven-audit/normals-build.log`.
- Native ASan/UBSan gate testi geçti: varsayılan kapalı, uygun olmayan kaynak reddi, sayaç, kare sıfırlama ve mod kapatıldıktan sonra bile eksik-girdi fallback'inin SIGABRT ile durması.
- Native test logu: `out/host-research/upstream-seven-audit/normals-gate-test.txt`; fixture `build/bces01229/host-normals-test/gate.c`.
- Python hazırlayıcı ve ölçüm aracı syntax kontrolü geçti.
- Gerçek oyun ölçümü henüz tamamlanmadı. Ölçülmüş FPS kazancı yok.

## Komutlar

```sh
env DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
 TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp python3 tools/prepare_host_research.py
env DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
 TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp \
 cmake --build build/bces01229/host-research --parallel 1
# Ayrı terminallerde; etiket mevcutsa yenisini seç:
python3 tools/run_host_research.py --label upstream-normals-01 --seconds 1800 \
 --install-template out/host-research/lighting-far-01
python3 tools/drive_host_gameplay.py --run out/host-research/upstream-normals-01
python3 tools/run_host_normals_comparison.py --run out/host-research/upstream-normals-01
```

Ölçüm sırasında build/analiz/GPU fixture çalıştırılmaz. Normalin geri okunması kaldırıldığında kaybolan bekleme, GPU hesabının yok olduğu anlamına gelmez. Gerçek katkı yalnız geçerli karşılaştırmadan raporlanacak. Bu adayın ölçümü ve doğruluk sınırları çözülmeden adres önbelleği/DMA adaylarıyla birleştirilmez. iPhone kurulumu yapılmaz.

## Gerçek oyun sonucu: aday kabul edilmedi

`upstream-normals-01`, PID53115, yaklaşık412s. Oynanış otomatik üç girdiyle doğrulandı. Kapalı ilk30s referans:415frame interval,13,609FPS,73,479ms ortalama; termal1. Bu tek kapalı pencere, önceki başka oturumlara göre kazanç kanıtı değildir.

Açık moda geçildiğinde, normal writeback'i atlandıktan sonra aydınlatma/SSAO fallback kapılarından en az biri özgün SPU yolunu istedi. Guard `[host-normals] unsupported SPU fallback after omitted writeback; experiment invalid` yazdı ve SIGABRT ile durdurdu. Session `stopped`, returncode−6: bu kez duruş launcher temizliği değil, özellikle eklenen fail-stop korumasıdır. Açık pencere `valid=false, stale report`; FPS sonucu yok. Rapor sayacının son örneğinde skipped0 görünmesi, son kontrol raporundan sonra yapılan atlamayı reddetmez: guard logu missing işaretinin kurulduğunu gösteriyor.

Bu kayıt hangi kapının ve hangi doğrulama koşulunun reddettiğini henüz ayırmıyor. Dolayısıyla belirli bir yeni consumer keşfedildiği veya kopyayı kaldırmanın imkânsız olduğu iddia edilmiyor. Kanıtlanan şey, **bu koşullarla normal kopyasını atlamanın mevcut fallback sözleşmesini karşılamadığı**. Guard kaldırılmayacak. Üretim varsayılanı açılmadı; iOS hiç değiştirilmedi.

İlk adayın mevcut uygulaması kabul edilmedi. Güvenli devam için fallback nedenini/job'ını ayıran tanı ve ardından gerektiğinde normal girdisini materialize eden ya da bütün ilgili job'ları önceden doğrulayan tasarım gerekir. Derinlik writeback'i için ayrıca özgün pass0 tüketicisi çözülmeli. Sıradaki bağımsız adres önbelleği/DMA adayları bu deneyle birleştirilmedi.
