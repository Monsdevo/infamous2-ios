# Skinning / culling karşılaştırma paketi — build 41

26 Ekim 2026. Bu not build38 teşhisinden sonraki hazırlık oturumunu anlatır.
O oturumda kullanıcı iPhone'a kurulum istemediği için Mac/SSD üzerinde çalışıldı.
**Sonraki gerçek cihaz ölçümü tamamlandı:** ARM64/ARM64 anlamlı FPS kazancı
göstermedi; mevcut Metal prototipleri çok daha yavaş. Özgün SPU geometri
yollarına dönüldü. [Cihaz ölçümü ve sonuçlar](geometry-device-measurement-tr.md).

## Build41: tek pakette kombinasyonlar

Geometri deneyleri bölümünde tekil anahtarlara ek olarak hazır seçimler var.
Bütün etiketlerde sıra **Skinning / Culling**:

| Skinning | Culling |
| --- | --- |
| ARM64 | Metal |
| Metal | ARM64 |
| ARM64 | ARM64 |
| Metal | Metal |
| Özgün SPU | Özgün SPU |

Seçim iki işlemin ayarlarını birlikte kaydeder; aktif kombinasyon işaretlenir.
Tekil anahtarlar üzerinden SPU/ARM64 gibi diğer eşleşmeler de mümkündür.
Uygulama yeniden açılmadan sonraki çağrılarda değişir; devam eden işler tamamlanır.
Metal ilk kez seçiliyorsa derleyici hazır olana kadar özgün kod çalışır.
CSV'ye `geometry_pair` sütunu eklendi; mevcut route/validation/fallback
sayaçları korunuyor. Preset seçimi sürekli doğrulama ayarını değiştirmez.

`out/geometry41-combinations-test.log`: ASan/UBSan + gerçek Mac Metal GPU'sunda
5 kombinasyon ×2 doğrulama modu ×3 tekrar = **30 ardışık skinning→culling
çalışması** (60 çağrı). Aynı mimari bağlamda skinning çıktısı culling girdisi
olur; tüm GPR/PC/LS çıktısı karşılaştırılır. Yeni eşleşme testlerinde0 uyuşmazlık,
0 beklenmedik fallback. Önceki bağımsız yol ve kasıtlı hata kurtarma testleri de
aynı çalıştırmada geçti. Kapsam hâlâ aynı türetilmiş geometri girdisidir;
tüm mesh biçimleri veya gerçek iPhone oynanışı doğrulandı denmez.

`out/geometry41-build.log`: Release/iPhoneOS build41. UIKit paneli derlendi;
gerçek cihazda etkileşim/görünüm testi yapılmadı. Kullanıcı uzakta olduğundan
cihaz aranmadı veya kurulmadı. Mevcut Metal culling hâlâ seri doğruluk
prototipidir; bu tur paralelleştirilmiş culling veya FPS kazancı iddiası yok.

## Kapsam ve akış

- `tools/prepare_skinning.py::patch`: yalnız türetilmiş iOS Edge kaynağında
  D0A8 skinning çağrısı (dönüş5980) ve A798 culling çağrısı (dönüş59F0)
  `bces_geometry_execute` üzerinden geçer. Özgün fonksiyonlar ve call/drain
  geri dönüşü korunur; kilitli upstream/runtime ve macOS hedefi değiştirilmez.
- `tools/skinning_ir.py::program`: kilitli modülün saf hesap çağrı grafiğini
  statik olarak çıkarır. CPU opcode yorumlayıcı/JIT eklenmedi. Bilinmeyen
  callback/PC, assertion yolu veya adım sınırı sonucu kullanılmaz.
- `tools/prepare_geometry_kernels.py`: bütün hesap için ARM64 ve Metal
  çekirdekleri üretir. Üretilmiş oyun kodu `build/` altında kalır.
  ARM64 sürümü tek statik kontrol akışına ve NEON RZ aritmetiğine geçer;
  normalizasyon dahil bütün çağrı kapsamındadır. SPU'nun özel float sıfır,
  taşma ve yuvarlama davranışları korunur; FPCR/FPSR geri yüklenir.
