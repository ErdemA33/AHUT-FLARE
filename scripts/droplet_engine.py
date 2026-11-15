#!/usr/bin/env python3
"""
scripts/droplet_engine.py — sıvı yakıt damlası yanması için fizik motoru (NASA FLEX / PSI-69 ile kalibre).

    from droplet_engine import droplet_engine
    droplet_engine(1e-4, 21, 101.3, 0, 2.0, "n-heptane", "droplet")          # ayrıntılı mod (1B, zamana bağlı)
    droplet_engine(1e-4, 21, 101.3, 0, 2.0, "n-heptane", "droplet", mod="hizli")

Arayüz scripts/engine.py ile aynı: (g, oksijen %, basinc kPa, akis cm/s, kalinlik = İLK DAMLA ÇAPI mm, malzeme,
numune_tipi, seyreltici="n2", mod="ayrintili"). İsteğe bağlı bilesim={"o2":..,"n2":..,"co2":..,"he":..}
mol oranları verilirse ortam bileşimi odur; verilmezse ortam = %oksijen O2 + geri kalanı seyreltici.
Dönüş: {"yanma": 0..1, "min_oksijen": %, "yayilma_hizi": None, "yanma_hizi_K": mm²/s,
        "sonme_capi": mm veya None, "sicaklik": K, "mesafe": 0,
        "kalibre", "tasinim_dogrulanmadi", "kismi_g_dogrulanmadi": bool, "uyarilar": [..],
        "soguk_alev": bool, "soguk_alev_suresi_s": s veya None (hızlı mod)}
Çalışırken sadece numpy + scipy + data/droplet_features.json kullanılır (Cantera ön hesapta, bkz.
scripts/droplet_feature_generate.py). Kalibre sayılar data/droplet_engine_parameters.json'da.

---------------------------------------------------------------------------------------------------
HIZLI MOD (yarı-durağan; ~ms):
  Klasik damla yanması kuramı (Godsave 1953, Spalding 1953; Law 2006 "Combustion Physics" böl. 6;
  Turns 2012 böl. 10), değişken özellikli iç bölge (Law & Law 1977) + ışınım + Damköhler sönmesi.
  B   = [c_p (T∞ - T_s) + Y_O∞ Q(1-χ_R)/ν] / L(T_s)                    aktarım sayısı
  Y_Fs = (B - Y_O∞/ν)/(1+B) = X_F(T_s) M_F/M̄,  p_sat: Clausius-Clapeyron   -> T_s
  T_f = T_s + (L/c_p)[(1+B)/(1+Y_O∞/ν) - 1]   (+ 2000 K üstünde ayrışma için yumuşak tavan)
  K   = 8 (λ/c_p)_iç ln(1+B)/ρ_l × kz × (Nu/2)      (iç bölge: yakıt buharı + ürün + ortam inerti)
  r_f/r_s (yarı-durağan) = ln(1+B)/ln(1+Y_O∞/ν);  gecikmeli alev:  r_f = FSR r_s^(1-β) r_0^β
        (mikro-g'de alev damla küçülürken neredeyse sabit kalır -> β; Nayagam 2012, Farouk & Dryer 2011)
  Işınım (optik ince, Planck ortalama; CO2 ve H2O için TNF/RADCAL eğrileri, Barlow ve ark.):
        Q_rad = C_rad · 4σ p (X_CO2 a_CO2(T_f) + X_H2O a_H2O(T_f)) (T_f⁴ - T∞⁴) · (4/3)π r_f³
        χ_R = Q_rad / (ṁ Q)   -> büyük damla / büyük alev = ışınımla sönme (FLEX'in ana sonucu)
  Damköhler: ln Da = ln(r_f²/α_f) + ln A + (a+b-1) ln ρ_f + b ln Y_O∞ - T_a/T_f ;  ln Da < 0 ya da
        T_f < 1200 K -> sönme.  Çap d0'dan küçülürken ilk sönme noktası = sönme çapı.
        yanma = σ(min_{d ∈ [0.85 d0, d0]} ln Da / s)   ("hemen söndü" = sönme çapı / d0 >= 0.85; scripts/psi_flex.py)
  g > 0 / akış: Nu/2 = 1 + 0.3 Pr^(1/3) (Re² + Gr)^(1/4)   (Gr terimi 1e-4..1e-2 g0 arasında log rampa ile açılır)  — Ranz & Marshall (1952) zorlanmış taşınım
        bağıntısının doğal taşınımla birleştirilmiş hali (Faeth 1977, Prog. Energy Combust. Sci. 3:191);
        Gr = g (T_f - T∞)/T∞ d³/ν². YAKLAŞIK: küresel simetri bozulur, bu sadece ortalama etkidir.
        Alev yarıçapı ve kalış süresi de (Nu/2) ile küçültülür.

AYRINTILI MOD (1B küresel, zamana bağlı): bkz. aşağıdaki "AYRINTILI MOD" bölümü.

Kalibrasyon:  python3 scripts/droplet_engine.py --kalibre-hizli     (FLEX testleri, scipy L-BFGS-B)
Doğrulama:    python3 scripts/droplet_engine.py --dogrula-hizli      (N2 -> CO2/He, yakıt dışarıda bırakma)
"""
import argparse
import json
import math
import os
import time
from pathlib import Path

import numpy as np

KOK = Path(__file__).resolve().parent.parent
OZELLIK_DOSYASI = KOK / "data/droplet_features.json"
PARAM_DOSYASI = KOK / "data/droplet_engine_parameters.json"
FLEX_ADAYLAR = [KOK / "psi_flex_testler.csv", Path("/mnt/ssd/nasaspaceapp/FLEX12/psi_flex_testler.csv"),
                Path("/media/user/Extreme Pro/nasaspaceapp/FLEX12/psi_flex_testler.csv")]   # harici disk (udisksctl)
FLEX2_DOSYASI = KOK / "data/psi_labeled_flex2.csv"

R_U = 8314.462618          # J/kmol K
SIGMA = 5.670374e-8
P0 = 101325.0
T_INF = 298.0
T_SONME = 1200.0           # alev bu sıcaklığın altına düşerse söndü
HEMEN_SONDU_ORANI = 0.85   # scripts/psi_flex.py ile aynı etiket kuralı
D_ORAN = np.linspace(1.0, 0.04, 49)   # hızlı modda taranan d/d0
D_ORAN_KAL = np.r_[np.linspace(1.0, 0.85, 4), np.linspace(0.8, 0.04, 20)]   # kalibrasyonda (daha seyrek)

# ------------------------------------------------------------------ sıvı yakıt verisi
# M kg/kmol, Tb K (1 atm), Tc K, Lb J/kg (Tb'de), ρ_l kg/m³ (kaynamaya yakın), c_l J/kg K, Q (alt ısıl değer) J/kg,
# nC, nH, Westbrook-Dryer 1981 tek adım: A [cgs], Ea kcal/mol, a (yakıt üssü), b (O2 üssü)
# Kaynak: NIST WebBook, Yaws (2003), Perry's 8. baskı; Westbrook & Dryer, CST 27:31 (1981) Tablo 2.
# 1-propanol WD tablosunda yok: etanol değerleri kullanıldı.
YAKIT = {
    "NC7H16":  dict(M=100.20, Tb=371.6, Tc=540.2, Lb=317e3, rho=640.0, cl=2240.0, Q=44.56e6, nC=7, nH=16,
                    A=5.1e11, Ea=30.0, a=0.25, b=1.5),
    "CH3OH":   dict(M=32.04, Tb=337.8, Tc=512.6, Lb=1100e3, rho=750.0, cl=2530.0, Q=19.92e6, nC=1, nH=4,
                    A=3.2e12, Ea=30.0, a=0.25, b=1.5),
    "C2H5OH":  dict(M=46.07, Tb=351.4, Tc=514.0, Lb=838e3, rho=740.0, cl=2440.0, Q=26.81e6, nC=2, nH=6,
                    A=1.5e12, Ea=30.0, a=0.15, b=1.6),
    "NC10H22": dict(M=142.28, Tb=447.3, Tc=617.7, Lb=272e3, rho=650.0, cl=2210.0, Q=44.24e6, nC=10, nH=22,
                    A=3.8e11, Ea=30.0, a=0.25, b=1.5),
    "NC3H7OH": dict(M=60.10, Tb=370.3, Tc=536.8, Lb=689e3, rho=740.0, cl=2390.0, Q=30.68e6, nC=3, nH=8,
                    A=1.5e12, Ea=30.0, a=0.15, b=1.6),
}
SU = dict(M=18.015, Tb=373.15, Tc=647.1, Lb=2.257e6)    # su (emilen) — NIST
SU_EMEN = {"CH3OH", "C2H5OH", "NC3H7OH"}                # suyla karışabilen alkoller (heptan/dekan: emmez)
for _y in YAKIT.values():
    _o2 = _y["nC"] + _y["nH"] / 4 - (1 if _y is YAKIT["CH3OH"] or _y is YAKIT["C2H5OH"]
                                       or _y is YAKIT["NC3H7OH"] else 0) / 2
    _y["nO2"] = _o2
    _y["nu"] = _o2 * 31.999 / _y["M"]               # kg O2 / kg yakıt
MALZEME_ADI = {"n-heptane": "NC7H16", "heptane": "NC7H16", "n-heptan": "NC7H16",
               "methanol": "CH3OH", "metanol": "CH3OH",
               "ethanol": "C2H5OH", "etanol": "C2H5OH",
               "n-decane": "NC10H22", "decane": "NC10H22", "n-dekan": "NC10H22", "dekan": "NC10H22",
               "1-propanol": "NC3H7OH", "propanol": "NC3H7OH", "n-propanol": "NC3H7OH"}
SEYRELTICI_TUR = {"n2": "N2", "co2": "CO2", "he": "HE", "ar": "AR", "xe": "XE"}
KALIBRE_YAKITLAR = ["NC7H16", "CH3OH"]          # FLEX'te veri olan yakıtlar


YAKIT_AD_TR = {"NC7H16": "n-heptan", "CH3OH": "metanol", "C2H5OH": "etanol", "NC10H22": "n-dekan",
               "NC3H7OH": "1-propanol"}
HAVUZ_TIPLERI = {"pool"}


def durum_notlari(yakit, g=None, akis=None, numune_tipi=None):
    """Motorun bu koşulda ne kadar doğrulandığı: (bayraklar, uyarılar).
    kalibre: yakıt FLEX kalibrasyonunda var mı (yalnız n-heptan, metanol);
    tasinim_dogrulanmadi: zorlanmış akış (akis > 0) — FLEX'te akış yoktu; Aşama 5c'de veri arandı, koşulları tam
    akışlı damla ölçümü bulunamadı (experiments/stage5c_flow.json)."""
    b = {"kalibre": yakit in KALIBRE_YAKITLAR, "tasinim_dogrulanmadi": False, "kismi_g_dogrulanmadi": False}
    u = []
    if str(numune_tipi or "").lower() in HAVUZ_TIPLERI:
        u.append("Havuz yangını modeli yok: damla motoru sıvı havuzu için kullanılmadı.")
        return b, u
    if yakit is not None and not b["kalibre"]:
        u.append(f"Bu yakıt motorda kalibre edilmedi ({YAKIT_AD_TR.get(yakit, yakit)}; FLEX'te yalnız n-heptan "
                 "ve metanol var): damla motoru sonucu düşük ağırlıklı ya da ağırlıksız.")
    b["kismi_g_dogrulanmadi"] = g is not None and 1e-3 < g < 0.9
    if b["kismi_g_dogrulanmadi"]:
        u.append("Kısmi g: damla için deney verisi yok; Faeth/Ranz–Marshall bağıntısıyla ara değer "
                 "(yalnız µg'de kalibre; 1 g'de 96 noktada sınandı, makale dışarıda AUC 0,60).")
    if akis is not None and akis > 0:
        b["tasinim_dogrulanmadi"] = True
        u.append("Damla için zorlanmış akış: Ranz–Marshall taşınım düzeltmesi doğrulanamadı (FLEX'te akış yoktu; "
                 "veri setinde µg/düşük g akışlı damla için koşulları tam bir ölçüm bulunamadı, Aşama 5c).")
    return b, u


def yakit_bul(malzeme):
    m = str(malzeme or "").strip().lower()
    return MALZEME_ADI.get(m) or next((v for k, v in MALZEME_ADI.items() if k in m), None)


# ------------------------------------------------------------------ gaz özellikleri (önceden hesaplanmış)
class Gaz:
    def __init__(self, dosya=OZELLIK_DOSYASI):
        d = json.loads(Path(dosya).read_text(encoding="utf-8"))
        self.turler = d["turler"]
        self.i = {t: k for k, t in enumerate(self.turler)}
        self.M = np.array(d["M"])
        self.T = np.array(d["T"])
        self.mu, self.lam, self.cp = np.array(d["mu"]), np.array(d["lam"]), np.array(d["cp"])
        self.D = np.array(d["D_1atm"])
        self.T0, self.dT = self.T[0], self.T[1] - self.T[0]

    def alt(self, idx):
        """sadece idx türlerini içeren hafif kopya (hızlı mod: yok olan türler hesaba girmez)."""
        idx = tuple(int(i) for i in idx)
        if not hasattr(self, "_alt"):
            self._alt = {}
        if idx not in self._alt:
            a = Gaz.__new__(Gaz)
            a.turler = [self.turler[i] for i in idx]
            a.i = {t: k for k, t in enumerate(a.turler)}
            a.M, a.T, a.T0, a.dT = self.M[list(idx)], self.T, self.T0, self.dT
            a.mu, a.lam, a.cp = self.mu[list(idx)], self.lam[list(idx)], self.cp[list(idx)]
            a.D = self.D[np.ix_(idx, idx)]
            self._alt[idx] = a
        return self._alt[idx]

    def _w(self, T):
        x = np.clip((np.asarray(T, float) - self.T0) / self.dT, 0, len(self.T) - 1.000001)
        j = np.floor(x).astype(int)
        return j, x - j

    def tablo(self, arr, T):
        """arr (ns, nT) -> (ns, *T.shape)"""
        j, w = self._w(T)
        return arr[:, j] * (1 - w) + arr[:, j + 1] * w

    def kutle_mol(self, Y):
        """Y (ns, ...) -> X, M̄"""
        n = Y / self.M.reshape((-1,) + (1,) * (Y.ndim - 1))
        s = n.sum(0)
        return n / s, 1.0 / s

    def mol_kutle(self, X):
        m = X * self.M.reshape((-1,) + (1,) * (X.ndim - 1))
        s = m.sum(0)
        return m / s, s

    def lam_mix(self, X, T):        # Mathur, Tondon & Saxena (1967)
        l = self.tablo(self.lam, T)
        return 0.5 * ((X * l).sum(0) + 1.0 / (X / l).sum(0))

    def cp_mix(self, Y, T):
        return (Y * self.tablo(self.cp, T)).sum(0)

    def mu_mix(self, X, T):         # Wilke (1950)
        mu = self.tablo(self.mu, T)
        sh = (-1,) + (1,) * (X.ndim - 1)
        Mi, Mj = self.M.reshape(sh)[:, None], self.M.reshape(sh)[None, :]
        phi = (1 + np.sqrt(mu[:, None] / mu[None, :]) * (Mj / Mi) ** 0.25) ** 2 / np.sqrt(8 * (1 + Mi / Mj))
        return (X * mu / (X[None, :] * phi).sum(1)).sum(0)

    def D_mix(self, X, Y, T, p):    # karışım-ortalamalı difüzyon katsayısı (Curtiss-Hirschfelder)
        Dij = self.tablo(self.D.reshape(len(self.M) ** 2, -1), T).reshape((len(self.M), len(self.M)) + T.shape)
        Dij = Dij * (P0 / p)
        ns = len(self.M)
        eye = np.eye(ns).reshape((ns, ns) + (1,) * T.ndim).astype(bool)
        s = np.where(eye, 0.0, X[None, :] / Dij).sum(1)
        return np.clip(1 - Y, 1e-6, None) / np.maximum(s, 1e-30)


