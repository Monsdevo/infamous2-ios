# MFC son yuva ipucu — uygulama ve iPhone deneyi

1 Kasım 2026. Kullanıcının istediği bu adım uygulama ve ölçümdür.

## Uygulanan yol

`tools/prepare_mfc_hint.py::patch`, yalnız üretilen iOS kanal kaynağındaki
`mfc_for` işlevini `mfc_for_scan` olarak adlandırıp önüne bir wrapper ekler.
Özgün arama/claim ve `spu_mfc_release` gövdeleri aynen korunur. Native test
bu dönüşümü geri çevirip kaynağın aynı olduğunu kontrol eder.

`mfc_for` thread-local son `spu_mfc_slot*` tutar. Slot tablosu process boyunca
yaşar; ipucu serbest bırakılmış context belleğine işaret etmez. Hit için
slot owner'ı atomik acquire ile mevcut context'e eşit olmalıdır. Miss özgün
aramaya gider; dönüş gerçek slot dizisindeyse ipucu güncellenir. Özgün
overflow/fallback engine dönüşünde ipucu temizlenir.

Bu, macOS/Linux yönteminin **ABI koruyan TLS uyarlamasıdır**. Upstream'deki
context başına alanı kopyalamaz: aynı host thread'de context değişimleri hit
oranını düşürebilir. `spu_context` düzeni, hazır SPU arşivleri ve pinned runtime
değişmedi. Poison taraması build 52'deki özgün sayaçsız biçimde açık; overlay,
slot hizalaması, DMA kopyası, fence, tag ve coherency değişmedi.

`MfcHintControl.c` modları: 0 özgün arama, 1 ipucu, 2 ipucu + her çağrıda
özgün oracle. **0/1 modlarında çağrı başına sayaç artırımı yoktur.** 2 yalnız
ölçüm dışındaki doğruluk/kapsam denemesidir; mismatch özgün sonuca dönüp
ipucunu kapatır. Varsayılan 0. `GameApp.mm` session-bound `mfc_hint` komutunu
yalnız `--mfc-hint-control` ile açılan süreçte kabul eder; katı integer 0/1/2
tür kontrolü `GeometryControl.mm` içindedir.

## Tamamlanan doğrulama

- `python3 tools/test_mfc_hint.py`: gerçek registry/wrapper ve gerçek
  context/engine türleriyle ASan/UBSan geçti. 128 slot, çoklu context,
  stale/reused slot, overflow, engine reset ve 32 eşzamanlı ilk claimant.
  42.504 oracle karşılaştırması, 37.218 hit, mismatch 0.
- Native katı kontrol komutu testi geçti; yanlış türler ve aralıklar reddedildi.
- Test edilen registry gövdesinin üretilen iPhone kaynak gövdesiyle birebir
  aynı olduğu doğrulandı. `out/ios-mfc53/source-hashes.json`.
- iPhoneOS Release build 53 tek işte derlendi: `out/mfc53-build.log`.
  Mevcut uygulamanın üzerine kuruldu; oyun verileri silinmedi.

İlk açılış PID 5118, ipucu modu 0 iken 1.074 sunumda durdu; ilerleme raporları
korundu. Tam log aktarımı iki kez dosya servisi tarafından yarıda kesildi.
Bu açılış ölçüm değildir; takılmanın kök nedeni bu turda belirlenmiş değildir.
İkinci açılış PID 5139 görüntü üretti, kayıtlı oyundan menüyle Yeni Oyun'a
geçildi. `out/ios-mfc53/relaunch.json` ve `newgame-selected/frame.png`.

## Ölçüm düzeni

`tools/measure_device_mfc53.py` sahne kanıtını bekler. Önce termal 0'da
durulma, ardından kısa mode2 oracle kontrolü; FPS pencerelerinde mode2 kapalı.
Sıra 0/1/0/1/0, her biri en az 30 saniye ve 180 ham sunum aralığı.
Sabit PID/session, nominal termal kategori, aynı baseline yolları,
shader/validation/log durumu ve renderer hataları kontrol edilir.
Oracle sayaçlarının FPS pencerelerinde değişmemesi şarttır. Sonunda yeniden
mode2 kapsamı kontrol edilir ve mod0 geri yüklenir.

