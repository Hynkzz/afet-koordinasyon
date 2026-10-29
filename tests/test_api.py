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
