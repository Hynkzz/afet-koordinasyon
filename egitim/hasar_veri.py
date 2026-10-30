"""Copernicus EMSR648 bolgelerinden (etiket) ve Maxar oncesi/sonrasi parcalarindan kesit veri seti.

Goruntu indirilmez: Maxar dosyalari bulutta COG; rasterio yalnizca blok pencerelerini okur.
Nokta etiketli bolgelerde (builtUpP) nokta cevresinde 16 m kare alinir.
Cikti: data/gercek/emsr/kesitler.npz (x, y, parca, sinif, bolge) -> egitim.hasar_siniflandirici --veri
  ~/afet-yolo/venv/bin/python -m egitim.hasar_veri
"""
import argparse
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
MAXAR = "https://maxar-opendata.s3.amazonaws.com/events/"
TURKIYE = "Kahramanmaras-turkey-earthquake-23"
BOYUT = 64
PAY_M = 4.0
NOKTA_YARI_M = 8.0
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")


def gorsel(yol: str, olay: str = TURKIYE) -> str:
    # Turkiye dosyasindaki yollar olay klasorune goreli, digerleri olay adiyla baslar.
    if yol.startswith("http"):
        return yol
    on = "" if yol.startswith(olay) else olay + "/"
    return MAXAR + on + yol.replace(".json", "-visual.tif")


def merkez(geometri: dict) -> tuple[float, float]:
    l, b, r, t = kutu(geometri["coordinates"])
    return (l + r) / 2, (b + t) / 2


def parca_isle(bloklar: list, once: str, sonra: str, parca: str, bolge: str, negatif_sinir: int) -> list:
    sonuc = []
    with rasterio.open(once) as o, rasterio.open(sonra) as s:
        if o.crs != s.crs or o.transform != s.transform:
            print(f"{bolge} {parca}: izgara farkli, atlandi")
            return sonuc
        # Parcaya dusenler once ucuz geometriyle bulunur; hasarsizlar goruntu okunmadan seyreltilir
        # (eskiden 30 bin binanin hepsi okunup sonra atiliyordu).
        sinir = transform_geom(o.crs, "EPSG:4326", {"type": "Polygon", "coordinates": [[
            [o.bounds.left, o.bounds.bottom], [o.bounds.right, o.bounds.bottom], [o.bounds.right, o.bounds.top],
            [o.bounds.left, o.bounds.top], [o.bounds.left, o.bounds.bottom]]]})
        sl, sb, sr, st = kutu(sinir["coordinates"])
        icerde = [f for f in bloklar if sl <= merkez(f["geometry"])[0] <= sr and sb <= merkez(f["geometry"])[1] <= st]
        negatif = [i for i, f in enumerate(icerde) if f["properties"]["damage_gra"] in NEGATIF]
        if len(negatif) > negatif_sinir * 1.2:
            at = set(np.random.default_rng(0).choice(negatif, len(negatif) - int(negatif_sinir * 1.2), replace=False).tolist())
            icerde = [f for i, f in enumerate(icerde) if i not in at]
        for f in icerde:
            lon, lat = merkez(f["geometry"])
            g = transform_geom("EPSG:4326", o.crs, f["geometry"])
            if g["type"] == "Point":
                x, y = g["coordinates"]
                d = NOKTA_YARI_M
                g = {"type": "Polygon", "coordinates": [[[x - d, y - d], [x + d, y - d], [x + d, y + d],
                                                          [x - d, y + d], [x - d, y - d]]]}
            l, b, r, t = kutu(g["coordinates"])
            if l < o.bounds.left or r > o.bounds.right or b < o.bounds.bottom or t > o.bounds.top:
                continue
            w = from_bounds(l - PAY_M, b - PAY_M, r + PAY_M, t + PAY_M, o.transform).round_offsets().round_lengths()
            a, c = o.read([1, 2, 3], window=w), s.read([1, 2, 3], window=w)
            if a.shape != c.shape or min(a.shape[1:]) < 8:
                continue
            if (a.sum(axis=0) == 0).mean() > 0.2 or (c.sum(axis=0) == 0).mean() > 0.2:
                continue
            m = geometry_mask([g], out_shape=a.shape[1:], transform=o.window_transform(w), invert=True)
            yigin = np.concatenate([a, c, m[None] * 255]).astype(np.uint8)
            kesit = np.stack([cv2.resize(k, (BOYUT, BOYUT), interpolation=cv2.INTER_AREA) for k in yigin], axis=-1)
            sinif = f["properties"]["damage_gra"]
            sonuc.append((kesit, 1 if sinif in POZITIF else 0 if sinif in NEGATIF else -1, parca, sinif, bolge, lon, lat))
    # Hasarsiz cok fazla olan bolgelerde (Cianjur 45 bin) bellek icin negatifler seyreltilir.
    negatif = [i for i, s in enumerate(sonuc) if s[1] == 0]
    if len(negatif) > negatif_sinir:
        at = set(np.random.default_rng(0).choice(negatif, len(negatif) - negatif_sinir, replace=False).tolist())
        sonuc = [s for i, s in enumerate(sonuc) if i not in at]
    print(f"{bolge} {parca}: {len(sonuc)} kesit")
    return sonuc


