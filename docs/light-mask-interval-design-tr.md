# Tam SPU aritmetiğiyle konservatif tile ışık listesi — tasarım

29 Ekim 2026. Mac araştırma hedefinde uygulandı; aşağıdaki doğrulama ve ölçüm sonuçları eklendi.
`gain40-05/mask-fixture.json` gerçek1280x720 depth +8272byte params girdisine
işaret eder; bu sahnede59 ışık vardır. Tamamen background elemesi ve ortak
erken bitiş tek başlarına hedefi karşılamadı. Bir sonraki hipotez: kesinlikle
tile dışında kalan ışıkları piksel başına sorgulamadan elemek.

## Uygulanabilir kesin sınır

Yeni sınıflandırma yalnız maske için olmalı; renk shader'ının ışık sırası veya
hesabı değişmez. Özgün `badd/bmul/bfma/brecip/bposition/bdistance/bmember`
fonksiyonları aynen tutulur. Float yaklaşık bbox yerine aynı integer SPU
aritmetiğiyle interval sınırları kurulabilir:

1.64 thread bütün geçerli depth örneklerinin özgün z24 dönüşümünden min/max
değerlerini toplar; geometry bit'i de özgün anlamıyla OR edilir. Tam background
tile mask0'dır. Depth alt/üst sınırı sky örneklerini de içermelidir; özgün
üyelik sky piksellerinde de denenir.
2.`BGrid` bir kez hesaplanır. Her h bileşeni için row=bfma(y,dy,top) uçları
y0/39'da değerlendirilir. Sonra a∈{.25,.5,.75,1} ve row interval'inin dört
uç kombinasyonu bfma(a,step,row) ile kapsanır.0..7 kez step eklenmesinin
interval hull'u badd ile kurulur. Son olarak z24 min/max ve dz çarpımının
uçları bfma ile h interval'ine taşınır. Korelasyon kaybı yalnız fazla aday
bırakır; yanlış ret üretmemelidir.
3.SPUnun normal/extended değerleri uint sıralama anahtarıyla karşılaştırılır:
exp0→zero-key0x80000000; negatif→~bits; pozitif→bits^0x80000000.
IEEE NaN/inf karşılaştırması kullanılmaz; SPU exponent255'i sonlu sayar.
4.h.w aralığı sıfırı içeriyorsa sınıflandırma fallback'tir. Aksi halde pinned
RCP monoton azalandır: invLo=brecip(wHi), invHi=brecip(wLo). Bunun parça parça
integer kanıt aracı `check_mask_recip_bounds.py`dir. FI her LUT segmentinde
nonpositive eğimli affine mantissa kullanır.2^31≤m<2^33 ise bir-normalizasyon
ve truncation monotondur; bütün segment birleşimleri kontrol edilmelidir.
5.Her P ekseni için bmul(hLo/Hi,invLo/Hi) dört köşe hesaplanır ve hull alınır.
RZ/flush/saturation monoton aritmetiği kullanıldığı için bu aşama da konservatif.
6.Işık pozisyonundan P interval'inin iki ucunu özgün badd ile çıkarmak q
aralığını verir.0 içeriyorsa o eksenin min|q| değeri0; yoksa iki uçtaki küçük
mutlak değer alınır. Özgün bdistance FMA sırasıyla bu üç alt sınırın kareleri
toplanır. Alt sınır≥özgün bmul(radius,radius) ise o ışık tile'da hiçbir
üyelik üretemez. Spot açısı bu kaba elemede kullanılmaz; kalanlar özgün
bmember ile sınanır.
7.Aday ışıklar threadgroup listesine konur. Maske yalnız existential OR
olduğu için bu listenin sırası sonucu değiştirmez. Sıfır aday tile mask0;
kalanlarda özgün bposition/bmember ve ortak erken bitiş kullanılır.

## Kanıt kapıları

- Interval noktalarının bütün gerçek fixture piksellerini kapsadığı GPU'da
ayrıca sınanmalı; yalnız son maskelerin eşleşmesi zayıf coverage olabilir.
- Değişken/negatif/zero-crossing w, kısmi tile, z sınırları, ışık sınırları,
SPU denormal flush/extended değerler ve negatif ışık radius'u ele alınmalı.
- RCP segment kanıtı yanlışsa uç-evaluasyon kullanılmamalı; fallback korunmalı.
- Herhangi bir belirsiz/unsupported durumda aday liste tüm ışıklar olmalı.
- Gerçek oyunda mode2 bütün720 tile'ı GPU'da özgün maskeyle karşılaştırır;
oyun bu modda özgün maskeyi kullanır. Uyuşmazlık adayı kapatır.
- FPS başarısı ayrı profilersiz OFF/ON/OFF/ON/OFF pencereleriyle ölçülür.
%40 hedefi henüz tamamlanmış değildir.

## Uygulama ve sonuç

`src/host/LightMaskInterval.metal` gerçek720tile girdisinde bütün konumları kapsadı ve maskenin tamamı aynı kaldı.576sentetik GPU fixture'ında2304tile eşit;2232containment ve72konservatif fallback. `gain40-06` gerçek oyunda47.520tile karşılaştırması0uyuşmazlık. Beş profilersiz pencerede ağırlıklı özgün12,8355FPS, aday13,9047FPS;77,9090→71,9184ms, +%8,33FPS. İstenen%40hedefi tamamlanmadı. Renk shader'ının hesabı ve sırası değişmez.

```sh
python3 tools/prepare_mask_interval.py
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcrun clang -fobjc-arc -O2 tools/tests/light_mask_empty.m -framework Foundation -framework Metal -o build/bces01229/gain40-mask-empty/test
build/bces01229/gain40-mask-empty/test build/bces01229/gain40-mask-empty/test-interval.metal
python3 tools/run_host_mask_comparison.py --run out/host-research/gain40-06
```

Son komut yalnız aynı canlı süreç ve scene-ready kanıtı varken, henüz kullanılmamış çıktı adıyla yeniden uygulanır. Eski bitmiş süreç için doğrudan yeniden ölçüm değildir.
