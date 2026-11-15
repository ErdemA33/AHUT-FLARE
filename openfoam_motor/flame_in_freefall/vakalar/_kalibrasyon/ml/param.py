"""Parametre uzayi: 6 fiziksel parametre, sinirlar, yeniden parametrelestirme.

Kaynaklar (optimizasyon_matched/literatur_araligi.md, parametreler.yaml, Cui & Liao 2024 Tablo 2):
  u        : tutusma bandi degiskeni; theta_g1 = ln k1(1350 K) = u + Ta1 * X_TEFF
  Ta1      : gaz fazi CH4 oksidasyonu aktivasyon sicakligi [K]  (KISMI capraz kontrol)
  theta_p  : ln k_p1(650 K), piroliz adim 1
  E1       : piroliz adim 1 aktivasyon enerjisi [J/mol]
  XL0      : piroliz gizli isisi [J/kg]
  eps      : ornek yuzey yayma katsayisi (0/fluid/G fluid_to_sibal)
theta_g2 (R2) kumeden CIKARILDI (kullanici karari 08.11).
Sayilar duz yazilir.
"""
import math
import numpy as np

R = 8.314                     # J/(mol K)
TREF_GAZ = 1350.0             # K
TREF_P = 650.0                # K
T_EFF = 1170.0                # K, tutusma bandi uyumu (8 koşu; TEKNIK_VERI.md)
X_TEFF = 1.0 / T_EFF - 1.0 / TREF_GAZ

# tutusma bandi modeli: ln t_ign = p0 u^2 + p1 u + p2  (piroliz ve eps SABITKEN, Ta in [21000, 28012] izgarasi)
BAND_KATSAYI = (0.24680027, -6.7667965, 47.23487255)
BAND_T_ALT, BAND_T_UST = 3.0, 4.4      # s

# literatur piroliz ciftleri (A [1/s], E [J/mol])
LIT_PIROLIZ = {
    "Zhao2017": (1.626e11, 161440.0),
    "Cui2024": (2.53e11, 171440.0),
    "S7_pamuk_FDS": (1.0e10, 125000.0),
}
A1_ALT, A1_UST = 1.0e10, 2.53e11

NAMES = ["u", "Ta1", "theta_p", "E1", "XL0", "eps"]
D = len(NAMES)

# Plan Revize 3 kosullu kurali: [S10] tam metni okunamazsa XL0 = 300000 sabitlenir ve "test edilemedi" listesine eklenir.
# 08.11 gece: osti.gov baglanti zaman asimi (ctx_fetch_and_index) -> tam metin okunamadi -> XL0 SABIT.
XL0_SERBEST = False
XL0_SABIT = 300000.0
SERBEST = [i for i, n in enumerate(NAMES) if n != "XL0" or XL0_SERBEST]
D_S = len(SERBEST)          # tasarim/vekil boyutu (serbest parametre sayisi)

THETA_G1_ALT, THETA_G1_UST = math.log(23140.0), math.log(4700000.0)   # yaml CH4ox_kref (WD 1981 via Wei 2021)
TA1_ALT, TA1_UST = 15100.0, 24358.0
TA1_FAZA_ALT = 21000.0                      # Faz A alt kutusu: band modeli yalniz burada kalibre
E1_ALT, E1_UST = 125000.0, 188000.0         # [S7], [S11]
XL0_ALT, XL0_UST = 300000.0, 538000.0       # [S4] ve [S10] (ZAYIF: S10 yalniz ozet)
EPS_ALT, EPS_UST = 0.8, 0.9                 # [S2], [S8]


def k_piroliz(A, E, T=TREF_P):
    return A * math.exp(-E / (R * T))


def theta_p_siniri():
    ks = [math.log(k_piroliz(A, E)) for (A, E) in LIT_PIROLIZ.values()]
    return min(ks), max(ks)


THETA_P_ALT, THETA_P_UST = theta_p_siniri()


