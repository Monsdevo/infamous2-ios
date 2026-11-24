# RSX yinelenen durum işleme — ilk uygulama / build43

27 Ekim 2026. Kullanıcı onayı: dar RSX uygulamasını hazırla, yerel doğruluğunu
kontrol et, iPhone'a kur; **cihaz ölçümü başlatma**. Bu oturumda oyun açılmadı.

## Değişiklik

`src/platform/RSXLegacyFastPath.c:bces_rsx_legacy_method`, yalnız aktif dispatch
engine ve eski backend yokken kullanılmayan eski `rsx_state` güncellemelerini
atlayan bir iOS adaptörü. Bu render algoritması veya yeni GPU shader'ı değil.
Aktif engine her FIFO method'unu hâlâ aynı yerde, değiştirilmeden bir kez alır.

Atlananlar açık bir whitelist: surface/viewport/blend/depth/stencil, texture,
vertex format/offset, shader program/constant ve benzeri **eski modelde yalnız
state yazan** method'lar. Bilinmeyen adresler ve whitelist dışı method'lar
özgün işlemciden geçer. Eski işlemcinin tüm maliyetini kaldırdığımız iddia edilmez.

Korunanlar özgün `rsx_process_method` üzerinden çalışır:

- `0x1D6C/1D70/1D74` semaphore offset/release, donanım byte-swap ve snapshot.
- `0x50` reference; FIFO'daki paced reference queue aynı kalır.
- BEGIN_END, draw arrays/index, clear değerleri/clear ve milestone bildirimleri.
- Legacy backend mevcutsa bütün method'lar ve backend callback'leri.
- Duruma bağlı RSX debug ortam değişkenleri varsa tam eski state yolu.

GCM'nin acquire, 2D, user-command, report ve flip kodu değiştirilmedi.
`tools/prepare_rsx_legacy.py:instrument` yalnız üç dar ekleme yapar: önceden
hesaplanan dispatch seçimini adaptöre geçirir; eski parser çağrısının yerine
adaptörü koyar; mevcut FIFO mutex'i bırakılmadan sayaçları yayınlar.
`tools/prepare_frame_diagnostics.py` bu dönüşümü derived iOS kaynağına uygular.

Original pinned `rsx_commands.c/.h` SHA-256 değerleri `sources.lock.json`'a
kaydedildi. Whitelist yeniden incelenmeden kaynak/header değişikliği prepare'da
reddedilir. Runtime fork, macOS hedefi, title/support arşivleri ve oyun kodunun
SPU/PPU davranışları değiştirilmedi. Eski `rsx_commands.o` aynen bağlıdır.

## Ayar ve sayaçlar

Üç nokta → **Renderer deneyi → RSX tekrarlı durum işlemeyi azalt**.
Varsayılan açık; seçim bir sonraki uygulama açılışında uygulanır. Backend
çalışırken değiştirme/hot-swap kapsam dışıdır; runtime API'si backend'i komut
işlenmeden önce kaydeder. Bir süreçte RSX seçimi dondurulur.

Yarın A/B için aynı binary'de `--rsx-legacy-off` veya `--rsx-legacy-on` açılış
argümanı kullanılabilir. Bu argüman kayıtlı ayarı yalnız o süreç için geçersiz kılar.
Metal aydınlatma/SSAO, geometri seçimleri ve önceki diğer ayarlar korunur.

HUD'a RSX yolu/atlanan method göstergesi, JSON ve CSV'ye dokuz alan eklendi:
`rsx_legacy_configured`, `requested`, `enabled`, `debug_fallback`, `methods`,
`state_skipped`, `forwarded`, `sync_forwarded`, `draw_forwarded` (hepsi
`rsx_legacy_` önekli). `enabled`, seçeneğin uygun olduğunu gösterir; gerçek
uygulama kapsamı `state_skipped` artışıyla doğrulanır. `hazır` yazısı tek başına
optimizasyonun uygulandığı anlamına gelmez.

