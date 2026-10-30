"""Sanal direk tespitinin benzetimde olcumu: bulma orani, yanlis alarm, yanlis binaya isaret.

Her denemede rastgele bir direk konumu ve rastgele 1-3 izlenen bina secilir; once yikimsiz kareler
(yanlis alarm), sonra yikim kareleri islenir. Isik 0.8-1.2 arasinda her karede degisir.
Uyari: goruntu sentetik (duz renkli prizma + gurultu); gercek kameradaki dogruluk bu degildir.
  python -m scripts.direk_olc --deneme 40
"""
import argparse
import json
import time

import numpy as np

from direk.geometri import Direk, gor
from direk.goruntu import enkaz_carpani, uret
from direk.tespit import ARDISIK_KARE, EN_AZ_PIKSEL, Tespitci, kur
from server.main import KOK

YIKIMSIZ_KARE, YIKIM_KARE = 10, ARDISIK_KARE + 2


def main():
    ayrac = argparse.ArgumentParser()
    ayrac.add_argument("--binalar", default=str(KOK / "data" / "binalar.geojson"))
    ayrac.add_argument("--deneme", type=int, default=40)
    ayrac.add_argument("--tohum", type=int, default=1)
    secim = ayrac.parse_args()
    with open(secim.binalar) as f:
        binalar = json.load(f)
    rng = np.random.default_rng(secim.tohum)
    # Direk konumlari: rastgele bir binanin 20-60 m yanina konur ki cevrede bina olsun.
    merkezler = [np.mean(f["geometry"]["coordinates"][0], axis=0) for f in binalar["features"]]

    yanlis_alarm = yikimsiz_bina_kare = 0
    kayit = []  # (gorunen piksel, gorunurluk, bulundu mu)
    yanlis_bina = 0
    basla = time.perf_counter()
    for d in range(secim.deneme):
        lon, lat = merkezler[rng.integers(len(merkezler))]
        aci = rng.uniform(0, 2 * np.pi)
        uzak = rng.uniform(20, 60)
        lat += uzak * np.cos(aci) / 111_195
        lon += uzak * np.sin(aci) / (111_195 * np.cos(np.radians(lat)))
        direk = Direk(lat=lat, lon=lon, yukseklik_m=25)
        k = kur(direk, binalar, tohum=d)
        izlenen = [i for i, b in enumerate(k.binalar) if b["piksel"] >= EN_AZ_PIKSEL]
        if not izlenen:
            continue
        t = Tespitci(k)
        g0 = gor(direk, k.liste)
        for i in range(YIKIMSIZ_KARE):
            yanlis_alarm += len(t.isle(uret(g0, isik=rng.uniform(0.8, 1.2), tohum=1000 * d + i)))
        yikimsiz_bina_kare += YIKIMSIZ_KARE * len(izlenen)

        yik = set(rng.choice(izlenen, size=min(len(izlenen), int(rng.integers(1, 4))), replace=False).tolist())
        g1 = gor(direk, k.liste, {s: enkaz_carpani(direk.genislik, 7 * d + s) for s in yik})
        bulunan = set()
        for i in range(YIKIM_KARE):
            for x in t.isle(uret(g1, isik=rng.uniform(0.8, 1.2), yikik=yik, tohum=1000 * d + 500 + i)):
                if x["durum"] != "normal":
                    bulunan.add(x["sira"])
        yanlis_bina += len(bulunan - yik)
        for s in yik:
            kayit.append((k.binalar[s]["piksel"], k.binalar[s]["gorunurluk"], s in bulunan))
        print(f"deneme {d + 1}: izlenen {len(izlenen)}, yikilan {len(yik)}, bulunan dogru "
              f"{len(bulunan & yik)}, yanlis bina {len(bulunan - yik)}")

    sure = time.perf_counter() - basla
    toplam = len(kayit)
    bulunan = sum(b for *_, b in kayit)
    print(f"\nyikilan bina {toplam}, bulunan {bulunan} (%{100 * bulunan / toplam:.1f})")
    print(f"yikilmayan bina yanlis isaretlenen (yikim karelerinde): {yanlis_bina}")
    print(f"yikimsiz karelerde yanlis alarm: {yanlis_alarm} / {yikimsiz_bina_kare} bina-kare")
    for alt, ust in [(200, 1000), (1000, 5000), (5000, 10**9)]:
        grup = [b for p, _, b in kayit if alt <= p < ust]
        if grup:
            print(f"  gorunen piksel {alt}-{ust if ust < 10**9 else 'ust'}: {sum(grup)}/{len(grup)}")
    for alt, ust in [(0, 0.5), (0.5, 0.9), (0.9, 1.01)]:
        grup = [b for _, g, b in kayit if alt <= g < ust]
        if grup:
            print(f"  gorunurluk %{alt * 100:.0f}-{min(ust, 1) * 100:.0f}: {sum(grup)}/{len(grup)}")
    print(f"sure {sure:.0f} sn")


if __name__ == "__main__":
    main()