_GAZ = None


def gaz():
    global _GAZ
    if _GAZ is None:
        _GAZ = Gaz()
    return _GAZ


# ------------------------------------------------------------------ ışınım (TNF / RADCAL Planck ortalama)
def a_planck(T):
    """Planck ortalama soğurma katsayıları [1/(m atm)]: (CO2, H2O). Barlow ve ark., TNF workshop
    (RADCAL'den uydurma, 300-2500 K)."""
    u = 1000.0 / np.clip(T, 300.0, 2500.0)
    h2o = -0.23093 - 1.12390 * u + 9.41530 * u ** 2 - 2.99880 * u ** 3 + 0.51382 * u ** 4 - 1.86840e-5 * u ** 5
    co2 = 18.741 - 121.310 * u + 273.500 * u ** 2 - 194.050 * u ** 3 + 56.310 * u ** 4 - 5.8169 * u ** 5
    return np.clip(co2, 0, None), np.clip(h2o, 0, None)


# ------------------------------------------------------------------ yardımcılar
def ortam_bilesimi(oksijen, seyreltici="n2", bilesim=None):
    """mol oranları sözlüğü (tür adı Cantera adıyla)."""
    G = gaz()
    X = np.zeros(len(G.M))
    if bilesim:
        for k, v in bilesim.items():
            t = SEYRELTICI_TUR.get(str(k).lower(), "O2" if str(k).lower() == "o2" else str(k).upper())
            if t in G.i and v and v > 0:
                X[G.i[t]] += float(v)
    else:
        X[G.i["O2"]] = float(oksijen) / 100.0
        X[G.i[SEYRELTICI_TUR.get(str(seyreltici or "n2").lower(), "N2")]] += 1 - float(oksijen) / 100.0
    return X / X.sum()


def p_doyma(T, y):
    """Clausius-Clapeyron (sabit L_b), Pa."""
    return P0 * np.exp(y["Lb"] * y["M"] / R_U * (1.0 / y["Tb"] - 1.0 / T))


def L_buhar(T, y):
    """Watson (1943) bağıntısı."""
    return y["Lb"] * (np.clip(y["Tc"] - T, 1.0, None) / (y["Tc"] - y["Tb"])) ** 0.38


def ayrisma(T):
    a = np.clip(T - 2000.0, 0, None)
    return np.minimum(T, 2000.0) + a / (1 + a / 700.0)


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50, 50)))


# ------------------------------------------------------------------ parametreler
PARAM_ADLARI = ["lnA_NC7H16", "lnA_CH3OH", "Ta", "ln_Crad", "beta", "kz", "s", "ln_kw", "ln_fsr"]
SINIRLAR = [(-15.0, 15.0), (-15.0, 15.0), (8000.0, 30000.0), (math.log(0.02), math.log(50.0)),
            (0.0, 1.0), (0.5, 1.6), (0.3, 4.0), (math.log(1e-6), math.log(0.3)), (0.0, 0.0)]
# ln_fsr: alev mesafesi oranı düzeltmesi, r_f = e^ln_fsr · FSR_yarı-durağan · ...  (Aşama 2e). Yarı-durağan kuram
# µg'de alev/damla oranını fazla verir (heptan: kuram ~30, FLEX ölçümü ~9). v1/2c'de 0'a sabit (düzeltme yok);
# DAMLA_W_ALEV > 0 iken serbest ve FLEX alev çapı ölçümüyle (data/droplet_flex_flame_target.csv) kalibre edilir.
# Aşama 2c (profil + dürüst test, bkz. experiments/asama2c_*.json):
#  - Ta ve lnA_*: profil tamamen düz (5000-18000 K aynı kayıp; lnA başlangıçtan hiç oynamıyor) -> FLEX'te
#    Damköhler ölçütü bağlayıcı değil, sönmeyi ışınım / T_f < 1200 K belirliyor. Veriden belirlenemiyor ->
#    Westbrook & Dryer (1981) değerlerine sabit: Ta = 15098 K (30 kcal/mol), lnA düzeltmesi 0.
#  - beta: profil en iyisi 1.1-1.25 (v1 sınırı 1.0). beta > 1: alev yarıçapı damla küçülürken büyür; µg'de
#    alev/damla oranının yanma boyunca arttığı gözlenir (yakıt buharı birikimi; Choi & Dryer 2001, Nayagam ve
#    ark. 2012) -> sınır 1.5. s (yanma olasılığının sigmoid genişliği, istatistiksel): sınır 4 -> 12.
#  - sönme çapı ızgara noktaları arasında ara değerle (DUZGUN_SONME): basamaklı kayıp kalibrasyonu kararsız
#    yapıyordu (aynı formül, farklı tohum -> 678-2348 arası kayıp).
DUZGUN_SONME = os.environ.get("DAMLA_DUZGUN_SONME", "1") == "1"
SABIT_PARAMETRELER = {"Ta": 15098.0, "lnA_NC7H16": 0.0, "lnA_CH3OH": 0.0, "ln_Crad": math.log(0.3)}
if os.environ.get("DAMLA_SINIR", "genis") == "genis":
    SINIRLAR[PARAM_ADLARI.index("beta")] = (0.0, 1.5)
    SINIRLAR[PARAM_ADLARI.index("s")] = (0.3, 12.0)
# Aşama 2e (benimsendi): FLEX alev çapı ölçümü (NASA/TP-2015-216046 Ek B, s. 29-305; sayısallaştırma
# scripts/flex_flame_quantify.py, doğrulama: ilk çap %1.1, K %1.5 medyan hata) kayba eklenir ve C_rad fiziksel
# aralıkta 0.3'e sabitlenir. Alev terimiyle C_rad serbestken 0.02 -> 0.19'a çıktı (beta-C_rad sırtı kırıldı).
# Dürüst AUC kaybı <= 0.011 (N2->CO2+He 0.807->0.805, heptan dışarıda 0.894->0.883, kontrol 0.712->0.711, 1 g
# 0.614->0.613); sönme çapı yakıt dışarıda heptan 2.17->0.63 mm, metanol 0.70->0.25 mm; alev oranı hatası %95->%27.
GERI_EMME = os.environ.get("DAMLA_GERI_EMME", "0") == "1"   # Aşama 2f/2g deneyi (gas_radiation.geri_emme); tam benimseme denendi, metanol-dışarıda sönme çapı hatası 0,25 -> 1,04 mm kötüleşti -> kapalı
W_ALEV = float(os.environ.get("DAMLA_W_ALEV", "1"))   # kayıpta alev çapı teriminin ağırlığı (0 = yok)
SIG_ALEV = 0.15                                     # ln(r_f/r_d) hatası ölçeği
if W_ALEV > 0:
    SINIRLAR[PARAM_ADLARI.index("ln_fsr")] = (math.log(0.05), math.log(3.0))
if os.environ.get("DAMLA_BETA_UST"):       # deney: beta üst sınırı
    SINIRLAR[PARAM_ADLARI.index("beta")] = (0.0, float(os.environ["DAMLA_BETA_UST"]))
if os.environ.get("DAMLA_SABIT_YOK") != "1":
    for _a, _v in SABIT_PARAMETRELER.items():
        SINIRLAR[PARAM_ADLARI.index(_a)] = (_v, _v)
for _k in filter(None, os.environ.get("DAMLA_SABIT", "").split(",")):
    _a, _v = _k.split("=")
    SINIRLAR[PARAM_ADLARI.index(_a)] = (float(_v), float(_v))
BASLANGIC = [0.0, 0.0, 15098.0, 0.0, 0.7, 1.0, 1.0, math.log(3e-3), 0.0]
# ln_kw: alkol damlasının su emme katsayısı k_w [kg/(m² s)] (birim su buharı kütle kesri başına)
# lnA_x: Westbrook-Dryer A'sına göre ln düzeltmesi (0 = WD değeri); Ta: K (WD: 30 kcal/mol = 15098 K)


def param_sozluk(v):
    return dict(zip(PARAM_ADLARI, [float(x) for x in v]))


def param_vektor(p):
    return [p.get(a, 0.0 if a == "ln_fsr" else BASLANGIC[PARAM_ADLARI.index(a)]) for a in PARAM_ADLARI]


ALEV_HEDEF = KOK / "data/droplet_flex_flame_target.csv"
_ALEV = None


def alev_hedefi():
    """FLEX Ek B'den sayısallaştırılmış alev/damla çap oranı (LLUV, OH* — alev yüzeyine en yakın ölçüm)."""
    global _ALEV
    if _ALEV is None:
        import pandas as pd
        _ALEV = pd.read_csv(ALEV_HEDEF) if ALEV_HEDEF.exists() else pd.DataFrame()
        if len(_ALEV):
            _ALEV = _ALEV[_ALEV.seri.eq("alev_lluv")].reset_index(drop=True)
    return _ALEV


def alev_orani(h):
    """hizli_hesap çıktısından r_f/r_d (N, Nd) ve d/d0 ızgarası (N, Nd)."""
    d_oran = np.asarray(h["d_oran"])
    rs = d_oran[None, :] * h["d0_mm"][:, None] / 2 * 1e-3
    return h["rf"] / rs, np.broadcast_to(d_oran, h["rf"].shape)


def alev_oran_model(oran, dgrid, t):
    """Hedef dilimlerinde modelin r_f/r_d oranı. -> (hedef satırları, model oranı, t'deki satır indisleri)"""
    a = alev_hedefi()
    if a is None or not len(a) or "test" not in t:
        return None
    yer = {int(x): i for i, x in enumerate(t.test.to_numpy())}
    a = a[a.test.isin(list(yer))]
    if not len(a):
        return None
    i = a.test.map(yer).to_numpy()
    m = np.array([np.interp(x, dgrid[k, ::-1], oran[k, ::-1]) for k, x in zip(i, a.d_oran.to_numpy())])
    return a, m, i


def varsayilan_parametreler():
    if PARAM_DOSYASI.exists():
        d = json.loads(PARAM_DOSYASI.read_text(encoding="utf-8"))
        return d["hizli"]["parametreler"], d.get("ayrintili", {}).get("parametreler")
    return param_sozluk(BASLANGIC), None


def lnA_yakit(p, yakit):
    """Kalibre edilmemiş yakıtlar: kalibre yakıtların WD düzeltmelerinin ortalaması."""
    k = f"lnA_{yakit}"
    if k in p:
        return p[k]
    return float(np.mean([p[f"lnA_{y}"] for y in KALIBRE_YAKITLAR if f"lnA_{y}" in p]))


