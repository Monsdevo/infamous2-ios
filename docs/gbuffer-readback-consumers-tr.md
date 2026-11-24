# G-buffer geri okuması ve tüketicileri

7 Kasım 2026. Build 63'ün üç iPhone izini ve Build 64'ün kompakt vertex
kapalı izini yeniden inceledim. Uygulama kaynakları ve cihaz değişmedi.
Adresler RSX I/O offsetleridir. SPU DMA ile karşılaştırırken
`bces_gcm_io_ea` ile guest efektif adrese çevrilmelidir.

| Yüzey | İlk/ikinci blit offseti | Bilinen guest tüketicisi |
| --- | --- | --- |
| Normaller (renk biçimli G-buffer) | `0x06FF3B80` / `0x06FF4B80` | Özgün aydınlatma; özgün SSAO AO pass 1 |
| Tam çözünürlüklü derinlik | `0x07377B80` / `0x07378B80` | Özgün aydınlatma; Metal SSAO açıkken bile özgün SSAO pass 0; tam SSAO fallback'te ayrıca pass 4 |

`nv3089_blit` önce `rsx_draw_engine_write_back_to` ile Metal yüzeyini
guest kaynak belleğine yazar, ardından CPU tarafındaki blit guest hedefini
doldurur. `eng_gpu_light_blit` aynı komut sırasında Metal normali ve
derinliği için GPU snapshot kayıtları ekler. Bu snapshot'ların GPU
tüketicileri ve sıraları korunmalıdır. Sadece readback'in dönüş değerini
değiştirmek CPU blit'ini durdurmaz ve güncel olmayan kaynak belleği
kopyalayabilir.

`ssao_skip_step` pass 0'da `0x5258` özgün SPU girişini çağırır.
`bces_ssao_allow_job` bu pass'in 1280×720 guest derinliğini okuyup
640×360 guest derinliği yazdığını pass tanımından doğrular.
`bces_ssao_depth_claim_guard` yalnız sonraki pass'lerin bu özgün
çağrı içinde alınmasını önler. Dolayısıyla Metal SSAO fallback sayacı
sıfır olsa bile derinliğin gerçek bir guest tüketicisi kalır.

Build 64'ün A/B/A performans pencerelerinde her pencerenin başı ve sonu
arasında sırasıyla 165/166/165 kare, 165/166/165 Metal ışık pass'i ve
2.185/2.208/2.133 aydınlatma fallback giriş sayacı artışı var.
Özgün derinlik çağrı sayacı 347.947/254.275/261.683, SSAO tam fallback
sayacı ise 0 arttı. Bir guard reddi tek başına DMA'nın yüzeyi okuduğunu
göstermez. Önceki Mac normal-atlama deneyi gerçek bir fallback kapısı
tarafından reddedildi. iPhone'da reddin nedeni ve bu retlerden hangisinin
ilk yüzey DMA'sına dönüştüğü mevcut sayaçlarla ayrıştırılamıyor.

## Seri RSX thread'indeki bütçe

Her izde dört tam kare. Her tam karede taban offsetli bir normal ve bir
derinlik writeback kapsamı, bunların içinde birer readback var. İkinci
offsetteki blit ayrı bir tam yüzey readback'i üretmiyor. CSV'de kind 450,
a=9 ve b=taban offseti olan kapsamları `stages.json` tam kareleriyle
eşledim. Her kapsam içindeki kind 12 bekleme ve kind 13 readback
aralıklarının birleşimini aldım. İç içe beklemeler iki kere sayılmadı.

| İz | Normal readback, ms | Normal bekleme, ms | Derinlik readback, ms | Derinlik bekleme, ms |
| --- | ---: | ---: | ---: | ---: |
| Build 63 A | 1,86 | 2,04 | 1,65 | 14,73 |
| Build 63 B2 | 1,72 | 1,41 | 1,74 | 15,01 |
| Build 63 C2 | 1,69 | 1,32 | 1,76 | 17,21 |
| Build 64 kapalı | 1,71 | 1,23 | 1,61 | 13,97 |

Her hücre dört kare medyanıdır. Bunlar aynı thread üzerinde gözlenen
aşamalar. Beklemenin önemli bölümü gerçek GPU işiyle örtüşür ve bu
süre doğrudan FPS kazancı olarak çıkarılamaz.

## Karar

İki yüzeyi topluca atlama güvenli değil. Normal tarafı tek başına
düşük bütçeli ve özgün ışık yolu etkin olarak reddediliyor. Derinlik
tarafı daha büyük fırsat, ancak özgün pass 0 ve guest yarım derinlik
çıktısı korunmalı. Bir sonraki tanı, kaynak ve hedef EA aralıklarını
kare nesliyle eşleyip seçici MFC GET/GETL ve ilgili CPU/RSX erişimlerini
kaydetmeli. İlk erişime kadar süre, iş kimliği ve ışık guard ret nedeni
ayrı tutulmalı. İlk işin derinlik pass 0 olduğu doğrulanırsa, onun GPU
çıktısını orijinal guest yarım derinlik sözleşmesiyle doğrulamak veya
aynı senkron noktayı öne çekmeden gereken guest girdisini hazırlamak
değerlendirilebilir. Gerçek uçtan uca kazanç henüz ölçülmedi.
