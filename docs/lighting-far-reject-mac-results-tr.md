# GPU aydınlatmada uzak ışık elemesi — Mac sonucu

28 Ekim 2026. **Mac M3 üzerinde aynı ilk serbest oynanış sahnesinde tekrarlanabilir
kare süresi kazancı doğrulandı. iPhone takip ölçümü de tamamlandı; ayrı sonuç notu
[burada](lighting-far-reject-iphone-results-tr.md).**

Toplu sonuç: referans **84,27ms /11,87FPS**, aday **75,78ms /13,20FPS**.
Ortalama **8,48ms**, yaklaşık **%10,07** kare süresi tasarrufu; FPS artışı
**%11,20**. İlk kapalı/açık/kapalı/açık/kapalı dizisinde tasarruf%10,24;
ters açık/kapalı/açık dizisinde%10,27. İki sırada da sonuç tekrarlandı.

## Ne değişti?

`tools/prepare_lighting_far_reject.py::fast_shader`, çalışan `eng_light_fs`
shader'ını koruyup ayrı `eng_light_fs_far` üretir. Özgün döngü her ışık için
uzaklık, normalize, attenuation ve dot hesaplıyor; katkı sıfırsa ancak sonra
`continue` ediyor. Aday önce uzaklık karesi/radius karesi için konservatif bir
sınır kontrol eder. Işık kesinlikle radius dışında, outer>inner ve spot
parametreleri güvenliyse özgün attenuation/weight sıfırdır; kalan hesaplar
atlanır.128 epsilon marjı kullanılır; küçük, sonlu olmayan ve alışılmadık
büyüklükler özgün hesap yolunda kalır.

Tile kabul maskesi, alpha tabanı, RGBM/specular paketleme, çözünürlük, ışık
sayısı ve oyun senkronizasyonu aynı kalır. Genel fast-math açılmaz.
`patch_backend` iki PSO'yu önceden hazırlar; `LightingFarReject.c` seçimi ve
hangi yolun gerçekten kullanıldığını sayar. Aday varsayılan kapalıdır.
Bu değişiklik CPU JIT içermez; mevcut Metal shader'ının işini azaltır.

## Ölçümün gerçek kapsamı

×, sağ analog yukarı ve sağ analog sola girdileri `drive_host_gameplay.py`
ile gerçek cellPad yolundan verildi. Her talimat önce görüntü/OCR ile görüldü;
sonra “Kargaşaya doğru ilerle” görev hedefi doğrulandı. Donmuş öğretici
sahnesi ölçülmedi. Aynı PID11508/session içinde karakter ve kamera sabit kaldı.

Her pencere45 saniye, toplam8 pencere ve4574 ham tamamlanmış GPU-present
aralığı. CPU profili, frame trace, GPU probe ve surface capture pencerelerde
kapalı. Shader derlemesi, render/compute hatası veya mod geçişi yok; bütün
örneklerde termal sınıf1, düşük güç kapalı. Dispatch ve renderer memo adayları
kapalı. Metrik ekran dışı Metal oyun karelerinin GPU completion zamanıdır;
ekran scanout'u veya iPhone FPS'si değildir.

| Pencere | Aday | FPS | Ortalama ms | P95 ms |
| --- | --- | ---: | ---: | ---: |
| far-reject A | Kapalı | 12.121 | 82.503 | 93.714 |
| far-reject B | Açık | 13.237 | 75.543 | 84.235 |
| far-reject C | Kapalı | 11.839 | 84.468 | 96.145 |
| far-reject D | Açık | 13.262 | 75.405 | 83.683 |
| far-reject E | Kapalı | 11.716 | 85.352 | 97.160 |
| far-reject-reverse A | Açık | 13.273 | 75.342 | 84.438 |
| far-reject-reverse B | Kapalı | 11.792 | 84.807 | 97.036 |
| far-reject-reverse C | Açık | 13.011 | 76.856 | 86.658 |

En yavaş açık pencere de en hızlı kapalı pencereden hızlıdır. Termal sınıf
aynılığı aynı saat frekansı garantisi değildir; bu nedenle iki farklı sırada
kontrollerle tekrarlandı. Diğer sahneler, uzun süreli iPhone termali ve A17
performansı bu sonuca dahil değildir.

