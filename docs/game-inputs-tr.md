# Oyun dosyalarını hazırlama

**Güncel seçim:** kullanıcı BCES01229 / 01.00 ile devamı onayladı.
Kaynak 7z mevcut; EBOOT çözüldü ve BCES üretimi başladı. Resmî firmware PUP
de indirildi. Şu anda yeni bir NPUA indirmesi beklenmiyor.
[9. adımın güncel yolları ve komutları](step9-bces-tr.md).
`check_inputs.py` varsayılan profili artık BCES'tir; tam dosya ağacı için
`data/game/BCES01229/` ayrıldı. Aşağıdaki NPUA hazırlığı önceki referans notudur;
ona ait denetimde `--profile profiles/NPUA80638-reference.json` belirtilmeli.

## NPUA referans hazırlığı (önceki not)

GitHub kaynakları oyun verilerini içermez. Gerçek boot için kendi oyun
kopyandan elde edilen veri gerekiyor. Mevcut portun adresleri **NPUA80638
(ABD dijital sürüm)** için hazırlanmış. APP_VER hakkında belgeler çelişiyor:
eski `infamous2/README.md` 01.03, `ROADMAP.md` installer planı 01.00 diyor.
Bu yüzden yalnız SFO sürümünden binary uyumluluğu çıkarılmayacak;
[güncel değerlendirme](bces-feasibility-tr.md). Eski hedefin runtime'ı
yeni iOS hedefine alınmıyor.

İlk yapacağın iş: kendi oyununun yedeğini aşağıdaki yerlerden uygun olana koy.
Çözülmüş ELF veya firmware PRX'lerini elle hazırlaman ilk aşamada gerekmiyor;
girdiler geldikten sonra dosya türünü ve sürümü kontrol edip dönüşümü yapacağız.

17 Ekim'de eklenen Turkey 7z arşivinin SFO'su **BCES01229 / 01.00** çıktı;
referans NPUA kimliğiyle eşleşmiyor. Kaynak arşiv korundu;
[inceleme ve sınırlar](input-inspection-tr.md).

## Yerleştirme

Kök: `/Volumes/monssd/Infamous2-iOS/data/`. Klasörler hazır, tamamı Git dışında.

| Elindeki dosya | Koyacağın yer |
| --- | --- |
| Kendi PSN kopyanın `.pkg` paketi / güncelleme paketi | `data/incoming/` — paketi yeniden adlandırma veya elle açma |
| Çıkarılmış NPUA80638 oyun klasörü | `data/game/NPUA80638/` — `PARAM.SFO` ve `USRDIR` bu klasörün doğrudan altında olsun |
| Resmî PS3 firmware `PS3UPDAT.PUP` | `data/incoming/PS3UPDAT.PUP` |
| Zaten çıkarılmış firmware ağacı varsa | `data/firmware/dev_flash/` |

Oyunu kendi PSN/PS3 kopyandan elde et. Başka bölge, disk sürümü veya farklı
güncelleme varsa önce bunu bildir; klasör adını değiştirerek uyumlu hale gelmez.
Dosyaların bulunduğu mevcut bir klasörü de kullanabiliriz; ikinci büyük bir
kopya oluşturman şart değil. Mevcut konumunu vermen yeterli.

Firmware, Sony'nin [resmî PS3 sistem yazılımı sayfasındaki](https://www.playstation.com/tr-tr/support/hardware/ps3/system-software/)
“PS3 Güncellemesini İndirin” bağlantısından alınabilir. 17 Ekim 2026'da sayfa
4.93 gösteriyor. İndirilen PUP yalnızca kaynak girdisidir: bu sürümün portun
sabit libsre/SPU adresleriyle uyumu henüz doğrulanmadı. Sürüm ve hash
kaydedilip modül yapısı incelenmeden sabit firmware offsetleri uygulanmayacak.
Firmware indirmek veya açmak, Mac/PS3 sistemini güncelleme işlemi değildir.

## İncelemeden sonra beklenen düzen

```text
data/
  incoming/                  # kaynak paketler / PUP
  game/NPUA80638/
    PARAM.SFO                # TITLE_ID ve APP_VER okunacak
    USRDIR/
      EBOOT.BIN              # varsa orijinal korunur
      EBOOT.elf              # daha sonra yerelde çözülmüş ELF
      ...                    # oyunun TAM arşivleri ve alt klasörleri
  firmware/
    dev_flash/               # tam firmware dosya ağacı, varsa
    prx/
      liblv2.prx             # çözülmüş ELF64 modüller
      libsysmodule.prx
      libsre.prx
```

Sadece EBOOT yeterli değil; USRDIR içindeki arşiv ve alt klasörler de gerekiyor.
`EBOOT.BIN` → `EBOOT.elf` veya `.sprx` → `.prx` **isim değişikliği değildir**.
Gerçek çözme işlemi ve ELF içerik doğrulaması yapılır. Upstream'in kendi
lisansıyla RPCS3 `--decrypt` yolu bir seçenek; cihazda RPCS3 çalışmayacak.
Orijinal girdiler korunarak ayrı türetilmiş çıktılar hazırlanacak.

Dosyaları yerleştirince ne koyduğunu ve konumunu söylemen yeterli. İlk inceleme:

```sh
cd /Volumes/monssd/Infamous2-iOS
python3 tools/check_inputs.py > out/game-input-inventory.json
# ELF/PRX henüz çıkarılmadıysa eksik raporu ve çıkış kodu 1 beklenir.
```

Varsayılan konum artık bu `data/` düzenidir. Başka yerdeki kendi kurulumun için:

```sh
python3 tools/check_inputs.py --game-dir '/mevcut/oyun/NPUA80638' \
  --eboot '/mevcut/cozulmus/EBOOT.elf' --firmware-dir '/mevcut/cozulmus/prx'
```

Araç salt okunur: SFO hedef sürümü, ELF64 / big-endian / PPC64, yükleme
segmentleri, gereken adres kapsamı, SHA-256 ve PSARC varlığını denetler.
Upstream kanonik EBOOT hash'i vermediği için bu kontroller tek başına tam
uyumluluk kanıtı değildir; arşivlerin varlığı bütünlüklerinin doğrulanması değildir.

## Telefonla ilişkisi

Önce girdiler Mac'te incelenip PPU/SPU kodu statik olarak C/C++'a çevrilecek.
Xcode bu kodu iPhone için ARM64 makine koduna derleyecek. Oyun verileri de
uygulamanın cihazdaki dosya alanına aktarılacak; büyük verileri aktarma yöntemi
ve iOS dosya yerleşimi henüz uygulanmadı. Son hedef **oyunun yalnızca iPhone'da,
Mac bağlantısı olmadan çalışması**. Mac geliştirme/kurulum bilgisayarıdır.
