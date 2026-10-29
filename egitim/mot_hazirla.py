"""MOT20 etiketli dizilerini tek sinifli (insan) YOLO veri setine cevirir.

MOT20 insanlari sinif 1/2/7 ile etiketler; digerleri ve gorunurlugu dusuk kutular
modeli yanilttigi icin atilir. Goruntuler kopyalanmaz, sembolik baglantiyla baglanir.
"""
import argparse
import configparser
import os
from pathlib import Path

# MOT20'te insan sayilan siniflar: 1 yaya, 2 aractaki kisi, 7 duran kisi.
INSAN_SINIFLARI = {1, 2, 7}


def satirlari_oku(gt_yolu, en_az_gorunurluk):
    """gt.txt satirlarini kare -> (sol, ust, gen, yuk) sozlugune indirger."""
    kareler = {}
    for satir in Path(gt_yolu).read_text().splitlines():
        parca = satir.strip().split(",")
        if len(parca) < 9:
            continue
        kare = int(float(parca[0]))
        sol, ust, gen, yuk = (float(p) for p in parca[2:6])
        dikkate_al = int(float(parca[6]))
        sinif = int(float(parca[7]))
        gorunurluk = float(parca[8])
        if dikkate_al == 0 or sinif not in INSAN_SINIFLARI or gorunurluk < en_az_gorunurluk:
            continue
        kareler.setdefault(kare, []).append((sol, ust, gen, yuk))
    return kareler


def yolo_satiri(sol, ust, gen, yuk, im_gen, im_yuk):
    """Kutuyu goruntu sinirlarina kisarip YOLO satirina cevirir; yoksa None.

    Kisma sonrasi 1 pikselden kucuk kutular egitimde gurultu olur, atilir.
    """
    sol2 = max(0.0, sol)
    ust2 = max(0.0, ust)
    sag = min(float(im_gen), sol + gen)
    alt = min(float(im_yuk), ust + yuk)
    gen2 = sag - sol2
    yuk2 = alt - ust2
    if gen2 < 1 or yuk2 < 1:
        return None
    return "0 {:.6f} {:.6f} {:.6f} {:.6f}".format(
        (sol2 + sag) / 2 / im_gen,
        (ust2 + alt) / 2 / im_yuk,
        gen2 / im_gen,
        yuk2 / im_yuk,
    )


def dizi_hazirla(dizi_klasoru, cikti, adim, en_az_gorunurluk):
    """Tek MOT dizisini isler; (alinan kare, yazilan kutu) sayilarini dondurur."""
    dizi_klasoru = Path(dizi_klasoru)
    cikti = Path(cikti)
    ayar = configparser.ConfigParser()
    ayar.read(dizi_klasoru / "seqinfo.ini")
    sek = ayar["Sequence"]
    im_gen = int(sek["imWidth"])
    im_yuk = int(sek["imHeight"])
    uzunluk = int(sek["seqLength"])
    im_dir = sek.get("imDir", "img1")
    im_ext = sek.get("imExt", ".jpg")
    kutular = satirlari_oku(dizi_klasoru / "gt" / "gt.txt", en_az_gorunurluk)
    (cikti / "images").mkdir(parents=True, exist_ok=True)
    (cikti / "labels").mkdir(parents=True, exist_ok=True)
    kare_sayisi = 0
    kutu_sayisi = 0
    for kare in range(1, uzunluk + 1, adim):
        kaynak = dizi_klasoru / im_dir / f"{kare:06d}{im_ext}"
        # Eksik kare atlaniyor ki tek bozuk dosya tum kurulumu durdurmasin.
        if not kaynak.exists():
            continue
        kok = f"{dizi_klasoru.name}_{kare:06d}"
        bag = cikti / "images" / f"{kok}{im_ext}"
        if not (bag.is_symlink() or bag.exists()):
            os.symlink(kaynak.resolve(), bag)
        satirlar = []
        for sol, ust, gen, yuk in kutular.get(kare, []):
            satir = yolo_satiri(sol, ust, gen, yuk, im_gen, im_yuk)
            if satir is not None:
                satirlar.append(satir)
        metin = "\n".join(satirlar)
        if metin:
            metin += "\n"
        (cikti / "labels" / f"{kok}.txt").write_text(metin)
        kare_sayisi += 1
        kutu_sayisi += len(satirlar)
    return kare_sayisi, kutu_sayisi


def main():
    arg = argparse.ArgumentParser(description="MOT20 dizilerini YOLO veri setine cevirir")
    arg.add_argument("--mot", required=True, help="MOT20/train klasoru")
    arg.add_argument("--cikti", required=True, help="YOLO veri seti klasoru")
    arg.add_argument("--adim", type=int, default=10, help="kac karede bir alinir (varsayilan 10)")
    arg.add_argument("--en-az-gorunurluk", type=float, default=0.25,
                     help="kabul edilen en az gorunurluk (varsayilan 0.25)")
    o = arg.parse_args()
    mot = Path(o.mot)
    cikti = Path(o.cikti)
    toplam_kare = 0
    toplam_kutu = 0
    for dizi in sorted(p for p in mot.iterdir() if (p / "seqinfo.ini").exists()):
        kare, kutu = dizi_hazirla(dizi, cikti, o.adim, o.en_az_gorunurluk)
        print(f"{dizi.name}: {kare} kare, {kutu} kutu")
        toplam_kare += kare
        toplam_kutu += kutu
    # YOLO egitimi tek dizin listesi ister; train ve val ayni klasoru isaret eder.
    (cikti / "mot20.yaml").write_text(
        "# MOT20, CC BY-NC-SA 3.0, Dendorfer ve ark. 2020\n"
        f"path: {cikti.resolve()}\n"
        "train: images\n"
        "val: images\n"
        "names: {0: person}\n"
    )
    print(f"toplam: {toplam_kare} kare, {toplam_kutu} kutu")


if __name__ == "__main__":
    main()