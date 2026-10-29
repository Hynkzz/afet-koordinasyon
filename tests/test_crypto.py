import os

import pytest

from server.crypto import GecersizPaket, Sifreleyici
from server.models import Taslak


@pytest.fixture
def ikili():
    psk = os.urandom(32)
    return Sifreleyici(psk), Sifreleyici(psk)


def taslak(sayac=1, **degisen):
    alanlar = dict(id=f"d3-{sayac}", tur="SOS", kaynak="d3", hedef="merkez", ttl=5,
                   yuk="Enkaz altindayim", gps={"lat": 38.42, "lon": 27.13}, sayac=sayac)
    return Taslak(**alanlar | degisen)


def test_sifrele_coz(ikili):
    gonderen, alan = ikili
    mesaj = alan.coz(gonderen.sifrele(taslak()))
    assert mesaj.yuk == "Enkaz altindayim"
    assert mesaj.gps.lat == 38.42
    assert mesaj.kaynak == "d3"


def test_yuk_acik_metin_olarak_gorunmez(ikili):
    gonderen, _ = ikili
    paket = gonderen.sifrele(taslak())
    assert "Enkaz" not in paket.model_dump_json()
    assert "38.42" not in paket.model_dump_json()


def test_ara_dugum_ttl_azaltabilir(ikili):
    gonderen, alan = ikili
    paket = gonderen.sifrele(taslak()).model_copy(update={"ttl": 2})
    assert alan.coz(paket).ttl == 2


@pytest.mark.parametrize("alan_adi, deger", [
    ("hedef", "d5"),
    ("kaynak", "d4"),
    ("tur", "hazir_mesaj"),
    ("id", "d3-99"),
    ("sayac", 2),
    ("imza", "AAAAAAAAAAAAAAAAAAAAAA=="),
])
def test_degistirilmis_baslik_reddedilir(ikili, alan_adi, deger):
    gonderen, alan = ikili
    paket = gonderen.sifrele(taslak()).model_copy(update={alan_adi: deger})
    with pytest.raises(GecersizPaket):
        alan.coz(paket)


def test_degistirilmis_sifreli_icerik_reddedilir(ikili):
    gonderen, alan = ikili
    paket = gonderen.sifrele(taslak())
    bozuk = ("B" if paket.sifreli[0] != "B" else "C") + paket.sifreli[1:]
    with pytest.raises(GecersizPaket):
        alan.coz(paket.model_copy(update={"sifreli": bozuk}))


def test_yanlis_anahtar_reddedilir():
    paket = Sifreleyici(os.urandom(32)).sifrele(taslak())
    with pytest.raises(GecersizPaket):
        Sifreleyici(os.urandom(32)).coz(paket)


def test_tekrar_gonderilen_paket_reddedilir(ikili):
    gonderen, alan = ikili
    paket = gonderen.sifrele(taslak())
    alan.coz(paket)
    with pytest.raises(GecersizPaket, match="tekrar"):
        alan.coz(paket)


def test_eski_sayacli_paket_reddedilir(ikili):
    gonderen, alan = ikili
    eski = gonderen.sifrele(taslak(sayac=4))
    alan.coz(gonderen.sifrele(taslak(sayac=5)))
    with pytest.raises(GecersizPaket, match="tekrar"):
        alan.coz(eski)


def test_sayac_kaynak_basina_tutulur(ikili):
    gonderen, alan = ikili
    alan.coz(gonderen.sifrele(taslak(sayac=10)))
    alan.coz(gonderen.sifrele(taslak(sayac=1, id="d4-1", kaynak="d4")))


def test_sahte_paket_sayaci_ilerletmez(ikili):
    gonderen, alan = ikili
    sahte = gonderen.sifrele(taslak(sayac=1)).model_copy(update={"sayac": 1000})
    with pytest.raises(GecersizPaket):
        alan.coz(sahte)
    alan.coz(gonderen.sifrele(taslak(sayac=2)))
