"""Copernicus EMSR648 bolgelerinden (etiket) ve Maxar oncesi/sonrasi parcalarindan kesit veri seti.

Goruntu indirilmez: Maxar dosyalari bulutta COG; rasterio yalnizca blok pencerelerini okur.
Nokta etiketli bolgelerde (builtUpP) nokta cevresinde 16 m kare alinir.
Cikti: data/gercek/emsr/kesitler.npz (x, y, parca, sinif, bolge) -> egitim.hasar_siniflandirici --veri
  ~/afet-yolo/venv/bin/python -m egitim.hasar_veri
"""
import glob
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom
from rasterio.windows import from_bounds

from scripts.hatay_olc import NEGATIF, POZITIF, kutu

KOK = Path(__file__).resolve().parent.parent
EMSR = KOK / "data" / "gercek" / "emsr"
HATAY = KOK / "data" / "gercek" / "hatay"
MAXAR = "https://maxar-opendata.s3.amazonaws.com/events/Kahramanmaras-turkey-earthquake-23/"
BOYUT = 64
NOKTA_YARI_M = 8.0
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")


def gorsel(yol: str) -> str:
    return MAXAR + yol.replace(".json", "-visual.tif")


def parca_isle(bloklar: list, once: str, sonra: str, parca: str, bolge: str) -> list:
    sonuc = []
    with rasterio.open(once) as o, rasterio.open(sonra) as s:
        if o.crs != s.crs or o.transform != s.transform:
            print(f"{bolge} {parca}: izgara farkli, atlandi")
            return sonuc
        for f in bloklar:
            g = transform_geom("EPSG:4326", o.crs, f["geometry"])
            if g["type"] == "Point":
                x, y = g["coordinates"]
                d = NOKTA_YARI_M
                g = {"type": "Polygon", "coordinates": [[[x - d, y - d], [x + d, y - d], [x + d, y + d],
                                                          [x - d, y + d], [x - d, y - d]]]}
            l, b, r, t = kutu(g["coordinates"])
            if l < o.bounds.left or r > o.bounds.right or b < o.bounds.bottom or t > o.bounds.top:
                continue
            w = from_bounds(l - 4, b - 4, r + 4, t + 4, o.transform).round_offsets().round_lengths()
            a, c = o.read([1, 2, 3], window=w), s.read([1, 2, 3], window=w)
            if a.shape != c.shape or min(a.shape[1:]) < 8:
                continue
            if (a.sum(axis=0) == 0).mean() > 0.2 or (c.sum(axis=0) == 0).mean() > 0.2:
                continue
            m = geometry_mask([g], out_shape=a.shape[1:], transform=o.window_transform(w), invert=True)
            yigin = np.concatenate([a, c, m[None] * 255]).astype(np.uint8)
            kesit = np.stack([cv2.resize(k, (BOYUT, BOYUT), interpolation=cv2.INTER_AREA) for k in yigin], axis=-1)
            sinif = f["properties"]["damage_gra"]
            sonuc.append((kesit, 1 if sinif in POZITIF else 0 if sinif in NEGATIF else -1, parca, sinif, bolge))
    print(f"{bolge} {parca}: {len(sonuc)} kesit")
    return sonuc


def main():
    isler = []
    for o in json.load(open(EMSR / "parcalar.json")):
        bloklar = json.load(open(o["dosya"]))["features"]
        for parca, (once, sonra) in o["ortak"].items():
            isler.append((bloklar, gorsel(once), gorsel(sonra), parca, o["aoi"]))
    # Antakya yerelde indirilmis parcalardan; test parcasi da burada, egitim betigi ayirir.
    antakya = json.load(open(next(HATAY.glob("monit/*builtUpA*.json"))))["features"]
    for once in sorted(glob.glob(str(HATAY / "maxar" / "*_2022-12-22.tif"))):
        isler.append((antakya, once, once.replace("2022-12-22", "2023-02-11"), Path(once).name.split("_")[0], "AOI11"))

    with ThreadPoolExecutor(8) as havuz:
        satirlar = [s for parca in havuz.map(lambda i: parca_isle(*i), isler) for s in parca]
    x, y, parca, sinif, bolge = zip(*satirlar)
    np.savez_compressed(EMSR / "kesitler.npz", x=np.stack(x), y=np.array(y), parca=np.array(parca),
                        sinif=np.array(sinif), bolge=np.array(bolge))
    y = np.array(y)
    print(f"toplam {len(y)} kesit, pozitif {(y == 1).sum()}, negatif {(y == 0).sum()}, belirsiz {(y == -1).sum()}")


if __name__ == "__main__":
    main()
