import asyncio
import hashlib
import html
import logging
import os
import secrets
import socket
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request

from server import llm
from fastapi.responses import HTMLResponse, RedirectResponse

log = logging.getLogger("afet")

# Bu sure icinde ayni cihazdan gelen yeni cagri yeni kayit acmaz, oncekini gunceller.
BIRLESTIRME_SN = 600
ASILSIZ_SN = 3600
# Karistirilan harfler yok (0/O, 1/I/L); kod sesli okunup elle yazilabilsin.
KOD_HARFLERI = "ACDEFGHJKMNPRTUVWXY3479"

DURUMLAR = {
    "enkaz": ("Enkaz altındayım", "Mahsur kaldım, çıkamıyorum", "SOS"),
    "yarali": ("Yaralı var", "Tıbbi yardım gerekiyor", "SOS"),
    "guvende": ("Güvendeyim", "Yardıma ihtiyacım yok, haber veriyorum", "hazir_mesaj"),
    "baska": ("Başka bir durum", "Kendim yazacağım", "SOS"),
}
TAKIP_ADI = {"yeni": "Yeni", "ekip_yonlendirildi": "Ekip yönlendirildi", "kurtarildi": "Kurtarıldı"}


def kod_uret() -> str:
    harfler = "".join(secrets.choice(KOD_HARFLERI) for _ in range(6))
    return f"{harfler[:3]}-{harfler[3:]}"


def mac_bul(ip: str) -> str | None:
    # Erisim noktasi bu makinedeyse istemcinin MAC'i ARP tablosunda bulunur.
    try:
        satirlar = Path("/proc/net/arp").read_text().splitlines()[1:]
    except OSError:
        return None
    for satir in satirlar:
        alanlar = satir.split()
        if alanlar and alanlar[0] == ip and alanlar[3] != "00:00:00:00:00:00":
            return alanlar[3]
    return None


def yerel_ip() -> str:
    # Paket gonderilmez; isletim sistemi hangi arayuzden cikacagini secer, o arayuzun IP'si alinir.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def sayfa(govde: str, yenile: int | None = None) -> HTMLResponse:
    meta = f'<meta http-equiv="refresh" content="{yenile}">' if yenile else ""
    return HTMLResponse(
        '<!doctype html><html lang="tr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>Afet Acil Yardım</title><link rel="stylesheet" href="/portal.css">{meta}</head><body>'
        "<header><b>AFET ACİL YARDIM</b><div>İnternet gerekmez. Mesajınız koordinasyon merkezine iletilir.</div></header>"
        f"<main>{govde}</main></body></html>"
    )


async def form_oku(istek: Request) -> dict[str, str]:
    # python-multipart bagimliligi eklememek icin form elle cozuluyor.
    govde = (await istek.body()).decode(errors="replace")
    return {k: v[0].strip() for k, v in parse_qs(govde).items()}


