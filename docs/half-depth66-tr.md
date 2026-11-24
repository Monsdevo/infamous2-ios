# Build 66 · SSAO yarım derinlik doğrulaması

`--half-depth-probe` ile türetilen iPhoneOS hedefi, frame trace açıkken
özgün SSAO pass 0 ve aynı renderer epoch'una ait Metal R32Float
yarım derinliğini karşılaştırmaya hazırlar. Kopyalama ve fallback
davranışı korunur.

Metal SSAO uygunluk kontrolü guest iterator durumunu ve doğrulanmış
640×360 hedef adresini renderer epoch'u ile kaydeder. `SSAODepthBoundary`
özgün atomik iterator sonraki pass'e geçtiğinde guest çıktısını alır.
Aynı epoch için `eng_ssao_pass` Metal kopyasını talep eder ve
`ENG_REC_SSAO` içindeki komut tamponunun tamamlanma callback'i iki
çıktıyı tek dosyada yayımlar. Guest değerleri big endian, Metal
R32Float değerleri little endian okunur. Analiz dosyayı zaman izi
başlangıcı ve tamamlanmış guest yayım olayı ile doğrular.

İz yarım derinlik EA aralığına gelen SPU GET/GETL, PPU vm_read
yardımcıları ve seçili renderer tampon taleplerini kapsar. Doğrudan
bellek erişimleri, atomik okumalar ve bu noktalardan geçmeyen texture
tüketicileri kapsam dışındadır. İlk gözlenen erişim bu sınır içinde
yorumlanır. Tanı kopyası FPS ölçümü için kullanılmaz.

```sh
PYTHONPATH=tools python3 tools/prepare_bces_ios.py \
  --support-report out/bces-support-critical62.json --half-depth-probe
cmake -S cmake/bces-ios -B build/bces01229/ios
# Release / generic platform=iOS / -jobs 1, mevcut geliştirme imzasıyla.
# --diagnose-frame ile başlat. Oynanıştan bir saniye frame trace kaydet.
# Aynı süreçten Documents/ssao-half-depth.bin dosyasını al.
python3 tools/analyze_half_depth_probe.py frame-trace.csv ssao-half-depth.bin \
  --output comparison.json
```

ASan/UBSan SSAO uygunluk testi, 416 özgün atomik claim ve yarış durumu
kontrolü, sentetik endian/ULP/okuma sırası ve eski yakalama reddi geçti.

## Cihaz sonucu

Release iPhoneOS derlendi, imzalandı ve iPhone 15 Pro'ya kuruldu.
İlk tanı dosyası planlanmış trace başlangıcından önceki bir kareye
aitti ve analiz tarafından reddedildi. Başlangıç/bitiş kontrolü
düzeltildi. Düzeltilmiş uygulamanın ilk oturumu, tanı kapalıyken
sinematikte kare üretmeyi durdurdu. Aynı kayıtla yeniden başlatınca
oynanışa ulaşıldı. Geçerli dört iz aynı süreçten ve
`3A08A280-41B8-3CAC-88BD-186A0AB3E360` UUID'li uygulamadan geldi.
Her iz bir saniye, termal kategori 2 ve olay kaybı sıfır.

| İz | Sahne | Birebir piksel | En fazla 1 ULP | En büyük ULP | Guest okuma |
| --- | --- | ---: | ---: | ---: | ---: |
| B | Sinematik | 49.480 / 230.400 | %98,87 | 2 | 0 |
| C | Sinematik sonrası pencere | 91.852 / 230.400 | %97,86 | 2 | 0 |
| D | Sabit bataklık | 92.075 / 230.400 | %97,82 | 2 | 0 |
| E | Sabit bataklık | 91.987 / 230.400 | %97,83 | 2 | 0 |

C için iz anına ait sahne görüntüsü yok. D/E öncesinde bataklık
oynanışı oyun yüzeyinden doğrulandı. Dört izde 38 SSAO epoch yayımı
ve hedef guest EA `0x47BFBB80` görüldü. Hiçbir karşılaştırmada
NaN/sonsuz çift veya 2 ULP üzeri fark çıkmadı. Guest belleği ile
bit düzeyinde uyumluluk kurulmadı. Tüm dört izde izlenen guest
okuma noktaları sıfır olay verdi. Daha geniş sahne ve fallback
kapsamı için bu sonuç tek başına yeterli değildir.

Sıradaki aday, eski pass 0'ın **iterator/label sözleşmesini** koruyarak
Metal yolunda SPU hesabını ve tam boy readback'i koşullu atlayan bir
prototip. Guest çıktısı gözlenen bir tüketiciye dönerse özgün yol
korunmalı. Mevcut Metal yarım derinlik dokusunu bit eşdeğerliği
kurmadan guest belleğine yayımlamamak gerekir. Bu tur optimizasyon
açılmadı ve kare süresi kazancı ölçülmedi.
