import base64
import json
import os

import msgpack
import pytest
from fastapi.testclient import TestClient

from server import kanal
from server.crypto import Sifreleyici
from server.main import app
from server.models import Taslak


def paket(yuk="Enkaz altindayim"):
    s = Sifreleyici(os.urandom(32))
    return s.sifrele(Taslak(id="d3-1", tur="SOS", kaynak="d3", hedef="merkez", ttl=5, yuk=yuk,
                            gps={"lat": 39.8181, "lon": 34.808}, sayac=1))


def test_msgpack_jsondan_kucuk_ve_geri_acilir():
    p = paket()
    veri = kanal.kodla(p)
    assert len(veri) < len(p.model_dump_json())
    acilmis = msgpack.unpackb(veri)
    assert acilmis["id"] == "d3-1"
    assert acilmis["imza"] == base64.b64decode(p.imza)


def test_ilk_acik_ve_sigan_kanal_secilir():
    sonuc = kanal.Kanallar().gonder(paket())
    assert sonuc["kanal"] == "BLE"
    assert sonuc["boyut"] < sonuc["json_boyut"]


def test_cokuk_kanal_atlanir():
    k = kanal.Kanallar()
    k.ayarla("BLE", False)
    sonuc = k.gonder(paket())
    assert sonuc["kanal"] == "LoRa"
    assert sonuc["denenen"][0] == "BLE: çökük"


def test_loraya_sigmayan_uyduya_gider():
    k = kanal.Kanallar()
    k.ayarla("BLE", False)
    sonuc = k.gonder(paket("x" * 190))
    assert sonuc["boyut"] > kanal.KANALLAR["LoRa"]
    assert sonuc["kanal"] == "Uydu"


def test_hepsi_cokukse_gonderilemez():
    k = kanal.Kanallar()
    for ad in kanal.KANALLAR:
        k.ayarla(ad, False)
    assert k.gonder(paket())["kanal"] is None


def test_bilinmeyen_kanal():
    with pytest.raises(KeyError):
        kanal.Kanallar().ayarla("WiFi", False)


@pytest.fixture
def istemci(monkeypatch):
    monkeypatch.setenv("AFET_PSK", base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("AFET_KAYNAK", "yok")
    with TestClient(app) as istemci:
        yield istemci


def test_mesaj_iletim_bilgisiyle_yayinlanir(istemci):
    with istemci.websocket_connect("/ws") as ws:
        istemci.post("/api/mesaj", json={"tur": "SOS", "yuk": "Yardim"})
        veri = ws.receive_json()["veri"]
    assert veri["iletim"]["kanal"] == "BLE"
    assert veri["iletim"]["boyut"] > 0


def test_panelden_kanal_cokertilir_ve_yayinlanir(istemci):
    with istemci.websocket_connect("/ws") as ws:
        assert istemci.post("/api/kanal/BLE", json={"acik": False}).status_code == 200
        paket_ = ws.receive_json()
    assert paket_["tip"] == "kanallar"
    assert [k["acik"] for k in paket_["veri"]["kanallar"]] == [False, True, True]
    assert istemci.post("/api/mesaj", json={"tur": "SOS", "yuk": "Yardim"}).json()["iletim"]["kanal"] == "LoRa"
    assert istemci.post("/api/kanal/WiFi", json={"acik": False}).status_code == 404


def test_portal_kaydi_iletilir(istemci):
    kod = istemci.post("/portal/cagri", data={"durum": "enkaz"}, follow_redirects=False).headers["location"].split("/")[-1]
    from server.main import portal
    iletim = portal.kayitlar[kod]["iletim"]
    assert iletim["kanal"] == "BLE"
    assert json.dumps(iletim)


def test_uzun_portal_mesaji_uyduya_sigacak_kadar_kirpilir(istemci):
    from server.main import kanallar, portal_ilet
    import asyncio

    kanallar.ayarla("BLE", False)
    kanallar.ayarla("LoRa", False)
    uzun = "Babamın bacağı kırık, yürüyemiyor; merdivenden inemiyoruz, çok acil. " * 3
    iletim = asyncio.run(portal_ilet("SOS", uzun[:200], {"lat": 39.8, "lon": 34.8}))
    assert iletim["kanal"] == "Uydu"
    assert iletim["kirpildi"] is True
    assert iletim["boyut"] <= kanal.KANALLAR["Uydu"]


def test_kisa_mesaj_kirpilmaz(istemci):
    from server.main import portal_ilet
    import asyncio

    iletim = asyncio.run(portal_ilet("SOS", "ABC-DEF; Enkaz altındayım; O1", None))
    assert "kirpildi" not in iletim
