"""Bir bolgeye izgara uzerine sanal direkler koyup her noktadan gorulen bina sayisini hesaplar.

Her izgara noktasi cikti GeoJSON'inda bir Point feature'dir: gorunen_bina, menzildeki_bina,
cati_ustu. Alici kamerasi icin en cok binayi kapsayan N nokta acgozlu secilir ve
secim_sirasi ile isaretlenir. Hesap direk.geometri uzerinden yapilir; piksel esigi
EN_AZ_PIKSEL_YERLESIM'dir.
  python -m scripts.direk_yerlesim --adim-m 100 --en-iyi 5
"""
import argparse
import json
import math
import time

import numpy as np

from direk.geometri import Direk, gor, prizmalar
from server.main import KOK

# Hiz icin kucuk cozunurluk: 720x180, 2048x512'ye gore her eksende ~2.8 kat kucuk,
# iki eksende alan ~8 kat az; tespit'teki 200 pikselin ~1/16'si = 12 piksel esik.
GENISLIK, YUKSEKLIK = 720, 180
EN_AZ_PIKSEL_YERLESIM = 12
ADIM_M, DIREK_M, MENZIL_M = 50.0, 25.0, 250.0
EN_IYI = 5


def nokta_bilgi(binalar: dict, lat: float, lon: float, direk_m: float = DIREK_M,
                menzil_m: float = MENZIL_M, genislik: int = GENISLIK,
                yukseklik: int = YUKSEKLIK) -> dict:
    """Gorunen bina kimlikleri, menzildeki bina sayisi ve cati ustu bilgisi."""
    direk = Direk(lat=lat, lon=lon, yukseklik_m=direk_m, genislik=genislik,
                  yukseklik=yukseklik, menzil_m=menzil_m)
    liste = prizmalar(binalar, direk)
    gorus = gor(direk, liste)
    sayi = np.bincount(gorus.etiket[gorus.etiket >= 0], minlength=len(gorus.kimlikler))
    gorunen = {k for s, k in enumerate(gorus.kimlikler) if sayi[s] >= EN_AZ_PIKSEL_YERLESIM}
    # Direk catinin ustuysa prizmalar o binayi atar; sinirsiz menzil onu bulur, sayim disi kalir.
    cati = {f["properties"]["id"] for f in binalar["features"]} - {
        p.kimlik for p in prizmalar(binalar, Direk(lat=lat, lon=lon, yukseklik_m=direk_m,
                                                   menzil_m=math.inf))}
    return {"gorunen": gorunen, "menzildeki": len(liste) + len(cati), "cati_ustu": bool(cati)}


def nokta_hesapla(binalar: dict, lat: float, lon: float, direk_m: float = DIREK_M,
                  menzil_m: float = MENZIL_M, genislik: int = GENISLIK,
                  yukseklik: int = YUKSEKLIK) -> set[str]:
    """Noktadan gorulen (EN_AZ_PIKSEL_YERLESIM'i gecen) bina kimlikleri."""
    return nokta_bilgi(binalar, lat, lon, direk_m, menzil_m, genislik, yukseklik)["gorunen"]


def acgozlu(kumeler: dict[int, set[str]], n: int) -> list[int]:
    """Nokta sirasi -> gorulen binalar; her adimda en cok YENI bina ekleyen noktayi secer."""
    secim, kapali, kalan = [], set(), dict(kumeler)
    for _ in range(min(n, len(kalan))):
        en_iyi = max(kalan, key=lambda s: len(kumeler[s] - kapali))
        kapali |= kumeler[en_iyi]
        secim.append(en_iyi)
        del kalan[en_iyi]
    return secim


def sinir_kutu(binalar: dict) -> tuple[float, float, float, float]:
    """Bina koselerinden bati, guney, dogu, kuzey."""
    nokta = [p for f in binalar["features"] for p in f["geometry"]["coordinates"][0]]
    boylam = [p[0] for p in nokta]
    enlem = [p[1] for p in nokta]
    return min(boylam), min(enlem), max(boylam), max(enlem)