# ------------------------------------------------------------------ HIZLI MOD (vektörel)
def hizli_hesap(p, yakitlar, X_inf, basinc_pa, d0_mm, g=1e-4, akis_cm_s=0.0, d_oran=D_ORAN, iter_sayisi=8):
    """yakitlar: N yakıt adı listesi; X_inf (ns, N); basinc_pa, d0_mm, g, akis: (N,)
    Dönüş: sözlük, her alan (N, Nd) ya da (N,)."""
    G0 = gaz()
    N = len(yakitlar)
    X_inf = np.asarray(X_inf, float)
    act = sorted(set(np.nonzero(X_inf.sum(1) > 0)[0]) | {G0.i[y] for y in yakitlar}
                 | {G0.i["O2"], G0.i["CO2"], G0.i["H2O"]})
    G = G0.alt(act)
    X_inf = X_inf[act]
    ns = len(G.M)
    yv = {k: np.array([YAKIT[y][k] for y in yakitlar], float)[:, None] for k in
          ("M", "Tb", "Tc", "Lb", "rho", "cl", "Q", "nC", "nH", "nu", "a", "b", "A")}
    fi = np.array([G.i[y] for y in yakitlar])
    lnA = np.array([lnA_yakit(p, y) + math.log(YAKIT[y]["A"]) for y in yakitlar])[:, None]
    pr = np.asarray(basinc_pa, float).reshape(N, 1)
    d0 = np.asarray(d0_mm, float).reshape(N, 1) * 1e-3
    gg = np.asarray(g, float).reshape(N, 1) * 9.81
    U = np.asarray(akis_cm_s, float).reshape(N, 1) * 1e-2
    rs = d0 * np.asarray(d_oran)[None, :] / 2                  # (N, Nd)
    r0 = d0 / 2
    shp = rs.shape

    Yinf, Minf = G.mol_kutle(X_inf)                             # (ns, N)
    YO = Yinf[G.i["O2"]][:, None]
    nu = yv["nu"]
    su_emer = np.array([y in SU_EMEN for y in yakitlar])[:, None]
    kw = math.exp(p.get("ln_kw", -50.0))
    Ywl = np.zeros(shp)                                        # sıvıdaki su kütle kesri (d boyunca)

    def alev_bilesimi(Ywl):
        """1 kg buhar (yakıt (1-Y_wl) + su Y_wl) + stokiyometrik O2 + beraberindeki inert -> kütle kesirleri."""
        fF = 1 - Ywl
        m = np.zeros((ns,) + shp)
        for k in range(ns):
            if k != G.i["O2"]:
                m[k] = nu * fF * Yinf[k][:, None] / np.clip(YO, 1e-9, None)
        m[G.i["CO2"]] += fF * yv["nC"] * 44.01 / yv["M"]
        m[G.i["H2O"]] += fF * yv["nH"] / 2 * 18.015 / yv["M"] + Ywl
        Yf = m / m.sum(0)
        Xf, Mf = G.kutle_mol(Yf)
        return Yf, Xf, Mf
    Yf, Xf, Mf = alev_bilesimi(Ywl)
    one_hot = np.zeros((ns, N, 1))
    one_hot[fi, np.arange(N), 0] = 1.0

    Q_ = yv["Q"]
    chi = np.zeros(shp)
    Tf = np.full(shp, 2000.0)
    Ts = np.full(shp, 300.0)
    beta, Crad, kz = p["beta"], math.exp(p["ln_Crad"]), p["kz"]
    yak = {k: v for k, v in yv.items()}
    for _ in range(iter_sayisi):
        fF = 1 - Ywl
        Qe = Q_ * fF * (1 - chi)                                 # 1 kg buhar başına
        num = nu * fF
        xFl = (fF / yv["M"]) / (fF / yv["M"] + Ywl / SU["M"])   # sıvıda yakıt mol kesri (Raoult)
        Mv = 1.0 / (fF / yv["M"] + Ywl / SU["M"])
        Tin = 0.5 * (Ts + Tf)
        cp_o = G.cp_mix(Yf, Tin)
        # T_s: Y_Fs(T_s) dengesi, ikiye bölme
        lo = np.full(shp, 250.0)
        hi = np.broadcast_to(yv["Tb"] + yv["Lb"] * yv["M"] / R_U * 0 + 0, shp).copy()
        hi = 1.0 / (1.0 / yv["Tb"] - R_U / (yv["Lb"] * yv["M"]) * np.log(pr / P0)) - 0.05   # p'deki kaynama
        hi = np.broadcast_to(hi, shp).copy()
        for _b in range(22):
            T = 0.5 * (lo + hi)
            L = fF * L_buhar(T, yak) + Ywl * L_buhar(T, SU)
            B = (cp_o * (T_INF - T) + YO * Qe / num) / L
            Yfs_enerji = (B - YO / num) / (1 + B)
            Xfs = np.clip((xFl * p_doyma(T, yak) + (1 - xFl) * p_doyma(T, SU)) / pr, 0, 0.9999)
            Mres = Mf                                          # yüzeyde buhar dışı = alev ürünleri + inert
            Yfs_denge = Xfs * Mv / (Xfs * Mv + (1 - Xfs) * Mres)
            fazla = Yfs_denge > Yfs_enerji                       # T çok yüksek
            hi = np.where(fazla, T, hi)
            lo = np.where(fazla, lo, T)
        Ts = 0.5 * (lo + hi)
        L = fF * L_buhar(Ts, yak) + Ywl * L_buhar(Ts, SU)
        B = np.clip((cp_o * (T_INF - Ts) + YO * Qe / num) / L, 1e-3, None)
        Yfs = np.clip((B - YO / num) / (1 + B), 0, 1)
        Tf_ad = Ts + L / cp_o * ((1 + B) / (1 + YO / num) - 1)
        Tf_new = ayrisma(np.clip(Tf_ad, T_INF, None))
        Tf = 0.5 * Tf + 0.5 * Tf_new
        # iç bölge (λ/c_p): yüzey (yakıt buharı + alev bileşimi) ile alev bileşiminin ortalaması
        Ys = Yfs[None] * (fF[None] * one_hot + Ywl[None] * (np.arange(ns) == G.i["H2O"])[:, None, None]) \
            + (1 - Yfs)[None] * Yf
        Yi = 0.5 * (Ys + Yf)
        Xi, _ = G.kutle_mol(Yi)
        Tin = 0.5 * (Ts + Tf)
        lcp = G.lam_mix(Xi, Tin) / G.cp_mix(Yi, Tin)
        # taşınım düzeltmesi (g, akış): film özellikleri ortam bileşimi ile
        if TASINIM_YOK(gg, U):
            nu2 = np.ones(shp)
        else:
            nu2 = _nu2(G, X_inf, Yinf, pr, Tf, rs, gg, U, shp, ns, p.get("c_tasinim", C_TASINIM),
                       p.get("n_tasinim", N_TASINIM))
        mdot = 4 * math.pi * lcp * kz * rs * np.log1p(B) * nu2      # kg/s
        FSR = np.log1p(B) / np.log1p(YO / num)
        rf = math.exp(p.get("ln_fsr", 0.0)) * FSR * rs ** (1 - beta) * r0 ** beta / nu2
        Xa_f = Xf
        kp = a_planck(Tf)
        p_atm = pr / P0
        Qrad = Crad * 4 * SIGMA * p_atm * (Xa_f[G.i["CO2"]] * kp[0] + Xa_f[G.i["H2O"]] * kp[1]) * \
            (Tf ** 4 - T_INF ** 4) * (4 / 3) * math.pi * rf ** 3
        if GERI_EMME:
            # scripts/gas_radiation.py (gaz oturumu): gri izotermal küre, L_m = 3.6 V/A = 1.2 r_f; ortam CO2/H2O'su da
            # aynı yol boyunca soğurur (modülün VARSAYIMI). Q = Q_ince · (1 - e^-τ)/τ
            import gas_radiation as gas_radiation
            k_alev = p_atm * (Xa_f[G.i["CO2"]] * kp[0] + Xa_f[G.i["H2O"]] * kp[1])
            kpa = a_planck(np.full(1, T_INF))
            k_ortam = p_atm * (X_inf[G.i["CO2"]][:, None] * kpa[0][0] + X_inf[G.i["H2O"]][:, None] * kpa[1][0])
            Qrad = Qrad * gas_radiation.geri_emme((k_alev + k_ortam) * 1.2 * rf)
        chi_new = np.clip(Qrad / (mdot * Q_ * fF), 0, 0.97)
        chi = 0.5 * chi + 0.5 * chi_new
        K = 8 * lcp * kz * np.log1p(B) * nu2 / yv["rho"]                 # m²/s
        if su_emer.any() and kw > 0 and shp[1] > 1:
            # su emme (Marchese & Dryer 1996; Dryer ve ark. 2014 FLEX): alevin suyu yüzeye yayınır ve
            # alkol damlasında çözünür. dm_w/dt = k_w π d² Y_H2O,s ;  t(d) d² eğrisinden.
            # Emilen su birikir -> Raoult ile yakıt buharı azalır, L artar, alev seyrelir/soğur.
            d = 2 * rs
            d2 = d ** 2
            Kort = 0.5 * (K[:, 1:] + K[:, :-1])
            dt = np.clip((d2[:, :-1] - d2[:, 1:]) / np.maximum(Kort, 1e-12), 0, None)
            Yws = (1 - Yfs) * Yf[G.i["H2O"]]
            akim = kw * math.pi * d2 * Yws
            mw = np.concatenate([np.zeros((N, 1)), np.cumsum(0.5 * (akim[:, 1:] + akim[:, :-1]) * dt, 1)], 1)
            ml = yv["rho"] * math.pi * d ** 3 / 6
            Ywl_yeni = np.where(su_emer, np.clip(mw / ml, 0, 0.8), 0.0)
            Ywl = 0.5 * Ywl + 0.5 * Ywl_yeni
            Yf, Xf, Mf = alev_bilesimi(Ywl)
    K = K * 1e6                                                      # mm²/s
    h = _hizli_son(G, p, yv, lnA, pr, Xf, Yf, Mf, YO, Tf, Ts, B, chi, rf, nu2, K, d_oran, d0, shp, ns)
    h["Ywl"] = Ywl
    return h


G_TASINIM = (1e-4, 1e-2)    # g/g0: doğal taşınım terimi bu aralıkta log ölçekte 0'dan 1'e açılır


def TASINIM_YOK(gg, U):
    """g <= 1e-4 g0 (FLEX / ISS; kalibrasyon burada, Nu/2 = 1) ve akış yoksa taşınım yok.
    Not: eski sürüm g < 1e-3'te kesiyordu; Gr^(1/4) orada %6-22 katkı veriyordu -> g = 1e-3'te sıçrama."""
    return bool(np.all(gg <= G_TASINIM[0] * 9.81 * 1.0001) and np.all(U <= 0))


def _tasinim_rampasi(gg):
    """Doğal taşınım teriminin ağırlığı: g <= 1e-4 g0 -> 0, g >= 1e-2 g0 -> 1, arada log-doğrusal.
    Mühendislik varsayımı (bu aralıkta veri yok): µg'de Stefan akışı baskın, Faeth'in Gr^(1/4) bağıntısı
    büyük Gr için; sert eşiğin yarattığı süreksizliği kaldırır. Ay / Mars / Dünya'yı etkilemez."""
    a, b = np.log10(G_TASINIM[0]), np.log10(G_TASINIM[1])
    return np.clip((np.log10(np.maximum(gg / 9.81, 1e-12)) - a) / (b - a), 0.0, 1.0)


C_TASINIM = 0.3     # Ranz & Marshall (1952) katsayısı
N_TASINIM = 0.25    # (Re² + Gr) üssü (Ranz & Marshall / Faeth: 1/4)


def _nu2(G, X_inf, Yinf, pr, Tf, rs, gg, U, shp, ns, c=C_TASINIM, n=None):
    """Nu/2 = 1 + c Pr^(1/3) (Re² + Gr)^(1/4)  (Ranz & Marshall 1952, c = 0.3; Faeth 1977) — yaklaşık."""
    Tfilm = 0.5 * (Tf + T_INF)
    Xa = np.broadcast_to(X_inf[:, :, None], (ns,) + shp)
    Ma = (Xa * G.M.reshape(-1, 1, 1)).sum(0)
    rho_a = pr * Ma / (R_U * Tfilm)
    mu = G.mu_mix(Xa, Tfilm)
    nu_k = mu / rho_a
    Pr = mu * G.cp_mix(np.broadcast_to(Yinf[:, :, None], (ns,) + shp), Tfilm) / G.lam_mix(Xa, Tfilm)
    d = 2 * rs
    Gr = gg * np.clip(Tf - T_INF, 0, None) / T_INF * d ** 3 / nu_k ** 2 * _tasinim_rampasi(gg) ** 4
    Re = U * d / nu_k
    n = N_TASINIM if n is None else n
    return 1 + c * Pr ** (1 / 3) * (Re ** 2 + Gr) ** n


def _hizli_son(G, p, yv, lnA, pr, Xf, Yf, Mf, YO, Tf, Ts, B, chi, rf, nu2, K, d_oran, d0, shp, ns):
    """Damköhler sayısı ve sönme."""
    Xfl = np.broadcast_to(Xf, (ns,) + shp)
    rho_f = pr * Mf / (R_U * Tf)
    alpha_f = G.lam_mix(Xfl, Tf) / (rho_f * G.cp_mix(np.broadcast_to(Yf, (ns,) + shp), Tf))
    lnDa = (np.log(rf ** 2 / alpha_f) + lnA + (yv["a"] + yv["b"] - 1) * np.log(rho_f)
            + yv["b"] * np.log(np.clip(YO, 1e-6, None)) - p["Ta"] / Tf)
    sonuk = (lnDa < 0) | (Tf < T_SONME)
    return {"K": K, "Tf": Tf, "Ts": Ts, "B": B, "chi": chi, "lnDa": lnDa, "sonuk": sonuk, "rf": rf,
            "nu2": nu2, "d_oran": np.asarray(d_oran), "d0_mm": d0[:, 0] * 1e3}


def hizli_ozet(h, s):
    """hizli_hesap çıktısından test başına: yanma, sönme çapı, ortalama K, alev sıcaklığı."""
    d_oran = h["d_oran"]
    bas = d_oran >= HEMEN_SONDU_ORANI
    marj = np.minimum(h["lnDa"], (h["Tf"] - T_SONME) / 100.0)     # sürekli: iki sönme ölçütünün en kötüsü
    yanma = sigmoid(marj[:, bas].min(1) / s)
    sonuk = h["sonuk"]
    ilk = np.where(sonuk.any(1), sonuk.argmax(1), -1)
    sonme_orani = np.where(ilk >= 0, d_oran[np.clip(ilk, 0, None)], np.nan)
    if DUZGUN_SONME:
        # sönme noktası iki ızgara noktası arasında marj = 0 kesişiminden (doğrusal ara değer): ızgaraya
        # yuvarlanan sönme çapı kaybı basamaklı yapıyordu (gradyan 0 / sıçrama -> kalibrasyon kararsız)
        j = np.clip(ilk, 1, None)
        r_ = np.arange(len(ilk))
        m0, m1 = marj[r_, j - 1], marj[r_, j]
        f = np.clip(m0 / np.where(m0 - m1 > 1e-12, m0 - m1, np.inf), 0, 1)
        ara = d_oran[j - 1] + f * (d_oran[j] - d_oran[j - 1])
        sonme_orani = np.where(ilk > 0, ara, sonme_orani)
    # d² eğrisi boyunca ortalama K (sönmeye kadar): t = ∫ d(d²)/K
    d2 = (d_oran[None, :] * h["d0_mm"][:, None]) ** 2
    dt = -np.diff(d2, axis=1) / (0.5 * (h["K"][:, 1:] + h["K"][:, :-1]))
    son = np.where(ilk >= 0, ilk, len(d_oran) - 1)
    maske = np.arange(len(d_oran) - 1)[None, :] < son[:, None]
    t_son = np.where(maske, dt, 0).sum(1)
    K_ort = np.where(t_son > 0, (d2[:, 0] - d2[np.arange(len(son)), son]) / np.maximum(t_son, 1e-12), h["K"][:, 0])
    oran, dgrid = alev_orani(h)
    return {"yanma": yanma, "sonme_orani": sonme_orani, "sonme_capi": sonme_orani * h["d0_mm"],
            "K": K_ort, "K0": h["K"][:, 0], "Tf0": h["Tf"][:, 0], "t_son": t_son, "chi0": h["chi"][:, 0],
            "_oran": oran, "_dgrid": np.ascontiguousarray(dgrid)}


def _hizli_tek(p, yakit, X, basinc_kpa, d0, g, akis):
    h = hizli_hesap(p, [yakit], X[:, None], [basinc_kpa * 1e3], [d0], [g], [akis])
    return hizli_ozet(h, p["s"]), h


def min_oksijen_bul(p, yakit, X, basinc_kpa, d0, g, akis):
    """O2 mol oranı değiştirilir, diğer gazların birbirine oranı sabit; yanma >= 0.5 olan en düşük O2 (%).
    Tek vektörel çağrıda 0.25'lik ızgara (%1-60)."""
    G = gaz()
    o2 = np.arange(1.0, 60.0001, 0.25)
    io = G.i["O2"]
    diger = X.copy()
    diger[io] = 0
    diger = diger / diger.sum()
    Xs = (diger[:, None] * (1 - o2 / 100)[None, :])
    Xs[io] = o2 / 100
    n = len(o2)
    h = hizli_hesap(p, [yakit] * n, Xs, np.full(n, basinc_kpa * 1e3), np.full(n, d0), np.full(n, g),
                    np.full(n, akis), d_oran=D_ORAN[D_ORAN >= HEMEN_SONDU_ORANI])
    y = hizli_ozet(h, p["s"])["yanma"]
    i = np.nonzero(y >= 0.5)[0]
    return float(o2[i[0]]) if len(i) else None


# ------------------------------------------------------------------ dış arayüz
def droplet_engine(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi=None, seyreltici="n2",
                 mod="hizli", bilesim=None, parametreler=None):
    """mod="hizli" (varsayılan, ~30 ms) ya da "ayrintili" (1B zamana bağlı, damla başına 20-60 s)."""
    yakit = yakit_bul(malzeme)
    bayrak, uyari = durum_notlari(yakit, g, akis, numune_tipi)
    bos = {"yanma": None, "min_oksijen": None, "yayilma_hizi": None, "yanma_hizi_K": None,
           "sonme_capi": None, "sicaklik": None, "mesafe": 0, "uyarilar": uyari, **bayrak}
    if yakit is None or oksijen is None or basinc is None or str(numune_tipi or "").lower() in HAVUZ_TIPLERI:
        return bos
    ek = {"uyarilar": uyari, **bayrak}
    p_h, p_a = varsayilan_parametreler()
    if parametreler:
        p_h = parametreler
    g = 1e-4 if g is None else float(g)
    akis = 0.0 if akis is None else float(akis)
    d0 = 2.0 if kalinlik is None or not kalinlik > 0 else float(kalinlik)
    X = ortam_bilesimi(oksijen, seyreltici, bilesim)
    min_o2 = min_oksijen_bul(p_h, yakit, X, float(basinc), d0, g, akis)
    if mod == "hizli":
        o, h = _hizli_tek(p_h, yakit, X, float(basinc), d0, g, akis)
        sc = o["sonme_capi"][0]
        sa, sa_t = soguk_alev(yakit, X, float(o["yanma"][0]), float(sc), float(o["K"][0]))
        ek = dict(ek, soguk_alev=sa, soguk_alev_suresi_s=None if sa_t is None else round(sa_t, 2),
                  sonme_turu=sonme_turu(p_h, yakit, X, float(basinc), d0, g, akis, float(sc)),
                  isinim_temsili=ISINIM_NOTU)
        if sa:
            ek["uyarilar"] = ek["uyarilar"] + [SOGUK_UYARI]
        return {"yanma": round(float(o["yanma"][0]), 4), "min_oksijen": min_o2, "yayilma_hizi": None,
                "yanma_hizi_K": round(float(o["K"][0]), 4),
                "sonme_capi": None if np.isnan(sc) else round(float(sc), 3),
                "sicaklik": round(float(o["Tf0"][0]), 1), "mesafe": 0, **ek}
    r = ayrintili_kosu(yakit, X, float(basinc), d0, g, akis, p_a or AYRINTILI_BASLANGIC)
    return {"yanma": r["yanma"], "min_oksijen": min_o2, "yayilma_hizi": None, "yanma_hizi_K": r["K"],
            "sonme_capi": r["sonme_capi"], "sicaklik": r["T_maks"], "mesafe": 0, **ek}


