# Antakya gerçek veri: basit değişiklik tespiti (30 Ekim 2026)

## Ne ölçüldü

Direk tespitindeki yöntemin (bina alanı içinde öncesi/sonrası karşılaştırma) gerçek görüntüde
ne kadar işe yaradığı. Kamera açısı değil, uydu açısı; amaç mantığı gerçek veride sınamak.

- Görüntü: Maxar Open Data (CC BY-NC 4.0), Antakya merkez iki ARD parçası (031133023302 batı,
  031133023303 doğu). Öncesi 22.12.2022 (0,5 m), sonrası 11.02.2023 (0,67 m), bulutsuz.
- Cevap anahtarı: Copernicus EMSR648 AOI11 GRA MONIT01, bina blokları (OSM 06.02.2023 tabanlı),
  uydu görüntüsünden insan yorumuyla derecelendirilmiş.
- Pozitif = Destroyed + Damaged, negatif = No visible damage; "Possibly damaged" ayrı raporlandı.
- Eşik batı parçasında (F1 en yüksek) seçildi, doğu parçasında test edildi.
- Blok başına özellikler: parlaklık/kontrastı eşitlenmiş gri fark, öncesi-sonrası korelasyonu,
  kenar yoğunluğu oranı.

```
~/afet-yolo/venv/bin/python -m scripts.hatay_olc
```

| Parça | Destroyed | Damaged | Possibly | No visible damage |
|---|---|---|---|---|
| Batı (eşik) | 19 | 92 | 34 | 1.165 |
| Doğu (test) | 18 | 63 | 28 | 796 |

| Özellik | AUC batı | AUC doğu (test) | Test duyarlılık | Test kesinlik | Test yanlış alarm |
|---|---|---|---|---|---|
| Fark | 0,755 | 0,669 | 13/81 (%16,0) | 13/74 (%17,6) | 61/796 (%7,7) |
| Korelasyon | 0,730 | 0,659 | 21/81 (%25,9) | 21/119 (%17,6) | 98/796 (%12,3) |
| Kenar oranı | 0,433 | 0,591 | 15/81 (%18,5) | 15/135 (%11,1) | 120/796 (%15,1) |

Yıkık (Destroyed) bloklarda korelasyon 10/18'ini işaretledi. Süre 28 sn (3.525 blok).

## Sonuç

Basit değişiklik tespiti gerçek uydu görüntüsünde zayıf (AUC 0,59–0,67). Benzetimdeki %91,4
bulma oranı gerçek veriye taşınmıyor. Görüntülere bakınca nedenler:

1. Etiket birimi bina bloğu: bir bloktaki birkaç binadan biri yıkılınca değişim ortalamada kaybolur.
2. Öncesi aralık, sonrası şubat; güneş açısı ve bakış açısı farklı: gölge ve bina eğikliği
   hasarsız blokları da "değişmiş" gösterir.
3. Etiket de yanılabilir: bazı "No visible damage" bloklarda enkaz görülüyor.

Direk kamerasında 2. madde daha hafiftir (sabit kamera, referans her gün güncellenebilir),
ama gölge ve ışık yine sorun olur. Bu sonuç, 2. aşamada eğitimli sınıflandırıcıya geçmenin gerekçesidir.

## 2. aşama: eğitimli sınıflandırıcı (egitim/hasar_siniflandirici.py)

```
CUDA_VISIBLE_DEVICES="" ~/afet-yolo/venv/bin/python -m egitim.hasar_siniflandirici --tohum 0   # 1, 2
```

- Girdi: blok başına 64×64 kesit, 7 kanal (öncesi RGB, sonrası RGB, blok maskesi).
- Model: ImageNet ön eğitimli ResNet18, ilk katman 7 kanala uyarlandı; 30 tur, çevirme/döndürme.
- Veri: 8 Maxar parçası (031133023322 bulutlu, alınmadı). Test parçası 031133023303
  eğitime hiç girmedi. Eğitim 2.235 blok (173 pozitif), doğrulama 394 (21 pozitif),
  test 890 (81 pozitif). Model ve eşik doğrulama kümesinde seçildi.
