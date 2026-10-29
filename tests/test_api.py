import base64
import os

import pytest
from fastapi.testclient import TestClient

from server.main import app

OLAY = {"olay_id": "api-1", "kaynak": "mikrofon", "etiket": "vurus", "guven": 0.6,
        "zaman": "2026-10-29T14:00:00+03:00"}


@pytest.fixture
def istemci(monkeypatch):
    monkeypatch.setenv("AFET_PSK", base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("AFET_KAYNAK", "yok")
    with TestClient(app) as istemci:
        yield istemci


def test_siginaklar(istemci):
    cevap = istemci.get("/api/siginaklar")
    assert cevap.status_code == 200
    assert cevap.json()["type"] == "FeatureCollection"


def test_olay_websocket_ile_yayinlanir(istemci):
    with istemci.websocket_connect("/ws") as ws:
        assert istemci.post("/api/olay", json=OLAY).status_code == 200
        paket = ws.receive_json()
    assert paket["tip"] == "olay"
    assert paket["veri"]["olay_id"] == "api-1"


def test_hatali_olay_422_doner(istemci):
    cevap = istemci.post("/api/olay", json=OLAY | {"guven": 3})
    assert cevap.status_code == 422


def test_mesaj_gonderilir_ve_yayinlanir(istemci):
    with istemci.websocket_connect("/ws") as ws:
        cevap = istemci.post("/api/mesaj", json={"tur": "SOS", "yuk": "Yardim"})
        paket = ws.receive_json()
    assert cevap.status_code == 200
    assert paket["tip"] == "mesaj"
    assert paket["veri"]["tur"] == "SOS"
    assert paket["veri"]["imza"] == cevap.json()["imza"]


def test_arayuz_ack_gonderemez(istemci):
    assert istemci.post("/api/mesaj", json={"tur": "ack", "yuk": "x"}).status_code == 422


def test_durum_raporu_ozeti():
    from server.main import Yayinci

    y = Yayinci()
    y.kaydet("olay", OLAY)
    y.kaydet("olay", OLAY | {"adet": 2})
    y.kaydet("mesaj", {"id": "d1-1", "tur": "SOS"})
    y.kaydet("portal", {"kod": "AAA-AAA", "tur": "SOS", "asilsiz": False, "triyaj": {"oncelik": 1}})
    y.kaydet("portal", {"kod": "CCC-CCC", "tur": "SOS", "asilsiz": True, "triyaj": {"oncelik": 1}})
    y.kaydet("sinyal", {"dugum_id": "d4", "rssi": -90, "paket_alim_orani": 0.95})
    y.kaydet("sinyal", {"dugum_id": "d5", "rssi": -60, "paket_alim_orani": 0.97})
    ozet = y.ozet()
    assert (ozet["vurus"], ozet["sos"], ozet["portal"], ozet["oncelik1"]) == (1, 2, 1, 1)
    assert ozet["zayif_dugum"] == ["d4"]


def test_gecmis_son_yayinlari_ve_portal_kayitlarini_verir(istemci):
    istemci.post("/api/olay", json=OLAY)
    istemci.post("/api/mesaj", json={"tur": "SOS", "yuk": "Yardim"})
    istemci.post("/portal/cagri", data={"durum": "enkaz"})
    paketler = istemci.get("/api/gecmis").json()
    tipler = [p["tip"] for p in paketler]
    assert tipler[-1] == "portal" and "olay" in tipler and "mesaj" in tipler
    assert all("alindi" in p for p in paketler if p["tip"] == "mesaj")
    assert "cihaz" not in paketler[-1]["veri"]


def test_kamera_karesi_yayinlanir_ve_saklanmaz(istemci):
    kare = {"jpeg": "AAAA", "kutular": [{"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4, "guven": 0.9}], "kaynak": "v.webm"}
    with istemci.websocket_connect("/ws") as ws:
        assert istemci.post("/api/kamera/kare", json=kare).status_code == 200
        paket = ws.receive_json()
    assert paket["tip"] == "kare" and paket["veri"]["kutular"][0]["guven"] == 0.9
    assert all(p["tip"] != "kare" for p in istemci.get("/api/gecmis").json())


def test_cok_buyuk_kare_reddedilir(istemci):
    kare = {"jpeg": "A" * 600_001, "kutular": [], "kaynak": "v"}
    assert istemci.post("/api/kamera/kare", json=kare).status_code == 422
