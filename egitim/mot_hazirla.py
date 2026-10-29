"""MOT20 etiketli dizilerini tek sinifli (insan) YOLO veri setine donusturur (goruntuler kopyalanmaz, baglanir).

MOT20 kutulari yaya / aractaki kisi / duran kisi diye ayrilir; modelimiz tek sinifli oldugu icin
ucunu da 0 sinifinda birlestiriyoruz, diger siniflar ve zayif gorunurlukler egitimi bozmasin diye atiliyor.
"""
import argparse
import configparser
import os
from pathlib import Path

INSAN_SINIFLARI = {1, 2, 7}  # 1 yaya, 2 aractaki kisi, 7 duran kisi


def satirlari_oku(gt_yolu, en_az_gorunurluk):
    """gt.txt'yi kare numarasina gore okur; atlanan satirlar disarida birakilir."""
    kareler = {}
    for satir in Path(gt_yolu).read_text().splitlines():
        if not satir.strip():
            continue
        p = satir.split(",")
        if int(p[6]) != 1 or int(p[7]) not in INSAN_SINIFLARI or float(p[8]) < en_az_gorunurluk:
            continue
        kareler.setdefault(int(p[0]), []).append(tuple(float(x) for x in p[2:6]))
    return kareler


def yolo_satiri(sol, ust, gen, yuk, im_gen, im_yuk):
    """Kutuyu goruntu sinirlarina kirpar, YOLO satirina cevirir; kutu gecersizse None."""
    sol2 = min(max(sol, 0.0), im_gen)
    sag2 = min(max(sol + gen, 0.0), im_gen)
    ust2 = min(max(ust, 0.0), im_yuk)
    alt2 = min(max(ust + yuk, 0.0), im_yuk)
    gen2, yuk2 = sag2 - sol2, alt2 - ust2
    if gen2 < 1 or yuk2 < 1:
        return None
    return "0 {:.6f} {:.6f} {:.6f} {:.6f}".format(
        (sol2 + sag2) / 2 / im_gen, (ust2 + alt2) / 2 / im_yuk, gen2 / im_gen, yuk2 / im_yuk
    )


def dizi_hazirla(dizi_klasoru, cikti, adim, en_az_gorunurluk):
    """Bir MOT dizisini isler; (alinan kare, yazilan kutu) sayilarini dondurur."""
    dizi_klasoru = Path(dizi_klasoru)
    cikti = Path(cikti)
    ayar = configparser.ConfigParser()
    ayar.read(dizi_klasoru / "seqinfo.ini")
    seq = ayar["Sequence"]
    im_gen, im_yuk = int(seq["imWidth"]), int(seq["imHeight"])
    uzanti, im_dir = seq["imExt"], seq["imDir"]
    kareler = satirlari_oku(dizi_klasoru / "gt" / "gt.txt", en_az_gorunurluk)
    (cikti / "images").mkdir(parents=True, exist_ok=True)
    (cikti / "labels").mkdir(parents=True, exist_ok=True)
    ad = dizi_klasoru.name
    kare_sayisi = kutu_sayisi = 0
    for kare in range(1, int(seq["seqLength"]) + 1):
        if (kare - 1) % adim:
            continue
        kok = f"{ad}_{kare:06d}"
        hedef = cikti / "images" / f"{kok}{uzanti}"
        if not hedef.exists():
            os.symlink((dizi_klasoru / im_dir / f"{kare:06d}{uzanti}").resolve(), hedef)
        satirlar = [s for s in (yolo_satiri(*k, im_gen, im_yuk) for k in kareler.get(kare, [])) if s]
        (cikti / "labels" / f"{kok}.txt").write_text("\n".join(satirlar) + ("\n" if satirlar else ""))
        kare_sayisi += 1
        kutu_sayisi += len(satirlar)
    return kare_sayisi, kutu_sayisi


def main():
    ap = argparse.ArgumentParser(description="MOT20 dizilerini tek sinifli YOLO setine donusturur")
    ap.add_argument("--mot", required=True, help="MOT20/train klasoru")
    ap.add_argument("--cikti", required=True, help="cikti klasoru")
    ap.add_argument("--adim", type=int, default=10, help="kac karede bir alinir")
    ap.add_argument("--en-az-gorunurluk", type=float, default=0.25)
    args = ap.parse_args()
    mot, cikti = Path(args.mot), Path(args.cikti)
    cikti.mkdir(parents=True, exist_ok=True)
    toplam_kare = toplam_kutu = 0
    for dizi in sorted(p for p in mot.iterdir() if (p / "seqinfo.ini").exists()):
        kare, kutu = dizi_hazirla(dizi, cikti, args.adim, args.en_az_gorunurluk)
        print(dizi.name, kare, "kare,", kutu, "kutu")
        toplam_kare += kare
        toplam_kutu += kutu
    (cikti / "mot20.yaml").write_text(
        "# MOT20, CC BY-NC-SA 3.0, Dendorfer ve ark. 2020\n"
        f"path: {cikti.resolve()}\n"
        "train: images\n"
        "val: images\n"
        "names: {0: person}\n"
    )
    print("toplam", toplam_kare, "kare,", toplam_kutu, "kutu")


if __name__ == "__main__":
    main()