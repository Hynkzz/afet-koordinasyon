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
