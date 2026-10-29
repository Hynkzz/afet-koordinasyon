"""Karisik set + MOT17 (yuksek ve goz hizasi sabit kameralar) -> karisik2.

Yalniz C2A + COCO ile egitilen model guvenlik kamerasi acisinda (MOT20) 0,63'te kaldi; MOT17 bu
aciyi ekler. MOT20 olcum icin ayrildi, egitime girmez (farkli kameralar ve sahneler).
MOT17'de her dizi uc dedektorle tekrarlanir; goruntu ve etiket ayni oldugu icin yalniz FRCNN kopyasi.
"""
import os
from pathlib import Path

VERI = Path.home() / "afet-yolo" / "veri"
KARISIK = VERI / "karisik"
MOT17 = VERI / "mot17-yolo"
HEDEF = VERI / "karisik2"

for bolum in ("train", "val"):
    for tur in ("images", "labels"):
        (HEDEF / bolum / tur).mkdir(parents=True, exist_ok=True)
        for f in (KARISIK / bolum / tur).iterdir():
            hedef = HEDEF / bolum / tur / f.name
            if not hedef.exists():
                os.symlink(f.resolve(), hedef)

# MOT17-13 dogrulamaya, digerleri egitime: ayni diziden kareler iki tarafta olmasin.
for tur in ("images", "labels"):
    for f in (MOT17 / tur).iterdir():
        bolum = "val" if f.name.startswith("MOT17-13") else "train"
        hedef = HEDEF / bolum / tur / f.name
        if not hedef.exists():
            os.symlink(f.resolve(), hedef)

for bolum in ("train", "val"):
    g = list((HEDEF / bolum / "images").iterdir())
    print(bolum, len(g), "goruntu,", sum(x.name.startswith("MOT17") for x in g), "MOT17")
