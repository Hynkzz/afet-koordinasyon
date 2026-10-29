from datetime import datetime, timezone

from server.main import OlayBirlestirici
from server.models import Olay


class Saat:
    def __init__(self):
        self.an = 0.0

    def __call__(self):
        return self.an


def olay(no, etiket="insan", guven=0.7):
    return Olay(olay_id=f"o{no}", kaynak="kamera" if etiket == "insan" else "mikrofon",
                etiket=etiket, guven=guven, zaman=datetime.now(timezone.utc))


def test_3_saniye_icinde_ayni_etiket_birlesir():
    saat = Saat()
    b = OlayBirlestirici(saat=saat)
    ilk = b.ekle(olay(1))
    saat.an = 2.9
    ikinci = b.ekle(olay(2, guven=0.9))
    assert ikinci["olay_id"] == ilk["olay_id"] == "o1"
    assert ikinci["adet"] == 2
    assert ikinci["guven"] == 0.9


def test_guven_en_yuksek_deger_kalir():
    saat = Saat()
    b = OlayBirlestirici(saat=saat)
    b.ekle(olay(1, guven=0.9))
    assert b.ekle(olay(2, guven=0.5))["guven"] == 0.9


def test_3_saniyeden_sonra_yeni_olay():
    saat = Saat()
    b = OlayBirlestirici(saat=saat)
    b.ekle(olay(1))
    saat.an = 3.1
    yeni = b.ekle(olay(2))
    assert yeni["olay_id"] == "o2"
    assert yeni["adet"] == 1


def test_farkli_etiketler_birlesmez():
    b = OlayBirlestirici(saat=Saat())
    b.ekle(olay(1, "insan"))
    assert b.ekle(olay(2, "vurus"))["adet"] == 1


def test_sure_son_gorulmeden_sayilir():
    saat = Saat()
    b = OlayBirlestirici(saat=saat)
    for no in range(5):
        saat.an = no * 2.0
        kayit = b.ekle(olay(no))
    assert kayit["olay_id"] == "o0"
    assert kayit["adet"] == 5


def test_birlesen_olayin_zaman_bicimi_degismez():
    b = OlayBirlestirici(saat=Saat())
    ilk = dict(b.ekle(olay(1)))
    ikinci = b.ekle(olay(2))
    assert ilk["zaman"][-1] == ikinci["zaman"][-1]
