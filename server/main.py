import argparse
import asyncio
import itertools
import logging
import os
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from server import llm
from server import portal as portal_modulu
from server.crypto import GecersizPaket, Sifreleyici, psk_oku
from server.db import Vakalar
from server.kanal import KANALLAR, Kanallar
from server.models import Dugumler, DurumIstek, KanalIstek, Mesaj, MesajIstek, Olay, Paket, Siginaklar, Sinyal, Taslak
from server.sources.mock import MockKaynak

KOK = Path(__file__).resolve().parent.parent
BIRLESTIRME_SURESI = 3.0
RAPOR_ARALIGI = 60
RAPOR_PENCERESI_DK = 10
SON_YAYIN_SAYISI = 300
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
        # Durum raporu icin: yayinlanan her sey son 10 dakikalik pencerede tutulur.
        self.gecmis: deque[tuple[float, str, dict]] = deque()
        self.son_sinyal: dict[str, dict] = {}
        # Panel yeniden yuklenince listeler bos kalmasin; yalnizca bellekte, en son 300 yayin.
        self.son_yayinlar: deque[dict] = deque(maxlen=SON_YAYIN_SAYISI)

    def kaydet(self, tip: str, veri: dict):
        simdi = time.time()
        if tip == "sinyal":
            self.son_sinyal[veri["dugum_id"]] = veri
        elif tip in ("olay", "mesaj", "portal"):
            self.gecmis.append((simdi, tip, veri))
            if tip != "portal":
                self.son_yayinlar.append({"tip": tip, "veri": veri, "alindi": datetime.now().astimezone().isoformat()})
        while self.gecmis and simdi - self.gecmis[0][0] > RAPOR_PENCERESI_DK * 60:
            self.gecmis.popleft()

    def ozet(self) -> dict:
        olaylar, mesajlar, portal = {}, {}, {}
        for _, tip, veri in self.gecmis:
            if tip == "olay":
                olaylar[veri["olay_id"]] = veri
            elif tip == "mesaj":
                mesajlar[veri["id"]] = veri
            elif tip == "portal":
                portal[veri["kod"]] = veri
        gecerli = [k for k in portal.values() if not k["asilsiz"]]
        return {
            "dakika": RAPOR_PENCERESI_DK,
            "sos": sum(m["tur"] == "SOS" for m in mesajlar.values()) + sum(k["tur"] == "SOS" for k in gecerli),
            "portal": len(gecerli),
            "oncelik1": sum(k["triyaj"]["oncelik"] == 1 for k in gecerli),
            "insan": sum(o["etiket"] == "insan" for o in olaylar.values()),
            "vurus": sum(o["etiket"] == "vurus" for o in olaylar.values()),
            "zayif_dugum": sorted(d for d, s in self.son_sinyal.items() if s["rssi"] <= -85 or s["paket_alim_orani"] <= 0.8),
        }

    async def yayinla(self, tip: str, veri: dict):
        self.kaydet(tip, veri)
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
            kayit["zaman"] = olay.model_dump(mode="json")["zaman"]
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
portal_sayac = itertools.count(time.time_ns() // 1_000_000)
kanallar = Kanallar()


@asynccontextmanager
async def omur(app: FastAPI):
    env_oku(KOK / ".env")
    app.state.sifreleyici = Sifreleyici(psk_oku())
    app.state.siginaklar = Siginaklar.model_validate_json((KOK / "data" / "siginaklar.geojson").read_text())
    log.info("%d siginak yuklendi", len(app.state.siginaklar.features))
    app.state.dugumler = Dugumler.model_validate_json((KOK / "data" / "dugumler.geojson").read_text())
    global vakalar
    vakalar = Vakalar(os.environ.get("AFET_DB", KOK / "data" / "afet.db"))
    portal.yukle(vakalar)
    log.info("Veritabani: %d acik vaka, %d portal kaydi", len(vakalar.kuyruk()), len(portal.kayitlar))
    kaynak_adi = os.environ.get("AFET_KAYNAK", "yok")
    gorev = None
    app.state.kaynak = None
    if kaynak_adi != "yok":
        kaynak = KAYNAKLAR[kaynak_adi](psk_oku())
        app.state.kaynak = kaynak
        gorev = asyncio.create_task(kaynak.calistir(olay_isle, paket_isle, sinyal_isle))
        gorev.add_done_callback(kaynak_bitti)
    log.info("Veri kaynagi: %s", kaynak_adi)
    log.info("LLM: %s", os.environ.get("AFET_LLM_ADRES") or "tanimli degil, kural tabanli yedek kullanilacak")
    rapor_gorevi = asyncio.create_task(rapor_dongusu())
    rapor_gorevi.add_done_callback(kaynak_bitti)
    yield
    rapor_gorevi.cancel()
    if gorev:
        gorev.cancel()
    for g in list(portal.gorevler):
        g.cancel()
    vakalar.kapat()


vakalar: Vakalar | None = None


son_rapor: dict | None = None


async def rapor_dongusu():
    global son_rapor
    while True:
        await asyncio.sleep(RAPOR_ARALIGI)
        ozet = yayinci.ozet()
        metin, yontem = await llm.durum_raporu(ozet)
        son_rapor = {"metin": metin, "yontem": yontem, "zaman": datetime.now().astimezone().isoformat()}
        await yayinci.yayinla("rapor", son_rapor)


def kaynak_bitti(gorev: asyncio.Task):
    if not gorev.cancelled() and gorev.exception():
        log.error("Arka plan gorevi durdu: %r", gorev.exception())


def vaka_konumu(vaka: dict) -> dict | None:
    """Portal ve GPS'li mesaj kendi konumunu tasir; digerleri onu ureten dugumun ya da sensorun konumunda."""
    veri = vaka["veri"]
    if veri.get("gps"):
        return veri["gps"]
    if vaka["kaynak"] == "mesaj":
        alan = "id"
    elif vaka["kaynak"] == "olay":
        alan = "tur"
    else:
        return None
    for f in app.state.dugumler.features:
        if getattr(f.properties, alan) == veri["kaynak"]:
            lon, lat = f.geometry.coordinates
            return {"lat": lat, "lon": lon}
    return None


def konumlu(vaka: dict) -> dict:
    return vaka | {"konum": vaka_konumu(vaka)}


async def vaka_kaydet(id: str, kaynak: str, oncelik: int, veri: dict):
    await yayinci.yayinla("vaka", konumlu(vakalar.kaydet(id, kaynak, oncelik, veri)))


async def olay_isle(olay: Olay) -> dict:
    kayit = birlestirici.ekle(olay)
    if app.state.kaynak:
        await app.state.kaynak.olay_bildir(olay)
    await yayinci.yayinla("olay", kayit)
    await olay_vakasi(kayit)
    return kayit


async def olay_vakasi(kayit: dict):
    # Ayni sensorun ayni etiketi, vaka kurtarilana kadar tek vakada toplanir; yoksa her vurus
    # serisi yeni bir vaka acar ve portaldan gelen SOS kuyrukta asagida kalir.
    anahtar = f"{kayit['kaynak']}-{kayit['etiket']}"
    acik = vakalar.acik_olay_vakasi(anahtar)
    if acik:
        id, veri = acik["id"], acik["veri"]
        veri["tespit"] += 1
        if kayit["olay_id"] != veri["son_olay"]["olay_id"]:
            veri["seri"] += 1
        veri["en_yuksek_guven"] = max(veri["en_yuksek_guven"], kayit["guven"])
        veri["son_olay"] = kayit
    else:
        id = f"olay-{anahtar}-{time.time_ns() // 1_000_000}"
        veri = {"anahtar": anahtar, "kaynak": kayit["kaynak"], "etiket": kayit["etiket"], "tespit": 1, "seri": 1,
                "en_yuksek_guven": kayit["guven"], "son_olay": kayit}
    # Vurus, enkaz altinda canli biri demek; kamerada gorulen kisi ise cogu zaman ulasilabilir durumda.
    await vaka_kaydet(id, "olay", 1 if kayit["etiket"] == "vurus" else 2, veri)


async def paket_isle(paket: Paket):
    try:
        mesaj = app.state.sifreleyici.coz(paket)
    except GecersizPaket as hata:
        log.warning("Paket reddedildi: %s", hata)
        return
    veri = mesaj.model_dump(mode="json", exclude_none=True)
    await yayinci.yayinla("mesaj", veri)
    if mesaj.tur == "SOS":
        await vaka_kaydet(mesaj.id, "mesaj", llm.kural_triyaj(mesaj.yuk, sos=True).oncelik, veri)


async def sinyal_isle(sinyal: Sinyal):
    await yayinci.yayinla("sinyal", sinyal.model_dump(mode="json", exclude_none=True))


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


@app.get("/api/kuyruk")
async def kuyruk() -> dict:
    return {"kuyruk": [konumlu(v) for v in vakalar.kuyruk()], "sayilar": vakalar.sayilar()}


@app.post("/api/vaka/{id}/durum")
async def durum_degistir(id: str, istek: DurumIstek) -> dict:
    try:
        vaka = vakalar.durum_degistir(id, istek.durum)
    except KeyError:
        raise HTTPException(404, "vaka yok")
    log.info("Vaka %s: %s", id, istek.durum)
    await yayinci.yayinla("vaka", konumlu(vaka))
    return vaka


@app.get("/api/gecmis")
async def gecmis() -> list[dict]:
    """Panel acilisinda yeniden oynatilacak paketler, eskiden yeniye."""
    portal_kayitlari = sorted(portal.kayitlar.values(), key=lambda k: k["guncellendi"] or k["zaman"])
    return [*yayinci.son_yayinlar,
            *({"tip": "portal", "veri": {a: d for a, d in k.items() if a != "cihaz"}} for k in portal_kayitlari[-SON_YAYIN_SAYISI:])]


@app.get("/api/dugumler")
async def dugumler() -> Dugumler:
    return app.state.dugumler


# Disa aktarilan dosya baska kurumlarla paylasilabilir; cihaz kimligi ve ad gibi kisisel alanlar cikarilir.
DISA_AKTARILMAZ = {"cihaz", "ad"}


@app.get("/api/disa-aktar")
async def disa_aktar():
    ozellikler = []
    for v in vakalar.hepsi():
        konum = vaka_konumu(v)
        veri = {k: d for k, d in v["veri"].items() if k not in DISA_AKTARILMAZ}
        ozellikler.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [konum["lon"], konum["lat"]]} if konum else None,
            "properties": {"id": v["id"], "kaynak": v["kaynak"], "oncelik": v["oncelik"], "durum": v["durum"],
                           "zaman": v["zaman"], "guncellendi": v["guncellendi"], "veri": veri},
        })
    dosya = f"afet-vakalar-{datetime.now():%Y%m%d-%H%M}.geojson"
    return JSONResponse({"type": "FeatureCollection", "features": ozellikler},
                        headers={"Content-Disposition": f'attachment; filename="{dosya}"'})


