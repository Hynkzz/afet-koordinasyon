"""Kamera benzetimi icin acik lisansli afet ve kurtarma videolarini Wikimedia Commons'tan indirir.

Gercek kamera kurulamadigi icin kamera programi bu videolari kamera yerine okur.
Videolar depoya konmaz (data/gercek/video/ git disinda); lisans ve yazar bilgisi
VIDEOLAR listesinde ve indirilen klasordeki KAYNAKLAR.txt dosyasinda.
"""
import json
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from server.main import KOK

# (yerel ad, Commons dosya adi)
VIDEOLAR = [
    ("hatay-uk-isar.webm", "2023-02-09 Turkey earthquake UK ISAR team rescue woman in Hatay.webm"),
    ("hatay-ukrayna.webm", "Emergency Service of Ukraine conducts search and rescue work in Hatay Province (2023-02-16) 01.webm"),
    ("enkaz-kurtarma.webm", "International rescue effort collapsed building.webm"),
    ("iskenderun-yikim.webm", "İskenderun'da Deprem Nedeniyle Yıkım.webm"),
]
API = "https://commons.wikimedia.org/w/api.php"
BASLIK = {"User-Agent": "afet-projesi (universite projesi)"}


def bilgi(ad: str) -> dict:
    sorgu = urllib.parse.urlencode({"action": "query", "prop": "imageinfo", "iiprop": "url|extmetadata",
                                    "format": "json", "titles": f"File:{ad}"})
    with urllib.request.urlopen(urllib.request.Request(f"{API}?{sorgu}", headers=BASLIK), timeout=30) as c:
        sayfa = next(iter(json.load(c)["query"]["pages"].values()))
    ii = sayfa["imageinfo"][0]
    m = ii["extmetadata"]
    return {"url": ii["url"], "sayfa": ii["descriptionurl"],
            "lisans": m.get("LicenseShortName", {}).get("value", "?"),
            "yazar": m.get("Artist", {}).get("value", "?")}


def indir(url: str) -> bytes:
    # Commons art arda isteklerde 429 donuyor; bekleyip yeniden denemek yetiyor.
    for deneme in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=BASLIK), timeout=300) as c:
                return c.read()
        except urllib.error.HTTPError as hata:
            if hata.code != 429 or deneme == 4:
                raise
            time.sleep(10 * (deneme + 1))


def renk_duzelt(dosya):
    # Ukrayna videosunda renk uzayi "reserved" yazilmis; ffmpeg ve opencv kareleri cozemiyor,
    # model bos kare goruyor. VP9 akisindaki bilgi BT.709 yapilir; goruntu yeniden kodlanmaz.
    if not shutil.which("ffprobe"):
        return
    renk = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                           "stream=color_space", "-of", "csv=p=0", str(dosya)], capture_output=True, text=True)
    if renk.stdout.strip() != "reserved":
        return
    gecici = dosya.with_suffix(".duzeltilmis.webm")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(dosya), "-c", "copy",
                    "-bsf:v", "vp9_metadata=color_space=bt709", "-an", str(gecici)], check=True)
    gecici.replace(dosya)
    print(f"{dosya.name}: renk uzayi bilgisi duzeltildi")


def main():
    hedef = KOK / "data" / "gercek" / "video"
    hedef.mkdir(parents=True, exist_ok=True)
    kaynaklar = []
    for yerel, ad in VIDEOLAR:
        b = bilgi(ad)
        dosya = hedef / yerel
        if not dosya.exists():
            dosya.write_bytes(indir(b["url"]))
            time.sleep(3)
            renk_duzelt(dosya)
        kaynaklar.append(f"{yerel}\n  {ad}\n  lisans: {b['lisans']}\n  sayfa: {b['sayfa']}\n")
        print(f"{yerel}: {dosya.stat().st_size / 1e6:.1f} MB, {b['lisans']}")
    (hedef / "KAYNAKLAR.txt").write_text("\n".join(kaynaklar))


if __name__ == "__main__":
    main()