class Portal:
    def __init__(self, yayinla: Callable[[str, dict], Awaitable[None]],
                 ilet: Callable[[str, str, dict | None], Awaitable[dict]], saat=time.time):
        self.yayinla = yayinla
        self.ilet = ilet
        self.saat = saat
        self.kayitlar: dict[str, dict] = {}
        self.son_cagri: dict[str, tuple[float, str]] = {}
        self.asilsiz_cihaz: dict[str, float] = {}
        self.gorevler: set[asyncio.Task] = set()
        self.vakalar = None

    def yukle(self, vakalar):
        self.vakalar = vakalar
        self.kayitlar = {v["id"]: v["veri"] for v in vakalar.hepsi("portal")}
        # Cihaz kimligi karma olarak tutulur; tuz her acilista degisir, kayitlar baska oturumla eslestirilemez.
        self.tuz = secrets.token_bytes(16)

    def cihaz(self, istek: Request) -> str:
        ip = istek.client.host if istek.client else "bilinmiyor"
        kimlik = mac_bul(ip) or ip
        return hashlib.sha256(self.tuz + kimlik.encode()).hexdigest()[:16]

    def konum(self) -> dict | None:
        deger = os.environ.get("AFET_AP_KONUM")
        if not deger:
            return None
        lat, lon = (float(x) for x in deger.split(","))
        return {"lat": lat, "lon": lon}

    async def yayinla_kayit(self, kayit: dict):
        vaka = self.vakalar.kaydet(kayit["kod"], "portal", kayit["triyaj"]["oncelik"], kayit)
        await self.yayinla("portal", {k: v for k, v in kayit.items() if k != "cihaz"})
        await self.yayinla("vaka", vaka | {"veri": {k: v for k, v in kayit.items() if k != "cihaz"}})

    def durum(self, kod: str) -> str:
        return self.vakalar.getir(kod)["durum"]

    async def cagri(self, cihaz: str, durum: str) -> tuple[dict, bool]:
        simdi = self.saat()
        onceki = self.son_cagri.get(cihaz)
        if onceki and simdi - onceki[0] <= BIRLESTIRME_SN and onceki[1] in self.kayitlar:
            kayit = self.kayitlar[onceki[1]]
            kayit["adet"] += 1
            kayit["guncellendi"] = datetime.now().astimezone().isoformat()
            # Guvendeyim'den SOS'a donus ya da tersi: son bildirilen durum gecerli.
            kayit["durum"], kayit["tur"] = durum, DURUMLAR[durum][2]
            yeni = False
        else:
            kod = kod_uret()
            while kod in self.kayitlar:
                kod = kod_uret()
            kayit = {
                "kod": kod, "durum": durum, "tur": DURUMLAR[durum][2],
                "zaman": datetime.now().astimezone().isoformat(), "guncellendi": None, "adet": 1,
                "gps": self.konum(), "kisi": None, "yarali": None, "tarif": "", "mesaj": "", "ad": "",
                "asilsiz": False, "onceden_asilsiz": self.asilsiz_cihaz.get(cihaz, 0) > simdi, "cihaz": cihaz,
            }
            self.kayitlar[kod] = kayit
            yeni = True
        # Ilk dokunusta serbest metin yok; secilen durumdan kural tabanli oncelik verilir.
        kayit["triyaj"] = llm.kural_triyaj(DURUMLAR[durum][0], sos=kayit["tur"] == "SOS").model_dump() | {"yontem": "kural"}
        kayit["iletim"] = await self.ilet(kayit["tur"], iletim_metni(kayit), kayit["gps"])
        self.son_cagri[cihaz] = (simdi, kayit["kod"])
        log.info("Portal cagrisi %s: %s (%s)", kayit["kod"], durum, "yeni" if yeni else "guncelleme")
        await self.yayinla_kayit(kayit)
        return kayit, yeni

    async def ayrinti(self, kod: str, form: dict[str, str]):
        kayit = self.kayitlar[kod]
        kisi = form.get("kisi", "")
        kayit["kisi"] = kisi if kisi in {"1", "2-5", "5+"} else None
        kayit["yarali"] = {"evet": True, "hayir": False}.get(form.get("yarali", ""))
        kayit["tarif"] = form.get("tarif", "")[:200]
        kayit["mesaj"] = form.get("mesaj", "")[:500]
        kayit["ad"] = form.get("ad", "")[:60]
        kayit["guncellendi"] = datetime.now().astimezone().isoformat()
        await self.yayinla_kayit(kayit)
        # LLM yanitini beklemeden kullaniciya donulur; sonuc gelince panel guncellenir.
        gorev = asyncio.create_task(self.triyaj_et(kod))
        self.gorevler.add(gorev)
        gorev.add_done_callback(self.gorevler.discard)

    async def triyaj_et(self, kod: str):
        kayit = self.kayitlar[kod]
        metin = f"{DURUMLAR[kayit['durum']][0]}. {kayit['mesaj']}".strip()
        sonuc, yontem = await llm.triyaj(metin, kayit["kisi"], kayit["yarali"], sos=kayit["tur"] == "SOS")
        kayit["triyaj"] = sonuc.model_dump() | {"yontem": yontem}
        # Ayrinti ve triyaj eklenmis hali yeniden gonderilir.
        kayit["iletim"] = await self.ilet(kayit["tur"], iletim_metni(kayit), kayit["gps"])
        log.info("Portal kaydi %s triyaj: oncelik %d (%s)", kod, sonuc.oncelik, yontem)
        await self.yayinla_kayit(kayit)

    async def asilsiz(self, kod: str, isaretle: bool):
        kayit = self.kayitlar[kod]
        kayit["asilsiz"] = isaretle
        if isaretle:
            self.asilsiz_cihaz[kayit["cihaz"]] = self.saat() + ASILSIZ_SN
        else:
            self.asilsiz_cihaz.pop(kayit["cihaz"], None)
        self.vakalar.gecmise_yaz(kod, "asilsiz" if isaretle else "asilsiz_kaldirildi")
        log.info("Portal kaydi %s asilsiz isareti: %s", kod, "kondu" if isaretle else "kaldirildi")
        await self.yayinla_kayit(kayit)


