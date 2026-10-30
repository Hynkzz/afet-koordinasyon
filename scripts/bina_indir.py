"""Bir bolgedeki binalari OpenStreetMap'ten (Overpass) indirip data/binalar.geojson yazar.

Internet yalnizca bu betik calisirken gerekir. Yukseklik yoksa kat sayisindan, o da yoksa
varsayilan kattan tahmin edilir ve `yukseklik_kaynak` ile isaretlenir.
Veri: (c) OpenStreetMap katkicilari, ODbL.
  python -m scripts.bina_indir --bbox 39.80,34.79,39.83,34.83

OSM'de Yozgat binalarinin cogu eksik. Overture Maps, OSM'yi Microsoft'un uydu goruntusunden
cikardigi bina sinirlariyla (CDLA Permissive 2.0) birlestirir. Dosya ayrica indirilir:
  overturemaps download --bbox=34.79,39.80,34.83,39.83 -f geojson --type=building -o overture.geojson
  python -m scripts.bina_indir --overture overture.geojson --osm data/binalar.geojson
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


def overture_donustur(overture: dict, osm: dict | None) -> dict:
    # Adres yalnizca OSM'de var; ayni bina OSM kimligiyle eslestirilip oradan alinir.
    osm_ozellik = {f["properties"]["id"]: f["properties"] for f in (osm or {"features": []})["features"]}
    ozellikler = []
    for sira, f in enumerate(overture["features"]):
        e = f["properties"]
        kaynak = (e.get("sources") or [{}])[0]
        if kaynak.get("dataset") == "OpenStreetMap":
            kimlik, veri = kaynak["record_id"].split("@")[0], "osm"
        else:
            kimlik, veri = "m" + (str(f.get("id") or sira).replace("-", "")[:12]), "microsoft"
        if e.get("height"):
            boy, kat, ykaynak = float(e["height"]), e.get("num_floors"), "overture_yukseklik"
        elif e.get("num_floors"):
            boy, kat, ykaynak = e["num_floors"] * KAT_YUKSEKLIGI_M, e["num_floors"], "overture_kat"
        else:
            boy, kat, ykaynak = VARSAYILAN_KAT * KAT_YUKSEKLIGI_M, VARSAYILAN_KAT, "tahmin"
        o = osm_ozellik.get(kimlik, {})
        halka = [[round(x, 7), round(y, 7)] for x, y in f["geometry"]["coordinates"][0]]
        ozellikler.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [halka]},
                           "properties": {"id": kimlik, "yukseklik_m": boy, "kat": kat, "yukseklik_kaynak": ykaynak,
                                          "adres": o.get("adres"), "ad": (e.get("names") or {}).get("primary") or o.get("ad"),
                                          "tur": e.get("class") or e.get("subtype"), "kaynak_veri": veri}})
    return {"type": "FeatureCollection",
            "kaynak": "Overture Maps (OpenStreetMap ODbL + Microsoft ML Buildings CDLA Permissive 2.0)",
            "features": ozellikler}


def main():
    ayrac = argparse.ArgumentParser()
    ayrac.add_argument("--bbox", help="guney,bati,kuzey,dogu (Overpass sirasi)")
    ayrac.add_argument("--overture", help="Overture bina GeoJSON'u; verilirse Overpass'a gidilmez")
    ayrac.add_argument("--osm", help="adres ve ad icin onceki OSM binalar.geojson")
    ayrac.add_argument("--cikti", default=str(KOK / "data" / "binalar.geojson"))
    secim = ayrac.parse_args()
    if secim.overture:
        with open(secim.overture) as f:
            overture = json.load(f)
        osm = None
        if secim.osm:
            with open(secim.osm) as f:
                osm = json.load(f)
        sonuc = overture_donustur(overture, osm)
        with open(secim.cikti, "w") as f:
            json.dump(sonuc, f, ensure_ascii=False)
        o = [x["properties"] for x in sonuc["features"]]
        print(f"{len(o)} bina yazildi: {secim.cikti}; osm {sum(x['kaynak_veri'] == 'osm' for x in o)}, "
              f"microsoft {sum(x['kaynak_veri'] == 'microsoft' for x in o)}; adresli {sum(bool(x['adres']) for x in o)}; "
              f"yukseklik tahmin {sum(x['yukseklik_kaynak'] == 'tahmin' for x in o)}")
        return
    if not secim.bbox:
        ayrac.error("--bbox ya da --overture gerekli")
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