- Laptop işlemcisinde (GPU belleği LLM'de), 3 eğitim paralel: tohum başına ~1.600 sn.

| Tohum | Test AUC | Duyarlılık (doğrulama eşiği) | Kesinlik | Yanlış alarm |
|---|---|---|---|---|
| 0 | 0,792 | 23/81 (%28,4) | 23/49 (%46,9) | 26/809 (%3,2) |
| 1 | 0,818 | 10/81 (%12,3) | 10/24 (%41,7) | 14/809 (%1,7) |
| 2 | 0,807 | 16/81 (%19,8) | 16/28 (%57,1) | 12/809 (%1,5) |

Test eğrisinden okunan işletme noktaları (yalnızca eğrinin şeklini gösterir; bu eşikler test verisinde belirlendiği için başarı iddiası olarak kullanılmaz):

| Yanlış alarm | Tohum 0 | Tohum 1 | Tohum 2 |
|---|---|---|---|
| %5 | 25/81 | 24/81 | 28/81 |
| %10 | 34/81 | 36/81 | 39/81 |
| %20 | 44/81 | 48/81 | 46/81 |

Sonuç: Eğitimli sınıflandırıcı basit değişiklik tespitinden belirgin iyi (test AUC 0,79–0,82,
basit yöntemde 0,59–0,67). Yine de yanlış alarm %10'dayken hasarlı blokların ancak %42–48'ini
buluyor. Doğrulama kümesinde 21 pozitif olduğu için seçilen eşik tohuma göre çok oynuyor
(duyarlılık %12–28). Daha çok etiketli veri (diğer şehirler, tek bina etiketleri) gerekir.

## 3. Diğer bölgeler eklendi (AI sunucusunda eğitim)

```
~/afet-yolo/venv/bin/python -m egitim.hasar_veri          # kesit çıkarma (laptop, Maxar bulut okuması, 14,5 dk)
python -m egitim.hasar_siniflandirici --veri data/gercek/emsr/kesitler.npz --tohum 0       # 1, 2
python -m egitim.hasar_siniflandirici --veri data/gercek/emsr/kesitler.npz --test-bolge AOI04   # bölge dışarıda
```

Veri: Copernicus EMSR648 bölgelerinden Maxar öncesi/sonrası parçası bulunan 6'sı + Antakya:
AOI01 Gaziantep, AOI02 Adıyaman, AOI04 Kahramanmaraş, AOI05 Malatya, AOI06 Osmaniye,
AOI10 İslahiye, AOI11 Antakya; 35 parça çifti, 26.207 kesit (1.470 pozitif, 24.123 negatif,
614 belirsiz). Nokta etiketli bölgelerde (builtUpP) nokta çevresinde 16 m kare. Sunucu (RX 9070 XT),
tur başına ~5 sn, model başına 150–181 sn.

**a) Aynı Antakya test parçası (031133023303), diğer bölgeler eğitime eklendi:**

| Tohum | Doğrulama AUC | Test AUC | Yanlış alarm %10 iken |
|---|---|---|---|
| 0 | 0,909 | 0,713 | 28/81 |
| 1 | 0,894 | 0,771 | 41/81 |
| 2 | 0,918 | 0,780 | 33/81 |

Yalnız Antakya ile eğitilen modelden (0,79–0,82) daha kötü.

**b) Bir bölge tamamen dışarıda (eğitime hiç girmedi), tohum 0:**

| Test bölgesi | Test blok (pozitif) | Doğrulama AUC | Test AUC | Yanlış alarm %10 iken |
|---|---|---|---|---|
| AOI04 Kahramanmaraş | 1.668 (389) | 0,928 | 0,570 | 39/389 |
| AOI11 Antakya | 3.519 (275) | 0,928 | 0,625 | 69/275 |
| AOI05 Malatya | 2.402 (267) | 0,917 | 0,692 | 90/267 |
| AOI06 Osmaniye | 2.167 (160) | 0,922 | 0,537 | 21/160 |

**Sonuç:** Model görmediği bölgeye genellenmiyor (test AUC 0,54–0,69, rastgele 0,50).
Doğrulama AUC'si (0,92) yanıltıcı: doğrulama blokları eğitimle aynı parçalardan rastgele
seçildiği için komşu bloklar benziyor. Doğru değerlendirme bölge/parça dışarıda bırakmaktır.
Neden olarak görülenler: bölgeler arası çekim tarihi, güneş ve bakış açısı farkı; Copernicus
etiketlerinin bölgeye göre farklı yorumlanması (blok/nokta, farklı analistler). Raporda
"görmediği şehirde çalıştığı ölçülmedi, ölçülünce zayıf çıktı" diye yazılmalı. Direk
kamerası için anlamı: model her kurulum yerinde kendi görüntüsüyle (yerel referans)
çalışmalı; genel bir model tek başına yeterli değil.
Modeller sunucuda: `~/afet-yolo/hasar/hasar_resnet18_t*_tum.pt`.

