"""Copernicus blok/nokta etiketlerini bina bazina cevirir (Overture bina sinirlari + OSM yikik bina etiketleri).

Kurallar (her bina Overture taban alani):
- Hasarsiz: Copernicus "No visible damage" blogunun icinde ya da "No visible damage" noktasini iceren bina.
  Hasarsiz blokta hic bina hasarli degildir; blok etiketi her binaya gecerlidir.
- Hasarli: OSM'de destroyed:building isaretli bina (merkezi Overture binasina duser) ya da Copernicus
  Destroyed/Damaged noktasini iceren bina.
- Belirsiz (atlanir): Hasarli blogun icinde olup OSM'de isaretlenmemis bina; blok etiketi hangi binanin
  yikildigini soylemez.
Cikti: data/gercek/bina_etiket/<bolge>.geojson (damage_gra alani hasar_veri ile ayni adlar) + parcalar_bina.json.
  ~/afet-yolo/venv/bin/python -m egitim.bina_etiket
"""
import json
import shutil
import subprocess
from pathlib import Path

import shapely
from shapely.geometry import Point, shape

KOK = Path(__file__).resolve().parent.parent
EMSR = KOK / "data" / "gercek" / "emsr"
CIKTI = KOK / "data" / "gercek" / "bina_etiket"
OSM = KOK / "data" / "gercek" / "hotosm" / "osm_hasar.json"
OVERTURE = shutil.which("overturemaps") or "overturemaps"  # pip install overturemaps
HASARLI = {"Destroyed", "Damaged"}


def overture_binalar(bolge: str, kutu: tuple) -> list:
    yol = CIKTI / f"overture_{bolge}.geojson"
    if not yol.exists():
        b = ",".join(f"{x:.5f}" for x in kutu)
        subprocess.run([OVERTURE, "download", f"--bbox={b}", "-f", "geojson", "--type=building", "-o", str(yol)],
                       check=True, capture_output=True)
    return [shape(f["geometry"]) for f in json.load(open(yol))["features"]
            if f["geometry"]["type"] in ("Polygon", "MultiPolygon")]


def main():
    CIKTI.mkdir(parents=True, exist_ok=True)
    osm = json.load(open(OSM))["elements"]
    yikik = [Point(sum(p["lon"] for p in x["geometry"]) / len(x["geometry"]),
                   sum(p["lat"] for p in x["geometry"]) / len(x["geometry"]))
             for x in osm if x.get("tags", {}).get("destroyed:building") and x.get("geometry")]
    yikik_agac = shapely.STRtree(yikik)
    girdiler = json.load(open(EMSR / "parcalar.json")) + json.load(open(EMSR / "parcalar_antakya.json"))
    yeni = []
    for o in girdiler:
        bolge = o["aoi"]
        etiket = json.load(open(KOK / o["dosya"]))["features"]
        geo = [shape(f["geometry"]) for f in etiket]
        sinif = [f["properties"]["damage_gra"] for f in etiket]
        kutu = shapely.total_bounds(geo)
        binalar = overture_binalar(bolge, tuple(kutu))
        agac = shapely.STRtree(binalar)
        durum = {}  # bina sirasi -> "hasarsiz" | "hasarli" | "belirsiz"
        for g, s in zip(geo, sinif):
            if g.geom_type == "Point":
                aday = [i for i in agac.query(g) if binalar[i].contains(g)]
                if not aday:
                    # Nokta binanin hemen yanina konmus olabilir: 8 m (~8e-5 derece) icindeki en yakin bina.
                    aday = list(agac.query_nearest(g, max_distance=8e-5))
            else:
                # Blok icindeki bina: merkezi blogun icinde olan.
                aday = [i for i in agac.query(g) if g.contains(binalar[i].centroid)]
            for i in aday:
                if s == "No visible damage":
                    durum.setdefault(i, "hasarsiz")
                elif s in HASARLI:
                    # Nokta tek binayi gosterir; blok gostermez.
                    durum[i] = "hasarli" if g.geom_type == "Point" else ("belirsiz" if durum.get(i) != "hasarli" else "hasarli")
                else:
                    durum[i] = "belirsiz" if durum.get(i) != "hasarli" else "hasarli"
        osm_say = 0
        for j in yikik_agac.query(shapely.box(*kutu)):
            p = yikik[j]
            for i in agac.query(p):
                if binalar[i].contains(p):
                    durum[i] = "hasarli"
                    osm_say += 1
        ozellik = []
        for i, d in durum.items():
            if d == "belirsiz":
                continue
            ozellik.append({"type": "Feature", "geometry": shapely.geometry.mapping(binalar[i]),
                            "properties": {"damage_gra": "Destroyed" if d == "hasarli" else "No visible damage"}})
        yol = CIKTI / f"{bolge}.geojson"
        json.dump({"type": "FeatureCollection", "features": ozellik}, open(yol, "w"))
        say = {k: sum(v == k for v in durum.values()) for k in ("hasarli", "hasarsiz", "belirsiz")}
        print(f"{bolge}: Overture {len(binalar)} bina; {say}; OSM yikik eslesen {osm_say}", flush=True)
        yeni.append({**o, "dosya": str(yol.relative_to(KOK))})
    json.dump(yeni, open(EMSR / "parcalar_bina.json", "w"), indent=1)


if __name__ == "__main__":
    main()
