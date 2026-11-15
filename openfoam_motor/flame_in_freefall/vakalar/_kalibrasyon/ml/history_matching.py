"""History matching (ana arac). Sensor basina birlesik gosterge (korelasyonlu ozellikler):

  I2_s(theta) = r' S_s^-1 r,  r = z_s - E[eta_s(theta)],  S_s = D R D + S_olcum + S_cfd + S_delta
  uyumlu sensor  <=>  I2_s < chi2_{k_s}(0.9973)   (k_s=1 icin 9 = 3 sigma)
  uyumlu theta   <=>  en fazla `max_basarisiz` (=1) sensor uyumsuz  (ikinci en kotu sensor kurali)

Mod 'kosegen': ozellikler bagimsiz; her ozellik I_j^2 < 9, sensor = tum ozellikler gecerse.
S_delta(kappa) = kappa^2 * diag(S_olcum) ('gereken minimum delta' icin tek parametre).
Esikler on-yazili (Revize 3); sonuc goruldukten sonra degistirilmez.
"""
import numpy as np
from scipy.stats import chi2, qmc
from . import param as P

NIVEL = 0.9973            # 3 sigma
ESIK_KOSEGEN = 3.0


def ledoit_wolf_korelasyon(Z):
    """Z: (n, p) standardize LOO artiklar. Olcekli birim hedefe Ledoit-Wolf buzulmesi; korelasyon matrisi dondurur."""
    Z = np.asarray(Z, float)
    n, p = Z.shape
    if p == 1:
        return np.eye(1), 0.0
    X = Z - Z.mean(axis=0)
    S = X.T @ X / n
    mu = np.trace(S) / p
    d2 = np.sum((S - mu * np.eye(p)) ** 2) / p
    b2bar = sum(np.sum((np.outer(x, x) - S) ** 2) for x in X) / (n * n) / p
    b2 = min(b2bar, d2)
    a = b2 / d2 if d2 > 0 else 1.0
    Ss = a * mu * np.eye(p) + (1 - a) * S
    dd = np.sqrt(np.diag(Ss))
    return Ss / np.outer(dd, dd), float(a)


class Problem:
    def __init__(self, gps, sensor_ozellik, z, S_obs, nugget_sd, R_emu=None):
        """gps: {ozellik: GP}; sensor_ozellik: {sensor: [ozellik,...]}; z: {ozellik: deney degeri};
        S_obs: {sensor: matris (olcum kovaryansi)}; nugget_sd: CFD tekrar sd; R_emu: {sensor: korelasyon} ya da None."""
        self.gps, self.so, self.z, self.S_obs = gps, sensor_ozellik, z, S_obs
        self.nugget_sd = nugget_sd
        self.R_emu = R_emu or {}

    def tahmin(self, Xc):
        mu, var = {}, {}
        for f, g in self.gps.items():
            mu[f], var[f] = g.tahmin(Xc)
        return mu, var

    def gosterge(self, Xc, mod="tam", emu_var_carpan=1.0, kappa=0.0):
        """Dondurur {sensor: (I2 (m,), esik)} ; kosegen modda I2 = en buyuk ozellik I_j^2 ve esik 9."""
        mu, var = self.tahmin(Xc)
        out = {}
        for s, fl in self.so.items():
            k = len(fl)
            r = np.stack([self.z[f] - mu[f] for f in fl], axis=1)                          # (m, k)
            sd = np.sqrt(np.stack([emu_var_carpan * var[f] for f in fl], axis=1))          # (m, k)
            So = np.asarray(self.S_obs[s], float).reshape(k, k)
            Sd = kappa ** 2 * np.diag(np.diag(So))
            Sc = (self.nugget_sd ** 2) * np.eye(k)
            if mod == "tam":
                R = self.R_emu.get(s, np.eye(k))
                S = sd[:, :, None] * R[None, :, :] * sd[:, None, :] + (So + Sd + Sc)[None, :, :]
                I2 = np.einsum("mi,mi->m", r, np.linalg.solve(S, r[:, :, None])[:, :, 0])
                out[s] = (I2, float(chi2.ppf(NIVEL, k)))
            else:
                tot = sd ** 2 + np.diag(So + Sd + Sc)[None, :]
                I2 = np.max(r ** 2 / tot, axis=1)
                out[s] = (I2, ESIK_KOSEGEN ** 2)
        return out

    def uyumlu(self, Xc, mod="tam", max_basarisiz=1, **kw):
        g = self.gosterge(Xc, mod=mod, **kw)
        basarisiz = sum((I2 >= esik).astype(int) for (I2, esik) in g.values())
        return basarisiz <= max_basarisiz, g

    def delta_min(self, Xc, mod="tam", max_basarisiz=1, emu_var_carpan=1.0, kmax=1000.0, tol=1e-3):
        """Uyumlu bolgeyi bos olmaktan cikaran en kucuk kappa (olcum sigma kati). 0 -> zaten bos degil; None -> kmax'ta da bos."""
        def bos(kp):
            m, _ = self.uyumlu(Xc, mod, max_basarisiz, emu_var_carpan=emu_var_carpan, kappa=kp)
            return not m.any()
        if not bos(0.0):
            return 0.0
        if bos(kmax):
            return None
        lo, hi = 0.0, kmax
        while hi - lo > tol * max(1.0, hi):
            mid = 0.5 * (lo + hi)
            if bos(mid):
                lo = mid
            else:
                hi = mid
        return hi


def aday_uzayi(faz="B", m=15, seed=2026):
    """Uyumlu bolge taramasi icin faz kutusunda kisitlari saglayan Sobol noktalari (fiziksel birimde)."""
    s = qmc.Sobol(d=P.D_S, scramble=True, seed=seed)
    x = P.birimden(s.random_base2(m=m), faz)
    ok = np.array([P.uygun(xi, faz) for xi in x])
    return x[ok]


def emu_korelasyonlari(gps, sensor_ozellik):
    """LOO standardize artiklarindan sensor basina Ledoit-Wolf korelasyonu. Dondurur ({sensor: R}, {sensor: buzulme})."""
    R, A = {}, {}
    for s, fl in sensor_ozellik.items():
        Z = []
        for f in fl:
            mu, var = gps[f].loo()
            Z.append((gps[f].y - mu) / np.sqrt(var))
        Z = np.stack(Z, axis=1)
        R[s], A[s] = ledoit_wolf_korelasyon(Z)
    return R, A
