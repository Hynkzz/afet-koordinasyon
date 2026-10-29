import wave

import numpy as np
import pytest

from vurus import tespit

HIZ = 16000
URETEC = np.random.default_rng(7)


def sinyal(sure=3.0, gurultu=0.002):
    return URETEC.normal(0, gurultu, int(sure * HIZ)).astype(np.float32)


def vur(x, zaman, frekans=400, genlik=0.5):
    # Sonumlenen kisa ton: tahtaya vurusun basit modeli.
    t = np.arange(int(0.04 * HIZ)) / HIZ
    darbe = genlik * np.sin(2 * np.pi * frekans * t) * np.exp(-t / 0.008)
    i = int(zaman * HIZ)
    x[i:i + len(darbe)] += darbe
    return x


def test_duzenli_uc_vurus_bir_seri():
    x = sinyal()
    for z in (0.5, 0.85, 1.2):
        vur(x, z)
    seriler = tespit.serileri_bul(tespit.vuruslari_bul(x, HIZ))
    assert len(seriler) == 1
    assert seriler[0].adet == 3
    # FFT filtresi nedensel degil; baslangic birkac on milisaniye erkene kayabilir.
    assert seriler[0].baslangic == pytest.approx(0.5, abs=0.03)
    assert 0.5 <= seriler[0].guven <= 1


def test_iki_vurus_seri_sayilmaz():
    x = sinyal()
    vur(x, 0.5)
    vur(x, 0.85)
    assert len(tespit.vuruslari_bul(x, HIZ)) == 2
    assert tespit.serileri_bul(tespit.vuruslari_bul(x, HIZ)) == []


def test_suren_ses_vurus_degil():
    x = sinyal()
    t = np.arange(int(1.0 * HIZ)) / HIZ
    x[HIZ // 2: HIZ // 2 + len(t)] += 0.3 * np.sin(2 * np.pi * 300 * t)
    assert tespit.vuruslari_bul(x, HIZ) == []


def test_bant_disindaki_ton_sayilmaz():
    x = sinyal()
    t = np.arange(int(0.04 * HIZ)) / HIZ
    # Yumusak zarfli 5 kHz ton: enerjisi yalnizca bant disinda.
    ton = 0.5 * np.sin(2 * np.pi * 5000 * t) * np.hanning(len(t))
    for z in (0.5, 0.85, 1.2, 1.55):
        i = int(z * HIZ)
        x[i:i + len(ton)] += ton
    assert tespit.vuruslari_bul(x, HIZ) == []


def test_duzensiz_vuruslar_seri_sayilmaz():
    x = sinyal()
    for z in (0.3, 0.45, 1.4, 1.55):
        vur(x, z)
    assert tespit.serileri_bul(tespit.vuruslari_bul(x, HIZ)) == []


def test_uzun_ara_iki_ayri_seri():
    x = sinyal(5.0)
    for z in (0.5, 0.85, 1.2, 3.0, 3.4, 3.8):
        vur(x, z)
    assert [s.adet for s in tespit.serileri_bul(tespit.vuruslari_bul(x, HIZ))] == [3, 3]


def test_tam_sessiz_kayitta_vurus_yok():
    assert tespit.vuruslari_bul(np.zeros(HIZ * 2, dtype=np.float32), HIZ) == []


def test_wav_okuma_stereo(tmp_path):
    x = sinyal()
    for z in (0.5, 0.85, 1.2):
        vur(x, z)
    yol = tmp_path / "s.wav"
    with wave.open(str(yol), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(HIZ)
        w.writeframes((np.repeat(x[:, None], 2, axis=1) * 32767).astype(np.int16).tobytes())
    assert [s.adet for s in tespit.dosyada_bul(yol)] == [3]
