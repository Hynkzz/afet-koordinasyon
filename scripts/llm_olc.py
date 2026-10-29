"""Triyajin dogrulugunu (LLM ve kural tabanli) ve LLM gecikmesini olcer.

Ornekler data/triyaj_ornekleri.json: ekibin elle etiketledigi 24 mesaj, gercek afet verisi degil.
LLM sunucusu ayri calisiyor olmali; adres ve model .env'deki AFET_LLM_* degiskenlerinden okunur.
  python -m scripts.llm_olc [--etiket "RTX 3050, qwen3-4b"]
"""
import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

from server import llm
from server.main import KOK, env_oku

ALANLAR = ["oncelik", "sikisma", "yarali", "kisi_sayisi"]


def puanla(sonuclar: list[dict], ornekler: list[dict]) -> dict[str, float]:
    return {a: sum(s[a] == o[a] for s, o in zip(sonuclar, ornekler)) / len(ornekler) for a in ALANLAR}


async def olc(ornekler: list[dict]):
    llm_sonuc, kural_sonuc, sureler, yontemler = [], [], [], []
    for o in ornekler:
        # Portaldaki gibi: mesajlar SOS dugmesinden gelmis sayilir.
        t0 = time.perf_counter()
        sonuc, yontem = await llm.triyaj(o["metin"], sos=False)
        sureler.append(time.perf_counter() - t0)
        yontemler.append(yontem)
        llm_sonuc.append(sonuc.model_dump())
        kural_sonuc.append(llm.kural_triyaj(o["metin"], sos=False).model_dump())
    return llm_sonuc, kural_sonuc, sureler, yontemler


def main():
    ayrac = argparse.ArgumentParser()
    ayrac.add_argument("--etiket", default="", help="ciktiya yazilacak donanim/model aciklamasi")
    secim = ayrac.parse_args()
    env_oku(KOK / ".env")
    ornekler = json.loads((KOK / "data" / "triyaj_ornekleri.json").read_text())

    llm_sonuc, kural_sonuc, sureler, yontemler = asyncio.run(olc(ornekler))
    sureler.sort()
    adres, model, _ = llm.ayar()
    print(f"etiket      : {secim.etiket}")
    print(f"LLM         : {adres} / {model}")
    print(f"ornek sayisi: {len(ornekler)}, LLM ile siniflanan: {yontemler.count('llm')}")
    print(f"sure (sn)   : ortalama {statistics.mean(sureler):.2f}, medyan {statistics.median(sureler):.2f}, "
          f"p95 {sureler[int(len(sureler) * 0.95) - 1]:.2f}, en yuksek {sureler[-1]:.2f}")
    print("dogruluk    :  alan          LLM    kural")
    lp, kp = puanla(llm_sonuc, ornekler), puanla(kural_sonuc, ornekler)
    for a in ALANLAR:
        print(f"               {a:<13} {lp[a]:>5.0%}  {kp[a]:>5.0%}")
    print("hatali oncelik (LLM):")
    for s, o in zip(llm_sonuc, ornekler):
        if s["oncelik"] != o["oncelik"]:
            print(f"  beklenen {o['oncelik']}, LLM {s['oncelik']}: {o['metin']}")


if __name__ == "__main__":
    main()
