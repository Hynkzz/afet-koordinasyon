import asyncio
import itertools
import os
import random
import time
from datetime import datetime

from server.crypto import Sifreleyici
from server.models import Kutu, Olay, Sinyal, Taslak
from server.sources.base import Kaynak

DUGUMLER = ["d1", "d2", "d3", "d4", "d5", "d6"]
HAZIR_MESAJLAR = ["Enkaz altindayim", "Yarali var", "Guvendeyim"]
# Enerji modeli. Kapasite ve dusuk guc akimi 12 Ekim planindaki ornekten (2000 mAh, 5 mA ~ 400 saat);
# acil mod akimi tahmin. EEE'nin guc butcesi gelince bu degerler degisecek.
KAPASITE_MAH = 2000
AKIM_MA = {"dusuk_guc": 5, "acil": 20}
OLCUM_ARALIGI_SN = {"dusuk_guc": 5, "acil": 1}
ACIL_SURE_SN = 120
# Gercek pil omru yuzlerce saat; demoda gorunsun diye simulasyon saati hizlandirilir (1 sn = 2 dk).
HIZ = float(os.environ.get("AFET_ENERJI_HIZ", "120"))

# Ornek siginaklarin cevresi; GPS'li mesajlar haritada bu bolgeye duser.
BOLGE = {"lat": (39.805, 39.830), "lon": (34.790, 34.830)}


def simdi() -> datetime:
    return datetime.now().astimezone()


class MockKaynak(Kaynak):
    def __init__(self, psk: bytes):
        # Gercek dugum gibi kendi sifreleyicisiyle paketler; boylece sunucunun cozme yolu da calisir.
        self.sifreleyici = Sifreleyici(psk)
        self.sayac = itertools.count(1)
        self.pil = {d: random.uniform(40, 100) for d in DUGUMLER}
        self.acil_bitis = {d: 0.0 for d in DUGUMLER}

    def mod(self, dugum: str) -> str:
        return "acil" if time.monotonic() < self.acil_bitis[dugum] else "dusuk_guc"

    def acil_yap(self, dugumler: list[str]):
        bitis = time.monotonic() + ACIL_SURE_SN
        for d in dugumler:
            self.acil_bitis[d] = bitis

    async def olay_bildir(self, olay):
        # Kamera ya da mikrofon bir sey gordugunde ag tam kapasiteye gecer; tum dugumler sik olcer.
        self.acil_yap(DUGUMLER)

    async def calistir(self, olay, paket, sinyal):
        async with asyncio.TaskGroup() as grup:
            grup.create_task(self.insan_uret(olay))
            grup.create_task(self.vurus_uret(olay))
            grup.create_task(self.mesaj_uret(paket))
            grup.create_task(self.sinyal_uret(sinyal))

    async def insan_uret(self, gonder):
        # Kisi birkac saniye kadrajda kalir, her karede tespit edilir, sonra cikar.
        no = itertools.count(1)
        while True:
            await asyncio.sleep(random.uniform(4, 15))
            x, y = random.uniform(0.1, 0.7), random.uniform(0.2, 0.5)
            w, h = random.uniform(0.08, 0.15), random.uniform(0.25, 0.4)
            for _ in range(random.randint(6, 20)):
                x = min(max(x + random.uniform(-0.02, 0.02), 0), 1 - w)
                await gonder(Olay(
                    olay_id=f"mock-kam-{next(no)}", kaynak="kamera", etiket="insan",
                    guven=round(random.uniform(0.55, 0.95), 2), zaman=simdi(),
                    kutu=Kutu(x=round(x, 3), y=round(y, 3), w=round(w, 3), h=round(h, 3)),
                ))
                await asyncio.sleep(0.5)

    async def vurus_uret(self, gonder):
        # Enkaz altindaki biri araliklarla birkac kez vurur.
        no = itertools.count(1)
        while True:
            await asyncio.sleep(random.uniform(10, 30))
            for _ in range(random.randint(2, 5)):
                await gonder(Olay(
                    olay_id=f"mock-mik-{next(no)}", kaynak="mikrofon", etiket="vurus",
                    guven=round(random.uniform(0.4, 0.85), 2), zaman=simdi(),
                ))
                await asyncio.sleep(random.uniform(0.8, 1.5))

    async def mesaj_uret(self, gonder):
        while True:
            await asyncio.sleep(random.uniform(8, 25))
            canli = [d for d in DUGUMLER if self.pil[d] > 0]
            if not canli:
                continue
            dugum = random.choice(canli)
            sayac = next(self.sayac)
            sos = random.random() < 0.3
            if sos:
                self.acil_yap([dugum])
            gps = None
            if sos or random.random() < 0.5:
                gps = {"lat": round(random.uniform(*BOLGE["lat"]), 5), "lon": round(random.uniform(*BOLGE["lon"]), 5)}
            await gonder(self.sifreleyici.sifrele(Taslak(
                id=f"{dugum}-{sayac}", tur="SOS" if sos else "hazir_mesaj", kaynak=dugum, hedef="merkez",
                ttl=random.randint(1, 5), sayac=sayac, gps=gps,
                yuk="Yardim edin" if sos else random.choice(HAZIR_MESAJLAR),
            )))

    async def sinyal_uret(self, gonder):
        rssi = {d: random.uniform(-90, -50) for d in DUGUMLER}
        son_olcum = {d: 0.0 for d in DUGUMLER}
        while True:
            for d in DUGUMLER:
                if self.pil[d] <= 0:
                    continue  # pili biten dugum susar
                mod = self.mod(d)
                harcanan_mah = AKIM_MA[mod] * HIZ / 3600
                self.pil[d] = max(self.pil[d] - harcanan_mah / KAPASITE_MAH * 100, 0)
                rssi[d] = min(max(rssi[d] + random.uniform(-2, 2), -100), -40)
                if time.monotonic() - son_olcum[d] < OLCUM_ARALIGI_SN[mod]:
                    continue
                son_olcum[d] = time.monotonic()
                # -65 dBm'e kadar kayip yok denecek kadar az; altinda hizla artar, -100 dBm'de ~%40.
                oran = 0.99 - max(0, -65 - rssi[d]) / 35 * 0.59 + random.uniform(-0.03, 0.01)
                await gonder(Sinyal(
                    dugum_id=d, rssi=round(rssi[d], 1),
                    paket_alim_orani=round(min(max(oran, 0), 1), 3), zaman=simdi(),
                    pil=round(self.pil[d], 1), mod=mod,
                ))
            await asyncio.sleep(1)
