from scripts.bina_indir import overture_donustur

KARE = {"type": "Polygon", "coordinates": [[[34.8, 39.8], [34.8001, 39.8], [34.8001, 39.8001], [34.8, 39.8]]]}


def ozellik(**e):
    return {"type": "Feature", "id": "08b1-2345-6789-abcd", "geometry": KARE, "properties": e}


def test_osm_kaynakli_bina_adresini_osmden_alir():
    overture = {"features": [ozellik(sources=[{"dataset": "OpenStreetMap", "record_id": "w11@3"}], names={"primary": "Cami"})]}
    osm = {"features": [{"properties": {"id": "w11", "adres": "Atatürk Cad. 5", "ad": None}}]}
    p = overture_donustur(overture, osm)["features"][0]["properties"]
    assert (p["id"], p["adres"], p["ad"], p["kaynak_veri"]) == ("w11", "Atatürk Cad. 5", "Cami", "osm")
    assert p["yukseklik_kaynak"] == "tahmin"


def test_yukseklik_once_height_sonra_kat():
    overture = {"features": [ozellik(sources=[{"dataset": "Microsoft ML Buildings"}], height=10),
                             ozellik(sources=[{"dataset": "Microsoft ML Buildings"}], num_floors=2)]}
    a, b = (f["properties"] for f in overture_donustur(overture, None)["features"])
    assert (a["yukseklik_m"], a["yukseklik_kaynak"], a["kaynak_veri"]) == (10.0, "overture_yukseklik", "microsoft")
    assert (b["yukseklik_m"], b["kat"], b["yukseklik_kaynak"]) == (6.0, 2, "overture_kat")
    assert a["id"].startswith("m") and a["adres"] is None
