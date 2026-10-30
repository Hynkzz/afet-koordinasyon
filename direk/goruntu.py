"""Gorus'ten (etiket + mesafe + yuzey) kameranin gorecegi renkli goruntuyu uretir.

Gercek fotograf degil: amac degisiklik tespitinin isik, gurultu ve enkaz altinda calistigini
gostermek. Isik ve gurultu her karede biraz degisir ki "fark var" demek kolay olmasin.
"""
import zlib

import numpy as np

from direk.geometri import GOK, ZEMIN, Gorus

ENKAZ_RENGI = np.array([150, 135, 115], dtype=np.float32)


def bina_rengi(kimlik: str) -> np.ndarray:
    # Her binaya sabit ama farkli bir cephe rengi: beton, sari, krem, kiremit tonlari arasinda.
    paletler = np.array([[190, 185, 175], [205, 190, 150], [215, 205, 185], [175, 120, 95],
                         [160, 165, 170], [200, 175, 140]], dtype=np.float32)
    h = zlib.crc32(kimlik.encode())
    return paletler[h % len(paletler)] * (0.9 + 0.2 * ((h >> 8) % 100) / 100)


def uret(gorus: Gorus, isik: float = 1.0, gurultu: float = 6.0, yikik: set[int] | None = None,
         tohum: int | None = None) -> np.ndarray:
    """(yukseklik, genislik, 3) uint8. isik: 1 normal gun isigi; yikik: enkaz rengi verilecek prizmalar."""
    rng = np.random.default_rng(tohum)
    yuk, gen = gorus.etiket.shape
    goruntu = np.zeros((yuk, gen, 3), dtype=np.float32)

    satir = np.linspace(0, 1, yuk)[:, None, None]
    goruntu[:] = np.where(gorus.etiket[..., None] == GOK, np.array([150, 185, 225]) * (1 - 0.3 * satir), 0)
    zemin = gorus.etiket == ZEMIN
    goruntu[zemin] = np.array([120, 125, 110], dtype=np.float32)

    for sira, kimlik in enumerate(gorus.kimlikler):
        alan = gorus.etiket == sira
        if not alan.any():
            continue
        if yikik and sira in yikik:
            renk = ENKAZ_RENGI
            # Enkaz duzensiz: piksel piksel parlaklik farki duvardan cok daha buyuk.
            doku = rng.uniform(0.6, 1.2, size=alan.sum())[:, None]
        else:
            renk = bina_rengi(kimlik)
            doku = 1.0
        golge = np.where(gorus.yuzey[alan] == 2, 0.78, 1.0)[:, None]
        goruntu[alan] = renk * golge * doku

    # Uzak yuzey sise karisir; 250 m'de yaklasik %40.
    sis = np.clip(1 - np.exp(-np.where(np.isfinite(gorus.mesafe), gorus.mesafe, 0) / 500), 0, 1)[..., None]
    goruntu = goruntu * (1 - sis) + np.array([185, 195, 205]) * sis
    goruntu = goruntu * isik + rng.normal(0, gurultu, goruntu.shape)
    return np.clip(goruntu, 0, 255).astype(np.uint8)


def enkaz_carpani(genislik: int, tohum: int) -> np.ndarray:
    """Yikilan binanin sutun basina yukseklik carpani: %15-40 arasi, duzensiz."""
    rng = np.random.default_rng(tohum)
    ham = rng.uniform(0.15, 0.4, genislik // 16 + 2)
    return np.interp(np.arange(genislik), np.linspace(0, genislik, len(ham)), ham)
