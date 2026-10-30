"""scripts.direk_yerlesim hesaplari: gorunurluk, menzil ve acgozlu secim."""
import json
import math

from scripts.direk_yerlesim import acgozlu, nokta_bilgi, nokta_hesapla


def bina(kimlik, lat, lon, yarim_m=10.0, yukseklik_m=12.0):
    dlat = yarim_m / 111_320
    dlon = yarim_m / (111_320 * math.cos(math.radians(lat)))
    halka = [[lon - dlon, lat - dlat], [lon + dlon, lat - dlat], [lon + dlon, lat + dlat],
             [lon - dlon, lat + dlat], [lon - dlon, lat - dlat]]
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [halka]},
            "properties": {"id": kimlik, "yukseklik_m": yukseklik_m}}


def yaz(tmp_path, binalar):
    # Elle kurulmus binalar dosyadan okunur; gercek akisla ayni olsun.
    yol = tmp_path / "binalar.geojson"
    yol.write_text(json.dumps({"type": "FeatureCollection", "features": binalar}),
                   encoding="utf-8")
    return json.loads(yol.read_text(encoding="utf-8"))


def test_yakin_noktada_bina_gorunur(tmp_path):
    binalar = yaz(tmp_path, [bina("b1", 39.8000, 34.8000), bina("b2", 39.8002, 34.8004),
                             bina("b3", 39.7999, 34.8006)])
    kume = nokta_hesapla(binalar, 39.7993, 34.8003)
    assert "b1" in kume
    assert len(kume) > 0


def test_menzil_disinda_bina_gorunmez(tmp_path):
    binalar = yaz(tmp_path, [bina("b1", 39.8000, 34.8000), bina("b2", 39.8002, 34.8004)])
    assert nokta_hesapla(binalar, 39.7500, 34.7500) == set()
    assert nokta_bilgi(binalar, 39.7500, 34.7500)["menzildeki"] == 0


def test_catida_hesap_devam_eder(tmp_path):
    binalar = yaz(tmp_path, [bina("b1", 39.8000, 34.8000), bina("b2", 39.8002, 34.8004)])
    bilgi = nokta_bilgi(binalar, 39.8000, 34.8000)  # b1 icinde
    assert bilgi["cati_ustu"] is True
    assert "b1" not in bilgi["gorunen"]
    assert "b2" in bilgi["gorunen"]


def test_acgozlu_kumulatif_azalmaz():
    kumeler = {0: {"a", "b", "c"}, 1: {"b", "c"}, 2: {"d", "e"}, 3: {"e"}}
    secim = acgozlu(kumeler, 2)
    assert secim == [0, 2]  # ikinci adimda en cok yeni binayi 2 ekler
    bir = kumeler[secim[0]]
    iki = bir | kumeler[secim[1]]
    assert len(iki) >= len(bir)