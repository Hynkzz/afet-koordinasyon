"""Triyaji 6 Subat 2023 depremlerinden gercek mesajlarla olcer (once scripts.gercek_veri_indir).

Veri setinin etiketleri bizimkinden farkli; su eslestirme kullanilir:
  sikisma       = "Enkaz Kaldirma" etiketi var
  yardim cagrisi = yalnizca "Alakasiz" degil
  oncelik       = enkaz 1, diger ihtiyaclar 2, alakasiz 3
  python -m scripts.gercek_olc [--orneklem 300] [--etiket "..."]
"""
import argparse
import asyncio
import json
import random
import statistics
import time

from server import llm
from server.main import KOK, env_oku


def gercek(satir: dict) -> dict:
    enkaz = "Enkaz Kaldirma" in satir["etiketler"]
    alakasiz = satir["etiketler"] == ["Alakasiz"]
    return {"sikisma": enkaz, "yardim": not alakasiz, "oncelik": 1 if enkaz else 3 if alakasiz else 2}


def tahmin(t: llm.Triyaj) -> dict:
    return {"sikisma": t.sikisma, "yardim": t.oncelik <= 2, "oncelik": t.oncelik}


def ikili(tahminler: list[dict], gercekler: list[dict], alan: str) -> str:
    dp = sum(t[alan] and g[alan] for t, g in zip(tahminler, gercekler))
    yp = sum(t[alan] and not g[alan] for t, g in zip(tahminler, gercekler))
    yn = sum(not t[alan] and g[alan] for t, g in zip(tahminler, gercekler))
    dogru = sum(t[alan] == g[alan] for t, g in zip(tahminler, gercekler))
    kesinlik = dp / (dp + yp) if dp + yp else 0
    duyarlilik = dp / (dp + yn) if dp + yn else 0
    return f"dogruluk {dogru / len(gercekler):.0%}, kesinlik {kesinlik:.0%}, duyarlilik {duyarlilik:.0%}"


def rapor(ad: str, tahminler: list[dict], gercekler: list[dict]):
    oncelik = sum(t["oncelik"] == g["oncelik"] for t, g in zip(tahminler, gercekler)) / len(gercekler)
    print(f"{ad} (n={len(gercekler)})")
    print(f"  sikisma        : {ikili(tahminler, gercekler, 'sikisma')}")
    print(f"  yardim cagrisi : {ikili(tahminler, gercekler, 'yardim')}")
    print(f"  oncelik        : dogruluk {oncelik:.0%}")


async def llm_olc(satirlar: list[dict]) -> tuple[list[dict], list[float], int]:
    tahminler, sureler, kurala_dusen = [], [], 0
    for s in satirlar:
        t0 = time.perf_counter()
        sonuc, yontem = await llm.triyaj(s["metin"], sos=False)
        sureler.append(time.perf_counter() - t0)
        kurala_dusen += yontem != "llm"
        tahminler.append(tahmin(sonuc))
    return tahminler, sureler, kurala_dusen


def main():
    ayrac = argparse.ArgumentParser()
    ayrac.add_argument("--orneklem", type=int, default=300)
    ayrac.add_argument("--etiket", default="")
    secim = ayrac.parse_args()
    env_oku(KOK / ".env")
    hepsi = json.loads((KOK / "data" / "gercek" / "deprem_niyet_test.json").read_text())
    orneklem = random.Random(42).sample(hepsi, secim.orneklem)

    print(f"etiket: {secim.etiket}")
    print(f"veri  : {len(hepsi)} mesaj, orneklem {len(orneklem)} (tohum 42)")
    rapor("kural, tum veri", [tahmin(llm.kural_triyaj(s["metin"], sos=False)) for s in hepsi], [gercek(s) for s in hepsi])
    rapor("kural, orneklem", [tahmin(llm.kural_triyaj(s["metin"], sos=False)) for s in orneklem],
          [gercek(s) for s in orneklem])

    adres, model, _ = llm.ayar()
    if not adres:
        print("LLM tanimli degil; LLM olcumu atlandi")
        return
    tahminler, sureler, kurala_dusen = asyncio.run(llm_olc(orneklem))
    sureler.sort()
    rapor(f"LLM {model}, orneklem", tahminler, [gercek(s) for s in orneklem])
    print(f"  kurala dusen   : {kurala_dusen}")
    print(f"  sure (sn)      : ortalama {statistics.mean(sureler):.2f}, medyan {statistics.median(sureler):.2f}, "
          f"p95 {sureler[int(len(sureler) * 0.95) - 1]:.2f}, en yuksek {sureler[-1]:.2f}")


if __name__ == "__main__":
    main()
