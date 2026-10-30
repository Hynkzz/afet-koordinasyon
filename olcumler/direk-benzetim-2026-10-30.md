# Direk kamerası: bina hasar tespiti benzetim ölçümü (30 Ekim 2026)

## Ne ölçüldü

Yüksek bir direğe konmuş 360° kameranın, kurulumda bir kez çıkarılan bina alanlarıyla (etiket
haritası) hangi binanın yıkıldığını bulup bulamadığı. Kamera görüntüsü **sentetiktir**: bina
taban alanları düz renkli prizmalara yükseltilir, yıkılan bina düzensiz yüksekliğe ve enkaz
dokusuna dönüşür, her karede ışık 0,8–1,2 kat değişir ve gürültü eklenir. Bu yüzden aşağıdaki
sayılar **yöntemin mantığının çalıştığını** gösterir, gerçek kameradaki doğruluğu göstermez.

- Bina verisi: Overture Maps, Yozgat merkez (34,79–34,83 D, 39,80–39,83 K), 4.593 bina
  (316 OpenStreetMap, 4.277 Microsoft ML Buildings). Yükseklik 4.591 binada yok, 12 m
  (4 kat) varsayıldı.
- Direk: 25 m, 360° × (+8° … −60°), 2048×512 piksel, menzil 250 m.
- Tespit (`direk/tespit.py`): parlaklık sahnenin medyanıyla referansa eşitlenir, piksel farkı
  35'ten büyükse "değişti"; binanın alanında değişen oran ≥ %25 hasarlı, ≥ %50 yıkık; karar
  3 ardışık karede aynı kalınca bildirilir. 200 pikselden küçük görünen bina izlenmez.

## 1. Tespit (scripts/direk_olc.py)

```
python -m scripts.direk_olc --deneme 40
```

40 deneme: her denemede rastgele bir binanın 20–60 m yanına direk, önce 10 yıkımsız kare,
sonra rastgele 1–3 izlenen bina yıkılıp 5 kare.

| Ölçüt | Sonuç |
|---|---|
| Yıkılan bina | 81 |
| Bulunan | 74 (%91,4) |
| Yıkım karelerinde yanlış binaya işaret | 0 |
| Yıkımsız karelerde yanlış alarm | 0 / 42.260 bina-kare |
| Görünen 200–1.000 piksel | 39/44 |
| Görünen 1.000–5.000 piksel | 23/25 |
| Görünen 5.000+ piksel | 12/12 |
| Görünürlük %0–50 (önündeki bina kapatıyor) | 34/39 |
| Görünürlük %50–90 | 19/20 |
| Görünürlük %90–100 | 21/22 |
| Süre | 407 sn (40 deneme, kurulumlar dahil) |

Kare başına süre (laptop işlemcisi, tek çekirdek ağırlıklı, 2048×512):
kurulum 2,3 sn (bir kez), tespit 107 ms/kare, sentetik görüntü üretimi 248 ms/kare.
Raspberry Pi'de ölçülmedi.

**Sınırlar (sayıları yorumlarken):**
- "Yanlış binaya işaret 0" benzetimin kurgusundan gelir: benzetimde enkaz binanın kendi
  tabanından dışarı taşmaz, toz bulutu ve sarsıntıyla kamera kayması yoktur. Gerçekte
  yan binaya düşen enkaz o binayı da "hasarlı" gösterebilir.
- Yanlış alarm 0, çünkü sahnede yalnızca ışık ve gürültü değişiyor; araç, insan, gölge
  hareketi, kar, yağmur, gece yok.
- Kaçan 7 binanın 5'i 1.000 pikselden küçük görünüyor (uzak ya da çoğu kapalı).

## 2. Direk yerleşimi (scripts/direk_yerlesim.py)

```
python -m scripts.direk_yerlesim --adim-m 100 --en-iyi 5
```

100 m ızgarada 1.295 aday nokta; her noktada 720×180 çözünürlükte en az 12 piksel görünen bina
"görülüyor" sayıldı. Açgözlü seçim: her adımda en çok yeni binayı gören nokta.

| Direk | Konum | Yeni bina | Toplam (4.593 içinde) |
|---|---|---|---|
| 1 | 39,81313 K 34,80087 D | 240 | 240 (%5,2) |
| 2 | 39,82391 K 34,79502 D | 228 | 468 (%10,2) |
| 3 | 39,81762 K 34,82309 D | 202 | 670 (%14,6) |
| 4 | 39,81583 K 34,80437 D | 182 | 852 (%18,5) |
| 5 | 39,82661 K 34,80321 D | 173 | 1.025 (%22,3) |

Süre 229 sn. Bina yükseklikleri tahmin olduğu için görülen bina sayıları da tahmindir;
yüksek binalar arkasını daha çok kapatır.

Aynı hesap seçimi 60 direğe kadar uzatarak (`--en-iyi 60`, 227 sn):

| Direk sayısı | Kapsanan bina | Oran |
|---|---|---|
| 5 | 1.025 | %22,3 |
| 10 | 1.818 | %39,6 |
| 15 | 2.479 | %54,0 |
| 20 | 2.995 | %65,2 |
| 30 | 3.722 | %81,0 |
| 40 | 4.079 | %88,8 |
| 50 | 4.287 | %93,3 |
| 60 | 4.418 | %96,2 |

Yaklaşık 3,4 × 2,9 km'lik Yozgat merkezinde binaların %80'ini görmek için ~30 direk gerekiyor;
sonrasında her yeni direk az sayıda bina ekliyor. "Görülüyor" eşiği (12 piksel) tespitin
izleme eşiğinden (200 piksel, 2048×512) gevşek olduğu için bu oranlar üst sınırdır.