def iletim_metni(kayit: dict) -> str:
    # LoRa ~200 bayt tasir; once en onemli bilgiler, serbest metin en sonda ve kirpilarak.
    t = kayit["triyaj"]
    parcalar = [kayit["kod"], DURUMLAR[kayit["durum"]][0], f"O{t['oncelik']}"]
    if kayit["kisi"]:
        parcalar.append(f"{kayit['kisi']} kisi")
    if kayit["yarali"]:
        parcalar.append("yarali")
    ozet = t["ozet"] if t["yontem"] == "llm" else kayit["mesaj"]
    for ek in (kayit["tarif"], ozet):
        if ek:
            parcalar.append(ek)
    return "; ".join(parcalar)[:200]


def baslangic_sayfasi() -> HTMLResponse:
    dugmeler = "".join(
        f'<button class="buyuk{" sos" if tur == "SOS" and anahtar != "baska" else ""}" name="durum" value="{anahtar}">'
        f"{ad}<small>{alt}</small></button>"
        for anahtar, (ad, alt, tur) in DURUMLAR.items()
    )
    return sayfa(
        '<div class="adim">Adım 1 / 2</div><h1>Durumunuzu seçin</h1>'
        f'<form method="post" action="/portal/cagri">{dugmeler}</form>'
        '<p class="not">Seçtiğiniz an mesajınız gönderilir. Gerçek bir durumdaysanız çekinmeden basın; '
        "gereksiz kullanım yardım bekleyenleri geciktirir.</p>"
        '<p class="not"><a href="/portal/takip">Takip kodum var</a></p>'
    )


def secim(ad: str, deger: str, metin: str) -> str:
    return f'<label><input type="radio" name="{ad}" value="{deger}">{metin}</label>'


def ayrinti_sayfasi(kayit: dict, yeni: bool) -> HTMLResponse:
    kod = html.escape(kayit["kod"])
    durum = html.escape(DURUMLAR[kayit["durum"]][0])
    ust = "Mesajınız gönderildi" if yeni else "Önceki mesajınız güncellendi"
    return sayfa(
        f'<div class="gonderildi">{ust}: <b>{durum}</b>. Takip kodunuz <b class="kod">{kod}</b></div>'
        '<div class="adim">Adım 2 / 2 · isteğe bağlı</div><h1>Ayrıntı ekleyin</h1>'
        f'<form method="post" action="/portal/ayrinti/{kod}">'
        '<label class="baslik" for="tarif">Neredesiniz? <span class="ip">adres veya tarif</span></label>'
        '<input id="tarif" name="tarif" maxlength="200" placeholder="Örn. Medrese Mah., caminin arkasındaki 4 katlı bina">'
        '<div class="baslik">Kaç kişisiniz?</div><div class="secim">'
        f'{secim("kisi", "1", "1")}{secim("kisi", "2-5", "2–5")}{secim("kisi", "5+", "5+")}</div>'
        '<div class="baslik">Yaralı var mı?</div><div class="secim">'
        f'{secim("yarali", "evet", "Evet")}{secim("yarali", "hayir", "Hayır")}</div>'
        '<label class="baslik" for="mesaj">Durumunuz</label>'
        '<textarea id="mesaj" name="mesaj" maxlength="500" placeholder="Örn. Merdiven çöktü, 3. kattayız"></textarea>'
        '<label class="baslik" for="ad">Adınız <span class="ip">isteğe bağlı</span></label>'
        '<input id="ad" name="ad" maxlength="60">'
        '<button class="gonder">Ayrıntıları Gönder</button></form>'
        '<p class="not">Bilgileriniz yalnızca kurtarma koordinasyonu için bu cihazda tutulur.</p>'
    )


