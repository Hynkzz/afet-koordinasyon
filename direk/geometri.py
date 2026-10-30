"""Yuksek direkteki 360 derece kameranin gorusu: binalar taban alanindan yukseltilmis prizmalardir.

Her piksel icin isinin ilk carptigi yuzey (bina duvari, bina catisi, zemin, gokyuzu) hesaplanir.
Ayni hesaptan iki sey cikar: hangi pikselin hangi binaya ait oldugu (etiket haritasi) ve kameranin
gorecegi goruntu. Gercek sistemde etiket haritasi kurulumda bir kez cikar; kamera yalnizca onu kullanir.
"""
import math
import warnings
from dataclasses import dataclass

import numpy as np

ZEMIN, GOK = -1, -2
DUNYA_YARICAP_M = 6_371_000


@dataclass
class Direk:
    lat: float
    lon: float
    yukseklik_m: float
    # Goruntunun dikey araligi: ufkun biraz ustunden direk dibine yakin asagiya.
    ust_derece: float = 8.0
    alt_derece: float = -60.0
    genislik: int = 2048
    yukseklik: int = 512
    menzil_m: float = 250.0


@dataclass
class Prizma:
    kimlik: str
    koseler: np.ndarray  # (n, 2) metre, direge gore dogu-kuzey
    yukseklik_m: float


def yerel(lon: float, lat: float, direk: Direk) -> tuple[float, float]:
    # Birkac yuz metrede esdikdortgen izdusum yeterli; hata santimetre duzeyinde.
    x = math.radians(lon - direk.lon) * DUNYA_YARICAP_M * math.cos(math.radians(direk.lat))
    y = math.radians(lat - direk.lat) * DUNYA_YARICAP_M
    return x, y


def prizmalar(binalar: dict, direk: Direk) -> list[Prizma]:
    sonuc = []
    for f in binalar["features"]:
        halka = f["geometry"]["coordinates"][0]
        koseler = np.array([yerel(lon, lat, direk) for lon, lat in halka])
        if np.hypot(*koseler.mean(axis=0)) > direk.menzil_m:
            continue
        # Direk binanin icindeyse (catisina dikilmisse) o bina goruntude yer almaz.
        if _icinde(koseler, 0.0, 0.0):
            continue
        sonuc.append(Prizma(f["properties"]["id"], koseler, float(f["properties"]["yukseklik_m"])))
    return sonuc


def _icinde(koseler: np.ndarray, x: float, y: float) -> bool:
    ic = False
    for (x1, y1), (x2, y2) in zip(koseler[:-1], koseler[1:]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            ic = not ic
    return ic


def acilar(direk: Direk) -> tuple[np.ndarray, np.ndarray]:
    """Sutun basina yon acisi (kuzeyden saat yonunde) ve satir basina egim (radyan, asagi negatif)."""
    yon = (np.arange(direk.genislik) + 0.5) / direk.genislik * 2 * np.pi
    egim = np.radians(direk.ust_derece + (np.arange(direk.yukseklik) + 0.5) / direk.yukseklik
                      * (direk.alt_derece - direk.ust_derece))
    return yon, egim


def _giris_cikis(prizma: Prizma, dx: np.ndarray, dy: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Her sutun isininin (birim yon dx, dy) prizma tabanina girdigi ve ciktigi mesafe; kesmiyorsa inf."""
    a, b = prizma.koseler[:-1], prizma.koseler[1:]
    ex, ey = (b - a).T
    ax, ay = a.T
    # Isin: t*(dx,dy); kenar: a + s*(b-a). Cozum: t = (a x e) / (d x e), s = (a x d) / (d x e).
    payda = dx[:, None] * ey[None, :] - dy[:, None] * ex[None, :]
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (ax * ey - ay * ex)[None, :] / payda
        s = (ax[None, :] * dy[:, None] - ay[None, :] * dx[:, None]) / payda
    gecerli = (np.abs(payda) > 1e-12) & (s >= 0) & (s <= 1) & (t > 0)
    t = np.where(gecerli, t, np.nan)
    # Prizmayi hic kesmeyen sutunlar tamamen nan; uyari beklenen durum.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        giris, cikis = np.nanmin(t, axis=1), np.nanmax(t, axis=1)
    return np.nan_to_num(giris, nan=np.inf), np.nan_to_num(cikis, nan=np.inf)


@dataclass
class Gorus:
    etiket: np.ndarray    # (yukseklik, genislik) prizma sirasi, ZEMIN ya da GOK
    mesafe: np.ndarray    # metre; gokyuzunde inf
    yuzey: np.ndarray     # 0 zemin/gok, 1 duvar, 2 cati
    kimlikler: list[str]  # etiket numarasi -> bina kimligi


def gor(direk: Direk, liste: list[Prizma], yukseklik_carpani: dict[int, np.ndarray] | None = None) -> Gorus:
    """yukseklik_carpani: prizma sirasi -> sutun basina carpan; yikik binada duzensiz enkaz yuksekligi."""
    yon, egim = acilar(direk)
    dx, dy = np.sin(yon), np.cos(yon)
    tan = np.tan(egim)[:, None]
    zemin_mesafe = np.where(tan < 0, -direk.yukseklik_m / np.minimum(tan, -1e-9), np.inf)
    zemin_mesafe = np.broadcast_to(zemin_mesafe, (direk.yukseklik, direk.genislik))

    en_yakin = zemin_mesafe.copy()
    etiket = np.where(np.isfinite(zemin_mesafe), ZEMIN, GOK).astype(np.int32)
    yuzey = np.zeros_like(etiket, dtype=np.int8)
    for sira, p in enumerate(liste):
        giris, cikis = _giris_cikis(p, dx, dy)
        sutun = np.isfinite(giris)
        if not sutun.any():
            continue
        h = np.full(direk.genislik, p.yukseklik_m)
        if yukseklik_carpani and sira in yukseklik_carpani:
            h = h * yukseklik_carpani[sira]
        g, c = giris[sutun][None, :], cikis[sutun][None, :]
        hh = h[sutun][None, :]
        z_giris = direk.yukseklik_m + g * tan
        # Duvar: isin tabana girdigi yerde binanin yuksekligi icinde.
        duvar = (z_giris >= 0) & (z_giris <= hh)
        # Cati: isin catinin ustunden girip taban icinde cati yuksekligine iner.
        with np.errstate(divide="ignore", invalid="ignore"):
            cati_d = (hh - direk.yukseklik_m) / tan
        cati = ~duvar & (z_giris > hh) & (cati_d >= g) & (cati_d <= c)
        mesafe = np.where(duvar, g, np.where(cati, cati_d, np.inf))
        bolge = en_yakin[:, sutun]
        daha_yakin = mesafe < bolge
        en_yakin[:, sutun] = np.where(daha_yakin, mesafe, bolge)
        etiket[:, sutun] = np.where(daha_yakin, sira, etiket[:, sutun])
        yuzey[:, sutun] = np.where(daha_yakin, np.where(duvar, 1, 2), yuzey[:, sutun])
    en_yakin = np.where(etiket == GOK, np.inf, en_yakin)
    return Gorus(etiket, en_yakin, yuzey, [p.kimlik for p in liste])
