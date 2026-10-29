"""Gercek deprem mesajlari sifreli pakete konunca kac bayt tutuyor, hangi kanala sigiyor.

Her mesajin ilk 200 karakteri yuk olur (sema siniri), GPS eklenir, ChaCha20-Poly1305 ile
sifrelenir; boyut msgpack ve JSON icin ayri hesaplanir. Once: python -m scripts.gercek_veri_indir
  python -m scripts.boyut_olc
"""
import json
import os
import statistics

from server.crypto import Sifreleyici
from server.kanal import KANALLAR, kodla
from server.main import KOK
from server.models import Taslak


def yuzdelik(sirali: list[int], oran: float) -> int:
    return sirali[int(len(sirali) * oran) - 1]


def main():
    mesajlar = json.loads((KOK / "data" / "gercek" / "deprem_niyet_test.json").read_text())
    sifreleyici = Sifreleyici(os.urandom(32))
    msgpack_boy, json_boy, yuk_bayt = [], [], []
    for i, m in enumerate(mesajlar):
        yuk = m["metin"][:200]
        paket = sifreleyici.sifrele(Taslak(id=f"d3-{i}", tur="SOS", kaynak="d3", hedef="merkez", ttl=5,
                                           yuk=yuk, gps={"lat": 39.81812, "lon": 34.80801}, sayac=i))
        msgpack_boy.append(len(kodla(paket)))
        json_boy.append(len(paket.model_dump_json()))
        yuk_bayt.append(len(yuk.encode()))
    print(f"mesaj sayisi: {len(mesajlar)} (6 Subat 2023, ilk 200 karakter)")
    for ad, liste in [("yuk (UTF-8)", yuk_bayt), ("paket msgpack", msgpack_boy), ("paket JSON", json_boy)]:
        s = sorted(liste)
        print(f"{ad:<14}: ortalama {statistics.mean(s):.0f}, medyan {statistics.median(s):.0f}, "
              f"p95 {yuzdelik(s, 0.95)}, en yuksek {s[-1]} bayt")
    print("kanala sigan paket orani (msgpack / JSON):")
    for ad, sinir in KANALLAR.items():
        mp = sum(b <= sinir for b in msgpack_boy) / len(msgpack_boy)
        js = sum(b <= sinir for b in json_boy) / len(json_boy)
        print(f"  {ad:<5} {sinir} bayt: {mp:.0%} / {js:.0%}")


if __name__ == "__main__":
    main()
