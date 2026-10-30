"""Egitilmis hasar modelleriyle egitimsiz iyilestirmelerin olcumu: TTA, AdaBN, topluluk, yalniz bas ince ayari.

AdaBN: BatchNorm istatistikleri test bolgesinin etiketsiz kesitlerinden yeniden hesaplanir (etiket kullanmaz).
TTA: 8 cevirme/dondurme tahmininin ortalamasi. Topluluk: 4 mimarinin olasilik ortalamasi.
Bas ince ayari: govde dondurulur, yalniz son katman k etiketle egitilir (tum agin guncellenmesi az ornekle asiri uyuyordu).
  python -m egitim.hasar_degerlendir --veri ... --test-bolge AOI04 --modeller deney
"""
import argparse
import copy
import json
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from egitim.hasar_model import MIMARI, Veri, auc, duyarlilik, hazirla

KURULUMLAR = [("erken", False), ("siyam", False), ("siyam", True), ("sonrasi", False)]


def tahmin(m, v, indeks, cihaz, norm, tta: bool) -> np.ndarray:
    m.eval()
    sonuc = []
    with torch.no_grad():
        for i in range(0, len(indeks), 128):
            t = hazirla(v.al(indeks[i:i + 128]), cihaz, False, norm)
            if tta:
                p = torch.stack([torch.sigmoid(m(torch.rot90(t.flip(3) if c else t, r, (2, 3))))
                                 for c in (0, 1) for r in range(4)]).mean(0)
            else:
                p = torch.sigmoid(m(t))
            sonuc.append(p.cpu().numpy())
    return np.concatenate(sonuc)


def adabn(m, v, indeks, cihaz, norm):
    # Momentum None: kumulatif ortalama; onceki (egitim bolgesi) istatistikleri tamamen birakilir.
    for k in m.modules():
        if isinstance(k, torch.nn.BatchNorm2d):
            k.reset_running_stats()
            k.momentum = None
    m.train()
    with torch.no_grad():
        for i in range(0, len(indeks), 128):
            m(hazirla(v.al(np.sort(indeks[i:i + 128])), cihaz, False, norm))
    m.eval()


def bas_katmani(m) -> list:
    if hasattr(m, "bas"):
        return list(m.bas.parameters())
    return list(m.ag.fc.parameters())


def bas_ince_ayar(m, v, secilen, cihaz, norm, adim=200):
    for p in m.parameters():
        p.requires_grad_(False)
    parametreler = bas_katmani(m)
    for p in parametreler:
        p.requires_grad_(True)
    eniyi = torch.optim.AdamW(parametreler, lr=1e-3, weight_decay=1e-3)
    poz = max(v.y[secilen].sum(), 1)
    agirlik = torch.tensor((len(secilen) - poz) / poz, device=cihaz)
    # Govde BN istatistikleri sabit kalsin: eval modunda egitilir.
    m.eval()
    for _ in range(adim):
        j = np.sort(np.random.choice(secilen, min(64, len(secilen)), replace=False))
        girdi = hazirla(v.al(j), cihaz, True, norm)
        eniyi.zero_grad()
        F.binary_cross_entropy_with_logits(m(girdi), torch.tensor(v.y[j], dtype=torch.float32, device=cihaz),
                                           pos_weight=agirlik).backward()
        eniyi.step()
    for p in m.parameters():
        p.requires_grad_(True)


def olc(p, e) -> dict:
    return {"auc": auc(p, e), "duyarlilik_ya10": duyarlilik(p, e, 0.10)}


