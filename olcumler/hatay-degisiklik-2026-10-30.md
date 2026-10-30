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

Test eğrisinden okunan işletme noktaları (betimleme; eşik testte ayarlanmadı demek değil, yalnız eğrinin şekli):

| Yanlış alarm | Tohum 0 | Tohum 1 | Tohum 2 |
|---|---|---|---|
| %5 | 25/81 | 24/81 | 28/81 |
| %10 | 34/81 | 36/81 | 39/81 |
| %20 | 44/81 | 48/81 | 46/81 |

Sonuç: Eğitimli sınıflandırıcı basit değişiklik tespitinden belirgin iyi (test AUC 0,79–0,82,
basit yöntemde 0,59–0,67). Yine de yanlış alarm %10'dayken hasarlı blokların ancak %42–48'ini
buluyor. Doğrulama kümesinde 21 pozitif olduğu için seçilen eşik tohuma göre çok oynuyor
(duyarlılık %12–28). Daha çok etiketli veri (diğer şehirler, tek bina etiketleri) gerekir.
