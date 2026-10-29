"""Olayin POST /api/olay ile gonderilmesinden WebSocket istemcisine ulasmasina kadar gecen sure.

Sunucu ayri calisiyor olmali: python -m server.main [--kaynak mock]
"""
import argparse
import asyncio
import json
import statistics
import time
import urllib.request
from datetime import datetime, timedelta, timezone

import websockets


def gonder(adres: str, olay: dict):
    istek = urllib.request.Request(adres + "/api/olay", json.dumps(olay).encode(), {"Content-Type": "application/json"})
    urllib.request.urlopen(istek).read()


async def olc(adres: str, adet: int, aralik: float) -> list[float]:
    gecikmeler = []
    baslangic = datetime.now(timezone.utc)
    async with websockets.connect(adres.replace("http", "ws") + "/ws") as ws:
        for i in range(adet):
            # Birlesen olay ilk olay_id'yi korur ama zamani gunceller; eslestirme zamana gore.
            damga = baslangic + timedelta(microseconds=i)
            zaman = damga.isoformat()
            olay = {"olay_id": f"olcum-{i}", "kaynak": "mikrofon", "etiket": "vurus", "guven": 0.5, "zaman": zaman}
            t0 = time.perf_counter()
            await asyncio.to_thread(gonder, adres, olay)
            while True:
                paket = json.loads(await ws.recv())
                if paket["tip"] == "olay" and datetime.fromisoformat(paket["veri"]["zaman"]) == damga:
                    break
            gecikmeler.append((time.perf_counter() - t0) * 1000)
            await asyncio.sleep(aralik)
    return gecikmeler


def main():
    ayrac = argparse.ArgumentParser()
    ayrac.add_argument("--adres", default="http://127.0.0.1:8000")
    ayrac.add_argument("--adet", type=int, default=500)
    ayrac.add_argument("--aralik", type=float, default=0.02, help="olaylar arasi bekleme, sn")
    secim = ayrac.parse_args()
    g = asyncio.run(olc(secim.adres, secim.adet, secim.aralik))
    g.sort()
    print(f"olay sayisi : {len(g)}")
    print(f"ortalama    : {statistics.mean(g):.2f} ms")
    print(f"medyan      : {statistics.median(g):.2f} ms")
    print(f"p95         : {g[int(len(g) * 0.95) - 1]:.2f} ms")
    print(f"en yuksek   : {g[-1]:.2f} ms")


if __name__ == "__main__":
    main()
