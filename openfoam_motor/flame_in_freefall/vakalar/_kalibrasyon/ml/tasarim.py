"""Faz A tasarimi: kisitli maximin ornekleme (OA(8,7,2) kose riski nedeniyle reddedildi; plan Revize 3).

Adaylar: kutu icinde scrambled Sobol (4096), kisitlari saglayanlar (theta_g1 siniri, A1 kesiti) kalir.
Secim: sabit noktalar (merkez) dahil min-mesafeyi buyuten acgozlu maximin, rastgele yeniden baslatmali.
Mesafe birim kupte (faz kutusuna gore). Tohum sabit -> tekrarlanabilir.
"""
import numpy as np
from scipy.stats import qmc
from . import param as P


def aday_havuzu(faz="A", m=12, seed=20261108, en_az=200):
    adaylar = []
    tur = 0
    while len(adaylar) < en_az and tur < 8:
        s = qmc.Sobol(d=P.D_S, scramble=True, seed=seed + tur)
        u = s.random_base2(m=m)
        x = P.birimden(u, faz)
        ok = np.array([P.uygun(xi, faz) for xi in x])
        adaylar.extend(list(u[ok]))
        tur += 1
    return np.array(adaylar)


def maximin_sec(adaylar, n_sec, sabit=None, seed=7, n_restart=300):
    rng = np.random.default_rng(seed)
    sabit = np.zeros((0, adaylar.shape[1])) if sabit is None else np.atleast_2d(sabit)
    en_iyi, en_iyi_d = None, -1.0
    for _ in range(n_restart):
        sec = [int(rng.integers(len(adaylar)))]
        for _k in range(n_sec - 1):
            ref = np.vstack([sabit, adaylar[sec]]) if len(sabit) else adaylar[sec]
            d = np.min(np.linalg.norm(adaylar[:, None, :] - ref[None, :, :], axis=2), axis=1)
            d[sec] = -1.0
            sec.append(int(np.argmax(d)))
        pts = adaylar[sec]
        ref = np.vstack([sabit, pts]) if len(sabit) else pts
        dm = pairwise_min(ref)
        if dm > en_iyi_d:
            en_iyi, en_iyi_d = pts, dm
    return en_iyi, en_iyi_d


def pairwise_min(pts):
    d = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=2)
    d[np.diag_indices(len(pts))] = np.inf
    return float(d.min())


def faz_a(n=8, seed=7):
    """Faz A: n nokta + sabit merkez (sensorlu_hedef02). Dondurur: (fiziksel x'ler, birim x'ler, min mesafe, rastgele-tasarim min mesafesi)."""
    ad = aday_havuzu("A")
    merkez_u = P.birime(P.merkez(), "A")
    pts, dm = maximin_sec(ad, n, sabit=merkez_u, seed=seed)
    rng = np.random.default_rng(seed + 1)
    rast = [pairwise_min(np.vstack([merkez_u, ad[rng.choice(len(ad), n, replace=False)]])) for _ in range(300)]
    return P.birimden(pts, "A"), pts, dm, float(np.mean(rast))
