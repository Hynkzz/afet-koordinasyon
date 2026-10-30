"""Hasar siniflandiricisi, ikinci surum: mimari karsilastirmasi, bolge farkina karsi cogaltma, yerel ince ayar.

Mimari: erken (oncesi+sonrasi+maske 7 kanal tek ag), siyam (oncesi ve sonrasi ayni agdan ayri gecer,
ozellikler ve farklari birlestirilir), sonrasi (yalniz sonrasi + maske). Test bolgesi egitime hic girmez;
dogrulama butun parcalardan secilir (ayni parcadan rastgele blok dogrulamayi iyimser gosteriyordu).
--ince-ayar: test bolgesinden k etiketli ornekle modeli uyarlar, kalan bolgede olcer (her k icin 3 tekrar).
  python -m egitim.hasar_model --veri a.npz b.npz --test-bolge AOI04 --mimari siyam --ince-ayar 20 50 100
"""
import argparse
import copy
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
import torchvision


class Veri:
    """Birden cok kesit dosyasi; x'ler mmap ile okunur, bellege tek seferde alinmaz."""

    def __init__(self, yollar: list[str]):
        self.x, meta = [], []
        for yol in yollar:
            m = dict(np.load(yol))
            self.x.append(np.load(yol.replace(".npz", "_x.npy"), mmap_mode="r"))
            meta.append(m)
        self.kaynak = np.concatenate([np.full(len(m["y"]), i) for i, m in enumerate(meta)])
        self.sira = np.concatenate([np.arange(len(m["y"])) for m in meta])
        for k in ("y", "parca", "sinif", "bolge"):
            setattr(self, k, np.concatenate([m[k].astype(str) if k != "y" else m[k] for m in meta]))
        self.parca = np.char.add(np.char.add(self.bolge, ":"), self.parca)
        # Koordinat yalniz yeni cikarilan dosyalarda var; zor negatif testi icin.
        self.lon = np.concatenate([m.get("lon", np.full(len(m["y"]), np.nan)) for m in meta])
        self.lat = np.concatenate([m.get("lat", np.full(len(m["y"]), np.nan)) for m in meta])

    def bolgede(self, ad: str) -> np.ndarray:
        """'AOI*' gibi sonu yildizli ad bir olayin tum bolgeleri (olay disarida birakma)."""
        return np.char.startswith(self.bolge, ad[:-1]) if ad.endswith("*") else self.bolge == ad

    def al(self, indeks: np.ndarray) -> np.ndarray:
        cikti = np.empty((len(indeks),) + self.x[0].shape[1:], np.uint8)
        for k in np.unique(self.kaynak[indeks]):
            s = self.kaynak[indeks] == k
            # mmap'ten sirali okumak rastgele okumadan cok hizli.
            sira = self.sira[indeks[s]]
            duzen = np.argsort(sira)
            parca = self.x[k][sira[duzen]]
            ters = np.empty_like(duzen)
            ters[duzen] = np.arange(len(duzen))
            cikti[s] = parca[ters]
        return cikti


