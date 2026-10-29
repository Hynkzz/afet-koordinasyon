"""Kamera ya da video dosyasinda YOLO ile insan tespiti; bulunani panel sunucusuna olay olarak gonderir.

Gercek kamera kurulamadigi icin video dosyasi kamera yerine kullanilabilir: video kendi hizinda
oynatilir ve --kare ile kareler panelin canli izleme ekranina da gider.
ultralytics ve torch gerektirir; ana sunucunun bagimliliklarina eklenmedi (kurulum: README, "Kamera").
  python -m kamera --model yolo11n.pt --kaynak video.webm --sunucu http://127.0.0.1:8000 --kare --dongu
  python -m kamera --model yolo11n.pt --kaynak 0 --sunucu http://127.0.0.1:8000
  python -m kamera --model yolo11n.pt --kaynak http://192.168.1.20:8080/video --sunucu ... --kare   # telefon (IP Webcam)
  python -m kamera --model yolo11n.pt --kaynak rtsp://kullanici:parola@192.168.1.30/stream1 ...   # IP kamera
  python -m kamera --model yolo11n.pt --kaynak video.webm --olc 300      # yalnizca FPS olcumu
"""
import argparse
import base64
import json
import statistics
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import cv2
from ultralytics import YOLO

INSAN = 0
KARE_GENISLIK = 640
KARE_ARALIK_SN = 0.2


def gonder(sunucu: str, yol: str, veri: dict):
    istek = urllib.request.Request(sunucu.rstrip("/") + yol, json.dumps(veri).encode(),
                                   {"Content-Type": "application/json"})
    urllib.request.urlopen(istek, timeout=2).read()


def kutular(sonuc) -> list[dict]:
    # YOLO merkez verir, sema sol ust kose ister.
    return [{"x": max(x - w / 2, 0), "y": max(y - h / 2, 0), "w": w, "h": h, "guven": round(float(g), 3)}
            for (x, y, w, h), g in zip(sonuc.boxes.xywhn.tolist(), sonuc.boxes.conf.tolist())]


def kare_jpeg(kare) -> str:
    # Panel icin kucuk ve dusuk kaliteli: saniyede 5 kare yerel agda ~150 KB/sn.
    yukseklik = int(kare.shape[0] * KARE_GENISLIK / kare.shape[1])
    _, jpeg = cv2.imencode(".jpg", cv2.resize(kare, (KARE_GENISLIK, yukseklik)), [cv2.IMWRITE_JPEG_QUALITY, 70])
    return base64.b64encode(jpeg.tobytes()).decode()


def main():
    ayrac = argparse.ArgumentParser(description="YOLO insan tespiti")
    ayrac.add_argument("--model", required=True)
    ayrac.add_argument("--kaynak", default="0", help="kamera numarasi ya da video dosyasi")
    ayrac.add_argument("--sunucu", help="ornek: http://127.0.0.1:8000; verilmezse gonderilmez")
    ayrac.add_argument("--esik", type=float, default=0.5)
    ayrac.add_argument("--aralik", type=float, default=0.5, help="iki olay gonderimi arasi en az saniye")
    ayrac.add_argument("--kare", action="store_true", help="kareleri panelin canli izleme ekranina gonder")
    ayrac.add_argument("--dongu", action="store_true", help="video bitince basa don")
    ayrac.add_argument("--olc", type=int, default=0, help="bu kadar kare isleyip FPS yazdir, gonderme")
    ayrac.add_argument("--imgsz", type=int, default=640)
    secim = ayrac.parse_args()

    model = YOLO(secim.model)
    # Canli kaynak: kamera numarasi ya da ag adresi (IP kamera RTSP, telefon uygulamasi HTTP akisi).
    canli = secim.kaynak.isdigit() or "://" in secim.kaynak
    dosya = not canli
    cap = cv2.VideoCapture(int(secim.kaynak) if secim.kaynak.isdigit() else secim.kaynak)
    if not cap.isOpened():
        raise SystemExit(f"kaynak acilamadi: {secim.kaynak}")
    # Video dosyasi kamera gibi davransin: kendi hizinda oynatilir, model hizinda degil.
    kare_suresi = 1 / (cap.get(cv2.CAP_PROP_FPS) or 25) if dosya and not secim.olc else 0
    # Adreste parola olabilir (rtsp://kullanici:parola@...); panele yalnizca sunucu adi gider.
    ad = Path(secim.kaynak).name if dosya else (secim.kaynak.split("@")[-1].split("/")[0] if canli and "://" in secim.kaynak else f"kamera {secim.kaynak}")

    sureler, son_olay, son_kare, kare_no = [], 0.0, 0.0, 0
    sonraki = time.monotonic()
    while True:
        ok, kare = cap.read()
        if not ok:
            if dosya and secim.dongu:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            break
        sonuc = model(kare, classes=[INSAN], conf=secim.esik, imgsz=secim.imgsz, verbose=False)[0]
        # Ultralytics kare basina on isleme + cikarim + son isleme suresini ms olarak verir.
        sureler.append(sum(sonuc.speed.values()))
        kare_no += 1
        if secim.olc:
            if kare_no >= secim.olc:
                break
            continue

        simdi = time.monotonic()
        if secim.sunucu and secim.kare and simdi - son_kare >= KARE_ARALIK_SN:
            gonder(secim.sunucu, "/api/kamera/kare", {"jpeg": kare_jpeg(kare), "kutular": kutular(sonuc), "kaynak": ad})
            son_kare = simdi
        # Sunucu ayni etiketi 3 sn icinde birlestirir; her karede degil araliklarla gondermek yeterli.
        if secim.sunucu and len(sonuc.boxes) and simdi - son_olay >= secim.aralik:
            en_iyi = max(kutular(sonuc), key=lambda k: k["guven"])
            gonder(secim.sunucu, "/api/olay", {
                "olay_id": f"kam1-{kare_no}", "kaynak": "kamera", "etiket": "insan", "guven": en_iyi.pop("guven"),
                "zaman": datetime.now().astimezone().isoformat(), "kutu": en_iyi,
            })
            son_olay = simdi
        if kare_suresi:
            sonraki += kare_suresi
            time.sleep(max(0.0, sonraki - time.monotonic()))

    if sureler:
        isinma = sureler[10:] or sureler  # ilk kareler model yuklenirken yavas
        print(f"kare: {len(sureler)}, kare basina medyan {statistics.median(isinma):.1f} ms, "
              f"~{1000 / statistics.median(isinma):.0f} FPS (ilk 10 kare haric)")


if __name__ == "__main__":
    main()