def main():
    ayrac = argparse.ArgumentParser()
    ayrac.add_argument("--veri", nargs="+", required=True)
    ayrac.add_argument("--test-bolge", required=True)
    ayrac.add_argument("--modeller", default="deney")
    ayrac.add_argument("--ince-ayar", type=int, nargs="*", default=[50, 100])
    ayrac.add_argument("--kurulumlar", nargs="*", default=["erken", "siyam", "siyam_norm", "sonrasi"])
    ayrac.add_argument("--zor-negatif-m", type=float, default=0,
                       help="yalniz bir hasarli binaya bu kadar metreden yakin hasarsizlar negatif sayilir")
    ayrac.add_argument("--tohum", type=int, default=0)
    secim = ayrac.parse_args()
    cihaz = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(0)
    np.random.seed(0)
    v = Veri(secim.veri)
    test = np.flatnonzero((v.y >= 0) & v.bolgede(secim.test_bolge))
    if secim.zor_negatif_m:
        # Mahalle ezberi testi: enkazli mahalledeki saglam binalar; model cevreye bakiyorsa burada duser.
        poz = test[v.y[test] == 1]
        neg = test[v.y[test] == 0]
        dy = (v.lat[neg, None] - v.lat[None, poz]) * 111_195
        dx = (v.lon[neg, None] - v.lon[None, poz]) * 111_195 * np.cos(np.radians(v.lat[neg, None]))
        yakin = np.hypot(dx, dy).min(axis=1) <= secim.zor_negatif_m
        test = np.sort(np.concatenate([poz, neg[yakin]]))
        print(f"zor negatif: {yakin.sum()}/{len(neg)} hasarsiz bina hasarliya {secim.zor_negatif_m:.0f} m'den yakin")
    et = v.y[test] == 1
    sonuc = {"test_bolge": secim.test_bolge, "test_n": int(len(test)), "test_pozitif": int(et.sum())}
    olasilik = {}
    for mimari, norm in KURULUMLAR:
        ad = f"{mimari}{'_norm' if norm else ''}"
        if ad not in secim.kurulumlar:
            continue
        m = MIMARI[mimari]().to(cihaz)
        dosya = f"model_{ad}_{secim.test_bolge.replace('*', 'hepsi')}_t{secim.tohum}.pt"
        m.load_state_dict(torch.load(Path(secim.modeller) / dosya, map_location=cihaz))
        temel = copy.deepcopy(m.state_dict())
        p = {"duz": tahmin(m, v, test, cihaz, norm, False), "tta": tahmin(m, v, test, cihaz, norm, True)}
        adabn(m, v, test, cihaz, norm)
        p["adabn"] = tahmin(m, v, test, cihaz, norm, False)
        p["adabn_tta"] = tahmin(m, v, test, cihaz, norm, True)
        olasilik[ad] = p
        sonuc[ad] = {k: olc(x, et) for k, x in p.items()}
        print(ad, {k: round(x["auc"], 3) for k, x in sonuc[ad].items()}, flush=True)

        rng = np.random.default_rng(0)
        for k in secim.ince_ayar:
            # Olcum icin bolgede yeterli hasarli bina kalmali.
            if k // 2 > 0.8 * et.sum():
                print(f"  {ad} k={k}: atlandi (bolgede {et.sum()} hasarli)", flush=True)
                continue
            aucs = {"bas": [], "adabn_bas": []}
            for _ in range(3):
                poz, neg = test[et], test[~et]
                sec = np.concatenate([rng.choice(poz, k // 2, replace=False), rng.choice(neg, k - k // 2, replace=False)])
                kalan = np.setdiff1d(test, sec)
                ek = v.y[kalan] == 1
                for tur in aucs:
                    m.load_state_dict(temel)
                    if tur == "adabn_bas":
                        adabn(m, v, test, cihaz, norm)
                    bas_ince_ayar(m, v, sec, cihaz, norm)
                    aucs[tur].append(auc(tahmin(m, v, kalan, cihaz, norm, False), ek))
            sonuc[ad][f"ince_ayar_{k}"] = aucs
            print(f"  {ad} k={k}: " + ", ".join(f"{t} {np.mean(a):.3f}" for t, a in aucs.items()), flush=True)

    for tur in ("duz", "tta", "adabn", "adabn_tta"):
        p = np.mean([olasilik[a][tur] for a in olasilik], axis=0)
        sonuc[f"topluluk_{tur}"] = olc(p, et)
    print("topluluk", {t: round(sonuc[f'topluluk_{t}']['auc'], 3) for t in ("duz", "tta", "adabn", "adabn_tta")})
    ek = f"_zor{secim.zor_negatif_m:.0f}" if secim.zor_negatif_m else ""
    json.dump(sonuc, open(Path(secim.modeller) / f"degerlendirme_{secim.test_bolge.replace('*', 'hepsi')}{ek}.json", "w"), indent=1)


if __name__ == "__main__":
    main()
