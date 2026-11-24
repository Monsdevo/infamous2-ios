# Build42 — ilk geometri karşılaştırması ve devam noktası

27 Ekim 2026. Kullanıcı ilk oynanışı ve sabit kamerayı doğruladı.
İlk normal termal tur tamamlandı; ikinci, yeniden açılmış süreç turu başlamadı.
Kullanıcı şu anda telefonu soğutamayacağını belirtti; yeni ölçüm başlatılmadı.

## Tamamlananlar

- 16 gerçek iPhone fixture: 4 skinning/12 culling. Tüm GPR/PC/LS ve rollback
  kontrolü geçti; 62 zorlanan GPU batch ve dört-worker izolasyonu Mac’te geçti.
  `out/geometry42-real-batch-test-v2.log`. İlk host kontrolündeki negatif alias
  deneyi tek iterasyonlu girdide bağımlılık varsaydığı için durdu; test yalnız
  yeterli iterasyonlu girdilere uygulanacak biçimde düzeltildi ve tamamı tekrar geçti.
- Dört canlı profilin doğrulama penceresinde toplam453.108 çağrı karşılaştırması;
  uyuşmazlık/failure/unsupported/fallback0. Bu sayı tüm çağrı doğrulamasıdır;
  Metal seçili profillerin çoğu CPU’da yürüdü. GPU batch adayları ayrıca
  kalibrasyonda karşılaştırıldı, maliyet eşiğini geçemedi.
- İlk ılık koşul girişimi henüz FPS penceresi başlamadan termal0’a geçince durduruldu.
  Sonrasında altı pencerenin tamamında örneklenen termal0; doğrulama/captureOFF,
  shader kalibrasyonu durmuş, Metal lighting/SSAOON, sahne aynı.

| Skinning / Culling | FPS | Gerçek kare aralığı | GPU kullanımı |
|---|---:|---:|---|
| SPU / SPU — başlangıç | 6.08 | 189 | CPU |
| ARM64 / ARM64 | 6.26 | 200 | CPU |
| ARM64 / Metal | 6.14 | 197 | CPU’da kaldı |
| Metal / Metal | 6.13 | 196 | CPU’da kaldı |
| Metal / ARM64 | 5.81 | 192 | CPU’da kaldı |
| SPU / SPU — dönüş | 6.46 | 207 | CPU |

Bunlar istenen profil sonuçlarıdır; sıfır kabul edilmiş GPU batch’i olan
profiller GPU performans kazancı/başarısı olarak sunulamaz. Her pencere en az
30s/120 gerçek kare aralığıdır. Ham sayılar, sunum CSV’leri ve tam çağrı
sayaçları `out/geometry42-sweep1-normal/` altında.

SPU referansı6,08→6,46 FPS (~%6,2) kaydı. ARM64/ARM64’ün ilk referansa
göre ~%2,9 farkı bu kaymadan küçük: anlamlı FPS kazancı henüz doğrulanmadı.
ARM64 geometri çağrılarının toplanmış duvar süresi azaldı; örtüşen thread
süreleri doğrudan kare süresinden çıkarılamaz. Termal0 aynı chip clock
anlamına gelmez. Son ayar SPU/SPU, validationOFF; yeni profil varsayılan yapılmadı.

## Kalanlar / yarın devam

1. Uygulamayı yeniden aç; kullanıcı aynı ilk oynanışı ve sabit kamerayı tekrar doğrulasın.
2. GPU hazırlığını ölçüm dışında bitir; fresh process’te maliyet/doğruluk
   kalibrasyonunu yeniden al. İlk kalibrasyonlar ılıktı; bu da ayrıca sınırdır.
3. Termal koşul sabitken ters sırada ikinci profil turu + baş/son SPU kontrolleri:
   `python3 tools/run_geometry_sweep.py --device 00008130-001129E00243001C --output out/geometry42-sweep2 --thermal-state 0 --reverse`
   Bu komut sabit sahne teyidinden VE GPU ön hazırlık/doğrulamasından sonra çalıştırılmalı.
4. İki turu birlikte değerlendir; fark kontrol kaymasından küçükse FPS kazancı ilan etme.
   GPU reddi sürerse küçük işleri tek tek GPU’ya göndermek yerine daha büyük batch/veri
   akışı değişikliği ayrı bir sonraki çalışma olarak planlanmalı. Bu aşamada uygulanmadı.

Yeni uygulama derleme/kurulumu gerekmiyor; build42 cihazda. Kayıtlar kaybolmadı.

## Sonraki kaynak incelemesiyle güncellenen öncelik

27 Ekim çevrimdışı incelemesi, CPU'da kalan Metal profillerinin ters sırada
tekrarını ana ilerleme adımı olarak önermiyor. Önce seri renderer'ın somut
maliyetleri ele alınmalı. Yukarıdaki ölçüm sırası tarihsel devam planıdır;
[yeni rapor](optimization-review-tr.md) güncel öneriyi ve kanıt sınırlarını açıklar.