- `tools/geometry_parallel.py`: skinning'in bağımsız döngülerini GPU gruplarına
  dağıtır (D800/D5B0/DA28/DCE0/DF20). 7030 normalizasyonunun üç iterasyonluk
  yazılım boru hattı için geriye doğru register bağımlılığı çıkarılır;
  ön hazırlık ve son register durumu korunur. Metal skinning'in hesap grafiği
  GPU'dadır; kontrol bölümleri tek thread, veri döngüleri paraleldir.
  Culling Metal yolu şimdilik tek thread doğruluk referansıdır; optimize
  edilmiş paralel culling diye sunulmaz.
- `src/platform/GeometryKernels.mm`: her iş için LS/GPR özel çalışma kopyası;
  GPU'dan CPU'ya sonuç dönüşü; yalnız yazılan 16 byte alanların ve mimari
  register çıktısının commit'i. Renderer'ın CPU vertex hazırlığı korunur.
  CPU/GPU kopyalama ve bekleme bedeli hâlâ var; sıfır kopya çizim değildir.

## Güvenlik ve ölçüm anahtarları

Üç nokta → **Geometri deneyleri** bölümünde ayrı ARM64/Metal skinning ve
ARM64/Metal culling anahtarları bulunur. Aynı işin iki yolu birlikte açılamaz;
ikisi de kapalıysa özgün SPU çalışır. Yeni yolların hepsi varsayılan kapalıdır.
Aydınlatma ve SSAO'nun mevcut ayarları korunur.

**Her çağrıyı özgün kodla doğrula** varsayılan açıktır. Bu modda trial sonucunu
özgün canlı yürütmeyle tam GPR/PC/256KiB LS karşılaştırırız; oyuna özgün sonuç
verilir. Uyuşmazlık ilgili yolu süreç sonuna kadar durdurur. Bu mod performans
karşılaştırması değildir. Kapatıldığında dahi yol başına ilk8 çağrı zorunlu
karşılaştırılır. İlk gerçek cihaz kontrolü bu modda yapılmalıdır.

Metal kaynak/PSO hazırlığı arka plandadır; hazırlanırken oyun özgün kodda kalır.
Private LS olmayan RAW/paylaşılan bağlamlar, stop, etkin debug hook veya bekleyen
interrupt varsa özgün yol kullanılır. Paralel hesap LS giriş snapshot'ını okur;
yazma çakışması ve önceki iterasyonun yazdığı veriye bağımlılık GPU'da kontrol
edilir. İhlal ve başarısız/sınırlı işte özel sonuç atılır; özgün çağrı yürür.
Metal kuyruğu renderer'dan ayrıdır; geçici kaynaklar sınırlandırılmıştır.

HUD/JSON/CSV: seçilen yol, başarılı trial çağrısı, fallback, doğrulama,
uyuşmazlık, hata; trial/GPU/referansın **kümülatif** süreleri. Aralık hesabı için
iki örnek farkı alınır; bu süreler tek kare ms'si değildir. Eşzamanlı işler
nedeniyle toplanıp kare süresinden çıkarılamaz. Metal hazırlanıyor/engellendi
bilgisi HUD'da görünür. İlk derleme ve zorunlu doğrulama ısınma süresine dahildir.

## Yerel kanıtın sınırları

Tam giriş/çıkış cihaz snapshot'ı bu tur alınamadı. Eski gerçek D808 ortası
`out/edge35-failure.bin` verisinden geçerli tam çağrı girdileri yeniden kuruldu.
5 skinning argüman varyantı ve skinning çıktısından3 culling modu var.
Bu 5 skinning durumu aynı geometri veri biçimini ve esas iş yükünü kullanır;
5 ayrı mesh/sahne veya tüm uniform/matris biçimleri kapsandı denemez.
Özgün fonksiyon grafiği golden çıktı üretir. Bütün GPR/PC/LS ve dirty alanlar
karşılaştırılır. Mac Metal testi iPhone performansı veya oyunda görüntü testi
**değildir**. GPU süreleri tek job fixture'ıdır; FPS karşılığı verilmez.

İlk seri Metal skinning referansı Mac M3'te yaklaşık77–81ms/job idi. Döngülerin
paralelleştirilmesi belirgin düşüş sağladı; son korumalı sürüm için ham kayıt
`out/geometry-final-metal-test.log` (son sınırlı sürümde yaklaşık5–10ms/job; ısınma dahil, eşlenmiş hız testi değil). Metal culling referansı yaklaşık65ms/job
olduğu için hızlanma beklentisiyle açılmamalı. Cihazda ARM64 ve Metal toplam
maliyetlerini ölçmeden bir yol varsayılan yapılmayacak.