def resnet(kanal: int) -> torch.nn.Module:
    m = torchvision.models.resnet18(weights="IMAGENET1K_V1")
    eski = m.conv1.weight.data
    m.conv1 = torch.nn.Conv2d(kanal, 64, 7, 2, 3, bias=False)
    rgb = kanal - 1  # son kanal maske
    m.conv1.weight.data = torch.cat([eski.repeat(1, rgb // 3, 1, 1) / (rgb // 3), torch.zeros_like(eski[:, :1])], 1)
    return m


class Erken(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.ag = resnet(7)
        self.ag.fc = torch.nn.Linear(512, 1)

    def forward(self, x):
        return self.ag(x)[:, 0]


class Sonrasi(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.ag = resnet(4)
        self.ag.fc = torch.nn.Linear(512, 1)

    def forward(self, x):
        return self.ag(x[:, 3:])[:, 0]


class Siyam(torch.nn.Module):
    def __init__(self):
        super().__init__()
        r = resnet(4)
        self.govde = torch.nn.Sequential(*list(r.children())[:-2])
        # Ozellik haritalarinda oncesi, sonrasi ve fark: hangi yapinin degistigi yerinde karsilastirilir.
        self.bas = torch.nn.Sequential(torch.nn.Conv2d(1536, 256, 1), torch.nn.BatchNorm2d(256), torch.nn.ReLU(),
                                       torch.nn.AdaptiveAvgPool2d(1), torch.nn.Flatten(), torch.nn.Linear(256, 1))

    def forward(self, x):
        maske = x[:, 6:7]
        a = self.govde(torch.cat([x[:, :3], maske], 1))
        b = self.govde(torch.cat([x[:, 3:6], maske], 1))
        return self.bas(torch.cat([a, b, (a - b).abs()], 1))[:, 0]


MIMARI = {"erken": Erken, "siyam": Siyam, "sonrasi": Sonrasi}


def hazirla(x: np.ndarray, cihaz, cogalt: bool, ornek_norm: bool) -> torch.Tensor:
    t = torch.from_numpy(x).to(cihaz).permute(0, 3, 1, 2).float() / 255
    if cogalt:
        n = len(t)
        # Oncesi ve sonrasi ayri parlaklik/kontrast/renk: farkli uydu, mevsim, saat.
        for bas in (0, 3):
            g = t[:, bas:bas + 3]
            kontrast = torch.empty(n, 1, 1, 1, device=cihaz).uniform_(0.7, 1.3)
            parlaklik = torch.empty(n, 1, 1, 1, device=cihaz).uniform_(-0.15, 0.15)
            renk = torch.empty(n, 3, 1, 1, device=cihaz).uniform_(0.9, 1.1)
            ort = g.mean((1, 2, 3), keepdim=True)
            t[:, bas:bas + 3] = ((g - ort) * kontrast + ort + parlaklik) * renk
        # Iki goruntu arasinda birkac piksel kayma: bakis acisi farki.
        dx, dy = np.random.randint(-4, 5, 2)
        t[:, 3:6] = torch.roll(t[:, 3:6], (int(dy), int(dx)), (2, 3))
        if np.random.rand() < 0.5:
            t = t.flip(3)
        t = torch.rot90(t, int(np.random.randint(4)), (2, 3))
    if ornek_norm:
        for bas in (0, 3):
            g = t[:, bas:bas + 3]
            t[:, bas:bas + 3] = (g - g.mean((2, 3), keepdim=True)) / (g.std((2, 3), keepdim=True) + 1e-3)
    else:
        t[:, :6] = (t[:, :6] - 0.45) / 0.25
    return t


def tahmin(m, v: Veri, indeks, cihaz, ornek_norm) -> np.ndarray:
    m.eval()
    sonuc = []
    with torch.no_grad():
        for i in range(0, len(indeks), 256):
            sonuc.append(torch.sigmoid(m(hazirla(v.al(indeks[i:i + 256]), cihaz, False, ornek_norm))).cpu().numpy())
    return np.concatenate(sonuc) if sonuc else np.array([])


def auc(puan, etiket) -> float:
    if etiket.sum() == 0 or (~etiket).sum() == 0:
        return float("nan")
    sira = puan.argsort().argsort() + 1
    p, n = etiket.sum(), (~etiket).sum()
    return float((sira[etiket].sum() - p * (p + 1) / 2) / (p * n))


def duyarlilik(puan, etiket, yanlis_alarm) -> float:
    e = np.quantile(puan[~etiket], 1 - yanlis_alarm)
    return float((puan[etiket] >= e).mean())


def egit(m, v, egitim, dogrulama, cihaz, tur, ornek_norm, lr=3e-4, sessiz=False):
    eniyi = torch.optim.AdamW(m.parameters(), lr=lr, weight_decay=1e-4)
    adim = max(1, len(egitim) // 128) * tur
    zamanlayici = torch.optim.lr_scheduler.OneCycleLR(eniyi, lr, total_steps=adim)
    poz = max(v.y[egitim].sum(), 1)
    agirlik = torch.tensor((len(egitim) - poz) / poz, device=cihaz)
    en_iyi, durum = -1.0, None
    for t in range(tur):
        m.train()
        karisik = np.random.permutation(egitim)
        for i in range(0, max(len(karisik) - 127, 1), 128):
            j = np.sort(karisik[i:i + 128])
            girdi = hazirla(v.al(j), cihaz, True, ornek_norm)
            hedef = torch.tensor(v.y[j], dtype=torch.float32, device=cihaz)
            eniyi.zero_grad()
            F.binary_cross_entropy_with_logits(m(girdi), hedef, pos_weight=agirlik).backward()
            eniyi.step()
            zamanlayici.step()
        if dogrulama is None:
            continue
        d = auc(tahmin(m, v, dogrulama, cihaz, ornek_norm), v.y[dogrulama] == 1)
        if not sessiz:
            print(f"tur {t + 1}: dogrulama AUC {d:.3f}", flush=True)
        if d > en_iyi:
            en_iyi, durum = d, copy.deepcopy(m.state_dict())
    if durum:
        m.load_state_dict(durum)
    return en_iyi


def main():
    ayrac = argparse.ArgumentParser()
    ayrac.add_argument("--veri", nargs="+", required=True)
    ayrac.add_argument("--test-bolge", required=True)
    ayrac.add_argument("--mimari", choices=MIMARI, default="siyam")
    ayrac.add_argument("--tur", type=int, default=12)
    ayrac.add_argument("--ornek-norm", action="store_true", help="her goruntu kendi ortalama/sapmasiyla")
    ayrac.add_argument("--ince-ayar", type=int, nargs="*", default=[])
    ayrac.add_argument("--tohum", type=int, default=0)
    ayrac.add_argument("--cikti", default=".")
    secim = ayrac.parse_args()
    torch.manual_seed(secim.tohum)
    np.random.seed(secim.tohum)
    cihaz = "cuda" if torch.cuda.is_available() else "cpu"

    v = Veri(secim.veri)
    etiketli = v.y >= 0
    test_bolgesi = v.bolgede(secim.test_bolge)
    test = np.flatnonzero(etiketli & test_bolgesi)
    havuz_parca = np.unique(v.parca[etiketli & ~test_bolgesi])
    np.random.shuffle(havuz_parca)
    dogrulama_parca = set(havuz_parca[: max(1, len(havuz_parca) * 15 // 100)])
    diger = etiketli & ~test_bolgesi
    dp = np.isin(v.parca, list(dogrulama_parca))
    egitim, dogrulama = np.flatnonzero(diger & ~dp), np.flatnonzero(diger & dp)
    print(f"egitim {len(egitim)} (pozitif {v.y[egitim].sum()}), dogrulama {len(dogrulama)} "
          f"(pozitif {v.y[dogrulama].sum()}, {len(dogrulama_parca)} parca), test {len(test)} (pozitif {v.y[test].sum()})",
          flush=True)

    m = MIMARI[secim.mimari]().to(cihaz)
    basla = time.perf_counter()
    d_auc = egit(m, v, egitim, dogrulama, cihaz, secim.tur, secim.ornek_norm)
    sure = time.perf_counter() - basla
    pt, et = tahmin(m, v, test, cihaz, secim.ornek_norm), v.y[test] == 1
    sonuc = {"test_bolge": secim.test_bolge, "mimari": secim.mimari, "ornek_norm": secim.ornek_norm,
             "veri": secim.veri, "tohum": secim.tohum, "dogrulama_auc": d_auc, "sure_sn": round(sure),
             "test_n": int(len(test)), "test_pozitif": int(et.sum()), "test_auc": auc(pt, et),
             **{f"duyarlilik_ya{int(a * 100)}": duyarlilik(pt, et, a) for a in (0.05, 0.10, 0.20)}}
    print(f"\nTEST AUC {sonuc['test_auc']:.3f}; yanlis alarm %10 iken duyarlilik %{100 * sonuc['duyarlilik_ya10']:.1f} "
          f"({secim.mimari}, egitim {sure:.0f} sn)", flush=True)

    # Yerel ince ayar: kurulum yerinde k bina etiketlenir; kalan bina uzerinde olculur.
    sonuc["ince_ayar"] = {}
    rng = np.random.default_rng(secim.tohum)
    temel = copy.deepcopy(m.state_dict())
    for k in secim.ince_ayar:
        aucs, d10 = [], []
        for tekrar in range(3):
            poz, neg = test[v.y[test] == 1], test[v.y[test] == 0]
            secilen = np.concatenate([rng.choice(poz, k // 2, replace=False), rng.choice(neg, k - k // 2, replace=False)])
            kalan = np.setdiff1d(test, secilen)
            m.load_state_dict(temel)
            # Az ornekle cok tur: ornek basina ~20 gecis.
            egit(m, v, np.sort(np.repeat(secilen, max(1, 2560 // k))), None, cihaz, 1, secim.ornek_norm, lr=1e-4, sessiz=True)
            pk, ek = tahmin(m, v, kalan, cihaz, secim.ornek_norm), v.y[kalan] == 1
            aucs.append(auc(pk, ek))
            d10.append(duyarlilik(pk, ek, 0.10))
        sonuc["ince_ayar"][k] = {"auc": aucs, "duyarlilik_ya10": d10}
        print(f"ince ayar k={k}: AUC {np.mean(aucs):.3f} ({', '.join(f'{a:.3f}' for a in aucs)}), "
              f"yanlis alarm %10 iken duyarlilik %{100 * np.mean(d10):.1f}", flush=True)
    m.load_state_dict(temel)

    ad = f"{secim.mimari}{'_norm' if secim.ornek_norm else ''}_{secim.test_bolge.replace('*', 'hepsi')}_t{secim.tohum}"
    json.dump(sonuc, open(Path(secim.cikti) / f"sonuc_{ad}.json", "w"), indent=1)
    torch.save(m.state_dict(), Path(secim.cikti) / f"model_{ad}.pt")


if __name__ == "__main__":
    main()
