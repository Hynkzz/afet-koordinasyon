import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from server.models import Gps, Kimlik, Kutu, Olay, Sema, Yuk

log = logging.getLogger("afet")


class OlayAdimi(Sema):
    tip: Literal["olay"]
    kaynak: Literal["kamera", "mikrofon"]
    etiket: Literal["insan", "vurus"]
    guven: Annotated[float, Field(ge=0, le=1)]
    kutu: Kutu | None = None
    tekrar: Annotated[int, Field(ge=1, le=100)] = 1
    aralik: Annotated[float, Field(ge=0)] = 1.0


class MesajAdimi(Sema):
    tip: Literal["mesaj"]
    dugum: Kimlik
    tur: Literal["SOS", "hazir_mesaj"]
    yuk: Yuk
    gps: Gps | None = None


class PortalAdimi(Sema):
    tip: Literal["portal"]
    durum: Literal["enkaz", "yarali", "guvende", "baska"]
    kisi: Literal["1", "2-5", "5+"] | None = None
    yarali: Literal["evet", "hayir"] | None = None
    tarif: Annotated[str, Field(max_length=200)] = ""
    mesaj: Annotated[str, Field(max_length=500)] = ""


class KanalAdimi(Sema):
    tip: Literal["kanal"]
    ad: Literal["BLE", "LoRa", "Uydu"]
    acik: bool


class Adim(Sema):
    t: Annotated[float, Field(ge=0)]
    not_: Annotated[str, Field(alias="not", max_length=200)] = ""
    is_: Annotated[OlayAdimi | MesajAdimi | PortalAdimi | KanalAdimi, Field(alias="is", discriminator="tip")]


class Senaryo(Sema):
    ad: Annotated[str, Field(min_length=1, max_length=100)]
    aciklama: Annotated[str, Field(max_length=500)] = ""
    adimlar: Annotated[list[Adim], Field(min_length=1)]

    @property
    def sure(self) -> float:
        return max(a.t + (a.is_.tekrar - 1) * a.is_.aralik if a.is_.tip == "olay" else a.t for a in self.adimlar)


def listele(dizin: Path) -> list[dict]:
    sonuc = []
    for yol in sorted(dizin.glob("*.json")):
        s = Senaryo.model_validate_json(yol.read_text())
        sonuc.append({"dosya": yol.name, "ad": s.ad, "aciklama": s.aciklama, "adim": len(s.adimlar), "sure": s.sure})
    return sonuc


def simdi() -> datetime:
    return datetime.now().astimezone()


class Oynatici:
    """Senaryo adimlarini zamaninda sunucunun normal giris yollarina verir; panel farki bilmez."""

    def __init__(self, olay: Callable[[Olay], Awaitable], mesaj: Callable[[MesajAdimi], Awaitable],
                 portal: Callable[[str, PortalAdimi], Awaitable], kanal: Callable[[str, bool], Awaitable],
                 yayinla: Callable[[str, dict], Awaitable], sustur: Callable[[bool], None]):
        self.olay, self.mesaj, self.portal, self.kanal = olay, mesaj, portal, kanal
        self.yayinla, self.sustur = yayinla, sustur
        self.gorev: asyncio.Task | None = None
        self.durum = {"durum": "bos"}

    async def durum_yayinla(self, **degisen):
        self.durum = self.durum | degisen
        await self.yayinla("senaryo", self.durum)

    def baslat(self, senaryo: Senaryo):
        if self.gorev and not self.gorev.done():
            raise RuntimeError("senaryo zaten calisiyor")
        self.gorev = asyncio.create_task(self.oynat(senaryo))

    def durdur(self):
        if self.gorev and not self.gorev.done():
            self.gorev.cancel()

    async def oynat(self, senaryo: Senaryo):
        # Olay kimlikleri her oynatmada farkli; onceki oynatmanin olaylariyla birlesmesin.
        tur = time.time_ns() // 1_000_000
        is_listesi = []
        for no, adim in enumerate(senaryo.adimlar):
            if adim.is_.tip == "olay":
                for k in range(adim.is_.tekrar):
                    is_listesi.append((adim.t + k * adim.is_.aralik, no, k, adim))
            else:
                is_listesi.append((adim.t, no, 0, adim))
        is_listesi.sort(key=lambda x: (x[0], x[1], x[2]))

        log.info("Senaryo basladi: %s (%d is, %.0f sn)", senaryo.ad, len(is_listesi), senaryo.sure)
        self.sustur(True)
        baslangic = time.monotonic()
        try:
            await self.durum_yayinla(durum="calisiyor", ad=senaryo.ad, sure=senaryo.sure, adim=0,
                                     toplam=len(is_listesi), not_="", baslangic=simdi().isoformat())
            for sira, (t, no, k, adim) in enumerate(is_listesi, 1):
                await asyncio.sleep(max(0, t - (time.monotonic() - baslangic)))
                await self.calistir(adim, f"s{tur}-{no}-{k}" if adim.is_.tip == "olay" else f"s{tur}-{no}")
                await self.durum_yayinla(adim=sira, not_=adim.not_ or self.durum.get("not_", ""))
            await self.durum_yayinla(durum="bitti")
            log.info("Senaryo bitti: %s", senaryo.ad)
        except asyncio.CancelledError:
            await self.durum_yayinla(durum="durduruldu")
            log.info("Senaryo durduruldu: %s", senaryo.ad)
            raise
        finally:
            self.sustur(False)

    async def calistir(self, adim: Adim, kimlik: str):
        i = adim.is_
        if i.tip == "olay":
            await self.olay(Olay(olay_id=kimlik, kaynak=i.kaynak, etiket=i.etiket, guven=i.guven,
                                 zaman=simdi(), kutu=i.kutu))
        elif i.tip == "mesaj":
            await self.mesaj(i)
        elif i.tip == "portal":
            await self.portal(kimlik, i)
        else:
            await self.kanal(i.ad, i.acik)


def yukle(dizin: Path, dosya: str) -> Senaryo:
    yol = (dizin / dosya).resolve()
    # Panelden gelen dosya adiyla senaryo klasorunun disina cikilmasin.
    if yol.parent != dizin.resolve() or yol.suffix != ".json":
        raise FileNotFoundError(dosya)
    return Senaryo.model_validate(json.loads(yol.read_text()))
