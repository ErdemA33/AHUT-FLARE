"""T15: sentetik kurtarma. SINIR: veri VEKILDEN uretilir -> yalniz ALGORITMA UYGULAMASININ dogrulugunu sinar,
vekil dogrulugunu SINAMAZ. Gecmesi gerekli, yeterli degil.
Oyuncak simulator eta(theta) (6 boyut, 3 sensor x 3 ozellik) analitiktir; gercek CFD degildir.
"""
import numpy as np
from . import param as P
from .vekil import GP
from .history_matching import Problem

OZ = [f"S{s}_{k}" for s in range(3) for k in range(3)]
SENSOR = {f"S{s}": [f"S{s}_{k}" for k in range(3)] for s in range(3)}


def oyuncak(Xu):
    """Birim kupte pürüzsüz, korelasyonlu cikti (n, 9)."""
    Xu = np.atleast_2d(Xu)
    a = np.stack([3.0 + 1.5 * Xu[:, 0] - 0.8 * Xu[:, 1] + 0.3 * np.sin(3 * Xu[:, 2]) + 0.4 * Xu[:, 3] * Xu[:, 4],
                  4.0 + 1.0 * Xu[:, 0] + 0.6 * Xu[:, 2] ** 2 - 0.5 * Xu[:, 4],
                  5.0 - 0.7 * Xu[:, 1] + 0.5 * Xu[:, 3] + 0.2 * Xu[:, 0] * Xu[:, 2]], axis=1)
    cols = []
    for s in range(3):
        cols += [a[:, s], a[:, s] + 0.8 + 0.2 * Xu[:, s], a[:, s] * 1.2 + 0.1]
    return np.stack(cols, axis=1)


def kurtarma(n_tekrar=20, n_egitim=13, gurultu=0.02, seed=0, mod="kosegen"):
    """Her tekrar: rastgele egitim noktalari + bilinen theta*; y* = vekil ortalamasi + gurultu; HM theta*'i iceriyor mu?
    Dondurur kapsama orani (theta* uyumlu bolgede)."""
    rng = np.random.default_rng(seed)
    kapsa = 0
    for _ in range(n_tekrar):
        Xu = rng.random((n_egitim, P.D_S))
        Y = oyuncak(Xu) + rng.normal(0, 0.005, (n_egitim, 9))
        gps = {f: GP(0.005 ** 2).fit(Xu, Y[:, j]) for j, f in enumerate(OZ)}
        ts = rng.random((1, P.D_S))
        zt = np.array([gps[f].tahmin(ts)[0][0] for f in OZ]) + rng.normal(0, gurultu, 9)
        z = dict(zip(OZ, zt))
        S_obs = {s: (gurultu ** 2) * np.eye(3) for s in SENSOR}
        prob = Problem(gps, SENSOR, z, S_obs, 0.005)
        uy, _ = prob.uyumlu(ts, mod=mod)
        kapsa += int(uy[0])
    return kapsa / n_tekrar
