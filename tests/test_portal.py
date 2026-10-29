import base64
import os

import pytest
from fastapi.testclient import TestClient

from server import portal as portal_modulu
from server.main import app
from server.main import portal as nesne_


class Saat:
    def __init__(self):
        self.an = 1000.0

    def __call__(self):
        return self.an


@pytest.fixture
def ortam(monkeypatch):
    monkeypatch.setenv("AFET_PSK", base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("AFET_KAYNAK", "yok")
    monkeypatch.setenv("AFET_AP_KONUM", "39.8181,34.8080")
    saat = Saat()
    nesne = nesne_
    nesne.kayitlar.clear()
    nesne.son_cagri.clear()
    nesne.asilsiz_cihaz.clear()
    monkeypatch.setattr(nesne, "saat", saat)
    with TestClient(app) as istemci:
        yield istemci, nesne, saat


def cagri(istemci, durum="enkaz"):
    cevap = istemci.post("/portal/cagri", data={"durum": durum}, follow_redirects=False)
    assert cevap.status_code == 303
    return cevap.headers["location"].split("/")[-1].split("?")[0]


def test_ilk_dokunus_kaydi_acar_ve_yayinlar(ortam):
    istemci, nesne, _ = ortam
    with istemci.websocket_connect("/ws") as ws:
        kod = cagri(istemci)
        paket = ws.receive_json()
    assert paket["tip"] == "portal"
    assert paket["veri"]["kod"] == kod
    assert paket["veri"]["tur"] == "SOS"
    assert paket["veri"]["gps"] == {"lat": 39.8181, "lon": 34.808}
    assert "cihaz" not in paket["veri"]


def test_guvendeyim_sos_degil(ortam):
    istemci, nesne, _ = ortam
    kod = cagri(istemci, "guvende")
    assert nesne.kayitlar[kod]["tur"] == "hazir_mesaj"


def test_bilinmeyen_durum_kayit_acmaz(ortam):
    istemci, nesne, _ = ortam
    cevap = istemci.post("/portal/cagri", data={"durum": "x"}, follow_redirects=False)
    assert cevap.headers["location"] == "/portal"
    assert not nesne.kayitlar


def test_ayrinti_kayda_eklenir(ortam):
    istemci, nesne, _ = ortam
    kod = cagri(istemci)
    cevap = istemci.post(f"/portal/ayrinti/{kod}", follow_redirects=False,
                         data={"kisi": "2-5", "yarali": "evet", "tarif": "Cami arkasi", "mesaj": "3. kat", "ad": "Ali"})
    assert cevap.headers["location"] == f"/portal/takip?kod={kod}"
    k = nesne.kayitlar[kod]
    assert (k["kisi"], k["yarali"], k["tarif"]) == ("2-5", True, "Cami arkasi")


def test_takip_kodu_ile_durum_gorulur(ortam):
    istemci, nesne, _ = ortam
    kod = cagri(istemci)
    sayfa = istemci.get("/portal/takip", params={"kod": kod.replace("-", "").lower()}).text
    assert kod in sayfa
    assert "Yeni" in sayfa
    assert 'http-equiv="refresh"' in sayfa


def test_bilinmeyen_takip_kodu(ortam):
    istemci, _, _ = ortam
    assert "bulunamadı" in istemci.get("/portal/takip", params={"kod": "AAA-AAA"}).text


def test_kullanici_metni_kacislanir(ortam):
    istemci, _, _ = ortam
    assert "<script>" not in istemci.get("/portal/takip", params={"kod": "<script>"}).text


def test_10_dakika_icinde_ikinci_cagri_ayni_kaydi_gunceller(ortam):
    istemci, nesne, saat = ortam
    ilk = cagri(istemci, "yarali")
    saat.an += 599
    ikinci = cagri(istemci, "enkaz")
    assert ikinci == ilk
    k = nesne.kayitlar[ilk]
    assert k["adet"] == 2
    assert k["durum"] == "enkaz"
    assert k["guncellendi"] is not None


def test_guncellemede_son_durum_gecerli(ortam):
    istemci, nesne, _ = ortam
    kod = cagri(istemci, "enkaz")
    cagri(istemci, "guvende")
    assert nesne.kayitlar[kod]["tur"] == "hazir_mesaj"


def test_10_dakikadan_sonra_yeni_kayit(ortam):
    istemci, nesne, saat = ortam
    ilk = cagri(istemci)
    saat.an += 601
    assert cagri(istemci) != ilk
    assert len(nesne.kayitlar) == 2


def test_asilsiz_isareti_sonraki_kayda_etiket_koyar_silmez(ortam):
    istemci, nesne, saat = ortam
    ilk = cagri(istemci)
    assert istemci.post(f"/api/portal/{ilk}/asilsiz").json()["asilsiz"] is True
    saat.an += 601
    ikinci = cagri(istemci)
    assert ikinci != ilk
    assert nesne.kayitlar[ikinci]["onceden_asilsiz"] is True
    assert nesne.kayitlar[ikinci]["tur"] == "SOS"


def test_asilsiz_isareti_1_saatte_kalkar(ortam):
    istemci, nesne, saat = ortam
    ilk = cagri(istemci)
    istemci.post(f"/api/portal/{ilk}/asilsiz")
    saat.an += 3601
    assert nesne.kayitlar[cagri(istemci)]["onceden_asilsiz"] is False


def test_asilsiz_isareti_geri_alinir(ortam):
    istemci, nesne, saat = ortam
    ilk = cagri(istemci)
    istemci.post(f"/api/portal/{ilk}/asilsiz")
    istemci.post(f"/api/portal/{ilk}/asilsiz", params={"kaldir": "true"})
    assert nesne.kayitlar[ilk]["asilsiz"] is False
    saat.an += 601
    assert nesne.kayitlar[cagri(istemci)]["onceden_asilsiz"] is False


@pytest.mark.parametrize("yol", ["/generate_204", "/hotspot-detect.html", "/connecttest.txt"])
def test_telefon_baglanti_kontrolu_portala_yonlenir(ortam, yol):
    istemci, _, _ = ortam
    cevap = istemci.get(yol, follow_redirects=False)
    assert cevap.status_code == 302
    assert cevap.headers["location"] == "/portal"


def test_kod_karisan_harf_icermez():
    for _ in range(200):
        kod = portal_modulu.kod_uret()
        assert not set(kod) & set("0O1IL")
