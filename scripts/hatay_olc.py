"""Gercek veride olcum: OSM bina blogu + deprem oncesi/sonrasi uydu goruntusu -> hangi bloklar yikildi.

Direk tespitindeki mantigin aynisi (blok alani icinde oncesi/sonrasi karsilastirma), bu kez gercek
Antakya goruntusunde. Cevap anahtari Copernicus EMSR648 AOI11 (MONIT01) hasar derecelendirmesi.
Esik bati parcasinda secilir, dogu parcasinda test edilir; ayni veride ayar yapilmaz.
Gereken: rasterio (~/afet-yolo/venv). Veri: data/gercek/hatay/ (scripts/README'deki indirme adimlari).
  ~/afet-yolo/venv/bin/python -m scripts.hatay_olc
"""
import argparse
import glob
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom
from rasterio.windows import from_bounds

KOK = Path(__file__).resolve().parent.parent
HATAY = KOK / "data" / "gercek" / "hatay"
POZITIF = {"Destroyed", "Damaged"}
NEGATIF = {"No visible damage"}
EN_AZ_PIKSEL = 60  # ~0,5 m pikselde ~15 m2; daha kucuk blokta istatistik guvenilmez


def kutu(koordinat) -> tuple[float, float, float, float]:
    # Polygon da MultiPolygon da olabilir: ic ice listeler duzlestirilir.
    duz = []
    yigin = [koordinat]
    while yigin:
        k = yigin.pop()
        if isinstance(k[0], (int, float)):
            duz.append(k)
        else:
            yigin.extend(k)
    duz = np.array(duz, dtype=float)
    return duz[:, 0].min(), duz[:, 1].min(), duz[:, 0].max(), duz[:, 1].max()


def gri(rgb: np.ndarray) -> np.ndarray:
    return rgb[:3].astype(np.float32).mean(axis=0)


def egim(g: np.ndarray) -> np.ndarray:
    gy, gx = np.gradient(g)
    return np.hypot(gx, gy)


def ozellikler(once: np.ndarray, sonra: np.ndarray, maske: np.ndarray) -> dict:
    a, b = gri(once)[maske], gri(sonra)[maske]
    # Iki goruntu farkli gun/aci: parlaklik ve kontrast blok icinde esitlenir, kalan fark yapisaldir.
    a = (a - a.mean()) / (a.std() + 1e-3)
    b = (b - b.mean()) / (b.std() + 1e-3)
    ea, eb = egim(gri(once))[maske], egim(gri(sonra))[maske]
    return {
        "fark": float(np.abs(a - b).mean()),
        "korelasyon": float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else 0.0,
        # Enkaz duz cati ve duvar kenarlarini bozar: kenar yogunlugu degisir.
        "kenar_orani": float(np.log((eb.mean() + 1) / (ea.mean() + 1))),
    }


def auc(puan: np.ndarray, etiket: np.ndarray) -> float:
    sira = puan.argsort().argsort() + 1
    p, n = etiket.sum(), (~etiket).sum()
    return float((sira[etiket].sum() - p * (p + 1) / 2) / (p * n))


def main():
    ayrac = argparse.ArgumentParser()
    ayrac.add_argument("--etiket", default=str(next(HATAY.glob("monit/*builtUpA*.json"))))
    secim = ayrac.parse_args()
    bloklar = json.load(open(secim.etiket))["features"]

    satirlar = []
    for once_yol in sorted(glob.glob(str(HATAY / "maxar" / "*_2022-12-22.tif"))):
        parca = Path(once_yol).name.split("_")[0]
        sonra_yol = once_yol.replace("2022-12-22", "2023-02-11")
        with rasterio.open(once_yol) as o, rasterio.open(sonra_yol) as s:
            assert o.crs == s.crs and o.transform == s.transform, "parcalar ayni izgarada degil"
            for f in bloklar:
                sinif = f["properties"]["damage_gra"]
                g = transform_geom("EPSG:4326", o.crs, f["geometry"])
                l, b, r, t = kutu(g["coordinates"])
                if l < o.bounds.left or r > o.bounds.right or b < o.bounds.bottom or t > o.bounds.top:
                    continue
                # Iki goruntu arasinda bakis acisi farki birkac metre kaydirir; pencereye pay birakilir.
                w = from_bounds(l - 2, b - 2, r + 2, t + 2, o.transform).round_offsets().round_lengths()
                a, c = o.read(window=w), s.read(window=w)
                if a.shape != c.shape or a.shape[1] < 4 or a.shape[2] < 4:
                    continue
                maske = geometry_mask([g], out_shape=a.shape[1:], transform=o.window_transform(w), invert=True)
                # Goruntu kenarindaki bos (siyah) alan karsilastirmaya girmesin.
                maske &= (a[:3].sum(axis=0) > 0) & (c[:3].sum(axis=0) > 0)
                if maske.sum() < EN_AZ_PIKSEL:
                    continue
                satirlar.append({"parca": parca, "sinif": sinif, "piksel": int(maske.sum()),
                                 **ozellikler(a, c, maske)})
        print(f"parca {parca}: toplam {len(satirlar)} blok")

    json.dump(satirlar, open(HATAY / "olcum_bloklar.json", "w"))
    parcalar = sorted({x["parca"] for x in satirlar})
    egitim, test = parcalar[0], parcalar[-1]
    print(f"\nesik secimi: parca {egitim}; test: parca {test}")
    for sinif in ["Destroyed", "Damaged", "Possibly damaged", "No visible damage"]:
        print(f"  {sinif}: " + ", ".join(f"{p} {sum(x['sinif'] == sinif and x['parca'] == p for x in satirlar)}" for p in parcalar))

    for ozellik, yon in [("fark", 1), ("korelasyon", -1), ("kenar_orani", 1)]:
        def veri(p):
            r = [x for x in satirlar if x["parca"] == p and x["sinif"] in POZITIF | NEGATIF]
            return np.array([yon * x[ozellik] for x in r]), np.array([x["sinif"] in POZITIF for x in r])
        pe, ee = veri(egitim)
        pt, et = veri(test)
        # Esik: egitim parcasinda F1'i en yuksek yapan deger.
        adaylar = np.quantile(pe, np.linspace(0.5, 0.995, 200))
        f1 = [2 * (ee & (pe >= e)).sum() / max(ee.sum() + (pe >= e).sum(), 1) for e in adaylar]
        esik = adaylar[int(np.argmax(f1))]
        tahmin = pt >= esik
        dp = (tahmin & et).sum()
        print(f"\n{ozellik}: AUC egitim {auc(pe, ee):.3f}, test {auc(pt, et):.3f}")
        print(f"  test (esik egitimden): duyarlilik {dp}/{et.sum()} (%{100 * dp / max(et.sum(), 1):.1f}), "
              f"kesinlik {dp}/{tahmin.sum()} (%{100 * dp / max(tahmin.sum(), 1):.1f}), "
              f"yanlis alarm {(tahmin & ~et).sum()}/{(~et).sum()} (%{100 * (tahmin & ~et).sum() / max((~et).sum(), 1):.1f})")
        for sinif in ["Destroyed", "Damaged", "Possibly damaged"]:
            r = np.array([yon * x[ozellik] for x in satirlar if x["parca"] == test and x["sinif"] == sinif])
            if len(r):
                print(f"  test {sinif}: {(r >= esik).sum()}/{len(r)} isaretlendi")


if __name__ == "__main__":
    main()
