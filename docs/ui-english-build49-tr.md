# İngilizce göstergeler ve ayarlar — build49

30 Ekim2026. `src/ios/GamePerformance.mm` içindeki60arayüz metni İngilizceye çevrildi: gösterge başlıkları, durumlar, ayarlar/açıklamalar ve erişilebilirlik etiketi. Preference/CSV anahtarları ve optimizasyon davranışı korunur. Build49, aynı bundleID üzerine ağ üzerinden kuruldu; uygulama açılmadı ve ölçüm başlatılmadı.

Xcode27.2/iPhoneOS27.2 ile tek işte derlendi, imzalandı. İlk sandbox derlemesi izin nedeniyle başarısızdı; SSD DerivedData ile imzalı derleme başarılı. Sandbox dışı codesign verify başarılı. İlk ağ kurulumu connection reset ile başarısızdı; tekrarında başarı. Xcode devicectl sarmalayıcısı CoreDevice bileşen sürümünü yenilemeye takıldığından kurulu CoreDevice651.13.5 binary kullanıldı.

Kanıtlar: `out/ui-english-signed-build.log`, `out/ui-english-install-retry.json`, `out/ui-english-verification.json`. Sonraki optimizasyon adımı DMA PUT poison tanı taramasının ayrı kapatılabilir Mac deneyi olarak ölçülmesi.
