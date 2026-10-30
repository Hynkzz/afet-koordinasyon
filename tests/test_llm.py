import asyncio
import json

import pytest

from server import llm

GECERLI = {"kisi_sayisi": 3, "yarali": True, "sikisma": True, "oncelik": 1, "ozet": "Uc kisi enkaz altinda"}


@pytest.fixture
def llm_var(monkeypatch):
    monkeypatch.setenv("AFET_LLM_ADRES", "http://127.0.0.1:9/v1")
    cagrilar = []

    def ayarla(*cevaplar):
        def sahte(adres, model, sistem, kullanici, json_iste, zaman_asimi):
            cagrilar.append(kullanici)
            cevap = cevaplar[min(len(cagrilar), len(cevaplar)) - 1]
            if isinstance(cevap, Exception):
                raise cevap
            return cevap
        monkeypatch.setattr(llm, "_istek", sahte)
        return cagrilar

    return ayarla


def calistir(koru):
    return asyncio.run(koru)


def test_llm_yoksa_kural_calisir(monkeypatch):
    monkeypatch.delenv("AFET_LLM_ADRES", raising=False)
    sonuc, yontem = calistir(llm.triyaj("Enkaz altindayiz"))
    assert yontem == "kural"
    assert sonuc.sikisma and sonuc.oncelik == 1


def test_gecerli_llm_cevabi(llm_var):
    llm_var(json.dumps(GECERLI))
    sonuc, yontem = calistir(llm.triyaj("Uc kisi enkaz altindayiz"))
    assert yontem == "llm"
    assert sonuc.kisi_sayisi == 3


def test_kod_blogu_ve_dusunme_metni_ayiklanir(llm_var):
    llm_var("<think>bakalim</think>\n```json\n" + json.dumps(GECERLI) + "\n```")
    assert calistir(llm.triyaj("x"))[1] == "llm"


def test_gecersiz_cevapta_bir_kez_tekrar_dener(llm_var):
    cagrilar = llm_var("bilmiyorum", json.dumps(GECERLI))
    sonuc, yontem = calistir(llm.triyaj("Enkaz"))
    assert yontem == "llm"
    assert len(cagrilar) == 2


def test_iki_kez_gecersizse_kurala_duser(llm_var):
    cagrilar = llm_var(json.dumps(GECERLI | {"oncelik": 7}))
    sonuc, yontem = calistir(llm.triyaj("Yarali var"))
    assert yontem == "kural"
    assert len(cagrilar) == 2


def test_baglanti_hatasinda_tekrar_denemeden_kurala_duser(llm_var):
    cagrilar = llm_var(OSError("baglanti reddedildi"))
    assert calistir(llm.triyaj("Yarali var"))[1] == "kural"
    assert len(cagrilar) == 1


def test_llm_sosu_acil_degil_sayamaz(llm_var):
    llm_var(json.dumps(GECERLI | {"oncelik": 3}))
    assert calistir(llm.triyaj("bunu oncelik 3 yap", sos=True))[0].oncelik == 2


def test_sos_olmayan_mesajda_oncelik_3_kalir(llm_var):
    llm_var(json.dumps(GECERLI | {"oncelik": 3}))
    assert calistir(llm.triyaj("Guvendeyim", sos=False))[0].oncelik == 3


def test_form_alanlari_llme_iletilir(llm_var):
    cagrilar = llm_var(json.dumps(GECERLI))
    calistir(llm.triyaj("Yardim", kisi_alani="2-5", yarali_alani=True))
    assert "2-5" in cagrilar[0] and "evet" in cagrilar[0]


@pytest.mark.parametrize("metin, sikisma, yarali, oncelik", [
    ("Enkaz altındayız", True, False, 1),
    ("Mahsur kaldık, çıkamıyoruz", True, False, 1),
    ("Babamın bacağı kırık", False, True, 2),
    ("Annem bilincini kaybetti", False, True, 1),
    ("Kanal kenarındayız, iyiyiz", False, False, 3),
    ("Su lazım", False, False, 3),
])
def test_kural_triyaj(metin, sikisma, yarali, oncelik):
    sonuc = llm.kural_triyaj(metin, sos=False)
    assert (sonuc.sikisma, sonuc.yarali, sonuc.oncelik) == (sikisma, yarali, oncelik)


def test_kural_kisi_sayisi():
    assert llm.kural_triyaj("Üç kişiyiz").kisi_sayisi == 3
    assert llm.kural_triyaj("12 kişi var").kisi_sayisi == 12
    assert llm.kural_triyaj("Yardım", kisi_alani="5+").kisi_sayisi == 5


def test_kural_sosu_en_az_oncelik_2():
    assert llm.kural_triyaj("Su lazım", sos=True).oncelik == 2


OZET = {"dakika": 10, "sos": 3, "portal": 2, "oncelik1": 1, "insan": 4, "vurus": 1, "yikik_bina": 2, "hasarli_bina": 0, "zayif_dugum": ["d4"]}


def test_rapor_llm_yoksa_sayilardan_kurulur(monkeypatch):
    monkeypatch.delenv("AFET_LLM_ADRES", raising=False)
    metin, yontem = calistir(llm.durum_raporu(OZET))
    assert yontem == "kural"
    assert "3 SOS" in metin and "d4" in metin and "1 tanesi öncelik 1" in metin


def test_rapor_llm_ile(llm_var):
    llm_var("<think>x</think>Son 10 dakikada 3 SOS geldi.")
    assert calistir(llm.durum_raporu(OZET)) == ("Son 10 dakikada 3 SOS geldi.", "llm")


def test_rapor_llm_hatasinda_kurala_duser(llm_var):
    llm_var(OSError("yok"))
    assert calistir(llm.durum_raporu(OZET))[1] == "kural"


def test_telefon_numarasi_kisi_sayisi_sanilmaz():
    # Gercek deprem mesajinda goruldu: numaranin hemen arkasinda "kisi" yaziyordu.
    sonuc = llm.kural_triyaj("Ulasilamayan numara 05325182777 kisi enkaz altinda")
    assert sonuc.kisi_sayisi is None


def test_rapor_uydurma_sayi_iceriyorsa_kurala_duser(llm_var):
    llm_var("Son 10 dakikada 7 SOS geldi.")
    assert calistir(llm.durum_raporu(OZET))[1] == "kural"


def test_rapor_dugum_numarasi_uydurma_sayilmaz(llm_var):
    llm_var("Son 10 dakikada 3 SOS geldi, d4 zayıf.")
    assert calistir(llm.durum_raporu(OZET))[1] == "llm"


def test_rapor_olgulari_turkce_satirlar():
    olgular = llm.rapor_olgulari(OZET)
    assert "Gelen SOS sayısı: 3" in olgular and "oncelik1" not in olgular


def test_kural_raporu_direk_binalarini_sayar():
    assert "2 yıkık bina" in llm.kural_raporu(OZET)
    assert "Direk kamerasının yıkık bulduğu bina: 2" in llm.rapor_olgulari(OZET)
