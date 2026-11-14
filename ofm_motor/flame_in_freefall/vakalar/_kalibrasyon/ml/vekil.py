"""Gauss sureci vekili (sadelestirilmis; plan Revize 3):
izotropik Matern-5/2 (ortak uzunluk olcegi l), sabit ortalama (GLS ile analitik), SABIT nugget (CFD tekrar gurultusu).
Serbest hiperparametre: l, sigma_f^2 (+ ortalama c) = 3.  l icin sinir 0.3 <= l <= 3 (birim kup; tasarim secimi, LOO ile kontrol).
Yalniz numpy + scipy.
"""
import numpy as np
from scipy.linalg import cho_factor, cho_solve
from scipy.optimize import minimize

L_ALT, L_UST = 0.3, 3.0
SQ5 = np.sqrt(5.0)


def matern52(X1, X2, l, sf2):
    d = np.linalg.norm(X1[:, None, :] - X2[None, :, :], axis=2) / l
    return sf2 * (1.0 + SQ5 * d + 5.0 * d * d / 3.0) * np.exp(-SQ5 * d)


class GP:
    def __init__(self, nugget_var, l=None, sf2=None):
        self.nugget = float(nugget_var)
        self.l, self.sf2 = l, sf2

    # ---- temel cebir ----
    def _K(self, X):
        return matern52(X, X, self.l, self.sf2) + self.nugget * np.eye(len(X))

    def _hazirla(self):
        K = self._K(self.X)
        self.cf = cho_factor(K, lower=True)
        one = np.ones(len(self.X))
        self.Kinv1 = cho_solve(self.cf, one)
        self.s11 = float(one @ self.Kinv1)
        self.c = float(self.Kinv1 @ self.y / self.s11)          # GLS sabit ortalama
        self.alpha = cho_solve(self.cf, self.y - self.c)

    def log_olabilirlik(self, l, sf2):
        """REML (sabit ortalama integre) -log olabilirlik."""
        K = matern52(self.X, self.X, l, sf2) + self.nugget * np.eye(len(self.X))
        try:
            cf = cho_factor(K, lower=True)
        except np.linalg.LinAlgError:
            return 1e30
        one = np.ones(len(self.X))
        Ki1 = cho_solve(cf, one)
        s11 = float(one @ Ki1)
        c = float(Ki1 @ self.y / s11)
        r = self.y - c
        a = cho_solve(cf, r)
        logdet = 2 * np.sum(np.log(np.diag(cf[0])))
        n = len(self.y)
        return 0.5 * (r @ a) + 0.5 * logdet + 0.5 * np.log(s11) + 0.5 * (n - 1) * np.log(2 * np.pi)

    def fit(self, X, y, l=None, sf2=None):
        self.X = np.atleast_2d(np.asarray(X, float))
        self.y = np.asarray(y, float)
        if l is None or sf2 is None:
            v = max(self.y.var(), 1e-12)
            best = None
            for l0 in (0.4, 0.8, 1.5, 2.5):
                for s0 in (0.3 * v, 1.0 * v, 3.0 * v):
                    f = lambda p: self.log_olabilirlik(np.exp(p[0]), np.exp(p[1]))
                    r = minimize(f, [np.log(l0), np.log(s0)], method="L-BFGS-B",
                                 bounds=[(np.log(L_ALT), np.log(L_UST)), (np.log(1e-6 * v), np.log(1e3 * v))])
                    if best is None or r.fun < best.fun:
                        best = r
            self.l, self.sf2 = float(np.exp(best.x[0])), float(np.exp(best.x[1]))
        else:
            self.l, self.sf2 = float(l), float(sf2)
        self._hazirla()
        return self

    # ---- tahmin ----
    def tahmin(self, Xs):
        """Evrensel kriging: eta (gurultusuz) icin ortalama ve varyans."""
        Xs = np.atleast_2d(np.asarray(Xs, float))
        ks = matern52(Xs, self.X, self.l, self.sf2)                  # (m, n)
        mu = self.c + ks @ self.alpha
        Kis = cho_solve(self.cf, ks.T)                               # (n, m)
        var = self.sf2 - np.einsum("ij,ji->i", ks, Kis)
        corr = (1.0 - ks @ self.Kinv1) ** 2 / self.s11
        return mu, np.maximum(var + corr, 0.0)

    # ---- leave-one-out ----
    def loo(self):
        """Kapali form (Dubrule 1983): e_i = (C^-1 y)_i / (C^-1)_ii, Var = 1/(C^-1)_ii (gozlem hatasi, nugget dahil)."""
        n = len(self.y)
        Kinv = cho_solve(self.cf, np.eye(n))
        Cinv = Kinv - np.outer(self.Kinv1, self.Kinv1) / self.s11
        d = np.diag(Cinv)
        e = (Cinv @ self.y) / d
        return self.y - e, 1.0 / d      # tahmin, hata varyansi

    def loo_yeniden(self):
        """Kaba kuvvet: hiperparametreler sabit, her nokta disarida yeniden uydur."""
        mu, var = np.empty(len(self.y)), np.empty(len(self.y))
        for i in range(len(self.y)):
            m = np.ones(len(self.y), bool); m[i] = False
            g = GP(self.nugget).fit(self.X[m], self.y[m], self.l, self.sf2)
            a, b = g.tahmin(self.X[i:i + 1])
            mu[i], var[i] = a[0], b[0] + self.nugget
        return mu, var


def q2(y, mu):
    return 1.0 - np.sum((y - mu) ** 2) / np.sum((y - y.mean()) ** 2)