```sh
python3 tools/prepare_bces_ios.py --support-report out/bces-support-compile-iphoneos-spu-O2-copy.json --mfc-hint-experiment
cmake -S cmake/bces-ios -B build/bces01229/ios -DBCES_DMA_ORIGINAL_SCAN=ON
# iPhoneOS Release, -jobs 1; --mfc-hint-control ile başlat.
python3 tools/drive_device_gameplay.py --device 00008130-001129E00243001C --output out/ios-mfc53/tutorial
python3 tools/measure_device_mfc53.py --device 00008130-001129E00243001C --run out/ios-mfc53
```

## Tamamlanan iPhone sonucu

Kamera öğreticisi CROSS/RY=0/RX=0 ile otomatik tamamlandı; iki gerçek görev
yazısı ve sabit liman görüntüsü kaydedildi. İlk beşli tur ortasında runtime
log sınırına ulaşıldı. Sınırı geçen pencere dışlansa da ilk ve sonraki pencerelerin
log yükü farklı kalacağından bütün karşılaştırma dışlandı:
`out/ios-mfc53/verdict.json`.

Oyun yeniden açılmadan, aynı PID 5139 ve kamerada, log sınırı baştan aktifken
`out/ios-mfc53-stable` turu tamamlandı. Beş pencerede de termal 0, shader
1.431→1.431, renderer/lighting/SSAO hata 0, profiling/validation kapalı.
Oracle sayaçları her FPS penceresinde sabit kaldı. Ön/son ayrı doğrulamalarda
toplam 55.004.628 oracle karşılaştırması, mismatch 0. Gerçek TLS hit kapsamı
doğrulandı; bu sayılar FPS pencerelerinin hit oranı değildir.

| Tur | MFC ipucu | FPS | Ortalama kare aralığı |
|---|---|---:|---:|
| A | Kapalı | 6,67829 | 149,73894 ms |
| B | Açık | 6,67878 | 149,72797 ms |
| C | Kapalı | 6,66529 | 150,03106 ms |
| D | Açık | 6,67916 | 149,71947 ms |
| E | Kapalı | 6,48091 | 154,29925 ms |

Toplam 1.068 ham sunum aralığı. Frame/süre ağırlıklı kapalı **6,60825 FPS /
151,32602 ms**, açık **6,67897 FPS / 149,72378 ms**. Gözlenen fark **1,60224 ms,
FPS +%1,07013**. İlk dört pencere neredeyse aynı; toplu farkın çoğu son kapalı
pencerenin düşmesinden geliyor. İlk dört p95 de aynı 183,37129 ms.

**Anlamlı, tekrarlanabilir kare süresi kazancı doğrulanmadı; aday varsayılan
optimizasyona kabul edilmedi.** Bu, registry aramasının CPU süresinin hiç
değişmediği kanıtı değildir; yalnız bu sahnede presented frame-time kazanımı
gösterilmedi. Mac üzerinde performans ölçülmedi. Sabit termal kategori eşit
saat hızını veya bütün oyun için kazancı kanıtlamaz.

Ham kanıt: `out/ios-mfc53-stable/comparison.json`, `verdict.json`, A–E
`summary.json`/`frames.csv`, `oracle-before.json`, `oracle-after.json`,
`final-scene/frame.png`. Aggregation/restore durumu ayrıca kontrol edildi;
ölçüm sürücüsü başarıyla bitti ve MFC mode0 geri yüklendi.

Deneysel build 53 `build/bces01229/baselines/mfc53-experiment/Infamous2Game.app`
altında arşivlendi. Kazançsız wrapper'ın ek flag kontrolünü normal yola
taşımamak için hazırlayıcıda `--mfc-hint-experiment` opt-in kapısı eklendi;
normal hazırlama özgün aramayı korur. Mevcut üretilmiş kaynak hâlâ test edilen
53 varyantıdır; yeni bir normal hazırlama bunu yeniden üretir.

Telefon bilinen sayaçsız build 52'ye başarıyla geri kuruldu; kurulum kaydı
`out/ios-mfc53-stable/restore-build52.json`. Oyun verileri silinmez. Sonraki
bağımsız aday upstream overlay imza/LS-sayfa erken eleme filtresidir; bu turda
uygulanmadı.
