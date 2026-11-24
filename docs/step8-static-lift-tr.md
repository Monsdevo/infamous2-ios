# 8. adım — gerçek offline lifter ve oyun girdileri

Kullanıcı oyun dosyalarının henüz hazır olmadığını belirtti. Gerçek title/LLE
üretimi bu girdileri bekliyor. Buna karşılık gerçek **ELF → loader → lifter →
C++ → ARM64 → PPU dispatch** zinciri özgün, küçük bir PowerPC programıyla
uygulandı. İlk oyun görüntüsü elde edilmedi: **game_frames=0**.

## Ne değişti

Önceki `make_smoke_elf.py` yalnız ELF/veri/ABI kabuğu üretiyordu; CPU
fonksiyonları `FullRuntimeProbe.cpp` içinde elle yazılmıştı. Bu yol GCM ve
yaşam döngüsünü sınamaya devam ediyor. Yeni programın CPU fonksiyon gövdeleri
ise gerçekten sabitlenmiş `ppu_lifter.py` tarafından üretiliyor.

1. `tools/build_lifted_probe.py::build_elf()` kendi testimizin PPC komutlarını
   ELF64/big-endian/EM_PPC64 içine koyar. İki OPD descriptor, executable/data
   segmentleri ve BSS vardır; oyun veya firmware içeriği içermez.
2. Sabit fork'un `tools/ppu_loader.py::main()` fonksiyonu OPD section'ından
   iki fonksiyonu kendisi bulur. Hazır elle yazılmış function listesi verilmez.
3. `tools/ppu_lifter.py::main()` bu ELF ve bulunan function/import JSON'larıyla
   **tek iş** kullanarak C++ üretir. `--symbol-prefix aot_` tablo ve fonksiyon
   adlarının mevcut tanıyla çakışmasını önler. Gerçek PPC `sync`, lifter'ın
   `PPU_FENCE(seq_cst)` yolundan geçer; ARM bellek bariyerleri korunur.
4. `cmake/FullRuntime.cmake` bu üretimi build dependency olarak tanımlar;
   `lifted_ppu.cpp` ve `src/full/LiftedPPUProbe.cpp` aynı SDK ile derlenip
   mevcut tam runtime hedefine bağlanır. ELF uygulama bundle'ına alınır.
   macOS ve iOS için ayrı object'ler üretilir; host arşivi iOS'a bağlanmaz.
5. `LiftedPPUProbe.cpp::lifted_ppu_probe()` mevcut 3,5 GiB guest arena'da
   `ppu_load_elf()` ile yükler, üretilmiş `aot_function_table` kayıtlarını
   `ppu_register_function()` ile ekler ve **gerçek `ppu_run()`** çağırır.
   `FullRuntimeProbe.cpp::probe()` bunu mevcut GCM tanısından önce çağırır.

CPU komutları build sırasında çevrilir ve imzalı uygulamanın native kodudur.
Telefonda ELF'nin PPC metnini çalıştıran interpreter/JIT yoktur. Metal'in
shader derlemesi ayrı grafik yoludur; bu CPU statik derlemesiyle karıştırılmaz.

Bu hâlâ yalnız tanı hedefidir: iki küçük ELF aynı tek kullanımlık test VM'inde
çalışır; runtime image-high/thread kayıtları tutulur. Gerçek oyunun veya LLE
firmware'in başlatıcısı değildir ve gelecekteki oyun hedefine bu fixture
eklenmeyecek. Süreç içi tam runtime teardown/restart çözülmüş sayılmaz.

## Sonuçlar

**Gerçek iPhone 15 Pro / A17 Pro / iOS 27.2:** yeni sürüm imzalandı,
kuruldu ve çalıştı. Yedi AOT kontrolünün tamamı geçti:

- ELF entry OPD'si ve üretilmiş iki fonksiyonluk tablo;
- önceden 0xA5 ile doldurulmuş BSS'nin loader tarafından sıfırlanması;
- üretilmiş giriş fonksiyonunun dönmesi;
- PPC koşullu döngüyle 1..10 toplamı **55**;
- ayrı fonksiyon çağrısı / LR-stack dönüşü, `3 × 55 + 7 = 172`;
- big-endian store/load ve gerçek bellekte `12 34 56 78` bayt sırası.

Ardından mevcut GCM tanısı **12 submitted / 12 completed / 12 presented,
0 GPU hatası** ile bitti. 300 ms pause boyunca iş sayısı 5'te sabit kaldı,
resume ve PPU/renderer join + layer detach geçti. SDL controller init geçti;
gerçek oyun girişi ve ses testi yapılmadı. Son fiziksel footprint örneği
88.360.896 bayt, yaklaşık **84,27 MiB**; bu oyun belleği ölçümü değildir.

