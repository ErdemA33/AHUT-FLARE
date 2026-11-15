#!/usr/bin/env python3
"""
scripts/gas_radiation.py — alev ışınım kaybı: optik ince (Planck ortalama) + basit geri emme düzeltmesi.
Bağımsız modül (yalnız numpy): scripts/gas_engine.py kullanır; scripts/droplet_engine.py da aynı arayüzle kullanabilir
(scripts/droplet_engine.py DEĞİŞTİRİLMEDİ; oradaki a_planck() ile buradaki aynı uydurma).

Optik ince kayıp (Planck ortalama soğurma katsayısı κ_P, ör. Modest 2013 "Radiative Heat Transfer" 3. bs. §10.6):
    Q_ince = 4 σ κ_P (T⁴ - T∞⁴) V,     κ_P = p_atm (X_CO2 a_CO2(T) + X_H2O a_H2O(T))  [1/m]
    a_CO2, a_H2O: TNF workshop / RADCAL uydurması (Barlow ve ark., www.sandia.gov/TNF; droplet_engine ile aynı)

Geri emme düzeltmesi (gri, izotermal hacim; ortalama ışın yolu kavramı):
    L_m = 3.6 V / A                       Hottel ortalama ışın yolu (Hottel & Sarofim 1967; Modest 2013 §10.6,
                                          "L_m ≈ 3.6 V/A" tüm geometriler için ±%10)
    τ   = (κ_P,alev + κ_P,ortam) · L_m    ortam CO2/H2O'su (seyreltici CO2, kirlenmiş hazne) alevi saran ilk
                                          ışın yolu boyunca soğurur — VARSAYIM: ortam katkısı aynı L_m ile
    Q   = Q_ince · f(τ),   f(τ) = (1 - e^(-τ)) / τ
          (gri gaz hacminin yayınırlığı ε = 1 - e^(-κ L_m) ile Q = ε σ T⁴ A; ince sınırda ε A -> κ L_m A ≈ 4 κ V,
           yani f = ε / (κ L_m): τ -> 0'da 1, τ büyüdükçe 1/τ. Modest 2013 Eş. 10.x; Siegel & Howell.)
Sınırlama: Planck ortalaması bant doygunluğunu (bant merkezlerinin çok daha erken kalınlaşması) gri ortalama
içinde kaybeder; küçük alevlerde τ_P ~ 0.01-0.1 olduğundan bu düzeltme küçük kalır.
"""
import math

import numpy as np

# ---------------------------------------------------------------- is (kurum) ışınımı
# Planck ortalama is soğurma katsayısı, Rayleigh küçük parçacık biçimi: κ_is = C_is f_v T [1/m]
# (Modest 2013 §11: κ_P = 3.83 f_v C0 T / C2). C_is = 1200 1/(m K): SFPE El Kitabı 5. bs. (2016) Tablo 4.11'deki
# gaz yakıt alevleri için κ_S / (f_v T_s): CH4 1113, C2H4 1247, C3H8 1203 -> 1200.
C_IS = 1200.0
# Is eğilimi I (etilen = 1): laminer smoke point debisinin tersi, I = ṁ_sp(C2H4) / ṁ_sp(yakıt).
#   Kent 1986, Combust. Flame 63:349, Tablo 1 (1 g): ṁ_sp C2H4 3.84 mg/s, C3H8 7.87 mg/s -> C3H8 0.49
#   CH4: smoke point ölçülemedi — SFPE Böl. 36 ("ölçülen en büyük smoke point etan 0.24 m; metanınki daha uzun,
#        ölçülmedi"); SPICE ISS (Dotson & Sunderland 2010, AIAA 2010-1105): metanla smoke point bulunamadı -> 0
#   C2H6: SFPE smoke point boyları, etan 0.24 m / etilen 0.097 m (Linteris & Rafferty 2008 Tablo 1, SFPE sütunu)
#        -> 0.097/0.24 = 0.40 ;  H2: karbon yok -> 0
IS_EGILIMI = {"C2H4": 1.0, "C3H8": 0.49, "C2H6": 0.40, "CH4": 0.0, "H2": 0.0}


