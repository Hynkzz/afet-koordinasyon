"""Vurus tespitini ESC-50 kayitlariyla olcer (once: python -m scripts.vurus_veri_indir).

Bir kayitta en az bir vurus serisi bulunursa "tespit" sayilir. Esikler 1-2. bolumlere
bakilarak secildi; asil sonuc hic bakilmayan 3-5. bolumler.
  python -m scripts.vurus_olc
"""
import csv
import time
from collections import defaultdict

from scripts.vurus_veri_indir import NEGATIF, POZITIF
from server.main import KOK
from vurus.tespit import dosyada_bul


def main():
    dizin = KOK / "data" / "gercek" / "esc50"
    satirlar = [r for r in csv.DictReader((dizin / "esc50.csv").open()) if r["category"] in [POZITIF, *NEGATIF]]
    sonuc = defaultdict(lambda: [0, 0])  # (bolum grubu, sinif) -> [tespit, toplam]
    sureler = []
    for r in satirlar:
        t0 = time.perf_counter()
        bulundu = bool(dosyada_bul(dizin / r["filename"]))
        sureler.append(time.perf_counter() - t0)
        grup = "ayar (1-2)" if r["fold"] in ("1", "2") else "test (3-5)"
        sonuc[(grup, r["category"])][0] += bulundu
        sonuc[(grup, r["category"])][1] += 1

    print(f"kayit: {len(satirlar)}, kayit basina sure ortalama {sum(sureler) / len(sureler) * 1000:.1f} ms (5 sn ses)")
    for grup in ("ayar (1-2)", "test (3-5)"):
        print(f"\n{grup}")
        t, n = sonuc[(grup, POZITIF)]
        print(f"  {POZITIF:<16} tespit {t}/{n} = %{100 * t / n:.0f}  (duyarlilik)")
        yt = yn = 0
        for sinif in NEGATIF:
            t, n = sonuc[(grup, sinif)]
            yt, yn = yt + t, yn + n
            print(f"  {sinif:<16} yanlis alarm {t}/{n} = %{100 * t / n:.0f}")
        print(f"  {'negatif toplam':<16} yanlis alarm {yt}/{yn} = %{100 * yt / yn:.0f}")


if __name__ == "__main__":
    main()
