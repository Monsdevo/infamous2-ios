# Tanıtım README güncellemesi — 5 Kasım 2026

Kullanıcının isteğiyle yalnız `Monsdevo/infamous2-ios` tanıtım reposunun
README.md dosyası güncellendi ve main dalına gönderildi.
Commit: `270ba54d51378ed2aa250c6ddab55540a2b6e1b8`.

Ayrı checkout: `out/showcase-update-20261105/`. Ana oyun projesinin root
README.md dosyası geliştirme notudur; bu yayın için değiştirilmedi.
Desktop'taki `infamous2-ios` klasörünün remote'u farklıdır:
`Monsdevo/monsdevo.github.io`; bu görevde oraya yazılmadı.

Mevcut fotoğraflar korundu. Build56 durumu, başarılı Metal lighting/SSAO,
uzak ışık ve birleşik profil sonuçları, kazanç doğrulanmayan geometri,
renderer/cache ve DMA denemeleri eklendi. Mac/iPhone sonuçları ayrıldı.
Performans: soğutulmuş ilk liman6,99FPS/143,0ms; son sıcak bataklık
referansı8,96FPS/111,6ms. Bu iki sahne farkı optimizasyon artışı sayılmadı.
Oyun geneli FPS ortalaması veya sürdürülebilir30FPS iddiası yok.

GitHub main SHA ve yayımlanan raw README byte eşitliği doğrulandı:
`out/showcase-update-20261105-verification.json`. Değişen tek dosya README.md;
özel kaynaklar, oyun/firmware veya büyük üretilmiş çıktılar gönderilmedi.
Sonraki teknik adım büyük SPU alt çağrı zincirinin tamamını sürelemek.
