"""xBD (xView2, Hugging Face xview2-taco kopyasi) -> hasar_siniflandirici ile ayni bicimde kesit veri seti.

Lisans CC BY-NC-SA 4.0 (ticari olmayan kullanim); goruntu Maxar Open Data, etiket Gupta vd. 2019.
Hasar kodu: 0 hasarsiz, 1 hafif, 2 agir, 3 yikik, 4 siniflandirilmamis.
Copernicus ile ayni tanim: pozitif = agir + yikik, negatif = hasarsiz, hafif belirsiz (-1), 4 atlanir.
Bellek icin: goruntu basina en fazla 2 x pozitif (en az 2) negatif bina alinir.
  python -m egitim.xbd_veri --zip xbd/xview2.zip --cikti xbd/kesitler.npz
"""
import argparse
import io
import zipfile
from multiprocessing import Pool

import cv2
import numpy as np
import pyarrow.parquet as pq

BOYUT = 64
PAY = 8  # piksel; bina cevresinden biraz baglam
BELIRSIZSIZ = False
ORAN = 1.0  # bina basina alinma olasiligi; bellek icin isci icinde seyreltilir
SUTUNLAR = ["ml:source_file", "ml:disaster", "ml:damage", "ml:polygon_xy", "ml:polygon_len", "internal:relative_path"]
ZIP = None


def ac(yol, ayar):
    # Python 3.14'te isciler forkserver ile baslar, ana surecin global degerlerini almaz: acikca verilir.
    global ZIP, BOYUT, PAY, BELIRSIZSIZ, ORAN
    ZIP = zipfile.ZipFile(yol)
    BOYUT, PAY, BELIRSIZSIZ, ORAN = ayar


def resim(yol: str) -> np.ndarray:
    return cv2.cvtColor(cv2.imdecode(np.frombuffer(ZIP.read(yol), np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)


def isle(satir: dict) -> list:
    rng = np.random.default_rng(abs(hash(satir["ml:source_file"])) % 2**32)
    hasar = np.array(satir["ml:damage"])
    pozitif = int(np.isin(hasar, (2, 3)).sum())
    negatif = np.flatnonzero(hasar == 0)
    secilen_negatif = set(rng.choice(negatif, min(len(negatif), max(2, 2 * pozitif)), replace=False).tolist())
    on = f"DATA/{satir['internal:relative_path']}/"
    a, c = resim(on + "pre.png"), resim(on + "post.png")
    xy = np.array(satir["ml:polygon_xy"]).reshape(-1, 2)
    sonuc, bas = [], 0
    for i, (d, n) in enumerate(zip(hasar, satir["ml:polygon_len"])):
        halka = xy[bas:bas + n]
        bas += n
        if d == 4 or (d == 0 and i not in secilen_negatif) or (d == 1 and BELIRSIZSIZ) or rng.random() > ORAN:
            continue
        x0, y0 = np.floor(halka.min(axis=0)).astype(int) - PAY
        x1, y1 = np.ceil(halka.max(axis=0)).astype(int) + PAY
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, a.shape[1]), min(y1, a.shape[0])
        if x1 - x0 < 8 or y1 - y0 < 8:
            continue
        m = np.zeros(a.shape[:2], np.uint8)
        cv2.fillPoly(m, [np.round(halka).astype(np.int32)], 255)
        yigin = np.concatenate([a[y0:y1, x0:x1], c[y0:y1, x0:x1], m[y0:y1, x0:x1, None]], axis=2)
        kesit = np.stack([cv2.resize(yigin[..., k], (BOYUT, BOYUT), interpolation=cv2.INTER_AREA) for k in range(7)], -1)
        etiket = 1 if d in (2, 3) else 0 if d == 0 else -1
        sinif = ["no-damage", "minor-damage", "major-damage", "destroyed"][d]
        sonuc.append((kesit, etiket, satir["ml:source_file"], sinif, "xbd:" + satir["ml:disaster"]))
    return sonuc


def main():
    ayrac = argparse.ArgumentParser()
    ayrac.add_argument("--zip", required=True)
    ayrac.add_argument("--cikti", required=True)
    ayrac.add_argument("--isci", type=int, default=8)
    ayrac.add_argument("--boyut", type=int, default=64)
    ayrac.add_argument("--pay", type=int, default=8)
    ayrac.add_argument("--sinir", type=int, default=10**9, help="pozitif ve negatiften en fazla kac kesit")
    ayrac.add_argument("--belirsizsiz", action="store_true", help="hafif hasarlilari hic alma")
    ayrac.add_argument("--oran", type=float, default=1.0, help="her binanin alinma olasiligi")
    secim = ayrac.parse_args()
    global BOYUT, PAY, BELIRSIZSIZ, ORAN
    BOYUT, PAY, BELIRSIZSIZ, ORAN = secim.boyut, secim.pay, secim.belirsizsiz, secim.oran
    z = zipfile.ZipFile(secim.zip)
    tablo = pq.read_table(io.BytesIO(z.read("METADATA/sample.parquet")), columns=SUTUNLAR).to_pylist()
    print(f"{len(tablo)} goruntu cifti")
    with Pool(secim.isci, initializer=ac, initargs=(secim.zip, (BOYUT, PAY, BELIRSIZSIZ, ORAN))) as havuz:
        satirlar = []
        for i, s in enumerate(havuz.imap_unordered(isle, tablo, chunksize=16)):
            satirlar.extend(s)
            if (i + 1) % 1000 == 0:
                print(f"{i + 1}/{len(tablo)}, {len(satirlar)} kesit", flush=True)
    rng = np.random.default_rng(0)
    # Sinif basina sinir: afetler arasi dengeyi bozmamak icin rastgele alt kume.
    secilen = []
    for e in (1, 0, -1):
        i = [k for k, s in enumerate(satirlar) if s[1] == e]
        secilen += rng.choice(i, min(len(i), secim.sinir), replace=False).tolist() if i else []
    satirlar = [satirlar[k] for k in sorted(secilen)]
    x, y, parca, sinif, bolge = zip(*satirlar)
    y = np.array(y)
    np.save(secim.cikti.replace(".npz", "_x.npy"), np.stack(x))
    np.savez(secim.cikti, y=y, parca=np.array(parca), sinif=np.array(sinif), bolge=np.array(bolge))
    print(f"toplam {len(y)} kesit, pozitif {(y == 1).sum()}, negatif {(y == 0).sum()}, belirsiz {(y == -1).sum()}")


if __name__ == "__main__":
    main()
