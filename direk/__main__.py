"""Sanal direk kamerasi: kurulumu yapar, her karede binalari izler, degisen binayi sunucuya bildirir.

Gercek kamera yok; kareler direk.goruntu ile uretilir. Hangi binanin yikildigini yalnizca goruntu
uretimi bilir (sunucudaki /api/sim/binalar, senaryodan beslenir); tespit tarafi yalnizca kareye bakar.
  python -m direk --sunucu http://127.0.0.1:8000 --kare
"""
import argparse
import base64
import json
import logging
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import numpy as np

from direk.geometri import Direk, gor
from direk.goruntu import enkaz_carpani, uret
from direk.tespit import Tespitci, kur

KOK = Path(__file__).resolve().parents[1]
log = logging.getLogger("direk")
KARE_GENISLIK = 1280


def istek(sunucu: str, yol: str, veri: dict | None = None) -> dict:
    govde = json.dumps(veri, ensure_ascii=False).encode() if veri is not None else None
    r = urllib.request.Request(sunucu.rstrip("/") + yol, govde, {"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=2) as cevap:
        return json.load(cevap)


def kare_jpeg(kare: np.ndarray, kurulum, bildirilen: dict[int, str]) -> str:
    import cv2  # yalnizca panele kare gonderilirken gerekir

    bgr = cv2.cvtColor(kare, cv2.COLOR_RGB2BGR)
    olcek = KARE_GENISLIK / bgr.shape[1]
    bgr = cv2.resize(bgr, (KARE_GENISLIK, int(bgr.shape[0] * olcek)))
    yuk, gen = bgr.shape[:2]
    for sira, durum in bildirilen.items():
        k = kurulum.binalar[sira]["kutu"]
        if durum == "normal" or not k:
            continue
        renk = (60, 60, 230) if durum == "yikik" else (40, 150, 240)
        x, y = int(k["x"] * gen), int(k["y"] * yuk)
        cv2.rectangle(bgr, (x, y), (x + int(k["w"] * gen), y + int(k["h"] * yuk)), renk, 2)
        cv2.putText(bgr, kurulum.binalar[sira]["kimlik"], (x, max(y - 4, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, renk, 1, cv2.LINE_AA)
    _, jpeg = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return base64.b64encode(jpeg.tobytes()).decode()


def main():
    ayrac = argparse.ArgumentParser()
    ayrac.add_argument("--binalar", default=str(KOK / "data" / "binalar.geojson"))
    # Varsayilan: Yozgat merkez, Cumhuriyet Meydani cevresi; 25 m direk.
    ayrac.add_argument("--lat", type=float, default=39.8216)
    ayrac.add_argument("--lon", type=float, default=34.8075)
    ayrac.add_argument("--yukseklik", type=float, default=25.0)
    ayrac.add_argument("--ad", default="direk1")
    ayrac.add_argument("--sunucu", default="http://127.0.0.1:8000")
    ayrac.add_argument("--aralik", type=float, default=1.0, help="kareler arasi saniye")
    ayrac.add_argument("--kare", action="store_true", help="kareleri panelin canli izleme ekranina gonder")
    secim = ayrac.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    direk = Direk(secim.lat, secim.lon, secim.yukseklik)
    with open(secim.binalar) as f:
        kurulum = kur(direk, json.load(f))
    izlenen = sum(b["piksel"] >= 200 for b in kurulum.binalar)
    log.info("Kurulum: menzilde %d bina, %d bina izleniyor", len(kurulum.liste), izlenen)
    tespitci = Tespitci(kurulum)
    sira_no = {p.kimlik: i for i, p in enumerate(kurulum.liste)}

    rng = np.random.default_rng()
    dunya, gorus = None, None
    while True:
        try:
            yikik = {sira_no[k] for k in istek(secim.sunucu, "/api/sim/binalar")["yikik"] if k in sira_no}
        except OSError as hata:
            log.warning("Sunucuya ulasilamadi: %s", hata)
            time.sleep(secim.aralik)
            continue
        if yikik != dunya:
            dunya = yikik
            gorus = gor(direk, kurulum.liste, {s: enkaz_carpani(direk.genislik, s) for s in yikik})
        # Gun icindeki isik degisimi ve bulut: tespit bunu yikim sanmamali.
        kare = uret(gorus, isik=rng.uniform(0.85, 1.15), yikik=yikik)
        for d in tespitci.isle(kare):
            log.info("Bina %s: %s (guven %.2f, gorunen %%%d)", d["kimlik"], d["durum"], d["guven"],
                     round(d["gorunurluk"] * 100))
            istek(secim.sunucu, "/api/bina", {"bina_id": d["kimlik"], "durum": d["durum"], "guven": d["guven"],
                                             "gorunurluk": d["gorunurluk"], "kaynak": secim.ad,
                                             "zaman": datetime.now().astimezone().isoformat()})
        if secim.kare:
            istek(secim.sunucu, "/api/kamera/kare", {"jpeg": kare_jpeg(kare, kurulum, tespitci.bildirilen),
                                                    "kutular": [], "kaynak": secim.ad})
        time.sleep(secim.aralik)


if __name__ == "__main__":
    main()
