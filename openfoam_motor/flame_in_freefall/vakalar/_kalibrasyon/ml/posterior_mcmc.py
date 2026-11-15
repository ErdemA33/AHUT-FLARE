"""Ikincil arac: afin-degismez topluluk MCMC (Goodman & Weare stretch move). Yalniz uyumlu bolge kucuk ve vekil guvenilir ise.
logp(x) birim kupte tanimlidir; sinir disi -inf dondurmelidir."""
import numpy as np


def topluluk_mcmc(logp, x0, n_adim, a=2.0, seed=0):
    """x0: (K, d) baslangic topluluk (K >= 2d). Dondurur zincir (n_adim, K, d), kabul orani."""
    rng = np.random.default_rng(seed)
    K, d = x0.shape
    x = x0.copy()
    lp = np.array([logp(xi) for xi in x])
    zincir = np.empty((n_adim, K, d))
    kabul = 0
    toplam = 0
    for t in range(n_adim):
        for yarim in (0, 1):
            idx = np.arange(yarim, K, 2)
            diger = np.arange(1 - yarim, K, 2)
            for k in idx:
                j = int(rng.choice(diger))
                z = ((a - 1.0) * rng.random() + 1.0) ** 2 / a
                y = x[j] + z * (x[k] - x[j])
                lpy = logp(y)
                toplam += 1
                if np.log(rng.random()) < (d - 1) * np.log(z) + lpy - lp[k]:
                    x[k], lp[k] = y, lpy
                    kabul += 1
        zincir[t] = x
    return zincir, kabul / max(toplam, 1)
