import argparse
import asyncio
import itertools
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from server.crypto import GecersizPaket, Sifreleyici, psk_oku
from server.models import Mesaj, MesajIstek, Olay, Paket, Siginaklar, Sinyal, Taslak
from server.sources.mock import MockKaynak

KOK = Path(__file__).resolve().parent.parent
BIRLESTIRME_SURESI = 3.0
KAYNAKLAR = {"mock": MockKaynak}

log = logging.getLogger("afet")


def env_oku(yol: Path):
    if not yol.exists():
        return
    for satir in yol.read_text().splitlines():
        satir = satir.strip()
        if satir and not satir.startswith("#") and "=" in satir:
            anahtar, deger = satir.split("=", 1)
            os.environ.setdefault(anahtar.strip(), deger.strip())


class Yayinci:
    def __init__(self):
        self.baglantilar: set[WebSocket] = set()

    async def yayinla(self, tip: str, veri: dict):
        baglantilar = list(self.baglantilar)
        sonuclar = await asyncio.gather(
            *(ws.send_json({"tip": tip, "veri": veri}) for ws in baglantilar), return_exceptions=True
        )
        for ws, sonuc in zip(baglantilar, sonuclar):
            if isinstance(sonuc, Exception):
                self.baglantilar.discard(ws)


class OlayBirlestirici:
    """Ayni etiket `sure` saniye icinde tekrar gelirse yeni olay acilmaz, ilkinin adedi artar.

    Sure son gorulmeden itibaren sayilir; kamerada duran bir kisi her karede
    tespit edilse de tek olay olarak kalir.
    """

    def __init__(self, sure: float = BIRLESTIRME_SURESI, saat=time.monotonic):
        self.sure = sure
        self.saat = saat
        self._son: dict[str, tuple[float, dict]] = {}

    def ekle(self, olay: Olay) -> dict:
        simdi = self.saat()
        onceki = self._son.get(olay.etiket)
        if onceki and simdi - onceki[0] <= self.sure:
            kayit = onceki[1]
            kayit["adet"] += 1
            kayit["guven"] = max(kayit["guven"], olay.guven)
            kayit["zaman"] = olay.zaman.isoformat()
            if olay.kutu:
                kayit["kutu"] = olay.kutu.model_dump()
        else:
            kayit = olay.model_dump(mode="json", exclude_none=True) | {"adet": 1}
        self._son[olay.etiket] = (simdi, kayit)
        return kayit


yayinci = Yayinci()
birlestirici = OlayBirlestirici()
# Sayac saatten baslar; sunucu yeniden acilinca alicilar eski sayaci gorup paketi tekrar sanmasin.
merkez_sayac = itertools.count(time.time_ns() // 1_000_000)


@asynccontextmanager
async def omur(app: FastAPI):
    env_oku(KOK / ".env")
    app.state.sifreleyici = Sifreleyici(psk_oku())
    app.state.siginaklar = Siginaklar.model_validate_json((KOK / "data" / "siginaklar.geojson").read_text())
    log.info("%d siginak yuklendi", len(app.state.siginaklar.features))
    kaynak_adi = os.environ.get("AFET_KAYNAK", "yok")
    gorev = None
    if kaynak_adi != "yok":
        kaynak = KAYNAKLAR[kaynak_adi](psk_oku())
        gorev = asyncio.create_task(kaynak.calistir(olay_isle, paket_isle, sinyal_isle))
        gorev.add_done_callback(kaynak_bitti)
    log.info("Veri kaynagi: %s", kaynak_adi)
    yield
    if gorev:
        gorev.cancel()


def kaynak_bitti(gorev: asyncio.Task):
    if not gorev.cancelled() and gorev.exception():
        log.error("Veri kaynagi durdu: %r", gorev.exception())


async def olay_isle(olay: Olay) -> dict:
    kayit = birlestirici.ekle(olay)
    await yayinci.yayinla("olay", kayit)
    return kayit


async def paket_isle(paket: Paket):
    try:
        mesaj = app.state.sifreleyici.coz(paket)
    except GecersizPaket as hata:
        log.warning("Paket reddedildi: %s", hata)
        return
    await yayinci.yayinla("mesaj", mesaj.model_dump(mode="json", exclude_none=True))


async def sinyal_isle(sinyal: Sinyal):
    await yayinci.yayinla("sinyal", sinyal.model_dump(mode="json"))


app = FastAPI(title="Afet Paneli", lifespan=omur)


@app.websocket("/ws")
async def ws_ucu(ws: WebSocket):
    await ws.accept()
    yayinci.baglantilar.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        yayinci.baglantilar.discard(ws)


@app.get("/api/siginaklar")
async def siginaklar() -> Siginaklar:
    return app.state.siginaklar


@app.post("/api/olay")
async def olay_al(olay: Olay) -> dict:
    return await olay_isle(olay)


@app.post("/api/mesaj")
async def mesaj_gonder(istek: MesajIstek) -> Mesaj:
    sayac = next(merkez_sayac)
    taslak = Taslak(id=f"merkez-{sayac}", kaynak="merkez", hedef="*", ttl=5, sayac=sayac, **istek.model_dump())
    paket = app.state.sifreleyici.sifrele(taslak)
    log.info("Mesaj gonderildi: %s %s, %d bayt", paket.id, paket.tur, len(paket.model_dump_json()))
    mesaj = Mesaj(**taslak.model_dump(), imza=paket.imza)
    await yayinci.yayinla("mesaj", mesaj.model_dump(mode="json", exclude_none=True))
    return mesaj


# API yollarindan sonra baglanmali; "/" her yolu yakalar.
app.mount("/", StaticFiles(directory=KOK / "web", html=True, check_dir=False), name="web")


def main():
    ayrac = argparse.ArgumentParser(description="Afet paneli sunucusu")
    ayrac.add_argument("--host", default="127.0.0.1")
    ayrac.add_argument("--port", type=int, default=8000)
    ayrac.add_argument("--kaynak", choices=["yok", *KAYNAKLAR], help="veri kaynagi; verilmezse AFET_KAYNAK, o da yoksa 'yok'")
    secim = ayrac.parse_args()
    if secim.kaynak:
        os.environ["AFET_KAYNAK"] = secim.kaynak
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    uvicorn.run(app, host=secim.host, port=secim.port)


if __name__ == "__main__":
    main()
