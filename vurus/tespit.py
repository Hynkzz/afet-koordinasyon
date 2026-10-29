"""Ses kaydinda vurus serisi tespiti: bant geciren filtre, enerji esigi, duzenli vurus oruntusu.

Makine ogrenmesi yok. Esikler asagidaki sabitlerde; ESC-50'nin yalnizca 1-2. bolumlerine bakilarak
secildi, dogruluk hic bakilmayan 3-5. bolumlerde olculur (scripts/vurus_olc.py).
"""
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Tahtaya, betona vurulan sesin enerjisi bu bantta yogun; ruzgar ugultusu ve tiz cizirtilar disarida kalir.
ALT_HZ, UST_HZ = 150, 1500
CERCEVE_SN = 0.010
# Gurultu tabaninin bu kadar ustu "ses var" sayilir.
ESIK_DB = 12
# Kayit tamamen sessizse taban -120 dB olur; gurultuyu vurus saymamak icin mutlak alt sinir.
MUTLAK_ESIK_DBFS = -50
# Vurus = enerjide ani yukselis. Tahta vurusu 100-250 ms tinladigi icin "kisa sure" degil
# "keskin baslangic" aranir; hizli vuruslarda ses arada esigin altina inmeden yeni darbe gelir.
ARTIS_PENCERE_SN = 0.03
ARTIS_DB = 10
OLU_SURE_SN = 0.07
# Darbe soner: tepe sonrasi bu sure icinde en az bu kadar dusmeyen ses (konusma, motor, ton) vurus degil.
SONME_PENCERE_SN = 0.3
SONME_DB = 6
# Darbenin enerjisinin en az bu kadari vurus bandinda olmali; tiklama, klavye, alkis tiz ve genis bantli.
EN_AZ_BANT_ORANI = 0.6
# Seri: ardisik vuruslar arasi sure ve duzensizlik (standart sapma / ortalama) sinirlari.
EN_KISA_ARALIK_SN, EN_UZUN_ARALIK_SN = 0.06, 1.0
EN_AZ_VURUS = 3
EN_FAZLA_DUZENSIZLIK = 0.5


@dataclass
class Vurus:
    zaman: float
    snr_db: float


@dataclass
class Seri:
    baslangic: float
    bitis: float
    adet: int
    guven: float


def oku(yol: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(yol)) as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"yalnizca 16 bit PCM WAV: {yol}")
        orneklem = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        kanal, hiz = w.getnchannels(), w.getframerate()
    if kanal > 1:
        orneklem = orneklem.reshape(-1, kanal).mean(axis=1)
    return orneklem, hiz


def bant_gecir(x: np.ndarray, hiz: int) -> np.ndarray:
    # Dosya bastan sona elde oldugu icin FFT'de bant disini sifirlamak yeterli; ek bagimlilik gerekmez.
    spektrum = np.fft.rfft(x)
    frekans = np.fft.rfftfreq(len(x), 1 / hiz)
    spektrum[(frekans < ALT_HZ) | (frekans > UST_HZ)] = 0
    return np.fft.irfft(spektrum, n=len(x))


def cerceve_enerjisi(x: np.ndarray, boy: int) -> np.ndarray:
    adet = len(x) // boy
    return (x[: adet * boy].reshape(adet, boy) ** 2).mean(axis=1)


def vuruslari_bul(x: np.ndarray, hiz: int) -> list[Vurus]:
    boy = int(CERCEVE_SN * hiz)
    if len(x) < boy * 4:
        return []
    bant = cerceve_enerjisi(bant_gecir(x, hiz), boy)
    tum = cerceve_enerjisi(x, boy)
    db = 10 * np.log10(bant + 1e-12)
    taban = np.percentile(db, 30)
    esik = max(taban + ESIK_DB, MUTLAK_ESIK_DBFS)
    geri = max(int(ARTIS_PENCERE_SN / CERCEVE_SN), 1)

    vuruslar, son = [], -1.0
    for i in range(geri, len(db) - 1):
        artis = db[i] - db[i - geri:i].min()
        # Yerel tepe: artis bir sonraki cercevede daha buyukse darbe henuz baslamaktadir.
        sonraki = db[i + 1] - db[i + 1 - geri:i + 1].min()
        zaman = i * CERCEVE_SN
        if artis < ARTIS_DB or db[i] <= esik or sonraki > artis or zaman - son < OLU_SURE_SN:
            continue
        sonrasi = db[i + 1:i + 1 + int(SONME_PENCERE_SN / CERCEVE_SN)]
        if len(sonrasi) and sonrasi.min() > db[i] - SONME_DB:
            continue
        pencere = slice(i, min(i + geri, len(db)))
        if bant[pencere].sum() / (tum[pencere].sum() + 1e-12) < EN_AZ_BANT_ORANI:
            continue
        vuruslar.append(Vurus(zaman, float(db[i] - taban)))
        son = zaman
    return vuruslar


def guven(vuruslar: list[Vurus], duzensizlik: float) -> float:
    # Olasilik degil, siralama icin puan: guclu ve duzenli seri yuksek.
    snr = float(np.mean([v.snr_db for v in vuruslar]))
    guc = min(max((snr - ESIK_DB) / 18, 0), 1)
    duzen = 1 - duzensizlik / EN_FAZLA_DUZENSIZLIK
    return round(min(max(0.5 + 0.25 * guc + 0.25 * duzen, 0), 1), 2)


def serileri_bul(vuruslar: list[Vurus]) -> list[Seri]:
    seriler, grup = [], vuruslar[:1]

    def kapat():
        if len(grup) < EN_AZ_VURUS:
            return
        aralik = np.diff([v.zaman for v in grup])
        duzensizlik = float(aralik.std() / aralik.mean())
        if duzensizlik <= EN_FAZLA_DUZENSIZLIK:
            seriler.append(Seri(grup[0].zaman, grup[-1].zaman, len(grup), guven(grup, duzensizlik)))

    for onceki, v in zip(vuruslar, vuruslar[1:]):
        if EN_KISA_ARALIK_SN <= v.zaman - onceki.zaman <= EN_UZUN_ARALIK_SN:
            grup.append(v)
        else:
            kapat()
            grup = [v]
    kapat()
    return seriler


def dosyada_bul(yol: Path) -> list[Seri]:
    x, hiz = oku(yol)
    return serileri_bul(vuruslari_bul(x, hiz))
