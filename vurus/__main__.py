"""Ses dosyalarinda vurus serisi arar; bulunani panel sunucusuna olay olarak gonderir.

  python -m vurus kayit.wav [kayit2.wav ...] [--sunucu http://127.0.0.1:8000]
--sunucu verilmezse yalnizca yazdirir.
"""
import argparse
import json
import urllib.request
from datetime import datetime
from pathlib import Path

from vurus.tespit import dosyada_bul


def gonder(sunucu: str, olay: dict):
    istek = urllib.request.Request(sunucu.rstrip("/") + "/api/olay", json.dumps(olay).encode(),
                                   {"Content-Type": "application/json"})
    urllib.request.urlopen(istek, timeout=5).read()


def main():
    ayrac = argparse.ArgumentParser(description="Vurus serisi tespiti")
    ayrac.add_argument("dosyalar", nargs="+", type=Path)
    ayrac.add_argument("--sunucu", help="ornek: http://127.0.0.1:8000")
    secim = ayrac.parse_args()
    for yol in secim.dosyalar:
        seriler = dosyada_bul(yol)
        if not seriler:
            print(f"{yol.name}: vurus serisi yok")
        for no, s in enumerate(seriler):
            print(f"{yol.name}: {s.baslangic:.2f}-{s.bitis:.2f} sn, {s.adet} vurus, guven {s.guven}")
            if secim.sunucu:
                gonder(secim.sunucu, {
                    "olay_id": f"vurus-{yol.stem}-{no}", "kaynak": "mikrofon", "etiket": "vurus",
                    "guven": s.guven, "zaman": datetime.now().astimezone().isoformat(),
                })


if __name__ == "__main__":
    main()