# ------------------------------------------------------------------ veri
def flex_oku():
    import pandas as pd
    f = next((x for x in FLEX_ADAYLAR if x.exists()), None)
    if f is None:
        raise SystemExit("psi_flex_testler.csv bulunamadı: " + ", ".join(map(str, FLEX_ADAYLAR)))
    t = pd.read_csv(f)
    t = t[(t.basinc_kpa > 5) & t.ilk_cap_mm.notna() & t.oksijen_yuzde.notna()].copy()
    t["yakit"] = t.yakit.map({"heptane": "NC7H16", "methanol": "CH3OH"})
    t["yanar"] = (~t.hemen_sondu.astype(bool)).astype(int)
    t["sondu"] = t.test_sonu.eq("Extinction") & t.sonme_capi_mm.notna()
    t["kaynak_dosya"] = str(f)
    return t.reset_index(drop=True)


def flex_bilesim(t):
    G = gaz()
    X = np.zeros((len(G.M), len(t)))
    for kol, tur in (("oksijen_yuzde", "O2"), ("n2_yuzde", "N2"), ("co2_yuzde", "CO2"), ("he_yuzde", "HE")):
        X[G.i[tur]] = t[kol].fillna(0).to_numpy(float)
    return X / X.sum(0)


# ------------------------------------------------------------------ hızlı mod kalibrasyonu
W_K, W_D = 1.0, 1.0
SIG_K, SIG_D = 0.10, 0.10


def kayip_hizli(v, t, X, ayrinti=False):
    p = param_sozluk(v)
    h = hizli_hesap(p, list(t.yakit), X, t.basinc_kpa.to_numpy() * 1e3, t.ilk_cap_mm.to_numpy(),
                    np.full(len(t), 1e-4), np.zeros(len(t)), d_oran=D_ORAN_KAL)
    o = hizli_ozet(h, p["s"])
    y = t.yanar.to_numpy(float)
    q = np.clip(o["yanma"], 1e-6, 1 - 1e-6)
    bce = -np.sum(y * np.log(q) + (1 - y) * np.log(1 - q))
    Kobs = t.yanma_hizi_mm2_s.to_numpy(float)
    mk = np.isfinite(Kobs) & (Kobs > 0.05)
    kK = np.sum(((np.log(np.clip(o["K"][mk], 1e-4, None)) - np.log(Kobs[mk])) / SIG_K) ** 2)
    sond = t.sondu.to_numpy() & (y == 1)            # anlamlı sönme çapı (hemen sönmeyenler)
    d_obs = (t.sonme_capi_mm / t.ilk_cap_mm).to_numpy(float)
    d_mod = np.nan_to_num(o["sonme_orani"], nan=0.0)
    kD = np.sum(((d_mod[sond] - d_obs[sond]) / SIG_D) ** 2)
    ys = ~t.test_sonu.eq("Extinction").to_numpy()   # tamamen yandı / parçalandı: model erken söndürmesin
    kD += np.sum((np.clip(d_mod[ys] - 0.3, 0, None) / SIG_D) ** 2)
    top = bce + W_K * kK + W_D * kD
    kF = 0.0
    if W_ALEV > 0:
        r = alev_oran_model(*alev_orani(h), t)
        if r is not None:
            a, m, i = r
            e = ((np.log(np.clip(m, 1e-3, None)) - np.log(a.oran.to_numpy())) / SIG_ALEV) ** 2
            kF = float(np.bincount(i, e)[np.unique(i)].sum() / 1.0
                       / np.maximum(np.bincount(i)[np.unique(i)], 1).mean())   # test başına ~1 terim
            top += W_ALEV * kF
    if ayrinti:
        return top, {"bce": bce, "K": kK, "D": kD, "F": kF}
    return top


def kalibre_hizli(t, X, baslangic_sayisi=8, tohum=0, sabit=None, x_ilk=None):
    from scipy.optimize import minimize
    rng = np.random.default_rng(tohum)
    lo = np.array([b[0] for b in SINIRLAR])
    hi = np.array([b[1] for b in SINIRLAR])
    en_iyi = None
    for k in range(baslangic_sayisi):
        bas = BASLANGIC if x_ilk is None else x_ilk
        x0 = np.clip(np.array(bas, float), lo, hi) if k == 0 else lo + rng.random(len(lo)) * (hi - lo)
        r = minimize(kayip_hizli, x0, args=(t, X), method="L-BFGS-B", bounds=SINIRLAR,
                     options={"maxiter": 400})
        if en_iyi is None or r.fun < en_iyi.fun:
            en_iyi = r
    return en_iyi


def olcutler(t, o):
    from sklearn.metrics import roc_auc_score
    y = t.yanar.to_numpy()
    Kobs = t.yanma_hizi_mm2_s.to_numpy(float)
    mk = np.isfinite(Kobs) & (Kobs > 0.05)
    K_hata = np.abs(o["K"][mk] / Kobs[mk] - 1) * 100
    sond = t.sondu.to_numpy() & (y == 1)
    d_obs = t.sonme_capi_mm.to_numpy(float)
    d_mod = np.nan_to_num(o["sonme_capi"], nan=0.0)
    dh = np.abs(d_mod[sond] - d_obs[sond])
    auc = roc_auc_score(y, o["yanma"]) if len(set(y)) == 2 else float("nan")
    af = float("nan")
    if "_oran" in o:
        r = alev_oran_model(o["_oran"], o["_dgrid"], t)
        if r is not None:
            af = float(np.median(np.abs(r[1] / r[0].oran.to_numpy() - 1)) * 100)
    return {"n": int(len(t)), "alev_oran_medyan_hata_yuzde": af, "K_medyan_hata_yuzde": float(np.median(K_hata)) if mk.any() else float("nan"),
            "sonme_capi_medyan_hata_mm": float(np.median(dh)) if sond.any() else float("nan"),
            "sonme_capi_medyan_hata_oran": float(np.median(dh / t.ilk_cap_mm.to_numpy()[sond])) if sond.any()
            else float("nan"),
            "dogruluk": float(((o["yanma"] > 0.5).astype(int) == y).mean()), "auc": float(auc),
            "yanan_orani": float(y.mean())}


def hizli_tahmin(p, t, X):
    h = hizli_hesap(p, list(t.yakit), X, t.basinc_kpa.to_numpy() * 1e3, t.ilk_cap_mm.to_numpy(),
                    np.full(len(t), 1e-4), np.zeros(len(t)))
    return hizli_ozet(h, p["s"])


def flex2_kontrol(p):
    """data/psi_labeled_flex2.csv damla satırları (makaleler; kalibrasyonda kullanılmadı)."""
    import pandas as pd
    from sklearn.metrics import roc_auc_score
    d = pd.read_csv(FLEX2_DOSYASI)
    d = d[(d.numune_tipi == "droplet") & d.malzeme_sade.map(yakit_bul).notna()].reset_index(drop=True)
    yan = []
    for _, x in d.iterrows():
        X = ortam_bilesimi(x.oksijen_yuzde, x.seyreltici)
        o, _h = _hizli_tek(p, yakit_bul(x.malzeme_sade), X, x.basinc_kpa, x.kalinlik_mm, x.g_seviyesi, 0.0)
        yan.append(float(o["yanma"][0]))
    d["model"] = yan
    y = d.yanar.to_numpy()
    auc = roc_auc_score(y, d.model) if len(set(y)) == 2 else float("nan")
    return d, {"n": len(d), "dogruluk": float(((d.model > 0.5).astype(int) == y).mean()), "auc": float(auc)}