## Tekrar üretme (SSD, tek derleyici)

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
export TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp
python3 tools/test_geometry_kernels.py
python3 tools/test_geometry_runtime.py
# Yukarıdaki araç yalnız binary üretir; aşağısı Mac GPU testidir:
build/bces01229/skinning/runtime-check out/skinning-derived/skin-04.bin out/skinning-derived/cull-3.bin
python3 tools/prepare_bces_ios.py --support-report out/bces-support-compile-iphoneos-spu-O2-copy.json
/opt/homebrew/bin/cmake -S cmake/bces-ios -B build/bces01229/ios
xcodebuild -project build/bces01229/ios/Infamous2BCESIOS.xcodeproj -scheme Infamous2Game -configuration Release -destination 'generic/platform=iOS' -jobs 1 -derivedDataPath build/bces01229/DerivedData DEVELOPMENT_TEAM=BJ266NGN3H
```

Uygulama: `build/bces01229/ios/Release-iphoneos/Infamous2Game.app`.
Bu komutlar cihaz kurmaz/oyunu açmaz. Girdiler, firmware, capture'lar, generated
kod ve büyük derleme çıktıları Git'e eklenmez.

## Build40 çekirdeklerinin kontrolleri

- `out/geometry-final-host-test.log`: ASan/UBSan altında5 skinning +3 culling;
  özgün grafik / statik ARM64 / paralel döngü simülasyonu karşılaştırmaları.
  Tam GPR/PC/LS eşit; FPCR/FPSR saklama testi geçti.
- `out/geometry-final-metal-test.log`: Apple M3 Metal GPU'sunda8 durum;
  tam GPR/PC/LS ve dirty bitmap doğru, bellek çakışma koruması açık.
- `out/geometry-runtime-test.log`: üretim adaptöründe3 yol ×2 işlem ×10 çağrı;
  ilk8 karşılaştırma ve sonraki doğrudan commit'ler doğru. Sürekli doğrulama
  ve paylaşılan-LS fallback testleri geçti. Host testine özel kasıtlı register
  hatası özgün çıktının korunmasını ve yalnız ilgili yolun kilitlenmesini
  doğruladı; bu hata enjeksiyonu üretim uygulamasında derlenmez.
- `out/geometry40-final-build.log`: Release/iPhoneOS/arm64 build40.
  Ayarlar UIKit ile derlendi; cihazda panel/görüntü testi henüz yapılmadı.

**Önemli sonuç:** Mac adaptör testinde Metal yolu CPU'dan pahalı kaldı.
Bu test ASan/UBSan ve zorunlu karşılaştırmalar içerir; ölçülen toplamlar üretim
FPS A/B'si değildir. Yine de Metal'e taşımanın otomatik kazanç olmadığını açıkça
gösterir. Skinning Metal yolu bu aşamada doğrulanmış bir **hesap prototipi**;
hızlanma sonucu değil. ARM64 alternatifi aynı paketten ayrı ölçülebilir.
Culling Metal henüz paralelleştirilmedi. Sonraki cihaz oturumunda ilk karar,
bu yolların CPU'ya dönüş dahil maliyetini ve gerçek kare süresini karşılaştırmak.

## Hazırlıkta belirlenen cihaz protokolü (sonradan uygulandı)

Önce bir kez kurulum; bütün deneyler aynı paketten. İlk oynanışta tek yeni yol
ve doğrulama açık: uyuşmazlık/hata/fallback ve görüntü kontrolü. Sonra doğrulama
kapalı, zorunlu8 karşılaştırma ve ilk shader hazırlığı bittikten sonra normal
sıcaklıkta aynı kamera ile SPU/ARM64/SPU ve SPU/Metal/SPU. Culling ayrı ölçülür.
Doğrulama hatası veya düşük kapsama varsa hız sonucu verilmez; fixture alınıp
önce sözleşme düzeltilir. FPS, kare dağılımı, uçtan uca job süresi ve GPU/CPU
örtüşmesi birlikte değerlendirilir. Bilinmeyen diğer job'lar bu tur tahminle
GPU'ya taşınmadı; build38'de kanıtlanan iki işle sınırlı kaldık.
