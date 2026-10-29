"""Birden fazla YOLO modelini birden fazla veri setinde olcer, sonucu Markdown tablosu yazar.

Her uclem (model, veri, imgsz) tek satir ilerleme ile ekrana yazilir; CUDA bellegi yetmezse
batch=1 ile bir kez daha denenir, o da olmazsa tabloya "bellek yetmedi" yazilir.
  python scripts/yolo_karsilastir.py --model n=yolo11n.pt --veri mot20=data/mot20.yaml --imgsz 640 1280
"""
import argparse
import os
from datetime import datetime

import torch
import ultralytics
from ultralytics import YOLO


def ad_yol(deger):
    ad, _, yol = deger.partition("=")
    if not ad or not yol:
        raise argparse.ArgumentTypeError(f"ad=yol bicimi bekleniyordu: {deger}")
    return ad, os.path.expanduser(yol)


def ad_veri(deger):
    ad, yol = ad_yol(deger)
    if ":" in yol:
        yol, split = yol.rsplit(":", 1)
    else:
        split = "val"
    return ad, yol, split or "val"


def virgul(x):
    # Tablo degerleri Turkce yazimda oldugu gibi virgulle ayrilir.
    return f"{x:.3f}".replace(".", ",")


def olc(yol, veri, split, imgsz, batch, sinif):
    m = YOLO(yol)
    for denenen in (batch, 1):
        try:
            r = m.val(data=veri, split=split, imgsz=imgsz, batch=denenen, classes=[sinif],
                      device=0, max_det=500, plots=False, verbose=False)
            return {"map50": r.box.map50, "map": r.box.map, "kesinlik": r.box.mp,
                    "duyarlilik": r.box.mr, "ms": sum(r.speed.values())}
        except torch.OutOfMemoryError:
            # onceki denemenin ayirdigi bellek serbest birakilmazsa kucuk batch de yetmez.
            torch.cuda.empty_cache()
    return None


def ciz(satirlar, model_adlari, veri_adlari, imgszz):
    kolonlar = [(v_ad, imgsz) for v_ad, _ in veri_adlari for imgsz in imgszz]
    bul = {(m, v, s): sonuc for m, v, s, sonuc in satirlar}
    metin = [
        "# YOLO karsilastirma",
        "",
        f"- Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        f"- GPU: {torch.cuda.get_device_name(0)}",
        f"- ultralytics: {ultralytics.__version__}",
        f"- torch: {torch.__version__}",
        "",
        "## mAP@0,5",
        "",
        "| model | " + " | ".join(f"{v} ({s})" for v, s in kolonlar) + " |",
        "| " + " | ".join(["---"] * (len(kolonlar) + 1)) + " |",
    ]
    for m_ad in model_adlari:
        hucreler = []
        for v_ad, imgsz in kolonlar:
            sonuc = bul[(m_ad, v_ad, imgsz)]
            hucreler.append(virgul(sonuc["map50"]) if sonuc else "bellek yetmedi")
        metin.append("| " + m_ad + " | " + " | ".join(hucreler) + " |")

    metin += [
        "",
        "## Ayrintilar",
        "",
        "| model | veri | imgsz | mAP@0,5 | mAP@0,5:0,95 | kesinlik | duyarlılık | ms/görüntü |",
        "| " + " | ".join(["---"] * 8) + " |",
    ]
    for m_ad, v_ad, imgsz, sonuc in satirlar:
        if sonuc:
            hucreler = [virgul(sonuc["map50"]), virgul(sonuc["map"]), virgul(sonuc["kesinlik"]),
                        virgul(sonuc["duyarlilik"]), virgul(sonuc["ms"])]
        else:
            hucreler = ["bellek yetmedi"] + ["-"] * 4
        metin.append(f"| {m_ad} | {v_ad} | {imgsz} | " + " | ".join(hucreler) + " |")
    return "\n".join(metin) + "\n"


def main():
    ayrac = argparse.ArgumentParser(description="YOLO modellerini veri setlerinde karsilastirir")
    ayrac.add_argument("--model", action="append", type=ad_yol, required=True, metavar="AD=YOL",
                       help="olculacak model, tekrarlanabilir; ~ acilir")
    ayrac.add_argument("--veri", action="append", type=ad_veri, required=True, metavar="AD=YAML[:SPLIT]",
                       help="veri seti yamli, split verilmezse val")
    ayrac.add_argument("--imgsz", type=int, nargs="+", default=[640], help="goruntu boyutlari")
    ayrac.add_argument("--batch", type=int, default=8)
    ayrac.add_argument("--sinif", type=int, default=0, help="olculecek sinif kimligi")
    ayrac.add_argument("--cikti", help="Markdown dosyasi; verilmezse ekrana basilir")
    secim = ayrac.parse_args()

    satirlar = []
    toplam = len(secim.model) * len(secim.veri) * len(secim.imgsz)
    for m_ad, m_yol in secim.model:
        for v_ad, v_yol, v_split in secim.veri:
            for imgsz in secim.imgsz:
                sonuc = olc(m_yol, v_yol, v_split, imgsz, secim.batch, secim.sinif)
                satirlar.append((m_ad, v_ad, imgsz, sonuc))
                durum = f"mAP@0,5 {virgul(sonuc['map50'])}" if sonuc else "bellek yetmedi"
                print(f"[{len(satirlar)}/{toplam}] {m_ad} / {v_ad} / {imgsz}: {durum}")

    metin = ciz(satirlar, [ad for ad, _ in secim.model],
                [(ad, split) for ad, _, split in secim.veri], secim.imgsz)
    if secim.cikti:
        with open(secim.cikti, "w") as f:
            f.write(metin)
        print(f"yazildi: {secim.cikti}")
    else:
        print(metin)


if __name__ == "__main__":
    main()