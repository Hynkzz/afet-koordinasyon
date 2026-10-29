import pytest

from server.main import birlestirici, kanallar


@pytest.fixture(autouse=True)
def yalitilmis_ortam(monkeypatch, tmp_path):
    # Testler gercek data/afet.db dosyasina ve .env'deki LLM sunucusuna gitmesin.
    monkeypatch.setenv("AFET_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("AFET_LLM_ADRES", "")
    # Birlestirici modul duzeyinde; onceki testin olayi sonrakiyle birlesmesin.
    birlestirici._son.clear()
    for ad in kanallar.acik:
        kanallar.acik[ad] = True