## 4. xBD ve başka deprem verisi eklendi (64 piksel, 7 kanal model, tohum 0)

- xBD: Hugging Face `isp-uv-es/xview2-taco` (CC BY-NC-SA 4.0, 35,15 GB, sunucuda). 19 afet, çoğu
  kasırga/yangın/sel; deprem yalnız Meksika (57 hasarlı bina). Pozitif = major + destroyed,
  negatif = no-damage, minor dışarıda. Görüntü başına en fazla 2 × pozitif negatif: 139.304 kesit
  (61.464 pozitif, 40.980 negatif, 36.860 belirsiz).
- Endonezya Cianjur 2022: Copernicus EMSR641 + Maxar; 5.093 kesit (422 pozitif).
- Fas EMSR695 ve Myanmar EMSR798 hasar paketleri herkese açık indirilemedi (403); Afganistan 2022
  ve Japonya 2024 için Copernicus derecelendirmesi bulunamadı.

Test bölgesi eğitime hiç girmedi; değerler test AUC (yanlış alarm %10 iken yakalanan):

| Test bölgesi | Yalnız Türkiye | Yalnız xBD | xBD + Türkiye | xBD + Türkiye + Endonezya |
|---|---|---|---|---|
| Kahramanmaraş | 0,570 (39/389) | 0,739 | 0,651 (118/389) | 0,651 (99/389) |
| Antakya | 0,625 (69/275) | 0,636 | 0,726 (101/275) | 0,676 (82/275) |
| Malatya | 0,692 (90/267) | 0,481 | 0,505 (37/267) | 0,547 (40/267) |
| Osmaniye | 0,537 (21/160) | 0,546 | 0,537 (31/160) | 0,548 (30/160) |

"Yalnız xBD": Türkiye'nin 7 bölgesi birden test (toplam AUC 0,631; Gaziantep 0,767, Adıyaman 0,538,
İslahiye 0,573). Veri eklemek bölgeye göre değişen etki yapıyor; hiçbir kurulum görmediği bölgede
AUC 0,74'ü geçmedi.

## 5. Model 2: mimari, çoğaltma, yerel ince ayar (egitim/hasar_model.py, sunucu)

```
python -m egitim.xbd_veri --zip xbd/xview2.zip --cikti v128/xbd.npz --boyut 128 --pay 24 --belirsizsiz --oran 0.25
python -m egitim.hasar_veri --parcalar data/gercek/emsr/parcalar.json --cikti v128/turkiye.npz --antakyasiz --boyut 128 --pay-m 10
python -m egitim.hasar_model --veri v128/xbd.npz v128/turkiye.npz v128/antakya.npz v128/endonezya.npz \
    --test-bolge AOI04 --mimari siyam --tur 8 --ince-ayar 20 50 100
```

- Kesit 128×128, bina çevresinde 10 m (xBD 24 piksel) bağlam. xBD alt kümesi 25.523 kesit
  (15.343 pozitif). Eğitim ~48 bin kesit (test bölgesine göre değişir).