@app.get("/api/rapor")
async def rapor() -> dict | None:
    return son_rapor


@app.get("/api/siginaklar")
async def siginaklar() -> Siginaklar:
    return app.state.siginaklar


@app.post("/api/olay")
async def olay_al(olay: Olay) -> dict:
    return await olay_isle(olay)


@app.post("/api/mesaj")
async def mesaj_gonder(istek: MesajIstek) -> dict:
    sayac = next(merkez_sayac)
    taslak = Taslak(id=f"merkez-{sayac}", kaynak="merkez", hedef="*", ttl=5, sayac=sayac, **istek.model_dump())
    paket = app.state.sifreleyici.sifrele(taslak)
    iletim = kanallar.gonder(paket)
    veri = Mesaj(**taslak.model_dump(), imza=paket.imza).model_dump(mode="json", exclude_none=True) | {"iletim": iletim}
    await yayinci.yayinla("mesaj", veri)
    return veri


async def portal_ilet(tur: str, yuk: str, gps: dict | None) -> dict:
    # Portal kaydi merkeze/AFAD'a mesh uzerinden gider; telefon disariya dogrudan ulasamaz.
    def gonder(metin: str) -> dict:
        sayac = next(portal_sayac)
        taslak = Taslak(id=f"portal-{sayac}", tur=tur, kaynak="portal", hedef="*", ttl=5, yuk=metin, gps=gps, sayac=sayac)
        return kanallar.gonder(app.state.sifreleyici.sifrele(taslak))

    iletim = gonder(yuk)
    en_genis = max((s for ad, s in KANALLAR.items() if kanallar.acik[ad]), default=0)
    # Hicbir acik kanala sigmiyorsa metin sondan kirpilir; onemli bilgiler metnin basinda.
    for _ in range(3):
        if iletim["kanal"] or not en_genis or iletim["boyut"] <= en_genis:
            break
        fazla = iletim["boyut"] - en_genis
        yuk = yuk.encode()[: max(len(yuk.encode()) - fazla, 0)].decode(errors="ignore")
        iletim = gonder(yuk) | {"kirpildi": True}
    return iletim


@app.get("/api/kanallar")
async def kanal_listesi() -> list[dict]:
    return kanallar.durum()


@app.post("/api/kanal/{ad}")
async def kanal_ayarla(ad: str, istek: KanalIstek) -> list[dict]:
    try:
        kanallar.ayarla(ad, istek.acik)
    except KeyError:
        raise HTTPException(404, "kanal yok")
    await yayinci.yayinla("kanallar", {"kanallar": kanallar.durum()})
    return kanallar.durum()


portal = portal_modulu.Portal(yayinci.yayinla, portal_ilet)
portal_modulu.kur(app, portal)
app.mount("/karolar", StaticFiles(directory=KOK / "data" / "tiles", check_dir=False), name="karolar")
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
