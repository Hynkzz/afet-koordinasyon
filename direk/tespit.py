"""Kurulum ve bina bina degisiklik tespiti: direk cihazinda (Raspberry Pi gibi) calisacak kisim.

Kurulumda bir kez: etiket haritasi (piksel -> bina), referans goruntu ve binalarin gorunen orani.
Izlemede her karede: parlaklik referansa esitlenir, her binanin alaninda degisen piksel orani
hesaplanir; oran esikleri gecer ve art arda birkac karede ayni kalirsa durum bildirilir.
Agir is (geometri) kurulumda; cihazdaki is yalnizca piksel karsilastirmasi.
"""
from dataclasses import dataclass, field

import numpy as np

from direk.geometri import Direk, Prizma, gor, prizmalar
from direk.goruntu import uret

EN_AZ_PIKSEL = 200
# Isik farki ve gurultu tek pikselde ~20 birime kadar oynatir; enkaz dokusu bunun cok ustunde.
PIKSEL_ESIGI = 35
HASAR_ORANI, YIKIK_ORANI = 0.25, 0.5
ARDISIK_KARE = 3


@dataclass
class Kurulum:
    direk: Direk
    liste: list[Prizma]
    etiket: np.ndarray
    referans: np.ndarray
    binalar: list[dict]  # sira basina: kimlik, piksel, tam_piksel, gorunurluk, kutu (oranli x, y, w, h)


def kur(direk: Direk, binalar_geojson: dict, referans_kare: int = 5, tohum: int = 0) -> Kurulum:
    liste = prizmalar(binalar_geojson, direk)
    gorus = gor(direk, liste)
    rng = np.random.default_rng(tohum)
    # Referans birkac karenin ortalamasi: tek karenin gurultusu esige yazilmasin.
    referans = np.mean([uret(gorus, isik=rng.uniform(0.9, 1.1), tohum=tohum + i)
                        for i in range(referans_kare)], axis=0)
    yuk, gen = gorus.etiket.shape
    bilgiler = []
    for sira, p in enumerate(liste):
        alan = gorus.etiket == sira
        piksel = int(alan.sum())
        # Ortulmeseydi kac piksel tutacakti: gorunurluk orani icin tek basina cizilir.
        tam = int((gor(direk, [p]).etiket == 0).sum())
        kutu = None
        if piksel:
            satir, sutun = np.nonzero(alan)
            kutu = {"x": sutun.min() / gen, "y": satir.min() / yuk,
                    "w": (sutun.max() - sutun.min() + 1) / gen, "h": (satir.max() - satir.min() + 1) / yuk}
        bilgiler.append({"kimlik": p.kimlik, "piksel": piksel, "tam_piksel": tam,
                         "gorunurluk": round(piksel / tam, 3) if tam else 0.0, "kutu": kutu})
    return Kurulum(direk, liste, gorus.etiket, referans, bilgiler)


@dataclass
class Tespitci:
    kurulum: Kurulum
    aday: dict[int, tuple[str, int]] = field(default_factory=dict)   # sira -> (durum, kac karedir)
    bildirilen: dict[int, str] = field(default_factory=dict)

    def __post_init__(self):
        e = self.kurulum.etiket.ravel()
        self._izlenen = np.array([b["piksel"] >= EN_AZ_PIKSEL for b in self.kurulum.binalar])
        self._e = np.where(e >= 0, e, len(self.kurulum.binalar))  # bina disi pikseller son kutuya
        self._sayi = np.bincount(self._e, minlength=len(self.kurulum.binalar) + 1)

    def oranlar(self, kare: np.ndarray) -> np.ndarray:
        """Bina basina degisen piksel orani."""
        ref = self.kurulum.referans
        # Tum sahnenin parlakligi referansa esitlenir: gunes, bulut, aksam isigi yikim sanilmasin.
        carpan = np.median(ref, axis=(0, 1)) / np.maximum(np.median(kare, axis=(0, 1)), 1)
        fark = np.abs(kare * carpan - ref).max(axis=2) > PIKSEL_ESIGI
        degisen = np.bincount(self._e, weights=fark.ravel(), minlength=len(self._sayi))
        return (degisen / np.maximum(self._sayi, 1))[:-1]

    def isle(self, kare: np.ndarray) -> list[dict]:
        """Durumu degisen binalari dondurur: kimlik, durum, guven (degisen oran), gorunurluk."""
        degisimler = []
        for sira, oran in enumerate(self.oranlar(kare)):
            if not self._izlenen[sira]:
                continue
            durum = "yikik" if oran >= YIKIK_ORANI else "hasarli" if oran >= HASAR_ORANI else "normal"
            onceki, kac = self.aday.get(sira, (durum, 0))
            kac = kac + 1 if onceki == durum else 1
            self.aday[sira] = (durum, kac)
            # Toz, kus, gecici golge tek karede kalir; art arda gorulmeyen degisim bildirilmez.
            if kac >= ARDISIK_KARE and self.bildirilen.get(sira, "normal") != durum:
                self.bildirilen[sira] = durum
                b = self.kurulum.binalar[sira]
                degisimler.append({"sira": sira, "kimlik": b["kimlik"], "durum": durum,
                                   "guven": round(float(min(oran / YIKIK_ORANI, 1.0)), 3),
                                   "gorunurluk": b["gorunurluk"]})
        return degisimler