## Doğruluk kontrolleri

- 9 mevcut tile ve2/8/32/128 ışıklı4 karışık tile'da GPU diffuse/specular
çıktıları referansla byte düzeyinde aynı. Karışık fixture'larda ayrı tanı
sayacı1.280/8.960/39.680/162.560 gerçek erken eleme kaydetti; bu tanı atomikleri
oyunun shader'ında bulunmaz.
- Gerçek aday koşulu,4.194.304 GPU girdisinde özgün uzaklık/attenuation/weight
hesabına karşı sınandı:1.212.839 eleme,0 uyuşmazlık. Tam float aralığı,
radius sınırı, inner/outer sınırı ve bozuk parametre sınıfları kullanıldı.
- Açık yolun gerçek oyun görüntüsü ayrıca incelendi; belirgin yeni bozulma
görülmedi. Bu, tüm oyunun byte/piksel eşitliği iddiası değildir.
- Ölçüm dışı son donanım kaydında aydınlatma fragment aşaması açık6,74ms,
kapalı16,77ms görüldü. Bunlar ayrı, değişken karelerdir; kesin10ms shader
kazancı veya toplam kare bütçesi diye kullanılmaz. Esas kazanç yukarıdaki
profilsiz ham kare karşılaştırmasıdır.

## Kimlik ve kanıtlar

Binary UUID `1A2B3B4F-00BC-3D58-B8BE-6A7C7AFC0BEF`;
SHA256 `289b15c4bf6c88f0a5eefaca263457e67bec2bdf17e8221d91ba113a4d42f57a`.
164 macOS PPU nesnesi,70 macOS O2 SPU birimi ve SDK'ya uygun bağımlılıklar;
iOS arşivleri Mac'e bağlanmadı. Eski çalışan Mac hedefi ve iPhone47 korundu.

Son denetim: `out/host-research/lighting-far-01/final-audit.json`.
`far-reject/` ve `far-reject-reverse/` altında bütün JSON örnekleri ve ham
CSV'ler var. Fixture sonuçları `out/lighting-far-guard/` ve
`out/lighting-far-mixed-test/`; sayısal test
`out/critical-path43/lighting-far-numeric-result.json`.
Oyun/firmware, shader dökümleri ve büyük üretilmiş çıktılar Git dışı.
GitHub'a değişiklik gönderilmedi.

## Tekrar üretim

Komutların başında `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer`
ve `TMPDIR=/Volumes/monssd/Infamous2-iOS/build/tmp` kullanılır. Derleme tek işçidir.

```sh
python3 tools/build_bces_spu_variant.py --sdk macosx --resume
python3 tools/prepare_host_research.py
cmake -S cmake/bces-research -B build/bces01229/host-research -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_ARCHITECTURES=arm64
cmake --build build/bces01229/host-research --target Infamous2Research --parallel 1
python3 tools/run_host_research.py --label next-unique-run --seconds 1800 --install-template out/host-research/lighting-far-01
```

Oyun oturumu çalışırken ayrı terminallerde:

```sh
python3 tools/drive_host_gameplay.py --run out/host-research/next-unique-run
python3 tools/run_host_light_comparison.py --run out/host-research/next-unique-run
python3 tools/run_host_light_comparison.py --run out/host-research/next-unique-run --label reverse --sequence 1,0,1 --warm-seconds 0
```

Sayısal GPU kontrolü, FPS pencereleri bittikten sonra:

```sh
python3 tools/prepare_lighting_far_numeric.py
xcrun clang -fobjc-arc -O2 tools/tests/lighting_far_numeric.m -framework Foundation -framework Metal -o build/bces01229/lighting-far-test/numeric-test
build/bces01229/lighting-far-test/numeric-test build/bces01229/lighting-far-test/numeric.metal
```

iOS entegrasyonu ve sıcak termal sınıfta iki yönlü karşılaştırma tamamlandı:
[iPhone sonuç notu](lighting-far-reject-iphone-results-tr.md). Mac kazancı
telefon için garanti olarak sunulmaz; ölçülen iPhone FPS artışı%3,83–5,14.

Ölçümlerden sonra aday kapatıldı ve yalnız bu Mac test oturumu durduruldu.
Bu sonlandırma bir oyun çökmesi değildir.