Mac'te **12/12 CTest PASS**, buna seri/threaded/stop sırasında yeni AOT
zinciri dahildir. iPhoneOS uygulaması IOS/minimum17.0/SDK27.1; sistem güven
deposuna erişen `codesign --verify --deep --strict` başarılı. Sandbox içindeki
ilk imza denetimi `CSSMERR_TP_NOT_TRUSTED` verdi; sistem bağlamında tekrar
doğrulandı. Bağımlılıklarda AppKit/Homebrew dylib'i yok.

Simulator SDK derlemesi/bağlantısı da **PASS**; executable platformu
IOSSIMULATOR/minimum17.0/SDK27.1. Simülatör açılmadı, simülatör performansı
ölçülmedi. Önceki dört upstream draw-engine
beklenti farkı baseline karşılaştırma kapısında korunur; ham upstream testin
tümü başarılıymış gibi değerlendirilmez.

## Araçlar ve girdiler

Ortamda **Python 3.12.5** doğrulandı:
`/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12`.
Gerçek loader/lifter'ın bu yolunda Python standart kütüphanesi yeterli oldu;
capstone, pycryptodome, construct vb. paket kurulmadı. Toolkit'in genel
`requirements.txt` listeleri alt sürüm sınırı içeriyor, bağımlılık kilidi değil.
İleride decryption/diğer analiz araçları gerekirse ayrı venv ve kaydedilmiş
sürümlerle hazırlanacak; tüm toolkit bu testle doğrulanmış sayılmaz.

Port ve fork pin'leri `tools/setup_sources.py` ile tekrar doğrulandı;
`770660a3971b87a453677e46125e5e01ac7891c0` + mevcut birleşik title yaması korunuyor.
Upstream kaynaklar değiştirilmedi. Derlemeler **en fazla 2 iş**, SDK'lar sırayla.

Kullanıcının yerleştireceği dosyalar ve tam yollar:
[oyun girdisi rehberi](game-inputs-tr.md). `data/incoming/`, `data/game/NPUA80638/USRDIR/`,
`data/firmware/{prx,dev_flash}/` oluşturuldu ve Git ignore kontrolünden geçti.
`check_inputs.py` varsayılan olarak artık bu `data/` konumlarını kullanır;
`--game-dir`, `--eboot`, `--firmware-dir` alternatifleri korunur.

`check_inputs.py::elf_facts()` artık file-size > memory-size, 3,5 GiB guest
arena dışına taşma ve EBOOT entry OPD'sinin executable code'a çözülmemesini
de reddeder; segment offset/flags ve OPD sonucunu raporlar. Özgün geçerli ELF
ve bu üç bozuk girdiyle kontrol edildi. Bu yapısal denetim içerik eşitliği,
oyun verisinin eksiksizliği veya firmware sürüm uyumu kanıtı değildir.

## Tekrar üretme / kanıtlar

```sh
cd /Volumes/monssd/Infamous2-iOS
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
python3 tools/setup_sources.py
tools/build_probe.sh host
tools/build_probe.sh ios
tools/build_probe.sh simulator
# İmzalama/cihaz kurulum komutları README'de.
xcrun devicectl device process launch --device "$PROBE_DEVICE_ID" \
  --terminate-existing dev.infamous2.iosprobe -- --lifecycle-test
xcrun devicectl device copy from --device "$PROBE_DEVICE_ID" \
  --domain-type appDataContainer --domain-identifier dev.infamous2.iosprobe \
  --source Documents/threaded-runtime-report.txt --destination out/step8-device-lifted-report.txt
python3 tools/check_inputs.py > out/step8-inputs-final.json
# Oyun/firmware eksikken son komutun çıkış kodu 1 beklenir.
```

Üretim komutunu tek başına çalıştırmak için:

```sh
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 \
  tools/build_lifted_probe.py --source upstream/infamous2-recomp/ps3recomp-fork \
  --output build/aot-check
```

Her SDK'nın `build/<sdk>/full-runtime-generated/lifted-probe.manifest.json`
dosyası Python sürümünü ve ELF/header/C++ SHA-256 değerlerini kaydeder.
Kanıtlar Git dışında `out/step8-{device-lifted-report.txt,host-final-tests.log,
ios-signed-build.log,simulator-build.log,codesign-verify.log,sources-check.log,
input-gate-tests.json,inputs-final.json,verification.json}` içindedir.

## Sıradaki somut adım

Kendi NPUA80638/01.03 oyun yedeği ve firmware kaynağı geldiğinde önce kaynak
dosyalar korunarak içerik/sürüm/hash envanteri çıkarılacak. Çözülmüş EBOOT ve
liblv2/libsysmodule/libsre üretilecek, firmware SPU sabitlerinin o içerikle
uyumu incelenecek. Ardından title PPU/SPU + firmware LLE çıktıları mevcut
oyuna özel GPU light/SSAO/SPU düzeltmeleriyle macOS referans hedefinde
başlatılacak, iOS başlatıcısına taşınacak. Bugünkü AOT testi **bu tam oyun
hedefinin hazır veya derlenmiş olduğu anlamına gelmez**. Başarı ölçütü
gerçek guest draw/flip ve doğru ilk oyun karesidir; menü/oynanış henüz yok.