def kaydet(cikti: str, x, y, parca, sinif, bolge, lon, lat):
    # Buyuk kesitler bellege sigmaz: x ayri .npy (egitimde mmap ile okunur), gerisi kucuk npz.
    np.save(cikti.replace(".npz", "_x.npy"), np.stack(x))
    np.savez(cikti, y=np.array(y), parca=np.array(parca), sinif=np.array(sinif), bolge=np.array(bolge),
             lon=np.array(lon), lat=np.array(lat))


def main():
    ayrac = argparse.ArgumentParser()
    ayrac.add_argument("--parcalar", default=str(EMSR / "parcalar.json"))
    ayrac.add_argument("--cikti", default=str(EMSR / "kesitler.npz"))
    ayrac.add_argument("--antakyasiz", action="store_true", help="yerel Antakya parcalarini ekleme")
    ayrac.add_argument("--negatif-sinir", type=int, default=10**9, help="parca basina en fazla hasarsiz kesit")
    ayrac.add_argument("--boyut", type=int, default=64)
    ayrac.add_argument("--pay-m", type=float, default=4.0, help="bina cevresinden alinan baglam (metre)")
    secim = ayrac.parse_args()
    global BOYUT, PAY_M
    BOYUT, PAY_M = secim.boyut, secim.pay_m
    isler = []
    for o in json.load(open(secim.parcalar)):
        bloklar = json.load(open(KOK / o["dosya"]))["features"]
        olay = o.get("olay", TURKIYE)
        for parca, (once, sonra) in o["ortak"].items():
            isler.append((bloklar, gorsel(once, olay), gorsel(sonra, olay), parca, o["aoi"], secim.negatif_sinir))
    if not secim.antakyasiz:
        # Antakya yerelde indirilmis parcalardan; test parcasi da burada, egitim betigi ayirir.
        antakya = json.load(open(next(HATAY.glob("monit/*builtUpA*.json"))))["features"]
        for once in sorted(glob.glob(str(HATAY / "maxar" / "*_2022-12-22.tif"))):
            isler.append((antakya, once, once.replace("2022-12-22", "2023-02-11"), Path(once).name.split("_")[0],
                          "AOI11", secim.negatif_sinir))

    with ThreadPoolExecutor(8) as havuz:
        satirlar = [s for parca in havuz.map(lambda i: parca_isle(*i), isler) for s in parca]
    x, y, parca, sinif, bolge, lon, lat = zip(*satirlar)
    kaydet(secim.cikti, x, y, parca, sinif, bolge, lon, lat)
    y = np.array(y)
    print(f"toplam {len(y)} kesit, pozitif {(y == 1).sum()}, negatif {(y == 0).sum()}, belirsiz {(y == -1).sum()}")


if __name__ == "__main__":
    main()
