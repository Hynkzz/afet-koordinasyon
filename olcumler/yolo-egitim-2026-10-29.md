# YOLO insan tespiti eğitimi ve ölçümü — 29.10.2026

Betikler: `egitim/` (AI sunucusunda çalıştırıldı), laptop ölçümü `python -m kamera --olc 300`.
Model: YOLO11n (ultralytics 8.4.192), 640 piksel, 60 tur, erken durma 15 tur (devreye girmedi).
Eğitim donanımı: RX 9070 XT 16 GB, ROCm 7.2, torch 2.14.1.

Veri:

- **C2A** [Nihal ve ark., 2024, arXiv:2408.04922], CC BY 4.0: 10.215 drone görüntüsü
  (yangın, sel, çökmüş bina, trafik kazası); insanlar arka plana sonradan
  yerleştirilmiş, gerçek fotoğraf değil. Hazır bölme: 6.130 eğitim, 2.044 doğrulama,
  2.044 test.
- **COCO val2017**, CC BY 4.0: insan içeren 2.693 görüntü; 2.193'ü eğitime, 500'ü
  doğrulamaya.
- Yer seviyesi kontrolü için **COCO128** (train2017'den 128 görüntü, 254 insan); eğitimde
  kullanılan val2017 ile örtüşmüyor.

## Sonuçlar

| Model | Eğitim süresi | C2A test mAP@0,5 | C2A test mAP@0,5:0,95 | COCO128 insan mAP@0,5 | COCO128 insan mAP@0,5:0,95 |
|---|---|---|---|---|---|
| Hazır YOLO11n (COCO) | — | 0,160 | 0,070 | 0,784 | 0,538 |
| Yalnız C2A ile ince ayar | 5.023 sn (1 sa 24 dk) | 0,787 | 0,504 | 0,014 | 0,005 |
| C2A + COCO karışık | 6.381 sn (1 sa 46 dk) | 0,782 | 0,498 | 0,497 | 0,285 |

C2A testinde kesinlik / duyarlılık: yalnız C2A 0,848 / 0,743; karışık 0,842 / 0,738.

Laptop (RTX 3050 Laptop 4 GB, CUDA, torch 2.15.0), 300 C2A test görüntüsü, kare başına
ön işleme + çıkarım + son işleme, ilk 10 kare hariç medyan:

| Model | Süre | FPS |
|---|---|---|
| Hazır YOLO11n | 10,1 ms | ~99 |
| Yalnız C2A | 9,9 ms | ~101 |
| Karışık | 11,0 ms | ~91 |

GPU belleği: YOLO süreci 208 MiB (PyTorch'un ayırdığı en yüksek 90 MiB). Ölçümler
sırasında LLM sunucusu da GPU'daydı (3,2 GB); ikisi birlikte 4 GB'a sığıyor.

## Gözlemler

- Hazır model dronedan görülen küçük insanları neredeyse bulamıyor (0,16).
- Yalnız C2A ile eğitilen model yer seviyesindeki insanları unuttu (0,784 → 0,014):
  demoda kamera yer seviyesinde olacağı için tek başına kullanılamaz.
- COCO görüntüleri eklenince C2A başarısı korunuyor (0,787 → 0,782), yer seviyesi
  kısmen geri geliyor (0,497) ama hazır modelin (0,784) altında. Daha fazla yer
  seviyesi görüntüsü (COCO train2017) ile kapatılabilir; denenmedi.
- C2A sentez görüntü olduğu için gerçek enkaz görüntüsündeki başarı bilinmiyor.
- Saatte yanlış alarm ölçülmedi: içinde insan olmayan uzun bir kayıt gerekiyor.

## Gerçek videolarla nitel deneme

Kamera kurulamadığı için kamera benzetiminde kullanılan 4 açık lisanslı video
(`scripts/video_indir.py`; Wikimedia Commons, CC BY / CC BY-SA / kamu malı). Videolarda
kare etiketi olmadığı için doğruluk ölçülemez; aşağıdaki sayı yalnızca insan bulunan
kare oranı (güven ≥ 0,5, her 5 karede bir).

| Video | Hazır YOLO11n | Yalnız C2A | Karışık |
|---|---|---|---|
| 2023 Hatay, İngiliz kurtarma ekibi (152 kare) | %82 | %41 | %65 |
| 2023 Hatay, Ukrayna kurtarma ekibi (296 kare) | %60 | %14 | %61 |
| Çökmüş binada uluslararası kurtarma (229 kare) | %63 | %12 | %23 |
| İskenderun yıkım (679 kare) | %48 | %73 | %51 |

Her videodan bir kare gözle incelendi: yer seviyesinden çekilmiş bu görüntülerde hazır
model karışık modelin kaçırdığı kişileri de buluyor (ör. enkazda yürüyen kurtarmacı);
yakın plandaki kişiyi ikisi de kaçırdı. Bu yüzden video benzetiminde hazır model
kullanılıyor. İskenderun videosu insanla dolu olduğu için yanlış alarm ölçümüne
uygun değil.

Ukrayna videosunun renk uzayı bilgisi bozuk ("reserved") olduğu için kareler önce
çözülemiyor ve üç model de %0 veriyordu; bilgi kayıpsız düzeltildi
(`scripts/video_indir.py`, `renk_duzelt`), sayılar düzeltilmiş videodan.

## Güvenlik kamerası açısı: MOT20 ölçümü

Kamera gerçekte yüksekte (3–6 m, aşağı eğik) duracağı için modeller bu açıdan da ölçüldü.
Veri: MOT20 [Dendorfer ve ark., 2020, arXiv:2003.09003], CC BY-NC-SA 3.0; 4 eğitim dizisi
(etiketleri açık olan), her 10 karede bir → 895 kare, 91.434 insan kutusu (yaya, araçtaki
ve duran kişi; görünürlük ≥ 0,25). Çok kalabalık sahneler: kare başına ortalama ~100 kişi.
Dönüşüm: `egitim/mot_hazirla.py`. Ölçüm laptopta (RTX 3050), `yolo detect val`, `max_det=500`.

| Model | mAP@0,5 (640 px) | mAP@0,5:0,95 (640 px) | mAP@0,5 (1280 px) | mAP@0,5:0,95 (1280 px) |
|---|---|---|---|---|
| Hazır YOLO11n | 0,516 | 0,203 | 0,639 | 0,256 |
| Yalnız C2A | 0,666 | 0,242 | 0,488 | 0,169 |
| Karışık | 0,630 | 0,225 | 0,594 | 0,237 |

Kare başına süre (ön işleme + çıkarım + son işleme): 640 px ~5 ms, 1280 px ~18–22 ms.

- Güvenlik kamerası açısında en iyi iki seçenek birbirine yakın: yalnız C2A modeli 640 px'te
  (0,666) ve hazır model 1280 px'te (0,639). Hiçbiri 0,67'yi geçmiyor.
- Giriş büyüyünce insanlar büyük görünür: küçük insana alışmış C2A modeli 1280 px'te kötüleşiyor,
  hazır model iyileşiyor.
- 1280 px, LLM sunucusu GPU'da açıkken (3,1 GB) toplu işlemde belleğe sığmadı; tek görüntü
  işlemle çalıştı. Canlı kamera zaten tek kare işlediği için demoda sorun değil.
- MOT20 sahneleri afet değil (yaya kalabalığı); açı benzer, ortam farklı.

## MOT17 eklenmiş karışık model (karisik2) — 30.10.2026

Eğitim: C2A + COCO + MOT17 (7 eğitim dizisi, her 5 karede bir, FRCNN kopyası; MOT17-13
doğrulamada) = 9.236 eğitim görüntüsü (914 MOT17). 60 tur, 7.082 sn (1 sa 58 dk), RX 9070 XT.
Betikler: `egitim/karisik2_hazirla.py`, `egitim/egit3.sh`. MOT20 eğitime girmedi.
MOT20 ölçümü: `scripts/yolo_karsilastir.py` (laptop, RTX 3050).

| Model | MOT20 640 px | MOT20 1280 px | C2A test (640) | COCO128 insan (640) |
|---|---|---|---|---|
| Hazır YOLO11n | 0,516 | 0,639 | 0,160 | 0,784 |
| Yalnız C2A | 0,666 | 0,488 | 0,787 | 0,014 |
| Karışık (C2A + COCO) | 0,630 | 0,594 | 0,782 | 0,497 |
| Karışık2 (+ MOT17) | **0,790** | 0,760 | 0,781 | 0,518 |

(mAP@0,5.) MOT17 eklemek güvenlik kamerası açısında 0,63'ten 0,79'a çıkardı; drone başarısı
korundu (0,781), yer seviyesi hâlâ hazır modelin altında (0,518'e karşı 0,784). MOT17 ile MOT20
farklı kamera ve sahneler, ama ikisi de yaya kalabalığı; afet ortamındaki başarı bilinmiyor.
