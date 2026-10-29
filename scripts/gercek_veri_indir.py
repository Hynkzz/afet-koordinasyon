"""6 Subat 2023 depremlerinde toplanan, etiketli Turkce yardim mesajlarini indirir.

Kaynak: Hugging Face deprem-private/intent_test_v13_anonymized (Acik Kaynak Deprem Yardim
projesi; isimler [MASK] ile gizlenmis, adresler duruyor, lisans belirtilmemis). Veri
gercek kisilerin adreslerini icerdigi icin depoya konmaz; data/gercek/ git disinda.
"""
import json
import time
import urllib.error
import urllib.request

from server.main import KOK

KAYNAK = "https://datasets-server.huggingface.co/rows?dataset=deprem-private/intent_test_v13_anonymized&config=default&split=train"
PARCA = 100


def parca_al(offset: int) -> list[dict]:
    istek = urllib.request.Request(f"{KAYNAK}&offset={offset}&length={PARCA}", headers={"User-Agent": "afet-projesi"})
    # Servis zaman zaman baglantiyi kesiyor; birkac kez denemek yetiyor.
    for deneme in range(3):
        try:
            with urllib.request.urlopen(istek, timeout=60) as cevap:
                return [r["row"] for r in json.load(cevap)["rows"]]
        except urllib.error.URLError:
            if deneme == 2:
                raise
            time.sleep(3)


def main():
    satirlar = []
    while True:
        gelen = parca_al(len(satirlar))
        # Metin alani veri setinde yanlislikla "image_url" adini tasiyor.
        satirlar += [{"metin": r["image_url"], "etiketler": r["label"]} for r in gelen]
        if len(gelen) < PARCA:
            break
    hedef = KOK / "data" / "gercek" / "deprem_niyet_test.json"
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps(satirlar, ensure_ascii=False))
    print(f"{len(satirlar)} mesaj yazildi: {hedef}")


if __name__ == "__main__":
    main()
