"""2. asama: bina blogu hasar siniflandiricisi (Antakya, oncesi/sonrasi uydu kesiti -> hasarli mi).

Girdi 7 kanal: oncesi RGB, sonrasi RGB, blok maskesi; 64x64. Model ImageNet onegitimli ResNet18,
ilk katmani 7 kanala uyarlanmis. Test parcasi (031133023303) egitime hic girmez; esik dogrulama
kumesinde secilir. scripts/hatay_olc.py ile ayni test parcasi ve ayni etiket tanimi: karsilastirilabilir.
  ~/afet-yolo/venv/bin/python -m egitim.hasar_siniflandirici
"""
import argparse
import glob
import json
import time
from pathlib import Path

import numpy as np
import torch
import torchvision

KOK = Path(__file__).resolve().parent.parent
HATAY = KOK / "data" / "gercek" / "hatay"
TEST_PARCA = "031133023303"
BOYUT = 64


def kesitler() -> dict:
    onbellek = HATAY / "kesitler.npz"
    if onbellek.exists():
        return dict(np.load(onbellek))
    # Kesit cikarmak icin gerekir; egitim sunucusunda hazir npz ile calisilir.
    import cv2
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.warp import transform_geom
    from rasterio.windows import from_bounds

    from scripts.hatay_olc import NEGATIF, POZITIF, kutu

    bloklar = json.load(open(next(HATAY.glob("monit/*builtUpA*.json"))))["features"]
    x, y, parca, sinif = [], [], [], []
    for once_yol in sorted(glob.glob(str(HATAY / "maxar" / "*_2022-12-22.tif"))):
        p = Path(once_yol).name.split("_")[0]
        with rasterio.open(once_yol) as o, rasterio.open(once_yol.replace("2022-12-22", "2023-02-11")) as s:
            for f in bloklar:
                g = transform_geom("EPSG:4326", o.crs, f["geometry"])
                l, b, r, t = kutu(g["coordinates"])
                if l < o.bounds.left or r > o.bounds.right or b < o.bounds.bottom or t > o.bounds.top:
                    continue
                w = from_bounds(l - 4, b - 4, r + 4, t + 4, o.transform).round_offsets().round_lengths()
                a, c = o.read([1, 2, 3], window=w), s.read([1, 2, 3], window=w)
                if a.shape != c.shape or min(a.shape[1:]) < 8:
                    continue
                m = geometry_mask([g], out_shape=a.shape[1:], transform=o.window_transform(w), invert=True)
                if (a.sum(axis=0) == 0).mean() > 0.2 or (c.sum(axis=0) == 0).mean() > 0.2:
                    continue  # goruntu kenarina tasan blok
                yigin = np.concatenate([a, c, m[None] * 255]).astype(np.uint8)
                # OpenCV en fazla 4 kanal kucultur: kanallar tek tek.
                x.append(np.stack([cv2.resize(k, (BOYUT, BOYUT), interpolation=cv2.INTER_AREA) for k in yigin], axis=-1))
                d = f["properties"]["damage_gra"]
                y.append(1 if d in POZITIF else 0 if d in NEGATIF else -1)
                parca.append(p)
                sinif.append(d)
        print(f"{p}: {len(x)} kesit")
    veri = {"x": np.stack(x), "y": np.array(y), "parca": np.array(parca), "sinif": np.array(sinif)}
    np.savez_compressed(onbellek, **veri)
    return veri


def model_kur() -> torch.nn.Module:
    m = torchvision.models.resnet18(weights="IMAGENET1K_V1")
    eski = m.conv1.weight.data
    m.conv1 = torch.nn.Conv2d(7, 64, 7, 2, 3, bias=False)
    # Oncesi ve sonrasi ayni RGB agirligini yarisiyla paylasir; maske kanali sifirdan baslar.
    m.conv1.weight.data = torch.cat([eski / 2, eski / 2, torch.zeros_like(eski[:, :1])], dim=1)
    m.fc = torch.nn.Linear(512, 1)
    return m


def tensor(x: np.ndarray) -> torch.Tensor:
    return torch.from_numpy(x).permute(0, 3, 1, 2).float() / 255


def cogalt(t: torch.Tensor) -> torch.Tensor:
    # Uydu goruntusunde yon anlamsiz: rastgele cevirme ve 90 derece dondurme.
    if np.random.rand() < 0.5:
        t = t.flip(3)
    return torch.rot90(t, int(np.random.randint(4)), (2, 3))


def tahmin(m, x, cihaz) -> np.ndarray:
    m.eval()
    with torch.no_grad():
        return np.concatenate([torch.sigmoid(m(tensor(x[i:i + 256]).to(cihaz))).cpu().numpy()[:, 0]
                               for i in range(0, len(x), 256)])


def auc(puan, etiket) -> float:
    sira = puan.argsort().argsort() + 1
    p, n = etiket.sum(), (~etiket).sum()
    return float((sira[etiket].sum() - p * (p + 1) / 2) / (p * n))


