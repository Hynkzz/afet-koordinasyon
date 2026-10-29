import asyncio
import os
from datetime import datetime, timezone

import pytest

from server.models import Olay
from server.sources import mock


@pytest.fixture
def kaynak(monkeypatch):
    k = mock.MockKaynak(os.urandom(32))
    k.pil = {d: 50.0 for d in mock.DUGUMLER}
    return k


@pytest.fixture
def saat(monkeypatch):
    an = {"t": mock.time.monotonic()}
    monkeypatch.setattr(mock.time, "monotonic", lambda: an["t"])
    return an


def calistir(kaynak, tur: int, saat) -> list:
    """sinyal_uret dongusunu `tur` saniye boyunca beklemeden calistirir; saat her turda 1 sn ilerler."""
    gelen = []
    sayac = {"tur": 0}

    async def hizli_uyku(_):
        sayac["tur"] += 1
        saat["t"] += 1
        if sayac["tur"] >= tur:
            raise asyncio.CancelledError

    async def gonder(s):
        gelen.append(s)

    async def ana():
        eski = mock.asyncio.sleep
        mock.asyncio.sleep = hizli_uyku
        try:
            await kaynak.sinyal_uret(gonder)
        except asyncio.CancelledError:
            pass
        finally:
            mock.asyncio.sleep = eski

    asyncio.run(ana())
    return gelen


def test_dusuk_guc_modunda_pil_azalir(kaynak, saat):
    calistir(kaynak, 10, saat)
    beklenen = 50 - 10 * mock.AKIM_MA["dusuk_guc"] * mock.HIZ / 3600 / mock.KAPASITE_MAH * 100
    assert kaynak.pil["d1"] == pytest.approx(beklenen)


def test_acil_modda_pil_daha_hizli_azalir_ve_sik_olcer(kaynak, saat):
    kaynak.acil_yap(["d1"])
    gelen = calistir(kaynak, 10, saat)
    assert kaynak.pil["d1"] < kaynak.pil["d2"]
    olcum = {d: sum(s.dugum_id == d for s in gelen) for d in ("d1", "d2")}
    assert olcum["d1"] > olcum["d2"]
    assert {s.mod for s in gelen if s.dugum_id == "d1"} == {"acil"}


def test_olay_tum_dugumleri_acil_moda_alir(kaynak):
    olay = Olay(olay_id="x", kaynak="mikrofon", etiket="vurus", guven=0.7, zaman=datetime.now(timezone.utc))
    asyncio.run(kaynak.olay_bildir(olay))
    assert {kaynak.mod(d) for d in mock.DUGUMLER} == {"acil"}


def test_pili_biten_dugum_susar(kaynak, saat):
    kaynak.pil["d1"] = 0
    gelen = calistir(kaynak, 10, saat)
    assert not [s for s in gelen if s.dugum_id == "d1"]


def test_sinyal_pil_ve_mod_tasir(kaynak, saat):
    s = calistir(kaynak, 1, saat)[0]
    assert 0 <= s.pil <= 100 and s.mod == "dusuk_guc"
