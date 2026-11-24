# Gerçek upstream DMA değişiklikleri — kaynak karşılaştırması

1 Kasım 2026. Bu tur kaynak incelemesi ve kanıt kaydıdır; runtime yaması,
derleme, iPhone kurulumu veya FPS ölçümü yapılmadı.

## Önceki açıklamanın düzeltilmesi

MFC son eşleşme ipucunun yalnız bize ait bir fikir olduğu yönündeki önceki
açıklama yanlıştı. macOS yamasında `mfc_hint`, Linux yamasında `mfc_slot`
doğrudan bulunuyor. 30 Ekim arşivindeki macOS ROADMAP notu da üç DMA parçasını
açıkça sayıyordu; önceki cevapta bu kanıt gözden kaçırılmıştı.

## Kaynak kimliği ve doğrulama

- Bizim checkout: `b76ecda525b2b02bb1ca59aca63024fdebb78d06`;
  runtime tabanı `770660a3971b87a453677e46125e5e01ac7891c0` + kilitli yama
  ve mevcut yerel hazırlayıcılar. Etkin uygulama kaynakları `ios-prepared`.
- [macOS sabit commit yaması](https://github.com/erikomis/infamous2-recomp/blob/a69a0525b91e4b22f4ed0e3d6452c95159060643/infamous2-lle/patches/ps3recomp-fork-770660a-with-upstream-prs.patch).
  ROADMAP, setup scripti ve yama yeniden indirildi; üçü de 30 Ekim arşiviyle
  byte olarak aynı. `setup_toolkit.sh` yine `770660a` tabanına birleşik yama
  uyguluyor. Genel runtime HEAD'ine geçiş gerekçesi yok.
- [Linux sabit commit yaması](https://github.com/ThiagoFraga761/infamous2-pc/blob/1ab02e702c37247ad4f53ac0b361d92e8b3269bc/work/patches/ps3recomp.patch).
  Setup scripti, yama ve NOTES indirildi. Linux tabanı farklı:
  `42f5f8f9415117f324ca438c46573f2caca63468`. Birleşik yaması bizde doğrudan
  uygulanacak bir drop-in paket değildir.

macOS'un üç ilgili dosyası temiz pinned tabandan **yalnız inceleme klasöründe**
yeniden oluşturuldu; seçilmiş unified patch `git apply --check` ile doğrulandı.
Çıktıdaki `mfc_hint`, imza ve sayfa filtrelerinin gerçekten bulunduğu ayrıca
kontrol edildi. Etkin runtime'a uygulanmadı.

Kanıt klasörü `out/dma-upstream-audit/`: `provenance.json`,
`linux-provenance.json`, `mac-dma-only.patch`, `mac-reconstructed/`,
`audit.json`. Son dosyada 11 kaynak-kapsam kontrolü ve etkin dosyaların SHA256
değerleri var. Bunlar işlevsel test veya FPS ölçümü değildir.

## Tam olarak neler farklı?

| Parça | Diğer porttaki gerçek uygulama | Etkin iOS durumu |
|---|---|---|
| Poison tanısı | macOS `mfc_do_transfer`, lean açıkken bütün tanı bloğunu koşullandırıyor; tanı ortam değişkeniyle geri geliyor. | Build 51 yalnız payload tarama döngüsünü koşullandırdı; bölge kontrolü/log bloğu korundu ve ek örneklemeli sayaçlar eklendi. Build 52 kontrol/sayaç erişimlerini derlemeden çıkarıp özgün taramayı açık tutuyor. Tam upstream eşdeğeri değil. |
| MFC yuvasını bulma | macOS `mfc_for`: context'teki indeks+1 ipucu, her kullanımda acquire owner kontrolü. Linux: context'te yuva pointer'ı, inline hit ve ayrı slow arama. | `diagnostic_spu_channels.c::mfc_for` her seferinde 128 yuvaya kadar arıyor; ipucu yok. **Denenmedi.** |
| Overlay adaylarını erken eleme | macOS `ovl_cannot_match`: imzaların ilk kelimeleri için 4096-bit özet ve sabit kod bölgeleri için 1 KiB LS sayfa haritası. | Yalnız EA hash özeti ve tek birleşik LS aralığı var. Boyut ≥512 ise imza bulunabilir diye taramaya giriyor. Yeni imza/sayfa filtreleri **denenmedi**. |
| MFC yuva hizalaması | Linux `spu_mfc_slot` 128-byte aligned. | Mevcut typedef'ta bu açık hizalama yok. MFC ipucundan ayrı aday; ikisini aynı ölçümde açmak katkıyı belirsizleştirir. |
| Sık kullanılan MFC kanallarını inline işleme | Linux `spu_wrch_fast`/`spu_rdch_fast`, `spu_mfc_cmd`/`spu_mfc_tag_update`; tanı açıkken slow yol. | Basit runtime-only değişiklik sayılmaz; üretilen SPU kodu/helpers ve arşivlerin kapsamı birlikte denetlenmeli. MFC ipucuyla aynı şey değildir. |
| Fence azaltmaları | Linux notları x86 bellek sıralamasına dayanan kaldırmaları anlatıyor. | ARM64 için aynı gerekçe geçerli sayılmaz. Bu incelemede fence/atomic/coherency değişikliği önerilmedi. |

macOS'un `PS3_SPU_DMA_LEAN` başlığı ilk üç parçayı birlikte içeriyor. Dolayısıyla
tek poison denemesinin kazanç vermemesi **DMA_LEAN paketinin bizde başarısız
olduğu sonucu değildir**. Upstream'in paket için raporladığı yüzdeler de
MFC ipucunun tek başına kazancı veya iPhone FPS tahmini sayılamaz.

Overlay kaydı güncellenince özetin geçersizleştirilmesi de yamada var:
`spu_overlay_register_region` ve `_region_at` → `ovl_summary_invalidate`.
Bizde yalnız kaynak sayısına dayanan eski yeniden oluşturma var. Yeni filtre
taşınacaksa sonradan yazılan span/LSA bilgisiyle özetin tutarlılığı birlikte
ele alınmalı; yalnız negatif test kopyalanmamalı. Resident-code eviction
kontrolleri erken dönüşten **önce** kalmalı; gerçek eşleşme sırası korunmalı.

## Sıradaki uygulama için karar

İlk aday **yalnız MFC yuva ipucu**. Poison taraması build 52 referansındaki
gibi özgün kalacak; overlay ve hizalama aynı deneye katılmayacak. Yalnız
arama maliyeti hedeflenir, gerçek aktarım/tag/queue/coherency işi kaldırılmaz.
Kazanç miktarı henüz bilinmiyor.

Upstream context yapısına alan ekliyor. Bizde önceden derlenmiş SPU/runtime
arşivleri de `spu_context` düzenini kullanıyor. Alanı header'a ekleyip yalnız
kanal dosyasını derlemek, boyut/offset uyumsuzluğu yaratabilir. Uygulama
öncesinde iki seçenekten biri açıkça seçilmeli: tüm ilgili tüketicileri aynı
layout ile yeniden derlemek veya context yapısını değiştirmeyen, owner'ı
her kullanımda kontrol edilen harici/thread-local ipucu uyarlaması. İkinci
seçenek upstream ile aynı saklama biçimi diye sunulamaz; hit oranı farklı olabilir.

Doğruluk koşulları: ipucu yokluğu, ilk/son yuva, çoklu context geçişi, bırakılmış
yuvanın başka owner tarafından alınması, eski ipucuyla geri dönüş, context'in
yeniden başlatılması ve eşzamanlı ilk claim. Hit owner'ı atomik acquire ile
doğrular; miss özgün arama/claim yoluna döner. Release ve engine reset korunur.
Performans kaydı sırasında her çağrıda paylaşılan sayaç eklenmemeli; doğruluk
kapsamı ayrı tanı koşusunda sınanmalı.

MFC ardından overlay imza/sayfa negatif testi ayrı deney olabilir. Önce
özgün aramayla rastgele ve sınır girdilerde false-negative olmadığı, metadata
değişimi ve eviction sırasının korunduğu sınanmalı. Her aşama kendi iPhone
karşılaştırmasıyla değerlendirilir. Bu not iki aday için kazanç iddia etmez.
