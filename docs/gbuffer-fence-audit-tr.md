# G-buffer beklemesini birlikte ele alma

7 Kasım 2026. Build 63 ve 64'ün kayıpları sıfır olan dört iPhone 15 Pro
izindeki 16 tam kareyi yeniden analiz ettim. Yeni iPhone çalıştırması,
renderer davranışı değişikliği veya FPS A/B yapılmadı.

`nv3089_blit` önce derinliği, yaklaşık hemen ardından normalleri
guest belleğe taşır. `rsx_draw_engine_write_back_to` iki yüzey için
de `submit_and_wait` çağırır. Metal backend iki ara gönderimde de
aynı `s_queue` kuyruğunu kullanır. Analizde writeback kapsamı içindeki
encode, commit kimliği, gerçek GPU başlangıç/bitişi ve CPU beklemesi
eşlendi. İki yüzeyin de her tam karede tek bir ara gönderimi var.

| İz | Derinlikte encode edilen kayıt | Normalde kayıt | Derinlik beklemesi, ms | Derinlik beklemesinin sonundan normal commit'e, ms | Modelde normal commit anında kalan önceki GPU işi, ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| 63 A | 1.556 | 1 | 14,73 | 2,96 | 11,07 |
| 63 B2 | 1.556 | 1 | 15,01 | 3,49 | 10,82 |
| 63 C2 | 1.556 | 1 | 17,21 | 3,16 | 10,83 |
| 64 kapalı | 1.556 | 1 | 13,97 | 2,69 | 11,00 |

Her hücre dört kare medyanı. İlk gönderim G-buffer birikiminin büyük
kısmını yürütüyor. İkinci gönderim tek normal snapshot kaydını kodluyor.
Model, derinlik GPU gönderimini mevcut zamanda bırakıyor ve iki fence
arasındaki gözlenen CPU aralığının tamamını ilk beklemeden önceye çekiyor.
Buna prototipte kalkabilecek kopya işleri de dahil. Yaklaşık 11 ms,
aynı GPU zamanlaması varsayımıyla sonraki fence'e taşınabilecek önceki
GPU işidir. Ölçülmüş bir prototip sonucu ya da mutlak bir donanım sınırı
değildir. İlk gönderim de kaldırılır ve işi normal gönderime katılırsa,
önceki GPU işi yine aynı sırada çalışmak zorunda kalır.

## Uygulama kararı

Derinliği tek başına atlayan varyant uygulanmadı. İkinci senkron
normal gönderimi kalırken 14–17 ms'yi kaldırdığı varsayılamaz. İki
fence'i normal Metal yolunda kaldıracak tasarım için:

1. İlk blit'te iki yüzey için guest materyalizasyonunu ertelerken
   render komutları ve gerekli GPU snapshot'ları sıra içinde kalmalı.
   Frame/texture sahipliği next-frame yeniden kullanımı öncesinde
   güvenceye alınmalı.
2. Metal SSAO kararı onaylandığında pass 0 tile hesabı yerine aynı
   iterator ve label 136/137 sırası korunmalı. Normal ve derinlik
   girişleri için gerçek SPU fallback ayrı ayrı korunmalı.
3. SSAO/ışık uygunluk kontrolü geç geldiğinden, fallback bir kez
   tetiklendiğinde özgün girdiyi DMA'dan önce üretmeli. Bu yol,
   SPU label'ı bekleyip bloke olan FIFO'nun işi sonradan göndermesine
   bağlı olamaz. Belirsiz erişim veya sürümde özgün yol seçilmeli.
4. Ölçülecek A/B, aynı sahnede iki ara fence'i birlikte, fallback
   ve görüntü doğruluğu geçtikten sonra karşılaştırmalı.

```sh
python3 tools/analyze_gbuffer_fences.py \
  out/ios-compact64/trace-off/frame-trace.csv \
  out/ios-compact64/trace-off/stages.json \
  --output out/gbuffer-fence-audit/ios-compact64-trace-off.json
```
