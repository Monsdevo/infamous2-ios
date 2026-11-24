# Build 46 ilerleme yazıcısı teşhisi ve build 47 adayı

28 Ekim 2026. Amaç hâlâ devam ediyor; henüz bu aday için cihaz FPS kazancı yok.

## Gerçek cihaz kaydı

Build46 UUID `E1160583-A30E-3FC2-989B-6FC8DB009A66`, PID7471. Kullanıcı ilk oynanışta karakter/kamerayı sabit bıraktı. `out/critical-path43/46-joint-progress-cpu/` altında 15,003 saniye CPU örneklemesiyle örtüşen 2 saniye ilerleme yazıcısı izi var: 220.818 olay, düşen0, 495 PPU snapshot, 10.180 başarılı yazıcı grubu, eksik grup0. Beş saniyelik ilk deneme olay sınırını aştığı için reddedildi. Yoğun iz açıkken FPS performans sonucu çıkarılmadı.

`0x00504DF0`, satırın +2..+14 alanlarındaki yedi16bit değerin minimumunu hedefle karşılaştırıyor. `0x005054F0` ayrıca sıfır sonlandırıcılı komut etiketlerini tarıyor; yalnız minimum kontrolüne indirgenmedi. Kuyruk/yazıcı belleğine müdahale edilmedi.

Yedi lane yedi bağımsız SPU anlamına gelmiyor: lane1 ortak yazılıyor; lane2..6 değişimleri sırasıyla SPU8192..8196 ile güçlü biçimde eşleşiyor. Başarılı atomik yazıların native stacklerinde WWS `0x3450` tamamlanma ve `0x2478` iş alma/güncelleme kodları görülüyor. Tekrar aynı byte yazımı yeni ilerleme sayılmadı.

CPU ile eşleştirme yaklaşık: snapshot en fazla5ms eski, kendi lane geride ve arada o lane için gözlenen değişim yok şartlarıyla 367 SPU örneğinin19'u kabul edildi. 13 örnek `jobmod_1774dd41c4e8_e14f90`,3 örnek `jobmod_638a73a6476e_e60c0`,1 örnek `jobmod_867e5d2348b3_e2898`,2 örnek job atası olmayan runtime. Bu küçük altküme tam kritik yol veya job süresi kanıtı değildir. Interpreter stack atası tek başına yoğun yorumlama kanıtı sayılmaz.

## Build47 neden bu adayı deniyor?

`spu_indirect_branch` mevcut ortak hızlı resolver yoluna sahip, fakat resident overlay>=200 olduğunda doğrudan yavaş yola gidiyor. BCES WWS image100 için, özgün çözüm sırasını koruyarak ortak yola izin verildi. Gerçek IRQ register restore adresi/interrupt koşulu, stop, servis, tanı ve lookup miss yine özgün resolver'a gidiyor. Oyun hesapları, komut sırası veya senkronizasyon kontrolü atlanmıyor.

`spu_task_launch_check`, her trampoline geçişinde `spu_check_stack_reset` aramasını yineliyor. Kayıt anında tutulan konservatif256byte LS sayfa haritasıyla kesinlikle eşleşemeyecek PC'lerde bu arama atlanıyor. Pozitif sayfada özgün fonksiyon/image/TLS denetimi aynen çalışıyor. Adresler elle beyaz listeye alınmadı.

Kaynaklar: `tools/prepare_spu_dispatch.py`, `src/platform/SpuDispatchControl.{h,c}`. Değişiklik yalnız türetilmiş iOS runtime kaynaklarında. Özgün compact renderer nesnesi SHA256 `a38a783205f6f0c037aae5eb694396dc481748265b924df09b14c1ac1bf2c746` korundu. Sabitlenmiş genel runtime değiştirilmedi. Normal açılışta yeni yol kapalı.

## Doğruluk ve sınırlar

ASan/UBSan altında512 tam-context differential durumu: özgün ve aday aynı context/LS sonucu üretti. Overlay/task/reloc sahipliği, yüksek PC bitleri, bekleyen IRQ, gerçek IRQ dönüşü, interrupt kapalı ve servis/policy fallbacks sınandı. Adayda144 hızlı,368 fallback durum gerçekten çalıştı.

SDK dispatch/reset/return altkümesi her iki yolda29 başarılı, aynı1 eski fixture uyumsuzluğu verdi: `overwriting a code buffer invalidates its old image`. Fixture byte'ları değiştirmeden yalnız EA değiştiriyor; mevcut content-aware overlay aynı byte'ları koruyor. Tam SDK süiti geçmiş sayılmıyor. Differential kayıtları ayrı süreçte yürütülüyor; global kayıtların eski SDK fixture EAlarıyla çakışması bu şekilde önleniyor. Ayrı thread-group fixture eski import-handle ABI kullandığı için bu kapsamda değil.

Tekrar üretim:

```sh
python3 tools/prepare_bces_ios.py
python3 tools/test_spu_dispatch.py --baseline
python3 tools/test_spu_dispatch.py
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp cmake -S cmake/bces-ios -B build/bces01229/ios
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp cmake --build build/bces01229/ios --config Release --target Infamous2Game --parallel 1
```

Cihazda `--spu-dispatch-control` ile başlatılır; session/token kontrollü `tools/geometry_device_control.py --spu-dispatch 0|1` seçer. FPS penceresinde CPU profili, zaman izi ve yüzey capture kapalı olmalı. İki renderer memo kapalı; Metal lighting/SSAO açık, geometri SPU/SPU. Aynı sahnede kapalı/açık/kapalı kontrolü, termal sınıf ve gerçek present interval CSV ile ölçülecek. Çalışma sayacı düşmesi FPS kazancı sayılmaz.
