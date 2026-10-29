"""mot_hazirla betigini sahte bir MOT20 dizisiyle sinar (goruntu icerigi okunmaz)."""
import importlib.util
import sys
from pathlib import Path

import pytest

BETIK = Path(__file__).resolve().parent.parent / "egitim" / "mot_hazirla.py"
_spec = importlib.util.spec_from_file_location("mot_hazirla", BETIK)
mot_hazirla = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mot_hazirla)

# Satir 4 sinif 3, satir 5 dikkate_al=0, satir 6 gorunurluk 0.1; bunlar hic yazilmamali.
KARE1_BEKLENEN = {
    "0 0.200000 0.400000 0.200000 0.400000",  # sinif 1
    "0 0.450000 0.200000 0.100000 0.200000",  # sinif 2
    "0 0.650000 0.200000 0.100000 0.200000",  # sinif 7
    "0 0.500000 0.500000 1.000000 1.000000",  # goruntu disina tasan kutu, kirpildi
}
ATLANANLAR = {
    "0 0.100000 0.300000 0.100000 0.200000",  # sinif 3
    "0 0.300000 0.200000 0.100000 0.200000",  # dikkate_al=0
    "0 0.500000 0.500000 0.100000 0.200000",  # gorunurluk 0.1
}


def dizi_kur(kok: Path) -> Path:
    """imWidth=100 imHeight=50 seqLength=21'lik sahte bir MOT20 dizisi kurar."""
    dizi = kok / "MOT20" / "train" / "MOT20-01"
    (dizi / "img1").mkdir(parents=True)
    (dizi / "gt").mkdir()
    for kare in range(1, 22):
        (dizi / "img1" / f"{kare:06d}.jpg").write_bytes(b"")
    (dizi / "seqinfo.ini").write_text(
        "[Sequence]\n"
        "imWidth=100\n"
        "imHeight=50\n"
        "seqLength=21\n"
        "imExt=.jpg\n"
        "imDir=img1\n"
    )
    (dizi / "gt" / "gt.txt").write_text(
        "1,1,10,10,20,20,1,1,0.9\n"
        "1,2,40,5,10,10,1,2,0.5\n"
        "1,3,60,5,10,10,1,7,0.8\n"
        "1,4,5,5,10,10,1,3,0.9\n"
        "1,5,25,5,10,10,0,1,0.9\n"
        "1,6,45,20,10,10,1,1,0.1\n"
        "1,7,-10,-5,150,60,1,1,0.9\n"
        "5,8,10,10,10,10,1,1,0.9\n"
        "21,9,20,10,10,10,1,1,0.9\n"
    )
    return dizi


@pytest.fixture
def cikti(tmp_path, monkeypatch):
    dizi = dizi_kur(tmp_path)
    hedef = tmp_path / "cikti"
    monkeypatch.setattr(
        sys, "argv", ["mot_hazirla.py", "--mot", str(dizi.parent), "--cikti", str(hedef)]
    )
    mot_hazirla.main()
    return hedef


def etiket_satirlari(cikti, kare):
    return set((cikti / "labels" / f"MOT20-01_{kare:06d}.txt").read_text().splitlines())


def test_sinif_1_2_7_alinir_3_atilir(cikti):
    assert etiket_satirlari(cikti, 1) == KARE1_BEKLENEN


def test_dikkate_al_sifir_atilir(cikti):
    assert "0 0.300000 0.200000 0.100000 0.200000" not in etiket_satirlari(cikti, 1)


def test_dusuk_gorunurluk_atilir(cikti):
    assert "0 0.500000 0.500000 0.100000 0.200000" not in etiket_satirlari(cikti, 1)


def test_adim_10_ile_yalnizca_1_11_21(cikti):
    assert sorted(p.name for p in (cikti / "images").iterdir()) == [
        "MOT20-01_000001.jpg",
        "MOT20-01_000011.jpg",
        "MOT20-01_000021.jpg",
    ]
    assert sorted(p.name for p in (cikti / "labels").iterdir()) == [
        "MOT20-01_000001.txt",
        "MOT20-01_000011.txt",
        "MOT20-01_000021.txt",
    ]


def test_kirpma_ve_oranlar(cikti):
    satirlar = etiket_satirlari(cikti, 1)
    kirpilmis = "0 0.500000 0.500000 1.000000 1.000000"  # -10,-5,150,60 -> 0,0,100,50
    assert kirpilmis in satirlar
    for satir in satirlar:
        sayilar = [float(x) for x in satir.split()[1:]]
        assert all(0.0 <= x <= 1.0 for x in sayilar)


def test_kisisiz_karede_bos_etiket(cikti):
    yol = cikti / "labels" / "MOT20-01_000011.txt"
    assert yol.exists()
    assert yol.read_text().strip() == ""


def test_goruntuler_sembolik_baglanti(tmp_path, cikti):
    yol = cikti / "images" / "MOT20-01_000001.jpg"
    assert yol.is_symlink()
    assert yol.resolve() == (tmp_path / "MOT20" / "train" / "MOT20-01" / "img1" / "000001.jpg").resolve()


def test_mot20_yaml(cikti):
    yazi = (cikti / "mot20.yaml").read_text()
    assert "person" in yazi
    assert f"path: {cikti.resolve()}" in yazi