# 17 Ekim 2026 — kullanıcının eklediği arşivin incelemesi

`data/incoming/inFamous 2 (Turkey).7z` bulundu. Kaynak arşiv değiştirilmedi.
7-Zip 26.04 listelemesine göre iki dosya içeriyor:

- `inFamous 2 (Turkey).iso`: 15.327.297.536 bayt, arşiv başlığındaki CRC32 `245D231E`;
- `readme.txt`: 11 bayt. Okunmadı veya çalıştırılmadı.

Diskte yeterli boş alan vardı. ISO ayrı `data/inspection/turkey-disc/`
konumuna en fazla 2 iş ile çıkarılmaya başlandı. ISO'nun baş tarafındaki UDF
dizinleri okunabildiği için yalnız `PS3_GAME/PARAM.SFO` ve `PS3_DISC.SFB`
alındı. `tools/check_inputs.py::parse_sfo()` ile tam 1040 baytlık SFO okundu:

| Alan | Sağlanan kopya | Mevcut port hedefi |
| --- | --- | --- |
| TITLE_ID | **BCES01229** | **NPUA80638** |
| APP_VER | **01.00** | Belgeler çelişkili: 01.00 / 01.03 |
| CATEGORY | DG | Dijital NPUA hedefi |
| VERSION | 01.01 | APP_VER ile aynı alan değildir |
| PS3_SYSTEM_VER | 03.6000 | Firmware uyumu ayrıca incelenecek |

**Referans TITLE_ID ile eşleşmiyor.** İlk incelemedeki katı APP_VER 01.03
beklentisi, ROADMAP'teki 01.00 notu görülünce düzeltildi;
[sürüm belirsizliği ve BCES değerlendirmesi](bces-feasibility-tr.md).
Bu arşiv doğrudan NPUA80638 hedefinin VFS'sine
konmadı. Yeniden adlandırma veya ISO/PKG dönüşümü oyun executable'ının sürümünü
ve adreslerini eşitlemez. BCES desteği için ayrı EBOOT analizi, statik PPU/SPU
üretimi, sabit adresler ve oyuna özel düzeltmelerin karşılaştırılması gerekir.
Bu inceleme iki executable'ın byte/adres karşılaştırmasını yapmadı; BCES'in
portlanamayacağı sonucu çıkarılmıyor.

SFO sonucu alınınca kendi açma işlemimiz Ctrl-C ile durduruldu. Yalnız bizim
oluşturduğumuz **1.258.291.200 baytlık eksik ISO** kaldırıldı; orijinal 7z ve
küçük metadata dosyaları korundu. Kaynak arşivin veya ISO'nun tamamının CRC/
bütünlüğü doğrulanmadı. Eksik ISO üzerinde 7zz'nin verdiği exit 2 / unexpected
EOF bu sınırlamadan kaynaklanır; kaynak arşiv bozuk diye yorumlanmadı.

`data/incoming/PS3UPDAT.PUP`, çözülmüş firmware PRX seti ve kabul edilen
NPUA80638 referans oyun kurulumu hâlâ yok. Bu incelemede oyun başlatılmadı ve
derleme değiştirilmedi; önceki AOT/Metal tanısı sonuçları ayrı kalır.

## Kanıt ve komutlar

```sh
cd /Volumes/monssd/Infamous2-iOS
7zz l -slt 'data/incoming/inFamous 2 (Turkey).7z'
# ISO tam çıkarılırsa seçili metadata okumak için:
7zz x -mmt=2 -aos -odata/inspection/turkey-disc/metadata \
  'data/inspection/turkey-disc/inFamous 2 (Turkey).iso' \
  'PS3_GAME/PARAM.SFO' 'PS3_DISC.SFB'
python3 - <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, 'tools')
from check_inputs import parse_sfo
p = Path('data/inspection/turkey-disc/metadata/PS3_GAME/PARAM.SFO')
d = parse_sfo(p.read_bytes())
print(json.dumps({k: d[k] for k in ('TITLE_ID', 'APP_VER', 'VERSION')}, indent=2))
PY
```

Git dışında `out/turkey-input-inspection.json` dosyası kaynak boyutunu,
seçili metadata SHA-256 değerlerini ve inceleme sınırlarını kaydeder.
`turkey-archive-list.txt`, `turkey-archive-extract.log`, `turkey-iso-list.txt`,
`turkey-iso-list-errors.txt`, `turkey-metadata-extract.log` ham kayıtlardır.
Bu kayıtlar oyun veya firmware dosyalarının Git'e eklenmesini gerektirmez.
