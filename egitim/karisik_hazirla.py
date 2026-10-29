"""C2A + COCO val2017 insan goruntulerinden karisik egitim seti kurar (goruntuler kopyalanmaz, baglanir).

C2A yalnizca dronedan gorulen kucuk insanlari icerdigi icin onunla egitilen model yer seviyesindeki
insanlari unutuyordu (COCO128 mAP50 0.78 -> 0.01); COCO goruntuleri bunu onlemek icin.
COCO val2017 kullanilir; olcumdeki coco128 train2017'den, ortusme yok.
"""
import os
import zipfile
from pathlib import Path

VERI = Path.home() / "afet-yolo" / "veri"
C2A = VERI / "new_dataset3"
COCO = VERI / "coco"
HEDEF = VERI / "karisik"
COCO_DOGRULAMA = 500

if not (COCO / "images" / "val2017").exists():
    zipfile.ZipFile(COCO / "val2017.zip").extractall(COCO / "images")
etiket_zip = zipfile.ZipFile(COCO / "labels.zip")

for bolum in ("train", "val"):
    for tur in ("images", "labels"):
        (HEDEF / bolum / tur).mkdir(parents=True, exist_ok=True)


def bagla(kaynak: Path, hedef: Path):
    if not hedef.exists():
        os.symlink(kaynak, hedef)


for bolum in ("train", "val"):
    for g in (C2A / bolum / "images").iterdir():
        bagla(g, HEDEF / bolum / "images" / g.name)
        e = C2A / bolum / "labels" / (g.stem + ".txt")
        if e.exists():
            bagla(e, HEDEF / bolum / "labels" / e.name)

coco_insan = []
for ad in sorted(etiket_zip.namelist()):
    if not (ad.startswith("coco/labels/val2017/") and ad.endswith(".txt")):
        continue
    satirlar = [" ".join(s.split()[:5]) for s in etiket_zip.read(ad).decode().splitlines() if s.split()[:1] == ["0"]]
    if satirlar:
        coco_insan.append((Path(ad).stem, satirlar))

for no, (kok, satirlar) in enumerate(coco_insan):
    bolum = "val" if no < COCO_DOGRULAMA else "train"
    bagla(COCO / "images" / "val2017" / f"{kok}.jpg", HEDEF / bolum / "images" / f"coco_{kok}.jpg")
    (HEDEF / bolum / "labels" / f"coco_{kok}.txt").write_text("\n".join(satirlar) + "\n")

for bolum in ("train", "val"):
    goruntu = list((HEDEF / bolum / "images").iterdir())
    print(bolum, len(goruntu), "goruntu,", sum(g.name.startswith("coco_") for g in goruntu), "COCO")
