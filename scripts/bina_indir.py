"""Bir bolgedeki binalari OpenStreetMap'ten (Overpass) indirip data/binalar.geojson yazar.

Internet yalnizca bu betik calisirken gerekir. Yukseklik yoksa kat sayisindan, o da yoksa
varsayilan kattan tahmin edilir ve `yukseklik_kaynak` ile isaretlenir.
Veri: (c) OpenStreetMap katkicilari, ODbL.
  python -m scripts.bina_indir --bbox 39.80,34.79,39.83,34.83
"""
import argparse
import json
import urllib.parse
import urllib.request

from server.main import KOK

OVERPASS = "https://overpass-api.de/api/interpreter"
KAT_YUKSEKLIGI_M = 3.0
# Yozgat merkezde konut cogunlukla 4-6 katli; bilgi yoksa 4 kat varsayilir.
VARSAYILAN_KAT = 4


def yukseklik(etiket: dict) -> tuple[float, int | None, str]:
    try:
        return float(etiket["height"].split()[0]), None, "osm_yukseklik"
    except (KeyError, ValueError):
        pass
    try:
        kat = int(float(etiket["building:levels"]))
        return kat * KAT_YUKSEKLIGI_M, kat, "osm_kat"
    except (KeyError, ValueError):
        return VARSAYILAN_KAT * KAT_YUKSEKLIGI_M, VARSAYILAN_KAT, "tahmin"


def main():
    ayrac = argparse.ArgumentParser()
    ayrac.add_argument("--bbox", required=True, help="guney,bati,kuzey,dogu (Overpass sirasi)")
    ayrac.add_argument("--cikti", default=str(KOK / "data" / "binalar.geojson"))
    secim = ayrac.parse_args()
    sorgu = f'[out:json][timeout:90];way["building"]({secim.bbox});out tags geom;'
    istek = urllib.request.Request(OVERPASS, urllib.parse.urlencode({"data": sorgu}).encode(),
                                   headers={"User-Agent": "afet-projesi (universite projesi)"})
    with urllib.request.urlopen(istek, timeout=180) as cevap:
        ogeler = json.load(cevap)["elements"]

    ozellikler = []
    for o in ogeler:
        nokta = [[round(g["lon"], 7), round(g["lat"], 7)] for g in o.get("geometry", [])]
        if len(nokta) < 4 or nokta[0] != nokta[-1]:
            continue
        e = o.get("tags", {})
        boy, kat, kaynak = yukseklik(e)
        adres = " ".join(x for x in (e.get("addr:street"), e.get("addr:housenumber")) if x) or None
        ozellikler.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [nokta]},
                           "properties": {"id": f"w{o['id']}", "yukseklik_m": boy, "kat": kat,
                                          "yukseklik_kaynak": kaynak, "adres": adres, "ad": e.get("name"),
                                          "tur": e.get("building")}})
    with open(secim.cikti, "w") as f:
        json.dump({"type": "FeatureCollection", "kaynak": "OpenStreetMap katkicilari, ODbL",
                   "features": ozellikler}, f, ensure_ascii=False)
    sayi = {k: sum(x["properties"]["yukseklik_kaynak"] == k for x in ozellikler) for k in ("osm_yukseklik", "osm_kat", "tahmin")}
    print(f"{len(ozellikler)} bina yazildi: {secim.cikti}; yukseklik kaynagi {sayi}; "
          f"adresli {sum(bool(x['properties']['adres']) for x in ozellikler)}")


if __name__ == "__main__":
    main()
