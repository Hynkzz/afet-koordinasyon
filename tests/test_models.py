import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from server.models import Mesaj, Olay, Paket, Siginaklar, Sinyal

SHARED = Path(__file__).resolve().parent.parent / "shared"
GECERLI = {"olay_id": "k1", "kaynak": "kamera", "etiket": "insan", "guven": 0.8,
           "zaman": "2026-10-29T14:00:00+03:00", "kutu": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.3}}


@pytest.mark.parametrize("dosya, model", [
    ("olay", Olay), ("mesaj", Mesaj), ("paket", Paket), ("sinyal", Sinyal), ("siginak", Siginaklar),
])
def test_sema_ornekleri_modele_uyar(dosya, model):
    # Diger bolumler shared/ altindaki orneklere bakarak yazacak; ornek gecmiyorsa model ile sema ayrismis demektir.
    for ornek in json.loads((SHARED / f"{dosya}.schema.json").read_text())["examples"]:
        model.model_validate(ornek)


def test_ornek_siginak_dosyasi_gecerli():
    Siginaklar.model_validate_json((SHARED.parent / "data" / "siginaklar.geojson").read_text())


@pytest.mark.parametrize("degisen", [
    {"guven": 1.2},
    {"guven": -0.1},
    {"etiket": "kedi"},
    {"kaynak": "radar"},
    {"zaman": "2026-10-29T14:00:00"},
    {"zaman": "dun aksam"},
    {"etiket": "vurus", "kaynak": "mikrofon"},
    {"kutu": {"x": 0.1, "y": 0.1, "w": 0, "h": 0.3}},
    {"kutu": {"x": 1.5, "y": 0.1, "w": 0.2, "h": 0.3}},
    {"fazla_alan": 1},
], ids=str)
def test_semaya_uymayan_olay_reddedilir(degisen):
    with pytest.raises(ValidationError):
        Olay.model_validate(GECERLI | degisen)


def test_eksik_alanli_olay_reddedilir():
    for alan in ["olay_id", "kaynak", "etiket", "guven", "zaman"]:
        with pytest.raises(ValidationError):
            Olay.model_validate({k: v for k, v in GECERLI.items() if k != alan})


def test_kutusuz_vurus_gecerli():
    Olay.model_validate({k: v for k, v in GECERLI.items() if k != "kutu"} | {"etiket": "vurus", "kaynak": "mikrofon"})