def main():
    ayrac = argparse.ArgumentParser()
    ayrac.add_argument("--tur", type=int, default=30)
    ayrac.add_argument("--tohum", type=int, default=0)
    ayrac.add_argument("--veri", help="egitim.hasar_veri ciktisi (tum bolgeler); yoksa yalniz Antakya")
    ayrac.add_argument("--cikti", default=str(HATAY))
    ayrac.add_argument("--test-bolge", help="bu bolge (ör. AOI04) tamamen test; egitime hic girmez")
    secim = ayrac.parse_args()
    torch.manual_seed(secim.tohum)
    torch.set_num_threads(4)
    rng = np.random.default_rng(secim.tohum)
    v = dict(np.load(secim.veri)) if secim.veri else kesitler()
    bolge = v.get("bolge", np.full(len(v["y"]), "AOI11"))
    etiketli = v["y"] >= 0
    test_parcasi = (bolge == secim.test_bolge) if secim.test_bolge else (v["parca"] == TEST_PARCA) & (bolge == "AOI11")
    test = etiketli & test_parcasi
    havuz = np.flatnonzero(etiketli & ~test_parcasi)
    rng.shuffle(havuz)
    dogrulama, egitim = havuz[: len(havuz) * 15 // 100], havuz[len(havuz) * 15 // 100:]
    print(f"egitim {len(egitim)} (pozitif {v['y'][egitim].sum()}), dogrulama {len(dogrulama)} "
          f"(pozitif {v['y'][dogrulama].sum()}), test {test.sum()} (pozitif {v['y'][test].sum()})")

    cihaz = "cuda" if torch.cuda.is_available() else "cpu"
    m = model_kur().to(cihaz)
    eniyi = torch.optim.AdamW(m.parameters(), lr=3e-4, weight_decay=1e-4)
    poz = v["y"][egitim].sum()
    kayip = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor((len(egitim) - poz) / poz, device=cihaz))
    xe, ye = v["x"][egitim], torch.tensor(v["y"][egitim], dtype=torch.float32)
    en_iyi_auc, en_iyi_durum = -1, None
    basla = time.perf_counter()
    for tur in range(secim.tur):
        m.train()
        sira = rng.permutation(len(egitim))
        for i in range(0, len(sira), 64):
            j = sira[i:i + 64]
            girdi = cogalt(tensor(xe[j])).to(cihaz)
            eniyi.zero_grad()
            kayip(m(girdi)[:, 0], ye[j].to(cihaz)).backward()
            eniyi.step()
        d_auc = auc(tahmin(m, v["x"][dogrulama], cihaz), v["y"][dogrulama] == 1)
        if d_auc > en_iyi_auc:
            en_iyi_auc, en_iyi_durum = d_auc, {k: t.clone() for k, t in m.state_dict().items()}
        print(f"tur {tur + 1}: dogrulama AUC {d_auc:.3f}")
    m.load_state_dict(en_iyi_durum)
    sure = time.perf_counter() - basla

    pd = tahmin(m, v["x"][dogrulama], cihaz)
    ed = v["y"][dogrulama] == 1
    adaylar = np.unique(pd)
    f1 = [2 * (ed & (pd >= e)).sum() / max(ed.sum() + (pd >= e).sum(), 1) for e in adaylar]
    esik = float(adaylar[int(np.argmax(f1))])
    pt = tahmin(m, v["x"][test], cihaz)
    et = v["y"][test] == 1
    t_ = pt >= esik
    dp = (t_ & et).sum()
    print(f"\nen iyi dogrulama AUC {en_iyi_auc:.3f}, esik {esik:.3f}, egitim suresi {sure:.0f} sn ({cihaz})")
    print(f"TEST AUC {auc(pt, et):.3f}")
    print(f"test: duyarlilik {dp}/{et.sum()} (%{100 * dp / et.sum():.1f}), kesinlik {dp}/{t_.sum()} "
          f"(%{100 * dp / max(t_.sum(), 1):.1f}), yanlis alarm {(t_ & ~et).sum()}/{(~et).sum()} "
          f"(%{100 * (t_ & ~et).sum() / (~et).sum():.1f})")
    # Isletme noktalari test egrisinden okunur (ayar degil, betimleme): yanlis alarm X iken yakalanan.
    for oran in (0.05, 0.10, 0.20):
        e = np.quantile(pt[~et], 1 - oran)
        print(f"  test egrisi: yanlis alarm %{oran * 100:.0f} iken duyarlilik {(pt[et] >= e).sum()}/{et.sum()}")
    hepsi = test_parcasi
    ph = tahmin(m, v["x"][hepsi], cihaz)
    for sinif in ["Destroyed", "Damaged", "Possibly damaged"]:
        s = v["sinif"][hepsi] == sinif
        print(f"  test {sinif}: {(ph[s] >= esik).sum()}/{s.sum()} isaretlendi")
    torch.save(m.state_dict(), Path(secim.cikti) / f"hasar_resnet18_t{secim.tohum}{'_tum' if secim.veri else ''}.pt")


if __name__ == "__main__":
    main()
