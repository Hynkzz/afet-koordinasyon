# YOLO eğitimi (AI sunucusu)

Eğitim AI sunucusunda (Ubuntu, RX 9070 XT 16 GB, ROCm) `~/afet-yolo` altında
yapıldı; bu klasör o betiklerin kopyası. Laptopta yalnızca çıkan model dosyası
kullanılır (`kamera/`).

| Dosya | Ne yapar |
|---|---|
| `kur-ve-dene.sh` | Ayrı ortam (ROCm'lu PyTorch + ultralytics) ve küçük deneme eğitimi |
| `egit.sh` | Yalnızca C2A ile ince ayar ve ölçüm |
| `karisik_hazirla.py` | C2A + COCO val2017 insan görüntülerinden karışık set |
| `egit2.sh` | Karışık setle ince ayar ve iki test kümesinde ölçüm |
| `mot_hazirla.py` | MOT17/MOT20 etiketlerini YOLO biçimine çevirir |
| `karisik2_hazirla.py`, `egit3.sh` | Karışık sete MOT17 eklenerek ince ayar (güvenlik kamerası açısı) |
| `c2a.yaml`, `karisik.yaml`, `karisik2.yaml` | Veri tanımları |

Sunucuya özgü notlar: `/tmp` 7 GB'lık RAM diski olduğu için pip `TMPDIR=~/.cache/piptmp`
ile çalıştırılır; sunucuda `libGL` olmadığından `opencv-python-headless` kullanılır.

Veri: C2A (Nihal ve ark., 2024, arXiv:2408.04922, CC BY 4.0) Google Drive'dan;
COCO val2017 (CC BY 4.0) cocodataset.org'dan. Veri ve model dosyaları depoya konmaz.
Sonuçlar: `olcumler/yolo-egitim-2026-10-29.md`.