def kalibre_hizli_main():
    t = flex_oku()
    X = flex_bilesim(t)
    bas = time.time()
    r = kalibre_hizli(t, X)
    p = param_sozluk(r.x)
    _, parca = kayip_hizli(r.x, t, X, ayrinti=True)
    o = hizli_tahmin(p, t, X)
    m = olcutler(t, o)
    d2, m2 = flex2_kontrol(p)
    eski = json.loads(PARAM_DOSYASI.read_text(encoding="utf-8")) if PARAM_DOSYASI.exists() else {}
    eski["hizli"] = {"parametreler": p, "kayip": float(r.fun), "kayip_parcalari": parca,
                     "veri": f"{t.kaynak_dosya.iloc[0]} ({len(t)} test)", "olcut_egitim": m,
                     "olcut_flex2_kontrol": m2,
                     "not": "lnA_*: Westbrook-Dryer A'sına ln düzeltme; kalibre edilmeyen yakıtlar "
                            "(etanol, n-dekan, 1-propanol) kalibre yakıtların ortalama düzeltmesini alır"}
    PARAM_DOSYASI.write_text(json.dumps(eski, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Hızlı mod kalibrasyonu: {len(t)} test, kayıp {r.fun:.1f} {parca}, {time.time() - bas:.0f} s")
    for k, v in p.items():
        print(f"  {k:12s} {v:10.4f}")
    print("Eğitim:", {k: round(v, 3) for k, v in m.items()})
    print("flex2 kontrol:", m2)


def dogrula_hizli_main():
    import pandas as pd
    t = flex_oku()
    X = flex_bilesim(t)
    satir, kayit = [], []
    p_tum, _ = varsayilan_parametreler()      # --kalibre-hizli'nin sonucu (tekrar kalibre edilmez)
    o_tum = hizli_tahmin(p_tum, t, X)
    # 1) N2 -> CO2 / He
    n2 = (t.seyreltici == "n2").to_numpy()
    r_n2 = kalibre_hizli(t[n2].reset_index(drop=True), X[:, n2], baslangic_sayisi=6)
    p_n2 = param_sozluk(r_n2.x)
    print("N2 ile kalibre parametreler:", {k: round(v, 3) for k, v in p_n2.items()})
    o_n2 = hizli_tahmin(p_n2, t, X)
    for ad, mk in (("eğitim N2 (içeride)", n2), ("test CO2", (t.seyreltici == "co2").to_numpy()),
                   ("test He", (t.seyreltici == "he").to_numpy()), ("test CO2+He", ~n2)):
        satir.append({"deney": "N2 ile kalibre", "alt_kume": ad,
                      **olcutler(t[mk].reset_index(drop=True), {k: v[mk] for k, v in o_n2.items()})})
    # 2) yakıt dışarıda
    o_yd = {k: np.full(np.shape(v), np.nan) for k, v in o_tum.items()}
    for y in KALIBRE_YAKITLAR:
        mk = (t.yakit == y).to_numpy()
        p_y = param_sozluk(kalibre_hizli(t[~mk].reset_index(drop=True), X[:, ~mk], baslangic_sayisi=6).x)
        # dışarıdaki yakıtın A düzeltmesi bilinmiyor -> içerideki yakıtınki
        diger = [z for z in KALIBRE_YAKITLAR if z != y][0]
        p_y[f"lnA_{y}"] = p_y[f"lnA_{diger}"]
        o = hizli_tahmin(p_y, t, X)
        for k in o_yd:
            o_yd[k][mk] = o[k][mk]
        satir.append({"deney": "yakıt dışarıda", "alt_kume": f"test {y}",
                      **olcutler(t[mk].reset_index(drop=True), {k: v[mk] for k, v in o.items()})})
    satir.append({"deney": "tüm veriyle kalibre (içeride)", "alt_kume": "hepsi", **olcutler(t, o_tum)})
    for s in ("n2", "co2", "he"):
        mk = (t.seyreltici == s).to_numpy()
        satir.append({"deney": "tüm veriyle kalibre (içeride)", "alt_kume": s,
                      **olcutler(t[mk].reset_index(drop=True), {k: v[mk] for k, v in o_tum.items()})})
    tab = pd.DataFrame(satir)
    pd.set_option("display.width", 220)
    print(tab.round(3).to_string(index=False))
    # sönme çapı hatası: yakıt × seyreltici (üç modelle)
    g_s = []
    for (yk, sy), x in t.groupby(["yakit", "seyreltici"]):
        mk = t.index.isin(x.index)
        for ad, o in (("tüm veri (içeride)", o_tum), ("N2 ile kalibre", o_n2), ("yakıt dışarıda", o_yd)):
            m = olcutler(t[mk].reset_index(drop=True), {k: v[mk] for k, v in o.items()})
            sond = (x.sondu & (x.yanar == 1)).sum()
            g_s.append({"yakit": yk, "seyreltici": sy, "model": ad, "test": len(x), "sonme_olcumu": int(sond),
                        "sonme_capi_medyan_hata_mm": m["sonme_capi_medyan_hata_mm"],
                        "sonme_capi_medyan_hata_oran": m["sonme_capi_medyan_hata_oran"],
                        "K_medyan_hata_yuzde": m["K_medyan_hata_yuzde"], "dogruluk": m["dogruluk"], "auc": m["auc"]})
    gs = pd.DataFrame(g_s)
    print()
    print(gs.round(3).to_string(index=False))
    gs.to_csv(KOK / "data/droplet_validation_groups.csv", index=False, encoding="utf-8-sig")
    tab.to_csv(KOK / "data/droplet_validation_summary_fast.csv", index=False, encoding="utf-8-sig")
    nok = t[["test", "kimlik", "yakit", "seyreltici", "basinc_kpa", "oksijen_yuzde", "n2_yuzde", "co2_yuzde",
             "he_yuzde", "ilk_cap_mm", "sonme_capi_mm", "yanma_hizi_mm2_s", "test_sonu", "yanar"]].copy()
    for ad, o in (("hizli_tum", o_tum), ("hizli_n2kal", o_n2), ("hizli_yakitdisarida", o_yd)):
        nok[f"{ad}_yanma"] = o["yanma"]
        nok[f"{ad}_K"] = o["K"]
        nok[f"{ad}_sonme_capi"] = o["sonme_capi"]
    nok.to_csv(KOK / "data/droplet_validation.csv", index=False, encoding="utf-8-sig")
    print("Kaydedildi: data/droplet_validation.csv, data/droplet_validation_summary_fast.csv, data/droplet_validation_groups.csv")


# ------------------------------------------------------------------ belirsizlik bandı (Aşama 3b; bootstrap)
# FLEX testleri DENEY GRUBUNA (aynı yakıt + seyreltici + O2 + ~basınç: aynı koşulun tekrarları) göre yerine
# koyarak yeniden örneklenir, her örnekte hızlı mod yeniden kalibre edilir (python3 scripts/droplet_engine.py --bootstrap 50).
# Parametre kümeleri data/droplet_engine_parameters.json["bootstrap"]'ta; tahminde her küme ile yeniden hesaplanır,
# ± = 16-84 yüzdelik aralığının yarısı (~1σ). Yalnız kalibrasyon belirsizliği: model biçimi hatası dahil DEĞİL.
BS_TAHMIN_EN_FAZLA = 50


def deney_grubu(t):
    return (t.yakit.astype(str) + "|" + t.seyreltici.astype(str) + "|" + t.oksijen_yuzde.round(1).astype(str)
            + "|" + (t.basinc_kpa / 10).round().astype(int).astype(str))


def _bs_isci(arg):
    tohum, x_ilk = arg
    t = flex_oku()
    X = flex_bilesim(t)
    gr = deney_grubu(t).to_numpy()
    adlar = np.unique(gr)
    rng = np.random.default_rng(1000 + tohum)
    sec = rng.choice(adlar, size=len(adlar), replace=True)
    idx = np.concatenate([np.nonzero(gr == a)[0] for a in sec])
    tb = t.iloc[idx].reset_index(drop=True)
    r = kalibre_hizli(tb, X[:, idx], baslangic_sayisi=4, tohum=tohum, x_ilk=x_ilk)
    return {"tohum": tohum, "kayip": float(r.fun), "test": int(len(tb)), "parametreler": param_sozluk(r.x)}


def bootstrap_main(n, cekirdek):
    from multiprocessing import Pool
    p, _ = varsayilan_parametreler()
    x_ilk = param_vektor(p)
    t = flex_oku()
    bas = time.time()
    with Pool(cekirdek) as havuz:
        sonuc = []
        for k, r in enumerate(havuz.imap_unordered(_bs_isci, [(i, x_ilk) for i in range(n)])):
            sonuc.append(r)
            print(f"  bootstrap {k + 1}/{n}  tohum {r['tohum']}  kayıp {r['kayip']:.0f}  ({time.time() - bas:.0f} s)",
                  flush=True)
    sonuc.sort(key=lambda r: r["tohum"])
    d = json.loads(PARAM_DOSYASI.read_text(encoding="utf-8"))
    d["bootstrap"] = {"n": n, "grup": "deney grubu = yakıt|seyreltici|O2|basınç(10 kPa)",
                      "grup_sayisi": int(deney_grubu(t).nunique()), "baslangic": 4,
                      "sure_dk": round((time.time() - bas) / 60, 1), "kumeler": sonuc}
    PARAM_DOSYASI.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    P = np.array([param_vektor(r["parametreler"]) for r in sonuc])
    for j, a in enumerate(PARAM_ADLARI):
        print(f"  {a:12s} {param_vektor(p)[j]:10.4f}   bootstrap 16-84: {np.percentile(P[:, j], 16):.4f} .. "
              f"{np.percentile(P[:, j], 84):.4f}")
    print(f"Kaydedildi: {PARAM_DOSYASI.name}['bootstrap'] ({n} küme, {(time.time() - bas) / 60:.1f} dk)")


_BS = None


def bootstrap_kumeleri():
    global _BS
    if _BS is None:
        d = json.loads(PARAM_DOSYASI.read_text(encoding="utf-8")) if PARAM_DOSYASI.exists() else {}
        _BS = [r["parametreler"] for r in (d.get("bootstrap") or {}).get("kumeler", [])][:BS_TAHMIN_EN_FAZLA]
    return _BS


BS_MIN_OKSIJEN = 25     # en düşük O2 taraması pahalı: ilk 25 küme (yanma ve K: hepsi)


def belirsizlik(yakit, X, basinc_kpa, d0, g, akis, min_oksijen=True):
    """Bootstrap kümeleriyle ± (16-84 yüzdelik yarı genişliği). Küme yoksa None."""
    K = bootstrap_kumeleri()
    if not K:
        return None
    n = len(K)
    # tek vektörel çağrı yerine küme başına (parametre kümesi skaler); d_oran seyrek -> hızlı
    yan, Kh, mo = [], [], []
    for p in K:
        h = hizli_hesap(p, [yakit], X[:, None], [basinc_kpa * 1e3], [d0], [g], [akis], d_oran=D_ORAN_KAL)
        o = hizli_ozet(h, p["s"])
        yan.append(float(o["yanma"][0]))
        Kh.append(float(o["K"][0]))
        if min_oksijen and len(mo) < BS_MIN_OKSIJEN:
            m = min_oksijen_bul(p, yakit, X, basinc_kpa, d0, g, akis)
            mo.append(np.nan if m is None else m)
    yar = lambda a: None if not np.isfinite(a).any() else float((np.nanpercentile(a, 84) - np.nanpercentile(a, 16)) / 2)
    out = {"yanma": yar(np.array(yan)), "yanma_hizi_K": yar(np.array(Kh)),
           "min_oksijen": yar(np.array(mo)) if min_oksijen else None, "n": n,
           "yontem": f"FLEX deney grubu bootstrap ({n} kalibrasyon; en düşük O2 için ilk {min(n, BS_MIN_OKSIJEN)}), "
                     "± = 16-84 yüzdelik yarı genişliği; yalnız kalibrasyon belirsizliği (model biçimi hatası dahil "
                     "değil)"}
    if min_oksijen:
        out["min_oksijen_bulunamayan"] = int(np.isnan(np.array(mo)).sum())
    return out


# ------------------------------------------------------------------ soğuk alev (Aşama 3a; ampirik)
# FLEX'te n-heptan damlalarında sıcak (görünür) alev ışınımla söndükten sonra damla buharlaşmaya devam eder:
# düşük sıcaklık kimyasıyla süren, gözle görünmeyen "soğuk alev" (Nayagam ve ark. 2012, Combust. Flame 159:3583;
# Farouk & Dryer 2014). psi_flex_testler.csv'de soğuk alev sütunu yok; test başına gözlem NASA/TP-2015-216046
# şekil altyazılarından çıkarıldı (scripts/cold_flame_label.py -> data/droplet_cold_flame_label.csv: heptan 38 var / 8 yok).
# Ampirik kural (etiketlerle sınandı, kalibre EDİLMEDİ):
#   soğuk alev = n-alkan yakıt  VE  sıcak alev damla bitmeden söndü (sönme çapı var; hemen sönme dahil)  VE  He < %10
#   (FLEX: 'yok' denen 5 testin 3'ü He'li; metanol testlerinde hiç gözlenmedi). Etiketli 40 heptan testinde
#   doğruluk %87 (46 etiketli test; "hep var" %83; 4 kaçan, 2 yanlış alarm). Kural etiketlere bakılarak
#   seçildi ("yanma >= 0.5" koşulu kaldırıldı) -> örneklem içi sonuç, dürüst test değil. Eşleme: rapor
#   FLEX–NNN -> CSV test, data/droplet_flex_report_matching.csv (numaralar 157. testten sonra kayıyor).
# Süre: d_s (sıcak alevin sönme çapı) -> d_c = D_SOGUK_ORAN·d_s arası, K_soğuk = K_SOGUK_ORAN·K_sıcak ile
#   t = (d_s² - d_c²) / K_soğuk.  ORANLAR YAKLAŞIK (literatür düzeyi; FLEX verisinde ölçüm yok) -> süre kaba tahmin.
SOGUK_ALEV_YAKITLAR = {"NC7H16", "NC10H22"}
SOGUK_HE_SINIR = 0.10
K_SOGUK_ORAN = 0.5
D_SOGUK_ORAN = 0.5


def soguk_alev(yakit, X, yanma, sonme_capi_mm, K_mm2_s):
    """-> (var mı, süre s ya da None)."""
    G = gaz()
    he = float(X[G.i["HE"]]) if "HE" in G.i else 0.0
    var = (yakit in SOGUK_ALEV_YAKITLAR and sonme_capi_mm is not None
           and not (isinstance(sonme_capi_mm, float) and math.isnan(sonme_capi_mm)) and he < SOGUK_HE_SINIR)
    if not var or not K_mm2_s or K_mm2_s <= 0:
        return bool(var), None
    ds = float(sonme_capi_mm)
    return True, (ds ** 2 - (D_SOGUK_ORAN * ds) ** 2) / (K_SOGUK_ORAN * float(K_mm2_s))


# Aşama 2d (kullanıcı isteği): C_rad fiziksel aralıkta (0.3 / 0.5 / 1; optik ince üst sınır, yeniden soğurma
# düzeltmesi) sabit, beta serbest -> dürüst AUC N2->CO2+He 0.807 -> 0.738-0.747 (beta <= 3 ile 0.742), kontrol
# verisi 0.712 -> 0.59-0.63, 1 g 0.61 -> 0.40-0.50; havada 2-4 mm heptanı ateşlenir ateşlenmez söndürüyor (FLEX'e
# aykırı). Kayıp > 0.02 -> mevcut sürüm (C_rad = 0.02 etkin değer) korundu; bkz. experiments/stage2d_crad.json.
ISINIM_NOTU = ("Işınım fiziksel aralıkta (C_rad = 0,3, optik ince + yeniden soğurma payı); alev mesafesi FLEX alev "
               "çapı ölçümüyle kalibre (β ile C_rad ayrıldı). Yalnız gaz (CO2/H2O) ışınımı; is ışınımı yok.")


def sonme_turu(p, yakit, X, basinc_kpa, d0, g, akis, sonme_capi_mm):
    """Sönme mekanizması (karşıt durum): ışınım kapatılıp (C_rad -> 0) yeniden hesaplanır.
    -> None (sönme yok), "isinim" (ışınımsız sönme kalkıyor ya da sönme çapı yarıdan fazla küçülüyor),
       "kimyasal" (ışınımsız da sönüyor: oksijen/seyrelme ya da Damköhler sınırı)."""
    if sonme_capi_mm is None or (isinstance(sonme_capi_mm, float) and math.isnan(sonme_capi_mm)):
        return None
    q = dict(p, ln_Crad=-60.0)
    o, _h = _hizli_tek(q, yakit, X, basinc_kpa, d0, g, akis)
    sc0 = float(o["sonme_capi"][0])
    if math.isnan(sc0) or sc0 < 0.5 * float(sonme_capi_mm):
        return "isinim"
    return "kimyasal"


SOGUK_UYARI = "Görünmeyen soğuk alev: sıcak alev söndükten sonra damla yanmayı sürdürebilir — yangın bitti sanılabilir."


def soguk_alev_testi():
    """Etiketli FLEX heptan testlerinde kuralın isabeti (etiketler kalibrasyonda kullanılmadı)."""
    import pandas as pd
    f = KOK / "data/droplet_cold_flame_label.csv"
    if not f.exists():
        return None
    t = flex_oku()
    e = pd.read_csv(f)
    t = t.merge(e[["test", "soguk_alev"]].dropna(subset=["test"]).astype({"test": int}), on="test")
    t = t[t.yakit.eq("NC7H16") & t.soguk_alev.notna()].reset_index(drop=True)
    p, _ = varsayilan_parametreler()
    X = flex_bilesim(t)
    o = hizli_tahmin(p, t, X)
    tah = np.array([soguk_alev(y, X[:, k], float(o["yanma"][k]), float(o["sonme_capi"][k]), float(o["K"][k]))[0]
                    for k, y in enumerate(t.yakit)])
    y = t.soguk_alev.to_numpy().astype(bool)
    return {"n": int(len(t)), "var": int(y.sum()), "yok": int((~y).sum()),
            "dogruluk": float((tah == y).mean()), "hep_var_dogrulugu": float(y.mean()),
            "dogru_var": int((tah & y).sum()), "dogru_yok": int((~tah & ~y).sum()),
            "kacan": int((~tah & y).sum()), "yanlis_alarm": int((tah & ~y).sum())}


# ------------------------------------------------------------------ kısmi g doğrulaması (Aşama 2a)
KISMI_G = (1e-4, 0.165, 0.38, 1.0)
# K(1 g)/K(µg) literatür aralığı (asılı/serbest n-heptan damlası, ~1 mm, hava). Kaynaklar (sayılar derlemeden,
# yaklaşık): Okajima & Kumagai (1975) 15th Symp. (Int.) Combust. 401-407 (serbest düşüş, µg K ≈ 0.78 mm²/s);
# Law & Faeth (1994) Prog. Energy Combust. Sci. 20:65-113 (1 g K'nın µg'den ~%20-50 büyük olduğu derlemesi).
K_ORAN_LITERATUR = (1.2, 1.5)


def _flex2_1g(c_listesi=(0.0, C_TASINIM)):
    """Kalibrasyonda kullanılmayan 1 g damla noktaları (data/psi_labeled_flex2.csv): taşınım katsayısı c ile."""
    import pandas as pd
    from sklearn.metrics import roc_auc_score
    p, _ = varsayilan_parametreler()
    d = pd.read_csv(FLEX2_DOSYASI)
    d = d[(d.numune_tipi == "droplet") & d.malzeme_sade.map(yakit_bul).notna() & (d.g_seviyesi >= 0.9)]
    d = d.reset_index(drop=True)
    y = d.yanar.to_numpy()
    out = {"n": int(len(d)), "makale": int(d.makale_id.nunique())}
    for c in c_listesi:
        q = dict(p, c_tasinim=c)
        t = np.array([float(_hizli_tek(q, yakit_bul(r.malzeme_sade), ortam_bilesimi(r.oksijen_yuzde, r.seyreltici),
                                       r.basinc_kpa, r.kalinlik_mm, r.g_seviyesi, 0.0)[0]["yanma"][0])
                      for r in d.itertuples()])
        out[f"c={c:g}"] = {"auc": float(roc_auc_score(y, t)), "dogruluk": float(((t > 0.5) == y).mean())}
    return out


def kismi_g_tablosu(yakitlar=("NC7H16", "CH3OH"), caplar=(1.0, 2.0, 3.0), gler=KISMI_G):
    import pandas as pd
    p, _ = varsayilan_parametreler()
    X = ortam_bilesimi(21.0, "n2")
    sat = []
    for y in yakitlar:
        for d0 in caplar:
            K0 = None
            for g in gler:
                o, h = _hizli_tek(p, y, X, 101.3, d0, g, 0.0)
                K = float(o["K"][0])
                K0 = K if K0 is None else K0
                sc = float(o["sonme_capi"][0])
                sat.append({"yakit": YAKIT_AD_TR[y], "d0_mm": d0, "g": g, "K_mm2_s": K, "K_oran_ug": K / K0,
                            "Nu_2": float(h["nu2"][0, 0]), "yanma": float(o["yanma"][0]),
                            "sonme_capi_mm": None if math.isnan(sc) else sc, "T_alev_K": float(o["Tf0"][0]),
                            "min_oksijen": min_oksijen_bul(p, y, X, 101.3, d0, g, 0.0)})
    return pd.DataFrame(sat)


def kismi_g_main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    t = kismi_g_tablosu()
    t.to_csv(KOK / "data/droplet_partial_g.csv", index=False, encoding="utf-8-sig")
    pd_ = __import__("pandas")
    pd_.set_option("display.width", 200)
    print(t.round(3).to_string(index=False))
    test = _flex2_1g()
    ek_f = KOK / "data/droplet_validation_extra.json"
    ek = json.loads(ek_f.read_text(encoding="utf-8")) if ek_f.exists() else {}
    k1 = t[(t.g == 1.0) & (t.yakit == "n-heptan") & (t.d0_mm == 1.0)].K_oran_ug.iloc[0]
    ek["kismi_g"] = {"test_1g_flex2": test, "c_tasinim": C_TASINIM,
                     "c_secimi": "Aşama 5a (experiments/stage5a_transport.json): 96 noktalık 1 g verisinde (flex2 + veri_temiz) "
                                 "c serbest makale dışarıda AUC 0.602 -> 0.638 ama doğruluk 0.792 -> 0.781, c ızgara "
                                 "ucunda (1.0), K(1g)/K(µg) 1.94 (lit. 1.2-1.5), 1.6 g K ölçümleri bozuluyor -> c = 0.3, "
                                 "n = 0.25 korundu",
                     "K_oran_1g_heptan_1mm_model": float(k1), "K_oran_literatur": list(K_ORAN_LITERATUR),
                     "kismi_g_verisi": "heptan/metanol için kısmi g yanar/söner ya da K verisi yok: Ay/Mars "
                                       "değerleri Faeth bağıntısıyla ara değer (doğrulanmadı)"}
    ek_f.write_text(json.dumps(ek, ensure_ascii=False, indent=1), encoding="utf-8")
    # grafik: sürekli g taraması
    gs = np.logspace(-4, 0, 25)
    X = ortam_bilesimi(21.0, "n2")
    p, _ = varsayilan_parametreler()
    fig, ax = plt.subplots(1, 3, figsize=(17, 5.2))
    renk = {"NC7H16": "#c0392b", "CH3OH": "#2471a3"}
    for y in ("NC7H16", "CH3OH"):
        for d0, cz in ((1.0, "-"), (3.0, "--")):
            K, Y, M = [], [], []
            for g in gs:
                o, _h = _hizli_tek(p, y, X, 101.3, d0, g, 0.0)
                K.append(float(o["K"][0])), Y.append(float(o["yanma"][0]))
                M.append(min_oksijen_bul(p, y, X, 101.3, d0, g, 0.0) or np.nan)
            K = np.array(K)
            et = f"{YAKIT_AD_TR[y]}, d₀ = {d0:g} mm"
            ax[0].semilogx(gs, K / K[0], cz, color=renk[y], label=et)
            ax[1].semilogx(gs, M, cz, color=renk[y], label=et)
            ax[2].semilogx(gs, Y, cz, color=renk[y], label=et)
    ax[0].fill_between([0.7, 1.4], *K_ORAN_LITERATUR, color="0.75", alpha=0.6,
                       label="literatür, n-heptan ~1 mm, 1 g\n(Okajima & Kumagai 1975; Law & Faeth 1994)")
    for a in ax:
        for g, ad in ((0.165, "Ay"), (0.38, "Mars"), (1.0, "Dünya")):
            a.axvline(g, color="0.6", lw=0.8, ls=":")
            a.text(g, 1.0, ad, transform=a.get_xaxis_transform(), ha="center", va="bottom", fontsize=9)
        a.axvspan(1e-3, 0.9, color="#f9e79f", alpha=0.25, lw=0)
        a.set_xlabel("g / g₀")
        a.grid(alpha=0.3)
    ax[0].set_ylabel("K(g) / K(µg)")
    ax[0].set_title("Yanma hızı: doğal taşınım etkisi", pad=16)
    ax[1].set_ylabel("en düşük O₂ (%)")
    ax[1].set_title("Sönme sınırı (en düşük O₂, N₂, 1 atm)", pad=16)
    ax[2].set_ylabel("yanma ihtimali (21 % O₂)")
    ax[2].set_title(pad=16, label=f"1 g kontrol (65 nokta): AUC {test['c=0.3']['auc']:.2f} (düzeltmesiz {test['c=0']['auc']:.2f})")
    ax[0].legend(fontsize=8)
    ax[1].legend(fontsize=8)
    fig.suptitle("Damla motoru, kısmi g: Faeth / Ranz-Marshall bağıntısı (c = 0.3). Sarı bant: kısmi g — deney "
                 "verisi yok, ara değer (doğrulanmadı)", fontsize=11)
    fig.tight_layout()
    fig.savefig(KOK / "figures/droplet_partial_g.png", dpi=130)
    print("1 g testi:", test)
    print(f"K(1 g)/K(µg), heptan 1 mm: model {k1:.2f}, literatür {K_ORAN_LITERATUR}")
    print("Kaydedildi: data/droplet_partial_g.csv, figures/droplet_partial_g.png, data/droplet_validation_extra.json")


# ====================================================================================================
# AYRINTILI MOD
# ====================================================================================================
# 1B küresel simetrik, zamana bağlı gaz fazı + topaklanmış sıvı damla.
#  Izgara: r = r_s(t) + (R - r_s(t)) ξ,  ξ ∈ [0,1] logaritmik kümelenmiş (N hücre), R = R_DIS × r_0;
#          ızgara damla yüzeyiyle birlikte hareket eder (hareketli ızgara terimi v_g = ṙ_s (1-ξ)).
#  Denklemler (düşük Mach, izobarik; ρ = p M̄ / R_u T):
#     ρ c_p DT/Dt = (1/r²)∂(r² λ ∂T/∂r)/∂r - Σ c_p,k j_k ∂T/∂r + Q ω - q_rad
#     ρ DY_k/Dt  = -(1/r²)∂(r² j_k)/∂r + ω_k ,   j_k = -ρ D_k ∂Y_k/∂r + Y_k j_c  (karışım-ortalamalı Fick
#                                                    + düzeltme hızı; D_k: Curtiss-Hirschfelder)
#     (1/r²)∂(r² u)/∂r = (1/T) DT/Dt + M̄ Σ (1/M_k) DY_k/Dt     (süreklilik -> Stefan akışı dahil u(r))
#     u(r_s) = ṁ''(1/ρ_g - 1/ρ_l)
#  Yüzey: X_F,s = p_doyma(T_l)/p (Clausius-Clapeyron), yakıt akısı = ṁ'', diğer türlerin net akısı 0,
#         m_l c_l dT_l/dt = 4π r_s² λ ∂T/∂r|_s - ṁ L(T_l),   dr_s/dt = -ṁ''/ρ_l
#  Kimya: Westbrook & Dryer (1981) tek adım, ω = A exp(-T_a/T) [F]^a [O2]^b  (A yakıt başına kalibre)
#  Işınım: optik ince, q_rad = C_rad 4σ p (X_CO2 a_CO2 + X_H2O a_H2O)(T⁴ - T∞⁴)
#  Ateşleme: t < T_ATES süresince r ≈ R_ATES r_0 çevresinde sıcaklığı T_ATES_K'ye çeken kaynak (FLEX sıcak teli).
#  Sönme: t > T_ATES + 0.05 s sonra en yüksek gaz sıcaklığı < 1200 K.  Bitiş: d < 0.1 d0 ya da sönme.
#  Zaman: scipy solve_ivp(BDF), seyrek Jacobian deseni (komşu hücreler + yüzey + ilk hücre).
N_HUCRE = 100
TAM_DESEN = True
AYR_SU = os.environ.get("DAMLA_AYR_SU", "1") == "1"   # Aşama 4: ayrıntılı modda alkol damlasına su emme
CL_SU = 4180.0        # J/kg K, sıvı su
R_DIS = 60.0
IZGARA_Q = 6.5
T_ATES, T_ATES_K, R_ATES, W_ATES, TAU_ATES = 0.06, 1500.0, 2.5, 0.8, 5e-3
EPS_C = 1e-6          # kmol/m³; kesirli üslerin sıfır yakınında türevini sınırlar
AYRINTILI_ADLAR = ["lnA_NC7H16", "lnA_CH3OH", "Ta", "ln_Crad"]
AYRINTILI_BASLANGIC = {"lnA_NC7H16": 0.0, "lnA_CH3OH": 0.0, "Ta": 15098.0, "ln_Crad": 0.0}
AYRINTILI_SINIRLAR = [(-6.0, 6.0), (-6.0, 6.0), (10000.0, 22000.0), (math.log(0.1), math.log(5.0))]


class Damla1B:
    def __init__(self, yakit, X_inf, basinc_kpa, d0_mm, p, g=1e-4, akis=0.0, N=N_HUCRE):
        G0 = gaz()
        act = sorted(set(np.nonzero(X_inf > 0)[0]) | {G0.i[yakit], G0.i["O2"], G0.i["CO2"], G0.i["H2O"]})
        self.G = G = G0.alt(act)
        self.ns, self.N = len(G.M), N
        self.y = YAKIT[yakit]
        self.iF, self.iO, self.iC, self.iH = G.i[yakit], G.i["O2"], G.i["CO2"], G.i["H2O"]
        self.X_inf = X_inf[act]
        self.Y_inf, _ = G.mol_kutle(self.X_inf[:, None])
        self.Y_inf = self.Y_inf[:, 0]
        self.p = basinc_kpa * 1e3
        self.r0 = d0_mm * 1e-3 / 2
        self.R = R_DIS * self.r0
        eta = np.linspace(0, 1, N + 1)
        self.xf = (np.exp(IZGARA_Q * eta) - 1) / (np.exp(IZGARA_Q) - 1)
        self.xc = 0.5 * (self.xf[1:] + self.xf[:-1])
        y = self.y
        self.Ta = p["Ta"]
        self.A = math.exp(lnA_yakit(p, yakit)) * y["A"] * 1000.0 ** (1 - y["a"] - y["b"])   # SI kmol/m³ s
        self.Crad = math.exp(p["ln_Crad"])
        st = np.zeros(self.ns)
        st[self.iF] = -y["M"]
        st[self.iO] = -y["nO2"] * 31.999
        st[self.iC] = y["nC"] * 44.01
        st[self.iH] = y["nH"] / 2 * 18.015
        self.st = st                            # kg/kmol yakıt
        self.qF = y["Q"] * y["M"]               # J/kmol yakıt
        # Aşama 4: su emme (alkoller). Sıvı = yakıt + su (ideal Raoult, sabit yakıt yoğunluğu); ek durum Y_w,l
        self.su = AYR_SU and yakit in SU_EMEN
        self.ek = 3 if self.su else 2
        # g > 0: Nu/2 ile difüzif akıları büyüten yaklaşık düzeltme (hızlı moddaki bağıntı)
        self.nu2 = 1.0
        if g > 1e-3 or akis > 0:
            ph, _ = varsayilan_parametreler()
            h = hizli_hesap(ph, [yakit], X_inf[:, None], [self.p], [d0_mm], [g], [akis], d_oran=[1.0])
            self.nu2 = float(h["nu2"][0, 0])
        self.nv = 1 + self.ns

    # ---------------------------------------------------------- başlangıç
    def baslangic(self):
        G, N = self.G, self.N
        rf = self.r0 + (self.R - self.r0) * self.xf
        rc = 0.5 * (rf[1:] + rf[:-1])
        T = T_INF + (T_ATES_K - T_INF) * np.exp(-((rc - R_ATES * self.r0) / (W_ATES * self.r0)) ** 2)
        Xs = min(p_doyma(300.0, self.y) / self.p, 0.5)
        Ms = (self.X_inf * G.M).sum()
        Yfs = Xs * self.y["M"] / (Xs * self.y["M"] + (1 - Xs) * Ms)
        YF = Yfs * np.exp(-(rc - self.r0) / (0.3 * self.r0))
        Y = self.Y_inf[:, None] * (1 - YF)[None, :]
        Y[self.iF] += YF
        U = np.vstack([T[None, :], Y]).T.reshape(-1)
        return np.r_[U, 1.0, 300.0] if not self.su else np.r_[U, 1.0, 300.0, 0.0]

    def seyreklik(self):
        from scipy.sparse import lil_matrix
        nv, N = self.nv, self.N
        e = self.ek
        n = nv * N + e
        S = lil_matrix((n, n), dtype=np.int8)
        for i in range(N):
            for j in (i - 1, i, i + 1):
                if 0 <= j < N:
                    S[i * nv:(i + 1) * nv, j * nv:(j + 1) * nv] = 1
        if TAM_DESEN:                 # Stefan hızı: her hücre içerideki bütün hücrelere bağlı (alt üçgen)
            for i in range(N):
                S[i * nv:(i + 1) * nv, :(i + 1) * nv] = 1
        S[:, :nv] = 1                 # ilk hücre (yüzey akısı -> Stefan hızı her yerde)
        S[:, n - e:] = 1              # r_s, T_l (ve Y_w,l)
        S[n - e:, :] = 0
        S[n - e:, :nv] = 1
        S[n - e:, n - e:] = 1
        return S.tocsr()

    # ---------------------------------------------------------- sağ taraf
    def rhs(self, t, z, ayrinti=False):
        G, N, ns, y = self.G, self.N, self.ns, self.y
        k0 = N * self.nv
        s, Tl = max(z[k0], 1e-3), z[k0 + 1]
        Yw = min(max(z[k0 + 2], 0.0), 0.95) if self.su else 0.0
        U = z[:k0].reshape(N, self.nv)
        T = np.clip(U[:, 0], 250.0, 4000.0)
        Y = np.clip(U[:, 1:].T, 0.0, 1.0)
        Y = Y / Y.sum(0)
        rs = s * self.r0
        rf = rs + (self.R - rs) * self.xf
        rc = 0.5 * (rf[1:] + rf[:-1])
        A = rf ** 2
        V = (rf[1:] ** 3 - rf[:-1] ** 3) / 3
        X, Mb = G.kutle_mol(Y)
        rho = self.p * Mb / (R_U * T)
        cpk = G.tablo(G.cp, T)
        cp = (Y * cpk).sum(0)
        lam = G.lam_mix(X, T)
        Dk = G.D_mix(X, Y, T, self.p)
        # --- yüzey
        Tl = min(max(Tl, 200.0), y["Tc"] - 1.0)
        d0 = rc[0] - rs
        a = rho[0] * Dk[:, 0] / d0 * self.nu2
        eps = np.zeros(ns)
        if not self.su:
            Xfs = min(p_doyma(Tl, y) / self.p, 0.98)
            Yd = Y[:, 0].copy()
            Yd[self.iF] = 0
            Moth = 1.0 / (Yd / G.M).sum() * Yd.sum() if Yd.sum() > 0 else 28.0
            Yfs = Xfs * y["M"] / (Xfs * y["M"] + (1 - Xfs) * Moth)
            mpp = max(a[self.iF] * (Yfs - Y[self.iF, 0]) / max(1 - Yfs, 1e-6), 0.0)
            Ys = a * Y[:, 0] / (mpp + a)
            Ys[self.iF] = 0
            Ys = Ys / max(Ys.sum(), 1e-12) * (1 - Yfs)
            Ys[self.iF] = Yfs
            eps[self.iF] = 1
            mW = 0.0
        else:
            # Raoult: X_F,s = x_F p_doyma,F / p ; X_W,s = x_W p_doyma,W / p. Su, gaz tarafında yüzeydekinden
            # fazlaysa damlaya yoğuşur (mW < 0) ve gizli ısısını sıvıya bırakır.
            xF = ((1 - Yw) / y["M"]) / ((1 - Yw) / y["M"] + Yw / SU["M"])
            Xfs = xF * p_doyma(Tl, y) / self.p
            Xws = (1 - xF) * p_doyma(Tl, SU) / self.p
            tp = Xfs + Xws
            if tp > 0.98:
                Xfs, Xws = Xfs * 0.98 / tp, Xws * 0.98 / tp
            Yd = Y[:, 0].copy()
            Yd[self.iF] = 0
            Yd[self.iH] = 0
            Moth = 1.0 / (Yd / G.M).sum() * Yd.sum() if Yd.sum() > 0 else 28.0
            Mm = Xfs * y["M"] + Xws * SU["M"] + (1 - Xfs - Xws) * Moth
            Yfs, Yws = Xfs * y["M"] / Mm, Xws * SU["M"] / Mm
            mpp = max((a[self.iF] * (Yfs - Y[self.iF, 0]) + a[self.iH] * (Yws - Y[self.iH, 0]))
                      / max(1 - Yfs - Yws, 1e-6), 0.0)
            mW = mpp * Yws + a[self.iH] * (Yws - Y[self.iH, 0])     # kg/m² s; < 0 = emme
            Ys = a * Y[:, 0] / (mpp + a)
            Ys[self.iF] = 0
            Ys[self.iH] = 0
            Ys = Ys / max(Ys.sum(), 1e-12) * (1 - Yfs - Yws)
            Ys[self.iF], Ys[self.iH] = Yfs, Yws
            if mpp > 0:
                eps[self.iF], eps[self.iH] = (mpp - mW) / mpp, mW / mpp
        # --- akılar (yüzler 0..N)
        j = np.zeros((ns, N + 1))
        j[:, 0] = mpp * (eps - Ys)
        if self.su and mpp <= 0:
            j[self.iH, 0] = mW
        dr = rc[1:] - rc[:-1]
        rhoD_f = 0.5 * (rho[1:] * Dk[:, 1:] + rho[:-1] * Dk[:, :-1]) * self.nu2
        j[:, 1:N] = -rhoD_f * (Y[:, 1:] - Y[:, :-1]) / dr
        dN = rf[-1] - rc[-1]
        j[:, N] = -rho[-1] * Dk[:, -1] * self.nu2 * (self.Y_inf - Y[:, -1]) / dN
        Yf_ = np.concatenate([0.5 * (Y[:, 1:] + Y[:, :-1]), Y[:, -1:]], axis=1)
        j[:, 1:] -= Yf_ * j[:, 1:].sum(0)
        q = np.zeros(N + 1)
        q[0] = -lam[0] * self.nu2 * (T[0] - Tl) / d0
        q[1:N] = -0.5 * (lam[1:] + lam[:-1]) * self.nu2 * (T[1:] - T[:-1]) / dr
        q[N] = -lam[-1] * self.nu2 * (T_INF - T[-1]) / dN
        divq = (A[1:] * q[1:] - A[:-1] * q[:-1]) / V
        divj = (A[1:] * j[:, 1:] - A[:-1] * j[:, :-1]) / V
        # --- gradyanlar (merkezi) ve kaynaklar
        rg = np.r_[rs, rc, self.R]
        Tg = np.r_[Tl, T, T_INF]
        dTdr = (Tg[2:] - Tg[:-2]) / (rg[2:] - rg[:-2])
        jc = 0.5 * (j[:, 1:] + j[:, :-1])
        conc = rho * Y / G.M[:, None]
        cF = np.clip(conc[self.iF], 0, None)
        cO = np.clip(conc[self.iO], 0, None)
        e = EPS_C
        w = self.A * np.exp(-self.Ta / T) * cF / (cF + e) ** (1 - y["a"]) * cO / (cO + e) ** (1 - y["b"])
        qc = w * self.qF
        kp = a_planck(T)
        qr = self.Crad * 4 * SIGMA * (self.p / P0) * (X[self.iC] * kp[0] + X[self.iH] * kp[1]) * \
            (T ** 4 - T_INF ** 4)
        qi = 0.0
        if t < T_ATES:
            prof = np.exp(-((rc - R_ATES * self.r0) / (W_ATES * self.r0)) ** 2)
            qi = rho * cp * np.clip(T_ATES_K - T, 0, None) / TAU_ATES * prof
        DT = (-divq - (cpk * jc).sum(0) * dTdr + qc - qr + qi) / (rho * cp)
        DY = (-divj + self.st[:, None] * w[None, :]) / rho
        S = DT / T + Mb * (DY / G.M[:, None]).sum(0)
        rho_l = y["rho"]
        us = mpp * (1 / rho[0] - 1 / rho_l)
        rdot = -mpp / rho_l
        uf = (rs ** 2 * us + np.r_[0, np.cumsum(S * V)]) / A
        uc = 0.5 * (uf[1:] + uf[:-1])
        wv = uc - rdot * (1 - self.xc)
        # rüzgar yönlü türev
        Yg = np.concatenate([Ys[:, None], Y, self.Y_inf[:, None]], axis=1)
        geri = lambda F: (F[..., 1:-1] - F[..., :-2]) / (rg[1:-1] - rg[:-2])
        ileri = lambda F: (F[..., 2:] - F[..., 1:-1]) / (rg[2:] - rg[1:-1])
        dT_up = np.where(wv > 0, geri(Tg), ileri(Tg))
        dY_up = np.where(wv > 0, geri(Yg), ileri(Yg))
        dTdt = DT - wv * dT_up
        dYdt = DY - wv * dY_up
        mdot = 4 * math.pi * rs ** 2 * mpp
        ml = 4 / 3 * math.pi * rs ** 3 * rho_l
        out = np.vstack([dTdt[None, :], dYdt]).T.reshape(-1)
        if not self.su:
            dTl = (4 * math.pi * rs ** 2 * (-q[0]) - mdot * L_buhar(Tl, y)) / (ml * y["cl"])
            if ayrinti:
                return {"T": T, "Y": Y, "rc": rc, "w": w, "qr": qr, "qc": qc, "mpp": mpp, "uc": uc}
            return np.r_[out, rdot / self.r0, dTl]
        Ap = 4 * math.pi * rs ** 2
        mF = mpp - mW
        cl = (1 - Yw) * y["cl"] + Yw * CL_SU
        dTl = (Ap * (-q[0]) - Ap * (mF * L_buhar(Tl, y) + mW * L_buhar(Tl, SU))) / (ml * cl)
        dYw = Ap * (-mW + Yw * mpp) / ml
        if ayrinti:
            return {"T": T, "Y": Y, "rc": rc, "w": w, "qr": qr, "qc": qc, "mpp": mpp, "uc": uc, "mW": mW, "Yw": Yw}
        return np.r_[out, rdot / self.r0, dTl, dYw]


def ayrintili_kosu(yakit, X, basinc_kpa, d0_mm, g, akis, p, t_maks=None, N=N_HUCRE, kayit=False):
    """Tek bir ayrıntılı koşu. Dönüş: yanma (0/1 yumuşak), K (mm²/s), sonme_capi (mm/None), T_maks, süre."""
    from scipy.integrate import solve_ivp
    if isinstance(p, (list, tuple, np.ndarray)):
        p = dict(zip(AYRINTILI_ADLAR, p))
    m = Damla1B(yakit, X, basinc_kpa, d0_mm, p, g, akis, N)
    z0 = m.baslangic()
    if t_maks is None:
        ph, _ = varsayilan_parametreler()
        o, _h = _hizli_tek(ph, yakit, X, basinc_kpa, d0_mm, g, akis)
        t_maks = 1.6 * d0_mm ** 2 / max(float(o["K0"][0]), 0.05) + 1.0
    nv = m.nv
    k0 = m.N * nv                 # r_s/r0 indeksi; sonrası T_l (ve su emmede Y_w,l)

    def sonme(t, z):
        if t < T_ATES + 0.05:
            return 1.0
        return float(z[:k0].reshape(m.N, nv)[:, 0].max() - T_SONME)
    sonme.terminal, sonme.direction = True, -1

    def bitti(t, z):
        return z[k0] - 0.1
    bitti.terminal, bitti.direction = True, -1

    bas = time.perf_counter()
    atol = np.tile(np.r_[1e-2, np.full(m.ns, 1e-7)], m.N)
    atol = np.r_[atol, 1e-6, 1e-3] if not m.su else np.r_[atol, 1e-6, 1e-3, 1e-6]
    tk = np.linspace(0, t_maks, 400) if kayit else None
    try:
        r = solve_ivp(m.rhs, (0, t_maks), z0, method="BDF", jac_sparsity=m.seyreklik(), rtol=1e-4,
                      atol=atol, events=(sonme, bitti), t_eval=tk, dense_output=False, max_step=0.05)
    except Exception as e:      # sayısal hata: sonucu bilinmiyor say
        return {"yanma": None, "K": None, "sonme_capi": None, "T_maks": None, "sure_s": time.perf_counter() - bas,
                "hata": str(e)[:200]}
    sure = time.perf_counter() - bas
    s = r.y[k0]
    t = r.t
    Tm = r.y[:k0].reshape(m.N, nv, -1)[:, 0].max(0)
    d = 2 * m.r0 * 1e3 * s
    sondu = len(r.t_events[0]) > 0
    ates = (Tm[t > T_ATES].max() if (t > T_ATES).any() else 0) > 1500 if not sondu else Tm.max() > 1500
    d_son = 2 * m.r0 * 1e3 * (r.y_events[0][0][k0] if sondu else s[-1])
    # K: d² - t eğiminin (d²/d0² 0.9..0.2 aralığı) doğrusal uydurması
    d2 = d ** 2
    d02 = (2 * m.r0 * 1e3) ** 2
    mk = (d2 <= 0.9 * d02) & (d2 >= 0.2 * d02) & (t > T_ATES)
    if mk.sum() >= 3:
        K = float(-np.polyfit(t[mk], d2[mk], 1)[0])
    elif len(t) > 2 and t[-1] > T_ATES:
        k2 = t > T_ATES
        K = float((d2[k2][0] - d2[k2][-1]) / max(t[k2][-1] - t[k2][0], 1e-9))
    else:
        K = None
    sonme_capi = float(d_son) if sondu else None
    oran = (sonme_capi / (2 * m.r0 * 1e3)) if sondu else 0.0
    yanma = float(sigmoid((HEMEN_SONDU_ORANI - oran) / 0.03)) if ates else 0.0
    sonuc = {"yanma": round(yanma, 4), "K": None if K is None else round(K, 4),
             "sonme_capi": None if sonme_capi is None else round(sonme_capi, 3),
             "T_maks": round(float(np.median(Tm[t > T_ATES])) if (t > T_ATES).any() else float(Tm.max()), 1),
             "sure_s": round(sure, 2), "t_son": float(t[-1]), "adim": int(len(t)), "nfev": int(r.nfev),
             "ates": bool(ates), "su_son": round(float(r.y[k0 + 2][-1]), 4) if m.su else None}
    if kayit:
        Tp = r.y[:k0].reshape(m.N, nv, -1)[:, 0]
        rc = (s[None, :] * m.r0 + (m.R - s[None, :] * m.r0) * m.xc[:, None])
        sonuc["kayit"] = {"t": t.tolist(), "d": d.tolist(), "T_maks": Tm.tolist(),
                          "r_mm": (rc * 1e3).T.tolist(), "T": Tp.T.tolist()}
    return sonuc


# ------------------------------------------------------------------ ayrıntılı mod kalibrasyonu (paralel)
KOSU_SURE_SINIRI = 480.0        # s; tek koşu bunu aşarsa durdurulur (sonuç yok sayılır). Aşama 4: su emmeli metanol ~240 s


class _SureAsimi(Exception):
    pass


def _isci_baslat():
    os.environ["OMP_NUM_THREADS"] = "1"


def _ayrintili_isci(arg):
    """Ayrı süreçte tek test (spawn + OMP_NUM_THREADS=1)."""
    p, yakit, X, basinc, d0 = arg
    bas = time.perf_counter()
    orj = Damla1B.rhs

    def sinirli(self, t, z, ayrinti=False):
        if time.perf_counter() - bas > KOSU_SURE_SINIRI:
            raise _SureAsimi()
        return orj(self, t, z, ayrinti)
    Damla1B.rhs = sinirli
    try:
        return ayrintili_kosu(yakit, np.asarray(X), basinc, d0, 1e-4, 0.0, p)
    finally:
        Damla1B.rhs = orj


def ayrintili_hepsi(p, t, X, havuz):
    args = [(p, t.yakit.iloc[i], X[:, i].tolist(), float(t.basinc_kpa.iloc[i]), float(t.ilk_cap_mm.iloc[i]))
            for i in range(len(t))]
    return havuz.map(_ayrintili_isci, args, chunksize=1)


def kayip_ayrintili(sonuclar, t):
    y = t.yanar.to_numpy(float)
    q = np.array([np.nan if r["yanma"] is None else r["yanma"] for r in sonuclar])
    ok = np.isfinite(q)
    qq = np.clip(q[ok], 1e-4, 1 - 1e-4)
    bce = -np.sum(y[ok] * np.log(qq) + (1 - y[ok]) * np.log(1 - qq)) + 5.0 * (~ok).sum()
    K = np.array([np.nan if r["K"] is None else r["K"] for r in sonuclar])
    Kobs = t.yanma_hizi_mm2_s.to_numpy(float)
    mk = np.isfinite(K) & np.isfinite(Kobs) & (Kobs > 0.05) & (K > 0)
    kK = np.sum(((np.log(K[mk]) - np.log(Kobs[mk])) / SIG_K) ** 2)
    d0 = t.ilk_cap_mm.to_numpy(float)
    dm = np.array([0.0 if r["sonme_capi"] is None else r["sonme_capi"] for r in sonuclar]) / d0
    d_obs = (t.sonme_capi_mm / t.ilk_cap_mm).to_numpy(float)
    sond = t.sondu.to_numpy() & (y == 1) & ok
    kD = np.sum(((dm[sond] - d_obs[sond]) / SIG_D) ** 2)
    ys = ~t.test_sonu.eq("Extinction").to_numpy() & ok
    kD += np.sum((np.clip(dm[ys] - 0.3, 0, None) / SIG_D) ** 2)
    return bce + W_K * kK + W_D * kD, {"bce": float(bce), "K": float(kK), "D": float(kD), "basarisiz": int((~ok).sum())}


def alt_kume(t, n, tohum=0):
    """yakıt × seyreltici tabakalı alt küme."""
    import pandas as pd
    parca = []
    for _, x in t.groupby(["yakit", "seyreltici"]):
        k = max(2, int(round(n * len(x) / len(t))))
        parca.append(x.sample(min(k, len(x)), random_state=tohum))
    return pd.concat(parca).sort_index()


def kalibre_ayrintili_main(cekirdek, n_test, butce_dk, maxfev):
    import multiprocessing as mp
    from scipy.optimize import minimize
    os.environ["OMP_NUM_THREADS"] = "1"
    t = flex_oku()
    X = flex_bilesim(t)
    a = alt_kume(t, n_test)
    Xa = X[:, a.index.to_numpy()]
    a = a.reset_index(drop=True)
    gunluk = KOK / "logs/droplet_detailed_calibration.log"
    adlar = ["lnA_NC7H16", "lnA_CH3OH", "ln_Crad"]
    sinir = [AYRINTILI_SINIRLAR[AYRINTILI_ADLAR.index(k)] for k in adlar]
    ctx = mp.get_context("spawn")
    bas = time.time()
    gecmis = []
    with ctx.Pool(cekirdek, initializer=_isci_baslat) as havuz:
        # ölçüm: 1 test
        t1 = time.time()
        r1 = havuz.map(_ayrintili_isci, [(AYRINTILI_BASLANGIC, a.yakit.iloc[0], Xa[:, 0].tolist(),
                                          float(a.basinc_kpa.iloc[0]), float(a.ilk_cap_mm.iloc[0]))])[0]
        sure1 = time.time() - t1
        tahmin_tur = sure1 * len(a) / cekirdek
        mesaj = (f"1 test {sure1:.0f} s; {len(a)} test / {cekirdek} işçi -> tur başına ~{tahmin_tur / 60:.1f} dk; "
                 f"en fazla {maxfev} tur -> ~{maxfev * tahmin_tur / 60:.0f} dk (bütçe {butce_dk} dk)")
        print(mesaj, flush=True)
        with open(gunluk, "w", encoding="utf-8") as f:
            f.write(mesaj + "\n")

        def amac(v):
            if time.time() - bas > butce_dk * 60:
                raise _SureAsimi()
            p = dict(AYRINTILI_BASLANGIC)
            p.update(dict(zip(adlar, map(float, v))))
            tt = time.time()
            sonuc = ayrintili_hepsi(p, a, Xa, havuz)
            k, parca = kayip_ayrintili(sonuc, a)
            gecmis.append((k, p, parca, sonuc))
            satir = (f"tur {len(gecmis):3d} | {', '.join(f'{x}={p[x]:.3f}' for x in adlar)} | kayıp {k:.1f} {parca} "
                     f"| {time.time() - tt:.0f} s")
            print(satir, flush=True)
            with open(gunluk, "a", encoding="utf-8") as f:
                f.write(satir + "\n")
            return k
        x0 = [AYRINTILI_BASLANGIC[k] for k in adlar]
        try:
            minimize(amac, x0, method="Powell", bounds=sinir,
                     options={"maxfev": maxfev, "xtol": 0.05, "ftol": 1e-3})
        except _SureAsimi:
            print("Süre bütçesi doldu; o ana kadarki en iyi değer kullanılıyor.", flush=True)
    k, p, parca, sonuc = min(gecmis, key=lambda g: g[0])
    o = {"yanma": np.array([np.nan if r["yanma"] is None else r["yanma"] for r in sonuc]),
         "K": np.array([np.nan if r["K"] is None else r["K"] for r in sonuc]),
         "sonme_capi": np.array([np.nan if r["sonme_capi"] is None else r["sonme_capi"] for r in sonuc])}
    ok = np.isfinite(o["yanma"])
    m = olcutler(a[ok].reset_index(drop=True), {kk: v[ok] for kk, v in o.items()})
    eski = json.loads(PARAM_DOSYASI.read_text(encoding="utf-8")) if PARAM_DOSYASI.exists() else {}
    eski["ayrintili"] = {"parametreler": p, "kayip": float(k), "kayip_parcalari": parca, "tur": len(gecmis),
                         "alt_kume_test": a.test.astype(int).tolist(), "olcut_alt_kume_icinde": m,
                         "sure_dk": round((time.time() - bas) / 60, 1), "isci": cekirdek,
                         "not": "alt küme kalibrasyonu (tüm testler > 1 saat); Ta sabit (Westbrook-Dryer); "
                                + ("ayrıntılı modda su emme var (alkoller, Raoult; Aşama 4)" if AYR_SU else "ayrıntılı modda su emme yok"),
                         "C_rad": "kalibre edildi (ln_Crad)"}
    PARAM_DOSYASI.write_text(json.dumps(eski, ensure_ascii=False, indent=2), encoding="utf-8")
    import pandas as pd
    a2 = a[["test", "yakit", "seyreltici", "oksijen_yuzde", "basinc_kpa", "ilk_cap_mm", "sonme_capi_mm",
            "yanma_hizi_mm2_s", "test_sonu", "yanar"]].copy()
    a2["ayr_yanma"], a2["ayr_K"], a2["ayr_sonme_capi"] = o["yanma"], o["K"], o["sonme_capi"]
    a2["ayr_sure_s"] = [r.get("sure_s") for r in sonuc]
    a2["ayr_T_maks"] = [r.get("T_maks") for r in sonuc]
    a2["ayr_su_son"] = [r.get("su_son") for r in sonuc]
    a2.to_csv(KOK / "data/droplet_validation_detailed.csv", index=False, encoding="utf-8-sig")
    print("En iyi:", p, parca, m, flush=True)


# ------------------------------------------------------------------ grafikler
ORNEKLER = [("n-heptan, hava, 2 mm", "NC7H16", {"o2": 21, "n2": 79}, 101.3, 2.0),
            ("n-heptan, %30 CO2, 3.5 mm", "NC7H16", {"o2": 21, "n2": 49, "co2": 30}, 101.3, 3.5),
            ("metanol, hava, 3 mm", "CH3OH", {"o2": 21, "n2": 79}, 101.3, 3.0)]


def grafik_main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd
    t = flex_oku()
    X = flex_bilesim(t)
    ph, pa = varsayilan_parametreler()
    v = pd.read_csv(KOK / "data/droplet_validation.csv")
    renk = {"n2": "#1565C0", "co2": "#C62828", "he": "#2E7D32"}
    fig, ax = plt.subplots(2, 2, figsize=(12, 9.5))
    # (a) örnek d² eğrisi: hızlı mod + (varsa) ayrıntılı mod, deneyin K'sı ile karşılaştırma
    a = ax[0, 0]
    ornek = t[(t.yakit == "NC7H16") & (t.seyreltici == "n2") & t.sondu & (t.yanar == 1)].iloc[0]
    Xo = flex_bilesim(t.loc[[ornek.name]])[:, 0]
    o, h = _hizli_tek(ph, "NC7H16", Xo, ornek.basinc_kpa, ornek.ilk_cap_mm, 1e-4, 0.0)
    d = h["d_oran"] * ornek.ilk_cap_mm
    Kd = h["K"][0]
    tt = np.r_[0, np.cumsum(-np.diff(d ** 2) / (0.5 * (Kd[1:] + Kd[:-1])))]
    sonuk = h["sonuk"][0]
    son = int(np.argmax(sonuk)) if sonuk.any() else len(d) - 1
    a.plot(tt[:son + 1], d[:son + 1] ** 2, "-", color="#1565C0", lw=2, label="hızlı mod")
    if son < len(d) - 1:
        a.plot(tt[son], d[son] ** 2, "o", color="#1565C0", ms=8, label="hızlı mod sönme")
    tk = np.linspace(0, ornek.yanma_suresi_s if ornek.yanma_suresi_s == ornek.yanma_suresi_s else tt[son], 50)
    a.plot(tk, ornek.ilk_cap_mm ** 2 - ornek.yanma_hizi_mm2_s * tk, "--", color="k", label="deney: d0² - K t")
    a.axhline(ornek.sonme_capi_mm ** 2, color="#C62828", ls=":", label=f"deney sönme çapı ({ornek.sonme_capi_mm} mm)")
    a.set_xlabel("t (s)")
    a.set_ylabel("d² (mm²)")
    a.set_title(f"(a) d² eğrisi — FLEX test {int(ornek.test)}: n-heptan, %{ornek.oksijen_yuzde:g} O2, "
                f"d0={ornek.ilk_cap_mm} mm", fontsize=10)
    a.legend(fontsize=8)
    # (b) K
    a = ax[0, 1]
    for sy, x in v.groupby("seyreltici"):
        a.scatter(x.yanma_hizi_mm2_s, x.hizli_tum_K, s=14, color=renk.get(sy), alpha=.7, label=f"{sy} (tüm veri)")
        a.scatter(x.yanma_hizi_mm2_s, x.hizli_n2kal_K, s=14, marker="x", color=renk.get(sy), alpha=.7,
                  label=f"{sy} (N2 ile kalibre)")
    a.plot([0, 1.2], [0, 1.2], "k-", lw=.8)
    a.plot([0, 1.2], [0, 1.32], "k:", lw=.6)
    a.plot([0, 1.2], [0, 1.08], "k:", lw=.6)
    a.set_xlim(0, 1.15)
    a.set_ylim(0, 1.15)
    a.set_xlabel("deney K (mm²/s)")
    a.set_ylabel("model K (mm²/s)")
    a.set_title("(b) yanma hızı K (noktalı: ±%10)", fontsize=10)
    a.legend(fontsize=7, ncol=2)
    # (c) sönme çapı
    a = ax[1, 0]
    s_ = v[(v.test_sonu == "Extinction") & v.sonme_capi_mm.notna() & (v.yanar == 1)]
    for yk, mk in (("NC7H16", "o"), ("CH3OH", "^")):
        for sy, x in s_[s_.yakit == yk].groupby("seyreltici"):
            a.scatter(x.sonme_capi_mm, x.hizli_tum_sonme_capi.fillna(0), s=18, marker=mk, color=renk.get(sy),
                      alpha=.75, label=f"{'heptan' if yk == 'NC7H16' else 'metanol'} {sy}")
    a.plot([0, 4.5], [0, 4.5], "k-", lw=.8)
    a.set_xlabel("deney sönme çapı (mm)")
    a.set_ylabel("model sönme çapı (mm; 0 = sönmedi)")
    a.set_title("(c) sönme çapı (tüm veriyle kalibre hızlı mod)", fontsize=10)
    a.legend(fontsize=7, ncol=2)
    # (d) O2'ye göre yanma sınırı
    a = ax[1, 1]
    o2 = np.arange(8, 40.01, 0.5)
    G = gaz()
    for yk, ls, ad in (("NC7H16", "-", "heptan"), ("CH3OH", "--", "metanol")):
        for sy, oran in (("n2", {}), ("co2", {"co2": 0.3}), ("he", {"he": 0.4})):
            Xs = np.zeros((len(G.M), len(o2)))
            Xs[G.i["O2"]] = o2 / 100
            kalan = 1 - o2 / 100
            for k2, f in oran.items():
                Xs[G.i[SEYRELTICI_TUR[k2]]] = f
                kalan = kalan - f
            Xs[G.i["N2"]] += np.clip(kalan, 0, None)
            Xs = Xs / Xs.sum(0)
            hh = hizli_hesap(ph, [yk] * len(o2), Xs, np.full(len(o2), 101.3e3), np.full(len(o2), 3.0),
                             np.full(len(o2), 1e-4), np.zeros(len(o2)))
            a.plot(o2, hizli_ozet(hh, ph["s"])["yanma"], ls, color=renk[sy], label=f"{ad} {sy}")
    for yk, mk in (("NC7H16", "o"), ("CH3OH", "^")):
        x = t[(t.yakit == yk) & (t.basinc_kpa.between(90, 110))]
        a.scatter(x.oksijen_yuzde + np.random.default_rng(0).normal(0, .15, len(x)),
                  x.yanar + np.random.default_rng(1).normal(0, .03, len(x)), s=10, marker=mk,
                  c=[renk[z] for z in x.seyreltici], alpha=.5)
    a.axhline(.5, color="gray", lw=.6)
    a.set_xlabel("O2 (%, mol)")
    a.set_ylabel("yanma ihtimali")
    a.set_title("(d) O2'ye göre yanma (3 mm, 1 atm; CO2 %30, He %40 + N2)\nnoktalar: FLEX ~1 atm testleri "
                "(1 = hemen sönmedi)", fontsize=10)
    a.legend(fontsize=7, ncol=2)
    fig.suptitle("droplet_engine (hızlı mod) — NASA FLEX (PSI-69) karşılaştırması", fontsize=12)
    fig.tight_layout()
    fig.savefig(KOK / "figures/droplet_engine.png", dpi=130)
    print("Kaydedildi: figures/droplet_engine.png")


def ornek_ayrintili_main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    # Aşama 4 (2026-11-15): ayrıntılı kalibrasyon kabul edilmedi (experiments/stage4_decision.json);
    # örnek grafik hızlı modun sabit değerleriyle (lnA = 0, C_rad = 0,3) çizilir.
    pa = {k: SABIT_PARAMETRELER[k] for k in AYRINTILI_ADLAR}
    fig, ax = plt.subplots(2, len(ORNEKLER), figsize=(5 * len(ORNEKLER), 8.5))
    for j, (ad, yk, bil, pk, d0) in enumerate(ORNEKLER):
        X = ortam_bilesimi(None, None, bil)
        r = ayrintili_kosu(yk, X, pk, d0, 1e-4, 0.0, pa, kayit=True)
        k = r.pop("kayit")
        print(ad, r, flush=True)
        tt = np.array(k["t"])
        a = ax[0, j]
        n_kayit = min(len(tt), len(k["r_mm"]), len(k["T"]), len(k["d"]))
        for i in np.unique(np.linspace(min(3, n_kayit - 1), n_kayit - 1, 6).astype(int)) if n_kayit else []:
            a.plot(np.array(k["r_mm"][i]) / (d0 / 2), k["T"][i], label=f"t={tt[i]:.2f} s, d={k['d'][i]:.2f} mm")
        a.axhline(T_SONME, color="gray", ls=":", lw=.8)
        a.set_xscale("log")
        a.set_xlim(1, R_DIS)
        a.set_xlabel("r / r0")
        a.set_ylabel("T (K)")
        a.set_title(f"{ad}\nsıcaklık profili", fontsize=10)
        a.legend(fontsize=7)
        a = ax[1, j]
        a.plot(tt, np.array(k["d"]) ** 2, "-", color="#1565C0", label="ayrıntılı mod d²")
        a2 = a.twinx()
        a2.plot(tt, k["T_maks"], "-", color="#C62828", lw=.8, label="en yüksek T")
        a2.axhline(T_SONME, color="#C62828", ls=":", lw=.8)
        a2.set_ylabel("en yüksek T (K)", color="#C62828")
        txt = (f"K = {r['K']} mm²/s, sönme çapı = {r['sonme_capi']} mm\n"
               f"hesap süresi {r['sure_s']} s ({r['adim']} adım)")
        a.set_title(txt, fontsize=9)
        a.set_xlabel("t (s)")
        a.set_ylabel("d² (mm²)")
    fig.suptitle("droplet_engine ayrıntılı mod (1B küresel, zamana bağlı) — örnek koşular", fontsize=12)
    fig.tight_layout()
    fig.savefig(KOK / "figures/droplet_detailed_example.png", dpi=120)
    print("Kaydedildi: figures/droplet_detailed_example.png")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--kalibre-hizli", action="store_true")
    a.add_argument("--dogrula-hizli", action="store_true")
    a.add_argument("--kalibre-ayrintili", action="store_true")
    a.add_argument("--kismi-g", action="store_true", help="data/droplet_partial_g.csv/.png + 1 g testi")
    a.add_argument("--bootstrap", type=int, default=0, help="deney grubu bootstrap kalibrasyon sayısı (örn. 50)")
    a.add_argument("--grafik", action="store_true", help="figures/droplet_engine.png (4 panel)")
    a.add_argument("--ornek-ayrintili", action="store_true", help="figures/droplet_detailed_example.png (2-3 koşu)")
    a.add_argument("--cekirdek", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a.add_argument("--alt-kume", type=int, default=45)
    a.add_argument("--butce-dk", type=float, default=60)
    a.add_argument("--maxfev", type=int, default=30)
    k = a.parse_args()
    if k.kalibre_hizli:
        kalibre_hizli_main()
    if k.dogrula_hizli:
        dogrula_hizli_main()
    if k.bootstrap:
        bootstrap_main(k.bootstrap, k.cekirdek)
    if k.kismi_g:
        kismi_g_main()
    if k.grafik:
        grafik_main()
    if k.ornek_ayrintili:
        ornek_ayrintili_main()
    if k.kalibre_ayrintili:
        kalibre_ayrintili_main(k.cekirdek, k.alt_kume, k.butce_dk, k.maxfev)


if __name__ == "__main__":
    main()
