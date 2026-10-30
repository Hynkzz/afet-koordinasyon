import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.main import app
from server.models import BinaOlayi, Binalar

KOK = Path(__file__).resolve().parent.parent


@pytest.fixture
def istemci(monkeypatch):
    monkeypatch.setenv("AFET_PSK", base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("AFET_KAYNAK", "yok")
    with TestClient(app) as istemci:
        yield istemci


def olay(bina_id, durum="yikik"):
    return {"bina_id": bina_id, "durum": durum, "guven": 0.87, "gorunurluk": 0.7,
            "kaynak": "direk1", "zaman": datetime.now(timezone.utc).isoformat()}


def kuyruk(istemci):
    return istemci.get("/api/kuyruk").json()["kuyruk"]


def binalar(istemci):
    return istemci.get("/api/binalar").json()["features"]


def merkez(f):
    kose = f["geometry"]["coordinates"][0]
    return {"lat": sum(k[1] for k in kose) / len(kose), "lon": sum(k[0] for k in kose) / len(kose)}


def test_binalar_feature_collection_donner(istemci):
    veri = istemci.get("/api/binalar").json()
    assert veri["type"] == "FeatureCollection"
    assert len(veri["features"]) > 0  # su an ~316 bina
    p = veri["features"][0]["properties"]
    assert p["id"] and p["yukseklik_m"] > 0


def test_bilinmeyen_bina_404(istemci):
    assert istemci.post("/api/bina", json=olay("yok")).status_code == 404


def test_gecersiz_durum_422(istemci):
    id = binalar(istemci)[0]["properties"]["id"]
    assert istemci.post("/api/bina", json=olay(id, "az_hasarli")).status_code == 422


def test_yikik_olay_oncelik_1_vaka_acar_merkezde(istemci):
    f = binalar(istemci)[0]
    id = f["properties"]["id"]
    istemci.post("/api/bina", json=olay(id))
    vaka = kuyruk(istemci)[0]
    assert (vaka["id"], vaka["kaynak"], vaka["oncelik"]) == ("bina-" + id, "bina", 1)
    assert vaka["konum"] == merkez(f)
    assert vaka["veri"]["merkez"] == merkez(f)
    assert vaka["veri"]["adres"] == f["properties"]["adres"]


def test_ayni_binanin_ikinci_olayi_ayni_vakayi_gunceller(istemci):
    id = binalar(istemci)[0]["properties"]["id"]
    istemci.post("/api/bina", json=olay(id))
    istemci.post(f"/api/vaka/bina-{id}/durum", json={"durum": "ekip_yonlendirildi"})
    istemci.post("/api/bina", json=olay(id, "hasarli"))
    vakalar = kuyruk(istemci)
    assert [v["id"] for v in vakalar] == ["bina-" + id]
    assert vakalar[0]["durum"] == "ekip_yonlendirildi"


def test_normal_olay_vaka_acmaz_bina_yayinlar(istemci):
    id = binalar(istemci)[0]["properties"]["id"]
    with istemci.websocket_connect("/ws") as ws:
        cevap = istemci.post("/api/bina", json=olay(id, "normal"))
        paket = ws.receive_json()
    assert cevap.status_code == 200
    assert kuyruk(istemci) == []
    assert paket["tip"] == "bina"
    assert (paket["veri"]["bina_id"], paket["veri"]["durum"]) == (id, "normal")


@pytest.mark.parametrize("dosya, model", [("bina", Binalar), ("bina_olayi", BinaOlayi)])
def test_sema_ornekleri_modele_uyar(dosya, model):
    for ornek in json.loads((KOK / "shared" / f"{dosya}.schema.json").read_text())["examples"]:
        model.model_validate(ornek)


def test_bina_dosyasi_semaya_uyar():
    Binalar.model_validate_json((KOK / "data" / "binalar.geojson").read_text())