- Çoğaltma: öncesi ve sonrasına ayrı parlaklık/kontrast/renk, aralarında ±4 piksel kayma, çevirme/döndürme.
- Mimari: erken (7 kanal tek ağ), siyam (öncesi ve sonrası aynı ResNet18'den ayrı, özellik + fark),
  siyam + örnek normu (her görüntü kendi ortalama/sapmasıyla), sonrası (yalnız sonrası + maske).
- Doğrulama bütün parçalardan seçildi; yine de 0,97–0,98 çıktı (iyimser, kullanılmadı).
- İnce ayar: test bölgesinden k etiketli bina (yarısı hasarlı), 3 tekrar ortalaması, ölçüm bölgenin kalanında.
- Model başına eğitim 190–414 sn (RX 9070 XT), tohum 0.

Test AUC (bölge eğitime hiç girmedi); sütunlar: ince ayarsız / k=20 / k=50 / k=100:

| Bölge | Erken | Siyam | Siyam + norm | Sonrası |
|---|---|---|---|---|
| Kahramanmaraş | 0,663 / 0,750 / 0,838 / 0,848 | 0,616 / 0,719 / 0,853 / 0,869 | 0,598 / 0,686 / 0,760 / 0,822 | 0,671 / 0,783 / 0,845 / 0,861 |
| Antakya | 0,594 / 0,625 / 0,688 / 0,726 | 0,668 / 0,618 / 0,697 / 0,724 | 0,763 / 0,676 / 0,747 / 0,769 | 0,744 / 0,636 / 0,713 / 0,761 |
| Malatya | 0,631 / 0,725 / 0,741 / 0,752 | 0,653 / 0,666 / 0,745 / 0,772 | 0,578 / 0,704 / 0,748 / 0,781 | 0,692 / 0,656 / 0,703 / 0,743 |
| Osmaniye | 0,595 / 0,539 / 0,576 / 0,570 | 0,629 / 0,536 / 0,574 / 0,593 | 0,609 / 0,570 / 0,600 / 0,620 | 0,668 / 0,569 / 0,589 / 0,585 |
| Ortalama | 0,621 / – / – / 0,724 | 0,642 / – / – / 0,740 | 0,637 / – / – / 0,748 | 0,694 / – / – / 0,738 |

Yanlış alarm %10 iken yakalanan (seçilmiş): Kahramanmaraş sonrası k=100 %65,8 (ince ayarsız %37,6);
Antakya siyam + norm ince ayarsız %48,7; Malatya siyam + norm k=100 %42,4; Osmaniye en iyi %24,4.

**Sonuç:**
- İnce ayarsız en iyi ortalama "yalnız sonrası" modelinde (0,694): öncesi/sonrası açı farkını
  hiç kullanmamak bu veride avantaj. Her bölgede ilk turdaki 64 piksel modelden iyi ya da eşit
  (Kahramanmaraş 0,570→0,671, Antakya 0,625→0,744, Malatya 0,692 eşit, Osmaniye 0,537→0,668).
- 100 yerel etiketle ince ayar 3 bölgede belirgin kazanç verdi (Kahramanmaraş 0,87'ye kadar),
  Osmaniye'de zarar verdi. 20 etiket çoğunlukla yetmiyor, sonuç tekrardan tekrara çok oynuyor.
- Hiçbir mimari her bölgede en iyi değil; fark bölgeler arası farktan küçük.
- Osmaniye ve Antakya'da etiket birimi bina bloğu (alan), Kahramanmaraş'ta nokta; blok etiketi
  hangi binanın yıkıldığını söylemediği için ince ayarı da zorlaştırıyor olabilir (ölçülmedi).

## 6. Eğitimsiz iyileştirmeler ve yalnız baş ince ayarı (egitim/hasar_degerlendir.py)

```
python -m egitim.hasar_degerlendir --veri v128/xbd.npz v128/turkiye.npz v128/antakya.npz v128/endonezya.npz \
    --test-bolge AOI04 --modeller deney
```

Bölüm 5'teki modeller üzerinde. TTA: 8 çevirme/döndürme ortalaması. AdaBN: BatchNorm istatistikleri
test bölgesinin etiketsiz kesitlerinden yeniden. Topluluk: 4 mimarinin olasılık ortalaması.
Baş ince ayarı: gövde dondurulur, yalnız son katman k etiketle (200 adım, 3 tekrar ortalaması).

Test AUC, ince ayarsız (düz / TTA / AdaBN / AdaBN+TTA):

| Bölge | En iyi tek model (düz) | Topluluk düz | Topluluk TTA | Topluluk AdaBN |
|---|---|---|---|---|
| Kahramanmaraş | 0,671 (sonrası; TTA 0,720) | 0,670 | 0,681 | 0,728 |
| Antakya | 0,763 (siyam+norm; TTA 0,769) | 0,749 | 0,763 | 0,656 |
| Malatya | 0,692 (sonrası) | 0,670 | 0,666 | 0,461 |
| Osmaniye | 0,668 (sonrası) | 0,636 | 0,622 | 0,569 |

AdaBN 4 bölgenin 3'ünde düşürdü (Malatya sonrası 0,692 → 0,389): kullanılmamalı. TTA ve topluluk
küçük ve karışık etkili.

k=100 ince ayar, tüm ağ (bölüm 5) ile yalnız baş karşılaştırması (her bölgede en iyi mimari):

| Bölge | Tüm ağ, k=100 | Yalnız baş, k=50 | Yalnız baş, k=100 |
|---|---|---|---|
| Kahramanmaraş | 0,869 | 0,884 (siyam) | 0,911 (siyam) |
| Antakya | 0,769 | 0,771 (sonrası) | 0,795 (sonrası) |
| Malatya | 0,781 | 0,820 (siyam) | 0,830 (siyam) |
| Osmaniye | 0,620 | 0,595 (sonrası) | 0,624 (sonrası) |

Sonuç: Az etiketle yalnız son katmanı eğitmek tüm ağı güncellemekten iyi (3 bölgede +0,03–0,05).
Osmaniye'de yerel etiket hâlâ işe yaramıyor (ince ayarsız 0,668 daha iyi).

## 7. Bina bazlı etiket ve ezber kontrolleri (egitim/bina_etiket.py)

```
~/afet-yolo/venv/bin/python -m egitim.bina_etiket          # laptop: Overture + OSM yıkık + Copernicus
python -m egitim.hasar_veri --parcalar data/gercek/emsr/parcalar_bina.json --cikti v128/bina2.npz --antakyasiz --boyut 128 --pay-m 10 --negatif-sinir 1500
python -m egitim.hasar_model --veri v128/xbd.npz v128/endonezya2.npz v128/bina2.npz --test-bolge AOI11 --mimari siyam --tur 8
python -m egitim.hasar_degerlendir --veri ... --test-bolge AOI11 --modeller deney_bina --kurulumlar siyam sonrasi --zor-negatif-m 100
python -m egitim.hasar_model --veri ... --test-bolge "AOI*"      # Türkiye hiç görülmeden
```

Etiket kuralı (her bina Overture taban alanı): hasarsız = Copernicus "No visible damage" bloğunun içinde
ya da o noktayı içeren bina; hasarlı = OSM `destroyed:building` (HOT/OSM gönüllüleri, ODbL, ~3.200 bina)
ya da Copernicus Destroyed/Damaged noktasını içeren (8 m içinde en yakın) bina; hasarlı bloğun içindeki
işaretsiz bina belirsiz, atlandı. Görüntüsü olan parçalarda 41.121 kesit (1.072 hasarlı). Malatya'da 0,
Osmaniye'de 10 hasarlı bina olduğu için bina bazlı test Kahramanmaraş, Antakya, Adıyaman, İslahiye'de.

**a) Aynı bina bazlı test, test bölgesi eğitime hiç girmedi** (AUC; düz / TTA / yalnız baş ince ayar k=100):

| Bölge (test bina, hasarlı) | Blok etiketli model 2 (sonrası) | Bina etiketli, en iyi |
|---|---|---|
| Antakya (10.526, 327) | 0,764 / 0,775 / 0,882 | 0,856 / 0,873 / 0,921 (siyam) |
| Kahramanmaraş (1.380, 259) | 0,797 / 0,824 / 0,855 | 0,788 / 0,821 / 0,866 (sonrası; siyam ince ayar) |
| Adıyaman (6.182, 182) | – | 0,759 / 0,790 / 0,826 (sonrası) |
| İslahiye (5.092, 318) | – | 0,633 / 0,629 / 0,692 (siyam) |

Blok etiketli modeller bina testinde blok testindekinden yüksek çıktı (Kahramanmaraş 0,671 → 0,797):
blok testindeki düşük sayıların bir kısmı test etiketinin kirliliğinden geliyordu.

**b) Zor negatif (mahalle ezberi) testi:** yalnız bir hasarlı binaya 100 m'den yakın hasarsızlar negatif.
Bina etiketli modeller (düz, en iyi): Antakya 0,844 (667 negatif), Kahramanmaraş 0,764 (110), Adıyaman
0,753 (771), İslahiye 0,598 (1.666); topluluk 0,858 / 0,782 / 0,772 / 0,609. Normal testten en çok 0,02
düşük ya da eşit: model enkazlı mahalledeki sağlam binayı da ayırıyor, çevreyi ezberlemiyor.

**c) Deprem dışarıda (aynı olaydan hiç veri yok):**

| Eğitim | Test | Siyam | Sonrası |
|---|---|---|---|
| xBD + Endonezya (Türkiye yok) | Türkiye 7 bölge, 41.121 bina (1.072 hasarlı) | 0,668 | 0,703 |
| xBD + Türkiye (Endonezya yok) | Endonezya, 4.632 (422) | 0,591 | 0,558 |

**d) Tohum:** Antakya, siyam, bina etiketli: 0,856 / 0,833 / 0,830 (tohum 0, 1, 2).

**Sonuç:** Bina etiketi Antakya'da belirgin iyileşme verdi ve model mahalle ezberi yapmıyor. Ama a)'daki
0,76–0,86 değerleri aynı depremin başka bölgeleriyle eğitilmiş modelden; yeni bir depremde yerel etiket
olmadan beklenecek düzey c)'deki 0,56–0,70'tir. Yerel 50–100 bina etiketi bu yüzden gereklidir.
