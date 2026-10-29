import base64
import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from server import main, senaryo
from server.main import app

KOK = Path(__file__).resolve().parent.parent

KISA = {
    "ad": "Kisa deneme",
    "adimlar": [
        {"t": 0, "not": "vurus", "is": {"tip": "olay", "kaynak": "mikrofon", "etiket": "vurus", "guven": 0.7, "tekrar": 2, "aralik": 0.01}},
        {"t": 0.02, "is": {"tip": "mesaj", "dugum": "d3", "tur": "SOS", "yuk": "Enkaz altindayim"}},
        {"t": 0.03, "is": {"tip": "portal", "durum": "yarali", "kisi": "1", "mesaj": "Bacagi kirik"}},
        {"t": 0.04, "not": "BLE coktu", "is": {"tip": "kanal", "ad": "BLE", "acik": False}},
    ],
}


def test_ornek_senaryolar_gecerli():
    liste = senaryo.listele(KOK / "scenarios")
    assert liste and all(s["adim"] > 0 for s in liste)


def test_ornek_senaryo_semaya_uyar():
    sema = json.loads((KOK / "shared" / "senaryo.schema.json").read_text())
    for ornek in sema["examples"]:
        senaryo.Senaryo.model_validate(ornek)


def test_sure_tekrarlari_hesaba_katar():
    assert senaryo.Senaryo.model_validate(KISA).sure == pytest.approx(0.04)
    s = senaryo.Senaryo.model_validate({"ad": "x", "adimlar": [
        {"t": 5, "is": {"tip": "olay", "kaynak": "kamera", "etiket": "insan", "guven": 0.5, "tekrar": 11, "aralik": 2}}]})
    assert s.sure == 25


@pytest.mark.parametrize("bozuk", [
    {"ad": "x", "adimlar": []},
    {"ad": "x", "adimlar": [{"t": 0, "is": {"tip": "patlama"}}]},
    {"ad": "x", "adimlar": [{"t": -1, "is": {"tip": "kanal", "ad": "BLE", "acik": False}}]},
    {"ad": "x", "adimlar": [{"t": 0, "is": {"tip": "kanal", "ad": "WiFi", "acik": False}}]},
    {"ad": "x", "adimlar": [{"t": 0, "is": {"tip": "olay", "kaynak": "kamera", "etiket": "insan", "guven": 2}}]},
])
def test_bozuk_senaryo_reddedilir(bozuk):
    with pytest.raises(ValidationError):
        senaryo.Senaryo.model_validate(bozuk)


@pytest.fixture
def istemci(monkeypatch, tmp_path):
    monkeypatch.setenv("AFET_PSK", base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("AFET_KAYNAK", "yok")
    (tmp_path / "kisa.json").write_text(json.dumps(KISA))
    monkeypatch.setattr(main, "SENARYO_DIZINI", tmp_path)
    with TestClient(app) as istemci:
        yield istemci


def bekle_bitsin(istemci, sinir=5.0):
    bitis = time.time() + sinir
    while time.time() < bitis:
        if istemci.get("/api/senaryolar").json()["durum"].get("durum") in ("bitti", "durduruldu"):
            return
        time.sleep(0.05)
    raise AssertionError("senaryo bitmedi")


def test_senaryo_oynar_ve_normal_yollardan_gecer(istemci):
    assert istemci.post("/api/senaryo/baslat", json={"dosya": "kisa.json"}).status_code == 200
    bekle_bitsin(istemci)
    kuyruk = istemci.get("/api/kuyruk").json()["kuyruk"]
    assert sorted(v["kaynak"] for v in kuyruk) == ["mesaj", "olay", "portal"]
    olay = next(v for v in kuyruk if v["kaynak"] == "olay")
    assert olay["veri"]["tespit"] == 2
    assert [k["acik"] for k in istemci.get("/api/kanallar").json()] == [False, True, True]
    durum = istemci.get("/api/senaryolar").json()["durum"]
    assert (durum["adim"], durum["toplam"], durum["not_"]) == (5, 5, "BLE coktu")


def test_baslarken_kanallar_acilir_ve_temizle_eski_vakalari_siler(istemci):
    istemci.post("/api/kanal/Uydu", json={"acik": False})
    istemci.post("/portal/cagri", data={"durum": "enkaz"})
    assert len(istemci.get("/api/kuyruk").json()["kuyruk"]) == 1
    with istemci.websocket_connect("/ws") as ws:
        istemci.post("/api/senaryo/baslat", json={"dosya": "kisa.json", "temizle": True})
        assert ws.receive_json()["tip"] == "sifirla"
    bekle_bitsin(istemci)
    kuyruk = istemci.get("/api/kuyruk").json()["kuyruk"]
    assert len(kuyruk) == 3
    assert istemci.get("/api/kanallar").json()[2]["acik"] is True


def test_calisirken_ikinci_baslatma_409_ve_durdurma(istemci, tmp_path):
    uzun = {"ad": "uzun", "adimlar": [{"t": 30, "is": {"tip": "kanal", "ad": "BLE", "acik": False}}]}
    (tmp_path / "uzun.json").write_text(json.dumps(uzun))
    assert istemci.post("/api/senaryo/baslat", json={"dosya": "uzun.json"}).status_code == 200
    assert istemci.post("/api/senaryo/baslat", json={"dosya": "kisa.json"}).status_code == 409
    istemci.post("/api/senaryo/durdur")
    bekle_bitsin(istemci)
    assert istemci.get("/api/senaryolar").json()["durum"]["durum"] == "durduruldu"
    assert istemci.get("/api/kanallar").json()[0]["acik"] is True


@pytest.mark.parametrize("dosya", ["../.env", "/etc/passwd", "yok.json", "kisa.txt"])
def test_senaryo_klasoru_disina_cikilamaz(istemci, dosya):
    assert istemci.post("/api/senaryo/baslat", json={"dosya": dosya}).status_code == 404


def test_senaryodan_sonra_mock_paketleri_tekrar_sayilmaz():
    # Senaryo ve mock ayni dugum adiyla gonderir; sayac zamandan geldigi icin ikisi de kabul edilmeli.
    from server.crypto import Sifreleyici
    from server.models import Taslak

    psk = os.urandom(32)
    gonderen, alan = Sifreleyici(psk), Sifreleyici(psk)
    for _ in range(3):
        sayac = time.time_ns() // 1000
        alan.coz(gonderen.sifrele(Taslak(id=f"d3-{sayac}", tur="SOS", kaynak="d3", hedef="merkez", ttl=4,
                                         yuk="x", sayac=sayac)))
