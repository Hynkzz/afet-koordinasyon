"""Antakya uydu demosu verisi: secilen alandaki her binanin hasar olasiligi + oncesi/sonrasi goruntu.

Model Antakya'yi egitimde hic gormedi (egitim.hasar_model --test-bolge AOI11, bina etiketli). Cikti
web/demo/ altina: antakya.geojson (bina, olasilik, varsa gercek etiket), oncesi.jpg, sonrasi.jpg
(EPSG:4326'ya donusturulmus, Leaflet imageOverlay icin) ve antakya_ozet.json (alan, olcum).
Gercek etiket yalnizca karsilastirma icindir; model onu gormez.
  ~/afet-yolo/venv/bin/python -m scripts.antakya_demo
"""
import json
from pathlib import Path

import cv2
import numpy as np
import rasterio
import torch
from rasterio.features import geometry_mask
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_geom
from rasterio.windows import from_bounds
from shapely.geometry import box, mapping, shape

from egitim.hasar_model import Siyam, auc, hazirla
from scripts.hatay_olc import kutu

KOK = Path(__file__).resolve().parent.parent
MAXAR = KOK / "data" / "gercek" / "hatay" / "maxar"
PARCA = "031133023302"
# Bati Antakya, yikimin en yogun oldugu ~2 x 2 km (etiketli 2.836 bina, 213 yikik).
ALAN = (36.1398, 36.2025, 36.1618, 36.2205)
MODEL = Path.home() / "afet-yolo" / "modeller" / "model_siyam_AOI11_t0.pt"
CIKTI = KOK / "web" / "demo"
BOYUT, PAY_M = 128, 10.0
ESIK = 0.5
GORUNTU_M = 0.8  # demo goruntusu piksel boyu; 2 km ~ 2.500 piksel


def goruntu(yol: Path, cikti: Path):
    with rasterio.open(yol) as k:
        sinir = transform_geom("EPSG:4326", k.crs, mapping(box(*ALAN)))
        w = from_bounds(*kutu(sinir["coordinates"]), k.transform).round_offsets().round_lengths()
        veri = k.read([1, 2, 3], window=w)
        kaynak_t = k.window_transform(w)
        derece = GORUNTU_M / 111_195
        t, gen, yuk = calculate_default_transform(k.crs, "EPSG:4326", veri.shape[2], veri.shape[1],
                                                  *rasterio.transform.array_bounds(veri.shape[1], veri.shape[2], kaynak_t),
                                                  resolution=derece)
        hedef = np.zeros((3, yuk, gen), np.uint8)
        reproject(veri, hedef, src_transform=kaynak_t, src_crs=k.crs, dst_transform=t, dst_crs="EPSG:4326",
                  resampling=Resampling.bilinear)
    cv2.imwrite(str(cikti), cv2.cvtColor(np.moveaxis(hedef, 0, -1), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 80])
    bat, kuz = t.c, t.f
    return [[kuz + t.e * yuk, bat], [kuz, bat + t.a * gen]]  # [[guney, bati], [kuzey, dogu]]


def main():
    CIKTI.mkdir(parents=True, exist_ok=True)
    alan = box(*ALAN)
    binalar = [shape(f["geometry"]) for f in json.load(open(KOK / "data/gercek/bina_etiket/overture_AOI11.geojson"))["features"]
               if f["geometry"]["type"] in ("Polygon", "MultiPolygon")]
    binalar = [b for b in binalar if alan.contains(b.centroid)]
    gercek = {}
    for f in json.load(open(KOK / "data/gercek/bina_etiket/AOI11.geojson"))["features"]:
        c = shape(f["geometry"]).centroid
        if alan.contains(c):
            gercek[(round(c.x, 7), round(c.y, 7))] = f["properties"]["damage_gra"] != "No visible damage"

    kesitler, secilen = [], []
    with rasterio.open(MAXAR / f"{PARCA}_2022-12-22.tif") as o, rasterio.open(MAXAR / f"{PARCA}_2023-02-11.tif") as s:
        for b in binalar:
            g = transform_geom("EPSG:4326", o.crs, mapping(b))
            l, a, r, u = kutu(g["coordinates"])
            w = from_bounds(l - PAY_M, a - PAY_M, r + PAY_M, u + PAY_M, o.transform).round_offsets().round_lengths()
            x, y = o.read([1, 2, 3], window=w), s.read([1, 2, 3], window=w)
            if x.shape != y.shape or min(x.shape[1:]) < 8:
                continue
            m = geometry_mask([g], out_shape=x.shape[1:], transform=o.window_transform(w), invert=True)
            yigin = np.concatenate([x, y, m[None] * 255]).astype(np.uint8)
            kesitler.append(np.stack([cv2.resize(k, (BOYUT, BOYUT), interpolation=cv2.INTER_AREA) for k in yigin], -1))
            secilen.append(b)
    print(f"{len(binalar)} bina, {len(secilen)} kesit", flush=True)

    cihaz = "cpu"
    model = Siyam()
    model.load_state_dict(torch.load(MODEL, map_location=cihaz))
    model.eval()
    olasilik = []
    with torch.no_grad():
        for i in range(0, len(kesitler), 64):
            t = hazirla(np.stack(kesitler[i:i + 64]), cihaz, False, False)
            olasilik.append(torch.sigmoid(model(t)).numpy())
    olasilik = np.concatenate(olasilik)

    ozellik, p_etiketli, e_etiketli = [], [], []
    for b, p in zip(secilen, olasilik):
        c = b.centroid
        e = gercek.get((round(c.x, 7), round(c.y, 7)))
        if e is not None:
            p_etiketli.append(p)
            e_etiketli.append(e)
        ozellik.append({"type": "Feature", "geometry": mapping(b.simplify(1e-6)),
                        "properties": {"p": round(float(p), 3), "gercek": None if e is None else ("yikik" if e else "hasarsiz")}})
    json.dump({"type": "FeatureCollection", "features": ozellik}, open(CIKTI / "antakya.geojson", "w"), separators=(",", ":"))

    pe, ee = np.array(p_etiketli), np.array(e_etiketli)
    tahmin = pe >= ESIK
    ozet = {
        "alan": ALAN, "parca": PARCA, "esik": ESIK, "bina": len(secilen), "isaretlenen": int((olasilik >= ESIK).sum()),
        "etiketli": int(len(ee)), "etiketli_yikik": int(ee.sum()), "auc": round(auc(pe, ee), 3),
        "dogru_isaret": int((tahmin & ee).sum()), "yanlis_alarm": int((tahmin & ~ee).sum()),
        "kacan": int((~tahmin & ee).sum()),
        "model": "ResNet18 ikiz ağ, bina etiketli; Antakya (AOI11) eğitimde hiç yok",
        "oncesi": {"tarih": "2022-12-22", "sinir": goruntu(MAXAR / f"{PARCA}_2022-12-22.tif", CIKTI / "oncesi.jpg")},
        "sonrasi": {"tarih": "2023-02-11", "sinir": goruntu(MAXAR / f"{PARCA}_2023-02-11.tif", CIKTI / "sonrasi.jpg")},
        "kaynak": "Görüntü: Maxar Open Data (CC BY-NC 4.0). Bina: Overture Maps. Gerçek etiket: Copernicus EMSR648 + HOT/OSM.",
    }
    json.dump(ozet, open(CIKTI / "antakya_ozet.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in ozet.items() if k not in ("oncesi", "sonrasi")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
