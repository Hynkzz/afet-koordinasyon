"""Kamera ya da video dosyasinda YOLO ile insan tespiti; bulunani panel sunucusuna olay olarak gonderir.

ultralytics ve torch gerektirir; ana sunucunun bagimliliklarina eklenmedi (kurulum: README, "Kamera").
  python -m kamera --model best.pt --kaynak 0 --sunucu http://127.0.0.1:8000
  python -m kamera --model best.pt --kaynak video.mp4 --olc 300      # yalnizca FPS olcumu
"""
import argparse
import json
import statistics
import time
import urllib.request
from datetime import datetime

from ultralytics import YOLO

INSAN = 0


def gonder(sunucu: str, olay: dict):
    istek = urllib.request.Request(sunucu.rstrip("/") + "/api/olay", json.dumps(olay).encode(),
                                   {"Content-Type": "application/json"})
    urllib.request.urlopen(istek, timeout=2).read()


def main():
    ayrac = argparse.ArgumentParser(description="YOLO insan tespiti")
    ayrac.add_argument("--model", required=True)
    ayrac.add_argument("--kaynak", default="0", help="kamera numarasi ya da video dosyasi")
    ayrac.add_argument("--sunucu", help="ornek: http://127.0.0.1:8000; verilmezse gonderilmez")
    ayrac.add_argument("--esik", type=float, default=0.5)
    ayrac.add_argument("--aralik", type=float, default=0.5, help="iki gonderim arasi en az saniye")
    ayrac.add_argument("--olc", type=int, default=0, help="bu kadar kare isleyip FPS yazdir, gonderme")
    ayrac.add_argument("--imgsz", type=int, default=640)
    secim = ayrac.parse_args()

    model = YOLO(secim.model)
    kaynak = int(secim.kaynak) if secim.kaynak.isdigit() else secim.kaynak
    sureler, son_gonderim = [], 0.0
    for kare_no, sonuc in enumerate(model(source=kaynak, stream=True, classes=[INSAN], conf=secim.esik,
                                          imgsz=secim.imgsz, verbose=False)):
        # Ultralytics kare basina on isleme + cikarim + son isleme suresini ms olarak verir.
        sureler.append(sum(sonuc.speed.values()))
        if secim.olc:
            if kare_no + 1 >= secim.olc:
                break
            continue
        if not secim.sunucu or not len(sonuc.boxes) or time.monotonic() - son_gonderim < secim.aralik:
            continue
        # Sunucu ayni etiketi 3 sn icinde birlestirir; her karede degil araliklarla gondermek yeterli.
        en_iyi = int(sonuc.boxes.conf.argmax())
        x, y, w, h = sonuc.boxes.xywhn[en_iyi].tolist()
        gonder(secim.sunucu, {
            "olay_id": f"kam1-{kare_no}", "kaynak": "kamera", "etiket": "insan",
            "guven": round(float(sonuc.boxes.conf[en_iyi]), 3), "zaman": datetime.now().astimezone().isoformat(),
            # YOLO merkez verir, sema sol ust kose ister.
            "kutu": {"x": max(x - w / 2, 0), "y": max(y - h / 2, 0), "w": w, "h": h},
        })
        son_gonderim = time.monotonic()

    if sureler:
        isinma = sureler[10:] or sureler  # ilk kareler model yuklenirken yavas
        print(f"kare: {len(sureler)}, kare basina medyan {statistics.median(isinma):.1f} ms, "
              f"~{1000 / statistics.median(isinma):.0f} FPS (ilk 10 kare haric)")


if __name__ == "__main__":
    main()