def band_u_araligi(t_alt=BAND_T_ALT, t_ust=BAND_T_UST):
    """ln t = a u^2 + b u + c = ln(t) cozumu, tepe noktasinin solundaki kok (u < -b/2a)."""
    a, b, c = BAND_KATSAYI
    out = []
    for t in (t_ust, t_alt):               # uzun t -> kucuk u
        disc = b * b - 4 * a * (c - math.log(t))
        if disc < 0:
            raise ValueError("band koku yok")
        out.append((-b - math.sqrt(disc)) / (2 * a))
    return out[0], out[1]


U_ALT, U_UST = band_u_araligi()


def t_ign_band(u):
    a, b, c = BAND_KATSAYI
    return math.exp(a * u * u + b * u + c)


def sinirlar(faz="A"):
    """(alt, ust) 6'lik diziler. faz 'A' veya 'B'."""
    ta_alt = TA1_FAZA_ALT if faz == "A" else TA1_ALT
    xl_alt, xl_ust = (XL0_ALT, XL0_UST) if XL0_SERBEST else (XL0_SABIT, XL0_SABIT)
    alt = np.array([U_ALT, ta_alt, THETA_P_ALT, E1_ALT, xl_alt, EPS_ALT])
    ust = np.array([U_UST, TA1_UST, THETA_P_UST, E1_UST, xl_ust, EPS_UST])
    return alt, ust


def theta_g1(u, Ta1):
    return u + Ta1 * X_TEFF


def a_gaz(u, Ta1):
    """A [orkestrator.a_hesapla ile ayni bicim: exp(theta + Ta/1350)]."""
    return math.exp(theta_g1(u, Ta1) + Ta1 / TREF_GAZ)


def a_piroliz(theta_p, E1):
    return math.exp(theta_p + E1 / (R * TREF_P))


def fiziksel(x):
    """6'lik vektor -> modele verilecek degerler sozlugu."""
    u, Ta1, th_p, E1, XL0, eps = [float(v) for v in x]
    return dict(
        u=u, Ta1=Ta1, theta_g1=theta_g1(u, Ta1), A_gaz=a_gaz(u, Ta1),
        theta_p=th_p, E1=E1, A1=a_piroliz(th_p, E1), XL0=XL0, eps=eps,
        t_ign_band=t_ign_band(u),
    )


def uygun(x, faz="A"):
    """Tum kisitlar: kutu, theta_g1 siniri, A1 kesiti."""
    alt, ust = sinirlar(faz)
    x = np.asarray(x, float)
    if np.any(x < alt - 1e-12) or np.any(x > ust + 1e-12):
        return False
    f = fiziksel(x)
    if not (THETA_G1_ALT <= f["theta_g1"] <= THETA_G1_UST):
        return False
    if not (A1_ALT <= f["A1"] <= A1_UST):
        return False
    return True


def birimden(unit, faz="A"):
    """unit (..., D_S) birim kup -> tam 6'lik fiziksel vektor (sabit parametreler sabit degerde)."""
    alt, ust = sinirlar(faz)
    unit = np.asarray(unit, float)
    full = np.broadcast_to(alt, unit.shape[:-1] + (D,)).copy()
    full[..., SERBEST] = alt[SERBEST] + unit * (ust - alt)[SERBEST]
    return full


def birime(x, faz="A"):
    """tam 6'lik fiziksel vektor -> (..., D_S) birim kup (yalniz serbest parametreler)."""
    alt, ust = sinirlar(faz)
    x = np.asarray(x, float)
    return ((x - alt) / np.where(ust - alt == 0, 1.0, ust - alt))[..., SERBEST]


def merkez():
    """sensorlu_hedef02: A = 249200000000000.4, Ta = 24358, baslangic piroliz (Zhao 2017) ve eps 0.8."""
    A, Ta = 249200000000000.4, 24358.0
    th1 = math.log(A) - Ta / TREF_GAZ
    u = th1 - Ta * X_TEFF
    A1, E1 = LIT_PIROLIZ["Zhao2017"]
    return np.array([u, Ta, math.log(k_piroliz(A1, E1)), E1, 300000.0, 0.8])