def izgara(bbox: tuple[float, float, float, float], adim_m: float) -> list[tuple[float, float]]:
    """(lat, lon) noktalari; metre adimi bolgenin enlemine gore dereceye cevrilir."""
    bati, guney, dogu, kuzey = bbox
    enlem = adim_m / 111_320
    boylam = adim_m / (111_320 * math.cos(math.radians((guney + kuzey) / 2)))
    lats = np.arange(guney, kuzey + enlem / 2, enlem)
    lons = np.arange(bati, dogu + boylam / 2, boylam)
    return [(round(float(la), 7), round(float(lo), 7)) for la in lats for lo in lons]


def main():
    ayrac = argparse.ArgumentParser()
    ayrac.add_argument("--binalar", default=str(KOK / "data" / "binalar.geojson"))
    ayrac.add_argument("--adim-m", type=float, default=ADIM_M, help="izgara adimi (metre)")
    ayrac.add_argument("--direk-m", type=float, default=DIREK_M, help="kamera yuksekligi (metre)")
    ayrac.add_argument("--menzil-m", type=float, default=MENZIL_M)
    ayrac.add_argument("--bbox", help="bati,guney,dogu,kuzey; varsayilan binalarin sinir kutusu")
    ayrac.add_argument("--cikti", default=str(KOK / "data" / "direk_yerlesim.geojson"))
    ayrac.add_argument("--en-iyi", type=int, default=EN_IYI, help="acgozlu secilecek nokta sayisi")
    secim = ayrac.parse_args()

    basla = time.perf_counter()
    with open(secim.binalar) as f:
        binalar = json.load(f)
    bbox = tuple(float(x) for x in secim.bbox.split(",")) if secim.bbox else sinir_kutu(binalar)
    toplam_bina = len(binalar["features"])
    noktalar = izgara(bbox, secim.adim_m)
    print(f"{toplam_bina} bina, {len(noktalar)} izgara noktasi, adim {secim.adim_m} m")

    kumeler, bilgiler = {}, []
    for i, (lat, lon) in enumerate(noktalar):
        b = nokta_bilgi(binalar, lat, lon, secim.direk_m, secim.menzil_m)
        kumeler[i] = b["gorunen"]
        bilgiler.append({"gorunen_bina": len(b["gorunen"]), "menzildeki_bina": b["menzildeki"],
                         "cati_ustu": b["cati_ustu"]})
        if (i + 1) * 10 // len(noktalar) > i * 10 // len(noktalar):
            print(f"ilerleme %{(i + 1) * 100 // len(noktalar)} ({i + 1}/{len(noktalar)} nokta)")

    kapali = set()
    for sira, i in enumerate(acgozlu(kumeler, secim.en_iyi), 1):
        yeni = len(kumeler[i] - kapali)
        kapali |= kumeler[i]
        lat, lon = noktalar[i]
        bilgiler[i]["secim_sirasi"] = sira
        # Oran: acgozlu kac bina kapsiyor, hepsi gorulebilir olsaydi kac olurdu.
        oran = 100 * len(kapali) / toplam_bina if toplam_bina else 0
        print(f"secim {sira}: {lat:.5f}, {lon:.5f} yeni {yeni}; "
              f"kumulatif {len(kapali)}/{toplam_bina} (%{oran:.1f})")

    ozellikler = []
    for (lat, lon), b in zip(noktalar, bilgiler):
        ozellikler.append({"type": "Feature", "geometry": {"type": "Point",
                                                           "coordinates": [lon, lat]},
                           "properties": b})
    with open(secim.cikti, "w") as f:
        json.dump({"type": "FeatureCollection",
                   "parametreler": {"binalar": secim.binalar, "adim_m": secim.adim_m,
                                    "direk_m": secim.direk_m, "menzil_m": secim.menzil_m,
                                    "bbox": list(bbox), "en_iyi": secim.en_iyi,
                                    "genislik": GENISLIK, "yukseklik": YUKSEKLIK,
                                    "en_az_piksel": EN_AZ_PIKSEL_YERLESIM},
                   "features": ozellikler}, f, ensure_ascii=False)

    sirali = sorted(range(len(bilgiler)), key=lambda i: -bilgiler[i]["gorunen_bina"])[:10]
    print("en iyi 10 nokta (lat, lon, gorunen_bina):")
    for i in sirali:
        lat, lon = noktalar[i]
        print(f"  {lat:.5f}, {lon:.5f}, {bilgiler[i]['gorunen_bina']}")
    print(f"toplam sure: {time.perf_counter() - basla:.1f} sn; yazildi: {secim.cikti}")


if __name__ == "__main__":
    main()