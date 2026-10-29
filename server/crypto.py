import base64
import binascii
import hashlib
import json
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from server.models import Mesaj, Paket, Taslak

ETIKET_BOYU = 16


class GecersizPaket(Exception):
    pass


def psk_oku() -> bytes:
    deger = os.environ.get("AFET_PSK")
    if not deger:
        raise SystemExit(
            "AFET_PSK tanimli degil. .env dosyasina ekleyin, uretmek icin:\n"
            '  python -c "import os,base64;print(\'AFET_PSK=\'+base64.b64encode(os.urandom(32)).decode())"'
        )
    try:
        psk = base64.b64decode(deger, validate=True)
    except binascii.Error:
        raise SystemExit("AFET_PSK gecerli base64 degil")
    if len(psk) != 32:
        raise SystemExit("AFET_PSK 32 bayt olmali")
    return psk


def _nonce(kaynak: str, sayac: int) -> bytes:
    # Tum dugumler ayni PSK'yi paylasiyor; kaynak eklenmezse iki dugumun ayni sayaci ayni nonce olur.
    return hashlib.sha256(kaynak.encode()).digest()[:4] + sayac.to_bytes(8, "big")


def _aad(id: str, tur: str, kaynak: str, hedef: str, sayac: int) -> bytes:
    # ttl dahil degil: ara dugumler her aktarimda azaltiyor.
    return json.dumps([id, tur, kaynak, hedef, sayac], separators=(",", ":")).encode()


class Sifreleyici:
    def __init__(self, psk: bytes):
        self._aead = ChaCha20Poly1305(psk)
        self._son_sayac: dict[str, int] = {}

    def sifrele(self, taslak: Taslak) -> Paket:
        acik = taslak.model_dump(mode="json", include={"yuk", "gps"}, exclude_none=True)
        cikti = self._aead.encrypt(
            _nonce(taslak.kaynak, taslak.sayac),
            json.dumps(acik, separators=(",", ":")).encode(),
            _aad(taslak.id, taslak.tur, taslak.kaynak, taslak.hedef, taslak.sayac),
        )
        return Paket(
            id=taslak.id, tur=taslak.tur, kaynak=taslak.kaynak, hedef=taslak.hedef,
            ttl=taslak.ttl, sayac=taslak.sayac,
            sifreli=base64.b64encode(cikti[:-ETIKET_BOYU]).decode(),
            imza=base64.b64encode(cikti[-ETIKET_BOYU:]).decode(),
        )

    def coz(self, paket: Paket) -> Mesaj:
        if paket.sayac <= self._son_sayac.get(paket.kaynak, -1):
            raise GecersizPaket(f"tekrar paket: {paket.kaynak} sayac {paket.sayac}")
        try:
            acik = self._aead.decrypt(
                _nonce(paket.kaynak, paket.sayac),
                base64.b64decode(paket.sifreli, validate=True) + base64.b64decode(paket.imza),
                _aad(paket.id, paket.tur, paket.kaynak, paket.hedef, paket.sayac),
            )
        except (InvalidTag, binascii.Error):
            raise GecersizPaket(f"dogrulanamadi: {paket.id}")
        # Sayac ancak dogrulamadan sonra kaydedilir; yoksa sahte paket gercek dugumu kilitlerdi.
        self._son_sayac[paket.kaynak] = paket.sayac
        return Mesaj(**paket.model_dump(include={"id", "tur", "kaynak", "hedef", "ttl", "sayac", "imza"}), **json.loads(acik))
