import base64
import os
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from server.db import Vakalar
from server.main import app


@pytest.fixture
def db(tmp_path):
    v = Vakalar(tmp_path / "v.db")
    yield v
    v.kapat()


def test_yeni_vaka_yeni_durumunda_acilir(db):
    vaka = db.kaydet("o1", "olay", 2, {"etiket": "insan"})
    assert vaka["durum"] == "yeni"
    assert vaka["veri"] == {"etiket": "insan"}


def test_tekrar_kayit_durumu_korur_veriyi_gunceller(db):
    db.kaydet("o1", "olay", 2, {"adet": 1})
    db.durum_degistir("o1", "ekip_yonlendirildi")
    vaka = db.kaydet("o1", "olay", 1, {"adet": 2})
    assert vaka["durum"] == "ekip_yonlendirildi"
    assert (vaka["oncelik"], vaka["veri"]["adet"]) == (1, 2)
    assert vaka["guncellendi"] is not None


def test_kuyruk_oncelik_sonra_zaman_sirasi(db):
    db.kaydet("a", "olay", 2, {})
    db.kaydet("b", "mesaj", 1, {})
    db.kaydet("c", "portal", 2, {})
    db.kaydet("d", "portal", 1, {})
    assert [v["id"] for v in db.kuyruk()] == ["b", "d", "a", "c"]


def test_kurtarilan_kuyruktan_cikar(db):
    db.kaydet("a", "olay", 1, {})
    db.durum_degistir("a", "kurtarildi")
    assert db.kuyruk() == []
    assert db.sayilar() == {"kurtarildi": 1}


def test_gecersiz_durum_ve_bilinmeyen_vaka(db):
    db.kaydet("a", "olay", 1, {})
    with pytest.raises(ValueError):
        db.durum_degistir("a", "silindi")
    with pytest.raises(KeyError):
        db.durum_degistir("yok", "kurtarildi")


def test_durum_degisiklikleri_gecmise_yazilir(db):
    db.kaydet("a", "olay", 1, {})
    db.durum_degistir("a", "ekip_yonlendirildi")
    db.durum_degistir("a", "kurtarildi")
    assert [g["olay"] for g in db.gecmis("a")] == ["ekip_yonlendirildi", "kurtarildi"]


def test_kapatip_acinca_veriler_durur(tmp_path):
    yol = tmp_path / "kalici.db"
    v = Vakalar(yol)
    v.kaydet("a", "portal", 1, {"kod": "a"})
    v.durum_degistir("a", "ekip_yonlendirildi")
    v.kapat()
    v = Vakalar(yol)
    assert v.getir("a")["durum"] == "ekip_yonlendirildi"
    v.kapat()


@pytest.fixture
def istemci(monkeypatch):
    monkeypatch.setenv("AFET_PSK", base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("AFET_KAYNAK", "yok")
    monkeypatch.delenv("AFET_LLM_ADRES", raising=False)
    with TestClient(app) as istemci:
        yield istemci


def olay(etiket="vurus", no=1):
    return {"olay_id": f"t-{etiket}-{no}", "kaynak": "mikrofon" if etiket == "vurus" else "kamera",
            "etiket": etiket, "guven": 0.7, "zaman": datetime.now(timezone.utc).isoformat()}


def test_olay_kuyruga_girer_vurus_oncelik_1(istemci):
    istemci.post("/api/olay", json=olay("vurus"))
    kuyruk = istemci.get("/api/kuyruk").json()["kuyruk"]
    assert [(v["id"], v["oncelik"]) for v in kuyruk] == [("t-vurus-1", 1)]


def test_operator_durumu_degistirir_ve_yayinlanir(istemci):
    istemci.post("/api/olay", json=olay("vurus"))
    with istemci.websocket_connect("/ws") as ws:
        cevap = istemci.post("/api/vaka/t-vurus-1/durum", json={"durum": "ekip_yonlendirildi"})
        paket = ws.receive_json()
    assert cevap.status_code == 200
    assert paket["tip"] == "vaka" and paket["veri"]["durum"] == "ekip_yonlendirildi"


def test_gecersiz_durum_422_bilinmeyen_vaka_404(istemci):
    istemci.post("/api/olay", json=olay("vurus"))
    assert istemci.post("/api/vaka/t-vurus-1/durum", json={"durum": "x"}).status_code == 422
    assert istemci.post("/api/vaka/yok/durum", json={"durum": "kurtarildi"}).status_code == 404


def test_portal_takip_operator_durumunu_gosterir(istemci):
    kod = istemci.post("/portal/cagri", data={"durum": "enkaz"}, follow_redirects=False).headers["location"].split("/")[-1]
    istemci.post(f"/api/vaka/{kod}/durum", json={"durum": "ekip_yonlendirildi"})
    assert "Ekip yönlendirildi" in istemci.get("/portal/takip", params={"kod": kod}).text


def test_sunucu_yeniden_acilinca_portal_kodu_calisir(monkeypatch):
    monkeypatch.setenv("AFET_PSK", base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("AFET_KAYNAK", "yok")
    with TestClient(app) as istemci:
        kod = istemci.post("/portal/cagri", data={"durum": "yarali"}, follow_redirects=False).headers["location"].split("/")[-1]
        istemci.post(f"/api/vaka/{kod}/durum", json={"durum": "kurtarildi"})
    with TestClient(app) as istemci:
        sayfa = istemci.get("/portal/takip", params={"kod": kod}).text
    assert kod in sayfa and "Kurtarıldı" in sayfa
