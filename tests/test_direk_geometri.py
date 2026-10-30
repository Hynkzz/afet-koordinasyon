"""direk.geometri isin izme testleri; prizmalar elle kurulur, kucuk cozunurluk kullanilir."""
import math

import numpy as np
import pytest

from direk.geometri import DUNYA_YARICAP_M, GOK, ZEMIN, Direk, Prizma, acilar, gor, prizmalar

DIREK = Direk(lat=39.8, lon=34.8, yukseklik_m=25, genislik=720, yukseklik=360)


def en_yakin_indeks(direk, yon_derece, egim_derece):
    """Yon (kuzeyden saat yonunde) ve egim acisinin en yakin sutun/satir indeksi."""
    yon, egim = acilar(direk)
    fark = np.angle(np.exp(1j * (yon - math.radians(yon_derece))))  # yon cevresel
    return int(np.argmin(np.abs(fark))), int(np.argmin(np.abs(egim - math.radians(egim_derece))))


def kutu(kimlik, x, y, kenar, yukseklik_m):
    """Direge gore x dogu, y kuzey merkezli kare tabanli prizma; halka kapali."""
    a = kenar / 2
    koseler = np.array([[x - a, y - a], [x + a, y - a], [x + a, y + a], [x - a, y + a], [x - a, y - a]], float)
    return Prizma(kimlik, koseler, yukseklik_m)


def duvar_satirlari(gorus, sutun):
    return np.where(gorus.yuzey[:, sutun] == 1)[0]


def test_kuzeydeki_kutunun_on_duvari_gorunur():
    g = gor(DIREK, [kutu("kuzey", 0, 50, 10, 10)])
    sutun, _ = en_yakin_indeks(DIREK, 0, -20)
    # Duvar: isinin on duvara (45 m) carptigi yer binanin yuksekligi (0-10 m) icinde.
    ust = en_yakin_indeks(DIREK, 0, math.degrees(math.atan((10 - 25) / 45)))[1]
    taban = en_yakin_indeks(DIREK, 0, math.degrees(math.atan(-25 / 45)))[1]
    for satir in range(ust + 1, taban):
        assert g.etiket[satir, sutun] == 0
        assert g.yuzey[satir, sutun] == 1
        assert g.mesafe[satir, sutun] == pytest.approx(45, abs=1)


def test_duvar_ustu_cati_alti_zemin():
    g = gor(DIREK, [kutu("kuzey", 0, 50, 10, 10)])
    sutun, _ = en_yakin_indeks(DIREK, 0, -20)
    ust = en_yakin_indeks(DIREK, 0, math.degrees(math.atan((10 - 25) / 45)))[1]
    taban = en_yakin_indeks(DIREK, 0, math.degrees(math.atan(-25 / 45)))[1]
    # Kamera binadan yuksek: duvarin hemen ustunde ayni binanin catisi gorunur.
    assert np.all(g.yuzey[ust - 4:ust, sutun][g.etiket[ust - 4:ust, sutun] == 0] == 2)
    assert not np.any(g.etiket[taban + 1:taban + 5, sutun] == 0)


def test_ust_derece_yakinindaki_satirlar_gokyuzu():
    g = gor(DIREK, [])
    sutun, ust_satir = en_yakin_indeks(DIREK, 180, DIREK.ust_derece - 0.5)
    assert g.etiket[ust_satir, sutun] == GOK
    assert math.isinf(g.mesafe[ust_satir, sutun])


def test_bos_yonde_zemin_mesafesi_egimden_beklenir():
    g = gor(DIREK, [])
    _, egim = acilar(DIREK)
    for derece in (-20, -30, -45, -55):
        sutun, satir = en_yakin_indeks(DIREK, 180, derece)
        assert g.etiket[satir, sutun] == ZEMIN
        beklenen = DIREK.yukseklik_m / math.tan(-egim[satir])  # egim asagida negatif
        assert g.mesafe[satir, sutun] == pytest.approx(beklenen, rel=0.02)


def test_yakindaki_yuksek_bina_arkadakini_kapatir():
    liste = [kutu("yakin", 0, 40, 10, 20), kutu("uzak", 0, 80, 10, 10)]
    g = gor(DIREK, liste)
    sutun, _ = en_yakin_indeks(DIREK, 0, -20)
    yakin = int(np.sum(g.etiket[:, sutun] == 0))
    uzak = int(np.sum(g.etiket[:, sutun] == 1))
    assert yakin > 0
    assert uzak <= 0.02 * yakin  # ayni dogrultudaki uzak kutu tamamen perde arkasinda


def test_derin_kutunun_catisi_gorunur():
    k = Prizma("derin", np.array([[-5, 30], [5, 30], [5, 60], [-5, 60], [-5, 30]], float), 20)
    g = gor(DIREK, [k])
    assert np.any((g.etiket == 0) & (g.yuzey == 2))


def test_yukseklik_carpani_duvar_ust_kenarini_asagi_indirir():
    p = kutu("kuzey", 0, 50, 10, 10)
    sutun, _ = en_yakin_indeks(DIREK, 0, -20)
    normal = gor(DIREK, [p])
    karisik = gor(DIREK, [p], {0: np.full(DIREK.genislik, 0.3)})
    assert duvar_satirlari(karisik, sutun).min() > duvar_satirlari(normal, sutun).min()


def test_yukseklik_carpani_gorunen_pikseli_yariya_indirir():
    p = kutu("kuzey", 0, 50, 10, 10)
    normal = gor(DIREK, [p])
    karisik = gor(DIREK, [p], {0: np.full(DIREK.genislik, 0.3)})
    assert np.sum(karisik.etiket == 0) < 0.6 * np.sum(normal.etiket == 0)


def _bina_geojson(kimlik, x0, x1, y0, y1, yukseklik_m):
    """Metre kutusunu lon/lat halkasina cevirir (yerel() isleminin tersi)."""

    def lonlat(x, y):
        lon = DIREK.lon + math.degrees(x / (DUNYA_YARICAP_M * math.cos(math.radians(DIREK.lat))))
        lat = DIREK.lat + math.degrees(y / DUNYA_YARICAP_M)
        return [lon, lat]

    halka = [lonlat(x0, y0), lonlat(x1, y0), lonlat(x1, y1), lonlat(x0, y1), lonlat(x0, y0)]
    return {"type": "Feature", "properties": {"id": kimlik, "yukseklik_m": yukseklik_m},
            "geometry": {"type": "Polygon", "coordinates": [halka]}}


def test_prizmalar_menzil_disindakini_atar():
    geo = {"type": "FeatureCollection", "features": [_bina_geojson("uzak", -10, 10, 495, 505, 10)]}
    assert prizmalar(geo, DIREK) == []


def test_prizmalar_direk_icindekini_atar():
    geo = {"type": "FeatureCollection", "features": [_bina_geojson("icinde", -10, 10, -10, 10, 30)]}
    assert prizmalar(geo, DIREK) == []


def test_prizmalar_menzil_icindekini_tutar():
    geo = {"type": "FeatureCollection", "features": [_bina_geojson("yakin", -5, 5, 55, 65, 12)]}
    liste = prizmalar(geo, DIREK)
    assert len(liste) == 1
    assert liste[0].kimlik == "yakin"
    assert liste[0].yukseklik_m == 12
    np.testing.assert_allclose(liste[0].koseler,
                               [[-5, 55], [5, 55], [5, 65], [-5, 65], [-5, 55]], atol=1e-6)