def takip_sayfasi(kayit: dict | None, kod: str, takip: str = "yeni") -> HTMLResponse:
    if kayit is None:
        hata = f'<p class="hata">"{html.escape(kod)}" kodlu bir kayıt bulunamadı.</p>' if kod else ""
        return sayfa(
            f"<h1>Durum sorgula</h1>{hata}"
            '<form method="get" action="/portal/takip"><label class="baslik" for="kod">Takip kodu</label>'
            '<input id="kod" name="kod" autocapitalize="characters" placeholder="Örn. K7M-4C9">'
            '<button class="gonder notr">Sorgula</button></form>'
        )
    saat = datetime.fromisoformat(kayit["guncellendi"] or kayit["zaman"]).strftime("%H:%M")
    return sayfa(
        '<p class="not">Mesajınız alındı.</p><div class="baslik">Takip kodunuz</div>'
        f'<div class="kod-kutu">{html.escape(kayit["kod"])}</div>'
        '<p class="not">Bu kodu not edin. Bu sayfaya tekrar girip kodu yazarak durumunuzu görebilirsiniz.</p>'
        f'<div class="baslik">Durum</div><div class="durum {takip}">{TAKIP_ADI[takip]}'
        f'<div class="not">Son güncelleme {saat}</div></div>'
        f'<p class="not">Bu sayfa 30 saniyede bir kendini yeniler. <a href="/portal/ayrinti/{html.escape(kayit["kod"])}">Ayrıntı ekle</a></p>',
        yenile=30,
    )


def kur(app: FastAPI, portal: Portal):
    @app.get("/portal")
    async def portal_ana():
        return baslangic_sayfasi()

    @app.post("/portal/cagri")
    async def portal_cagri(istek: Request):
        durum = (await form_oku(istek)).get("durum", "")
        if durum not in DURUMLAR:
            return RedirectResponse("/portal", status_code=303)
        kayit, yeni = await portal.cagri(portal.cihaz(istek), durum)
        hedef = f"/portal/ayrinti/{kayit['kod']}" + ("" if yeni else "?guncelleme=1")
        return RedirectResponse(hedef, status_code=303)

    @app.get("/portal/ayrinti/{kod}")
    async def portal_ayrinti_formu(kod: str, guncelleme: int = 0):
        if kod not in portal.kayitlar:
            return takip_sayfasi(None, kod)
        return ayrinti_sayfasi(portal.kayitlar[kod], yeni=not guncelleme)

    @app.post("/portal/ayrinti/{kod}")
    async def portal_ayrinti(kod: str, istek: Request):
        if kod not in portal.kayitlar:
            return takip_sayfasi(None, kod)
        await portal.ayrinti(kod, await form_oku(istek))
        return RedirectResponse(f"/portal/takip?kod={kod}", status_code=303)

    @app.get("/portal/takip")
    async def portal_takip(kod: str = ""):
        kod = kod.strip().upper()
        if len(kod) == 6 and "-" not in kod:
            kod = f"{kod[:3]}-{kod[3:]}"
        kayit = portal.kayitlar.get(kod)
        return takip_sayfasi(kayit, kod, portal.durum(kod) if kayit else "yeni")

    @app.post("/api/portal/{kod}/asilsiz")
    async def asilsiz_isaretle(kod: str, kaldir: bool = False):
        if kod not in portal.kayitlar:
            raise HTTPException(404, "kayit yok")
        await portal.asilsiz(kod, not kaldir)
        return {"kod": kod, "asilsiz": not kaldir}

    @app.get("/api/portal/adres")
    async def portal_adresi(istek: Request):
        # Panel localhost'tan acilir ama telefon o adrese ulasamaz; agdaki IP verilir.
        adres = os.environ.get("AFET_PORTAL_ADRES") or f"http://{yerel_ip()}:{istek.url.port or 80}/portal"
        return {"adres": adres}

    # Telefonlar Wi-Fi'a baglaninca bu adresleri yoklar; yonlendirme gelince portal penceresini acar.
    for yol in ["/generate_204", "/gen_204", "/hotspot-detect.html", "/library/test/success.html",
                "/connecttest.txt", "/ncsi.txt", "/canonical.html"]:
        app.add_api_route(yol, lambda: RedirectResponse("/portal", status_code=302), include_in_schema=False)
