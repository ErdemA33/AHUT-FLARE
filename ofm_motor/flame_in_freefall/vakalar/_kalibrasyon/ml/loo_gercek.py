"""Gercek-CFD leave-one-out (T16, ana test). Her CFD kosusu sirayla 'bilinmeyen gercek' sayilir:
 (a) kalan kosulardan vekil kurulup o kosunun ozellikleri tahmin edilir; standardize artik z = (y - mu)/sqrt(var + nugget)
 (b) o kosunun ozelliklerinden history matching ile theta cikarilir; gercek theta uyumlu bolgede mi
Raporlanir: gecen fold sayisi / toplam, artik dagilimi (ortalama, sd, min, maks, histogram).
Bu dosya CFD calistirmaz; girdi: egitim matrisi (n x 6 fiziksel x, n x F ozellik). Eski kosular dahil/hariç icin iki kez cagrilir.
"""
import numpy as np
from . import param as P
from .vekil import GP
from .history_matching import Problem

Z_ESIK = 3.0


def loo_gercek(X, Y, ozellikler, sensor_ozellik, nugget_sd, S_obs_cfd, faz="B", mod="kosegen", n_aday=4000, seed=0, tasarim_birim=None):
    """X: (n,6) fiziksel; Y: (n,F) ozellikler; ozellikler: F adlar.
    S_obs_cfd: {sensor: matris} -- held-out CFD 'olcumu' icin kovaryans (CFD tekrar gurultusu; deney olcumu degil)."""
    n = len(X)
    Xu = P.birime(X, faz)
    z_art = np.full((n, len(ozellikler)), np.nan)
    theta_ok = np.zeros(n, bool)
    rng = np.random.default_rng(seed)
    for i in range(n):
        m = np.ones(n, bool); m[i] = False
        gps = {}
        for j, f in enumerate(ozellikler):
            ok = m & ~np.isnan(Y[:, j])
            if ok.sum() < 5 or np.isnan(Y[i, j]):
                continue
            gps[f] = GP(nugget_sd ** 2).fit(Xu[ok], Y[ok, j])
            mu, var = gps[f].tahmin(Xu[i:i + 1])
            z_art[i, j] = (Y[i, j] - mu[0]) / np.sqrt(var[0] + nugget_sd ** 2)
        so = {s: [f for f in fl if f in gps] for s, fl in sensor_ozellik.items()}
        so = {s: fl for s, fl in so.items() if fl}
        if not so:
            continue
        prob = Problem(gps, so, {f: Y[i, ozellikler.index(f)] for fl in so.values() for f in fl},
                       {s: np.asarray(S_obs_cfd[s])[np.ix_([sensor_ozellik[s].index(f) for f in fl], [sensor_ozellik[s].index(f) for f in fl])]
                        for s, fl in so.items()}, nugget_sd)
        uy, _ = prob.uyumlu(Xu[i:i + 1], mod=mod)
        theta_ok[i] = bool(uy[0])
    ok = ~np.isnan(z_art)
    z = z_art[ok]
    fold_gecen = int(np.sum([np.all(np.abs(z_art[i][~np.isnan(z_art[i])]) <= Z_ESIK) for i in range(n) if (~np.isnan(z_art[i])).any()]))
    fold_toplam = int(np.sum([(~np.isnan(z_art[i])).any() for i in range(n)]))
    h, kenar = np.histogram(z, bins=[-np.inf, -3, -2, -1, 0, 1, 2, 3, np.inf]) if len(z) else (np.array([]), np.array([]))
    rapor = dict(
        fold_gecen=fold_gecen, fold_toplam=fold_toplam, theta_kurtarilan=int(theta_ok.sum()),
        z_ortalama=float(z.mean()) if len(z) else np.nan, z_sd=float(z.std(ddof=1)) if len(z) > 1 else np.nan,
        z_min=float(z.min()) if len(z) else np.nan, z_maks=float(z.max()) if len(z) else np.nan,
        z_histogram=h.tolist(),
        loo_gecti=bool(fold_toplam > 0 and fold_gecen == fold_toplam),
    )
    return rapor, z_art, theta_ok