def is_kappa(f_v, T):
    """is Planck ortalama soğurma katsayısı [1/m]; f_v hacim kesri (ör. 1e-6)."""
    return C_IS * np.asarray(f_v) * np.asarray(T)

SIGMA = 5.670374e-8
T_INF = 298.15


def a_planck(T):
    """Planck ortalama soğurma katsayıları [1/(m atm)]: (CO2, H2O). TNF / RADCAL uydurması, 300-2500 K."""
    u = 1000.0 / np.clip(T, 300.0, 2500.0)
    h2o = -0.23093 - 1.12390 * u + 9.41530 * u ** 2 - 2.99880 * u ** 3 + 0.51382 * u ** 4 - 1.86840e-5 * u ** 5
    co2 = 18.741 - 121.310 * u + 273.500 * u ** 2 - 194.050 * u ** 3 + 56.310 * u ** 4 - 5.8169 * u ** 5
    return np.clip(co2, 0, None), np.clip(h2o, 0, None)


def kappa_P(X_CO2, X_H2O, T, p_atm):
    """Planck ortalama soğurma katsayısı [1/m]."""
    a_c, a_h = a_planck(T)
    return np.asarray(p_atm) * (np.asarray(X_CO2) * a_c + np.asarray(X_H2O) * a_h)


def ortalama_isin_yolu(V, A):
    """Hottel ortalama ışın yolu L_m = 3.6 V / A [m]."""
    return 3.6 * np.asarray(V) / np.maximum(np.asarray(A), 1e-30)


def geri_emme(tau):
    """f(τ) = (1 - e^-τ)/τ ; küçük τ'da seri (1 - τ/2 + τ²/6)."""
    tau = np.maximum(np.asarray(tau, float), 0.0)
    kucuk = tau < 1e-4
    return np.where(kucuk, 1 - tau / 2 + tau ** 2 / 6, -np.expm1(-tau) / np.where(kucuk, 1.0, tau))


def isinim_kaybi(T, kap_alev, V, A, C_rad=1.0, kap_ortam=0.0, T_inf=T_INF, duzeltme=True):
    """Q [W], τ, f.  T: alev sıcaklığı; kap_alev / kap_ortam: κ_P [1/m]; V [m³]; A: hacmi saran yüzey [m²]."""
    Q_ince = C_rad * 4 * SIGMA * kap_alev * (T ** 4 - T_inf ** 4) * V
    if not duzeltme:
        return Q_ince, np.zeros_like(np.asarray(Q_ince, float)), np.ones_like(np.asarray(Q_ince, float))
    tau = (np.asarray(kap_alev) + np.asarray(kap_ortam)) * ortalama_isin_yolu(V, A)
    f = geri_emme(tau)
    return Q_ince * f, tau, f


def kure_V_A(R, R_ic=0.0):
    """küresel kabuk (alev içi, iç yarıçap R_ic kaynak): V, dış yüzey A."""
    return 4 / 3 * math.pi * (R ** 3 - R_ic ** 3), 4 * math.pi * R ** 2


def yarim_kure_V_A(R):
    """düz brülör üstünde yarım küre: V, kapalı yüzey (kubbe + taban)."""
    return 2 / 3 * math.pi * R ** 3, 3 * math.pi * R ** 2


def sferoid_V_A(L, w):
    """uzun eksen L, çap w uzamış sferoit (jet alevi): V, yüzey (Knud Thomsen yaklaşığı, ±%1)."""
    a, b = L / 2, w / 2
    p = 1.6075
    A = 4 * math.pi * ((a ** p * b ** p * 2 + b ** (2 * p)) / 3) ** (1 / p)
    return math.pi * L * w ** 2 / 6, A
