"""Protomaps gunluk dunya haritasindan bir bolgeyi tek .pmtiles dosyasina keser.

Internet yalnizca bu betik calisirken gerekir; sonra panel dosyayi yerelden okur.
OSM'nin kendi karo sunucusuna istek atmaz.

Gerekli: pmtiles araci (https://github.com/protomaps/go-pmtiles/releases)

Ornek (Yozgat merkez):
  python scripts/karo_indir.py --bbox 34.72,39.75,34.90,39.87 --maxzoom 15
"""
import argparse
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
YAPILAR = "https://build-metadata.protomaps.dev/builds.json"


def main():
    ayrac = argparse.ArgumentParser()
    ayrac.add_argument("--bbox", required=True, help="bati,guney,dogu,kuzey (derece)")
    ayrac.add_argument("--minzoom", type=int, default=0)
    ayrac.add_argument("--maxzoom", type=int, default=15, help="Protomaps verisi en fazla 15")
    ayrac.add_argument("--cikti", type=Path, default=KOK / "data" / "tiles" / "bolge.pmtiles")
    ayrac.add_argument("--pmtiles", default="pmtiles", help="pmtiles aracinin yolu")
    secim = ayrac.parse_args()

    if not shutil.which(secim.pmtiles):
        sys.exit(f"pmtiles araci bulunamadi: {secim.pmtiles}")

    with urllib.request.urlopen(YAPILAR) as cevap:
        son = json.load(cevap)[-1]["key"]
    print(f"Kaynak: https://build.protomaps.com/{son}")

    secim.cikti.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        secim.pmtiles, "extract", f"https://build.protomaps.com/{son}", str(secim.cikti),
        f"--bbox={secim.bbox}", f"--minzoom={secim.minzoom}", f"--maxzoom={secim.maxzoom}",
    ], check=True)
    print(f"Yazildi: {secim.cikti} ({secim.cikti.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
