# BCES01229 ile ilerleme — kaynak incelemesi

**Sonraki gelişme:** kullanıcı BCES ile ilerlemeyi onayladı; gerçek EBOOT ve
SPU incelemesi/üretimi [9. adımda](step9-bces-tr.md) yapıldı. Aşağıdaki metin
bu çalışmadan önceki değerlendirmedir; açık soruların güncel durumu 9. adımdadır.

17 Ekim 2026. Kullanıcı, sağlanan BCES01229 kopyasıyla ilerlemenin ek
zorluğunu ve orijinal repoda oyun edinme bilgisi bulunup bulunmadığını sordu.
Bu çalışma kaynak incelemesidir; BCES EBOOT çıkarılmadı/çözülmedi, yeni
oyun hedefi üretilmedi ve oyun boot'u denenmedi. Kaynak pin'leri değiştirilmedi.

## Repoda oyun edinme hakkında bulunanlar

[Ana README](https://github.com/erikomis/infamous2-recomp#what-you-need)
RPCS3'e kurulmuş oyun, onun lisansı ve firmware ile başlanmasını istiyor.
Oyun verisi, firmware, anahtar ve bunlardan üretilmiş kod içermediğini açıkça
belirtiyor. İncelenen README'ler, roadmap ve hazırlık araçlarında oyunun
tam kopyasını indirecek bir bağlantı veya otomatik indirme aracı bulunmadı.
`tools/setup_toolkit.sh` yalnız runtime fork'unu ve yamalarını hazırlıyor;
oyunu indirmiyor. `infamous2-lle/README.md` yereldeki girdilerin dönüşüm tarifidir.

[ROADMAP — Game versions](https://github.com/erikomis/infamous2-recomp/blob/main/ROADMAP.md#app-to-install-and-play-launcher)
bugün yalnız NPUA80638 PSN sürümünün desteklendiğini söylüyor. BCUS98125
disk ISO desteği yapılacaklar arasında: güncellenmiş disk EBOOT'si PSN
EBOOT'siyle karşılaştırılacak; aynıysa girdi hazırlığı, farklıysa ikinci
recomp profili gerekecek. Bu bir tamamlanmış özellik değil ve **BCES01229
desteği** olarak okunamaz.

## Önceki sürüm varsayımının düzeltilmesi

- `infamous2/README.md:8` eski deneme için **NPUA80638, APP_VER 01.03** der.
- `ROADMAP.md:117` planlanan installer denetimi için **NPUA80638 01.00** der.
- Etkin LLE tarifinde ELF için kanonik SHA-256 verilmez. Hangi notun güncel
  executable'a karşılık geldiği bu belgelerden kesinleştirilemez; roadmap'in
  plan metni de tek başına yeni bir sürüm doğrulaması değildir.

Bu yüzden önceki “mutlaka 01.03” gerekliliği fazla kesindi. `check_inputs.py`
artık metadata aşamasında yalnız referans TITLE_ID'yi ayırır, gözlenen
APP_VER'yi kaydeder ve çelişkiyi raporlar. `binary_compatibility_verified`
ayrı olarak false kalır. `inputs_ready_for_review` derleme/çalıştırma izni
veya desteklenen binary kanıtı değildir. Eski oturum notlarındaki 01.03
beklentisi bu ek notla düzeltilmiştir. Bu değişiklik **BCES'i otomatik kabul
etmez**; onun TITLE_ID'si hâlâ farklıdır.

## Hangi iş korunuyor, hangisi ekleniyor?

UIKit/CAMetalLayer sunumu, her SDK'ya ayrı derlenen bağımlılıklar, pinned
runtime, ARM64 VM/fiber adaptasyonu, thread koordinasyonu ve statik PPU
üretim hattı korunur. Bunlar yalnız bir oyunun bölge kimliğine bağlı değil.
Bu altyapıyı baştan yazmak gerekmez. Gerçek oyunun iOS yaşam döngüsü, ses,
dosya yerleşimi ve kontrol entegrasyonu ise her iki sürümde de henüz yapılacak.

| Ek inceleme | Somut dosya/fonksiyon | Risk ve yapılacak iş |
| --- | --- | --- |
| PPU executable ve sınırlar | `infamous2-lle/README.md` içindeki `ppu_loader.py` / `ppu_lifter.py` çağrıları | NPUA için `--code-end 0x742e18` BCES'e körlemesine taşınamaz; BCES ELF segmentleri, OPD, TOC ve import sınırlarından profil üretilecek. |
| WWS job policy kaydı | `stubs.cpp::ps3_load_prx_modules()` | Guest EA `0x008E5B00`, uzunluk 11904, image ID 3 referansa ait. BCES'te içerik/konum bulunup doğrulanacak. |
| EBOOT içindeki SPU işler | `tools/extract_eboot_jobmods.py::is_module()`, `lift_datamods.py::find_blobs()`, `lift_relocmods.py::find_blobs()` | Araçlar magic/imza tarıyor, bu yüzden birçok blob yeniden bulunabilir. Ancak file offset → guest VA eşlemesi (`--va-offset` varsayılanı 0x10000) ve içerik hash'leri doğrulanmalı. NPUA'daki 27 / 5 / yaklaşık 30 blob sayısı BCES için varsayılmayacak. |
| GPU light optimizasyonu | `gpu_light.c::infamous2_gpu_light_install()` | `jobmod_c6e7383dc013...` sembolleri, image 219 ve LS 0x4AC8 / 0x4578'e bağlı. Kod aynıysa eşleme yeniden kullanılabilir; farklıysa işin algoritması/çağrı sözleşmesi karşılaştırılmalı. Hook geri dönüş kontrolü güvence sağlar ama bölge uyumluluğu kanıtlamaz. |
| GPU SSAO optimizasyonu | `gpu_ssao.c::infamous2_gpu_ssao_install()` | `jobmod_e6fe749031f8...`, image 226, LS 0x4330 ve job iç veri yerleşimine bağlı. Kör adres kaydırması yeterli olmayabilir. |
| Başlatma, dosya ve dil yolları | `main.cpp::derive_vfs_root()`, SFO okuma bloğu ve `run.sh` | Disk/dijital boot yolu, arşiv adları, dil paketleri ve kayıt hedefleri incelenecek. NPUA kurulum yoluna BCES verisi gizlice konmayacak. |
| Ortak runtime düzeltmeleri | pinned fork'un title yaması; GCM/RSX, shader, SPU dispatch, callback/senkronizasyon kodu | Düzeltmeler korunur. Ortak hata düzeltmesiyle executable'a özgü hook aynı şey değildir; BCES'te ikincisinin doğru hedefe bağlandığı ayrıca sınanır. |

## Zorluk değerlendirmesi

Bu, mevcut iOS çalışmasını çöpe atmak veya başka bir oyun için yeni port
yazmak değil; **ek bir oyun sürümü profili ve doğrulama çalışması**. Fakat
basit bir arşiv/paket dönüşümü de değil. Orta büyüklükte başlayıp executable
ve SPU farklarına göre büyüyebilecek, belirsizliği yüksek ek iştir.

- **Küçük fark senaryosu:** ELF yerleşimi/boot yolları değişmiş, kritik SPU
  blob'ları aynı kalmıştır. Çıkarma, yeniden lift, adres/image eşlemeleri ve
  regresyon kontrolleriyle mevcut düzeltmelerin çoğu taşınabilir.
- **Büyük fark senaryosu:** compiler çıktısı, SPU iş gövdeleri, job iç veri
  yerleşimleri veya senkronizasyon davranışı değişmiştir. Light/SSAO hook'ları
  ve diğer sabit varsayımlar yeniden incelenir; yeni lifter/runtime hataları
  çıkabilir. İlk kareye giden teşhis süreci belirgin biçimde uzar.

Bugün bu iki senaryodan hangisinde olduğumuzu gösteren executable analizi
yok. NPUA referans ELF'si de yerelde olmadığı için birebir binary diff
yapılamaz. **Yüzde, kaç gün veya kesin başarı tahmini vermek için yeterli
kanıt yok.** Güçlüğü “sadece bölge değişikliği” diye küçültmek doğru olmaz.

## Karar vermeyi sağlayacak sınırlı sonraki inceleme

Uyarlamanın tümüne girişmeden BCES EBOOT'sini yalnız veri olarak alıp
SELF/ELF durumunu saptamak; çözülmüş ELF oluştuğunda segment/OPD/import
envanteri, SPU imza/blob raporu ve kritik adres/hash eşlemelerini çıkarmak.
Çalışan NPUA çıktıları olmadan da bazı farklar kaynakta belgelenmiş job
imzalarıyla kıyaslanabilir; birebir eşitlik iddia edilemez. Ardından ayrı
BCES profili tasarlanır. NPUA'nın kod/veri sabitleriyle BCES'i çalıştırma
denemesi bu incelemenin parçası olmayacak.

Bu ilk analiz iPhone'a oyun yüklemek veya oynanışa ulaşmak değildir.
Firmware girdisi ve gerçek macOS/iOS oyun entegrasyonu ayrıca gerekecek.
