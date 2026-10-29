import base64
import logging

import msgpack

from server.models import Paket

log = logging.getLogger("afet")

# Sirayla denenir: once kisa menzilli ve ucuz olan, en son uydu.
# Sinirlar simulasyon degeri; BLE icin EEE'nin baglanti butcesiyle guncellenecek.
KANALLAR = {
    "BLE": 380,    # BLE mesh, segmentli erisim mesaji (yaklasik)
    "LoRa": 200,   # gorev tanimi: ~200 bayt
    "Uydu": 340,   # Iridium SBD, gonderilen mesaj basina 340 bayt
}


def kodla(paket: Paket) -> bytes:
    # Sifreli kisim ve imza ham bayt olarak yazilir; base64 metin boyutu ~%33 buyutur.
    alanlar = paket.model_dump()
    alanlar["sifreli"] = base64.b64decode(paket.sifreli)
    alanlar["imza"] = base64.b64decode(paket.imza)
    return msgpack.packb(alanlar)


class Kanallar:
    def __init__(self):
        self.acik = {ad: True for ad in KANALLAR}

    def durum(self) -> list[dict]:
        return [{"ad": ad, "sinir": sinir, "acik": self.acik[ad]} for ad, sinir in KANALLAR.items()]

    def ayarla(self, ad: str, acik: bool):
        if ad not in KANALLAR:
            raise KeyError(ad)
        self.acik[ad] = acik
        log.info("Kanal %s %s", ad, "acildi" if acik else "cokertildi")

    def gonder(self, paket: Paket) -> dict:
        boyut = len(kodla(paket))
        denenen = []
        for ad, sinir in KANALLAR.items():
            if not self.acik[ad]:
                denenen.append(f"{ad}: çökük")
            elif boyut > sinir:
                denenen.append(f"{ad}: {boyut} > {sinir} bayt")
            else:
                denenen.append(f"{ad}: gönderildi")
                log.info("Paket %s %s ile gonderildi, %d bayt", paket.id, ad, boyut)
                return {"kanal": ad, "boyut": boyut, "json_boyut": len(paket.model_dump_json()), "denenen": denenen}
        log.warning("Paket %s gonderilemedi: %s", paket.id, "; ".join(denenen))
        return {"kanal": None, "boyut": boyut, "json_boyut": len(paket.model_dump_json()), "denenen": denenen}