Per-method sayaçlar mevcut FIFO mutex'i altında normal integer olarak artar.
Her drain sonunda atomik snapshot yayınlanır; UI o snapshot'ı okur. Her method'a
atomik RMW veya saat ölçümü eklenmedi. CSV header/key sayısı115 ve sıra eşleşmesi
kontrol edildi. Eski kayıt dosyaları uygulama açılmadığından bu oturumda döndürülmedi.

## Yerel doğrulama

`python3 tools/test_rsx_legacy.py` gerçek pinned `rsx_commands.c` ile adaptörü
ASan/UBSan altında karşılaştırır. Yeni GPU benchmark'ı veya cihaz kaydı değildir.

Altı senaryo: açık/kapalı, dispatch yok, eski backend var, RSX debug açık ve
legacy seçimi. Her senaryoda **37.384 method**, bütün canonical aligned FIFO
adresleri ve sekiz veri dizisi. Aktif hızlı senaryoda20.032 state-only çağrı
atlandı; bu sentetik oran gerçek oyun kapsama yüzdesi değildir.

VM label yazıları, snapshot olayları, reference değerleri, draw milestone'ları
ve backend callback'leri aynı çıktı. Fallback senaryolarında bütün eski state
byte'ları da aynı. Eşzamanlı UI snapshot testi ve bir süreçte seçimin sabit
kalması geçti. Whitelist dışındaki bilinmeyen adresler de özgün yolda kaldı.

GCM kaynak dönüşümü tersine çevrildiğinde pinned kaynağın tamamı byte olarak
aynı: engine/2D/flip/report/reference/acquire/FIFO akışına başka değişiklik yok.
Bu kaynak/yapı testi, telefonda görüntü eşdeğerliği testi yerine geçmez.

Kayıt: `out/rsx43-host-tests.log`.

## Derleme ve kurulum

- iPhoneOS Release, jobs1, TMPDIR SSD: `out/rsx43-build.log` **BUILD SUCCEEDED**.
- İmza `codesign --verify --deep --strict` geçti.
- Binary build43 / `dev.infamous2.iosprobe`; gerçek GCM object'i yeni method ve
  publish fonksiyonlarını çağırıyor. Özgün `rsx_process_method` tek tanım halinde
  korunuyor. Bilgi/hash/UUID: `out/rsx43-build-result.json`.
- Mevcut uygulama kimliğine güncelleme başarılı: `out/rsx43-install.json`.
  Oyun dosyaları tekrar aktarılmadı; uygulama kaldırılmadı.
- Build42 geri dönüş paketi `build/bces01229/baselines/rsx43-app/Infamous2Game.app`;
  değişen küçük kaynakların önceki kopyaları `baselines/rsx43-source/`.
- **Kurulumdan sonra launch yapılmadı.** FPS, termal veya oynanış ölçümü yok.
  Cihazda görsel eşdeğerlik/kararlılık ve kazanç henüz doğrulanmadı.

```sh
python3 tools/test_rsx_legacy.py
python3 tools/prepare_bces_ios.py --support-report out/bces-support-compile-iphoneos-spu-O2-copy.json
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp /opt/homebrew/bin/cmake -S cmake/bces-ios -B build/bces01229/ios
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp xcodebuild -project build/bces01229/ios/Infamous2BCESIOS.xcodeproj -scheme Infamous2Game -configuration Release -destination 'generic/platform=iOS' -jobs 1 -derivedDataPath build/bces01229/DerivedData DEVELOPMENT_TEAM=BJ266NGN3H
```

## Yarın

Aynı ilk oynanış, sabit kamera, geometri SPU/SPU ve doğrulama kapalı;
Metal lighting/SSAO iki tarafta açık. Önce özgün RSX, sonra yeni yol, ardından
referans kontrolü. Sıcaklık/pipeline/arka plan ve ham sunum olayları aynı yöntemle
kontrol edilir; yeni yolun gerçekten `state_skipped` ürettiği doğrulanır.
Görüntü/sync hatası varsa FPS değerlendirmesine geçilmez. Kazanç ölçülmeden
başarı yüzdesi/FPS tahmini verilmez. Bu sıraya bu oturumda başlanmadı.
