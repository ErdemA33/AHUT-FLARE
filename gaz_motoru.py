#!/usr/bin/env python3
"""
gaz_motoru.py — gaz yakıt alevleri için yarı-durağan fizik motoru (NASA ACME: BRE, Flame Design / s-Flame;
SLICE tipi jetler kalibre değil). Bağımsız dosya: yalnız numpy (+ kalibrasyonda scipy, pandas, sklearn).

    from gaz_motoru import gaz_motoru
    gaz_motoru(1e-4, 34, 57, None, 25, "ethylene", "flat_burner", kutle_akisi_g_m2s=2.5)   # BRE
    gaz_motoru(1e-4, 28.4, 101.3, None, 6.4, "13.2% ethylene", "porous_sphere", debi_mg_s=4.49)
    gaz_motoru(1.0, 21, 101.3, 30, 3.2, "methane", "gas_jet")

Arayüz motor.py ile aynı (+ seyreltici):  gaz_motoru(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi,
seyreltici="n2", **ek)
    g: g0 cinsinden (ISS 1e-4), oksijen: ortam % O2 (mol), basinc: kPa, seyreltici: ortamın geri kalanı (n2/he/co2/ar)
    kalinlik: KAYNAK BOYUTU mm — küre çapı (varsayılan 6.4), düz brülör çapı (25), jet lüle iç çapı (3.2)
    akis: yakıt akımının kaynak yüzeyinden çıkış hızı cm/s (298 K, p'de). Verilmezse ek anahtarlarla:
    ek: debi_mg_s (yakıt akımı kütle debisi), kutle_akisi_g_m2s (düz brülör), yakit_orani (yakıt akımında yakıt
        mol oranı), yakit_seyreltici, brulor_sicakligi (K, 300), bilesim={"o2":..,"n2":..} (ortam mol oranları),
        parametreler, min_oksijen_hesapla (True)
    malzeme: "methane", "ethylene", "50% C2H4", "30% H2, 15% CH4, with He" ...
    numune_tipi: küre = porous_sphere/sphere/leak/sizinti ; düz = flat_burner/bre/burner ; jet = gas_jet/jet/coflow
Dönüş: {"yanma": 0..1, "min_oksijen": %, "sicaklik": K (kayıplı alev sıcaklığı), "sicaklik_adyabatik": K,
        "alev_yaricapi": mm (küre: alev yarıçapı; düz: hacim-eşdeğer yarıçap) veya None,
        "alev_boyu": mm (düz: y_f; jet: L_f) veya None, "sonme_turu": "isinim"/"kimyasal"/"yok",
        "isinim_orani", "isi_akisi_kW_m2" (düz brülöre net alev ısı akısı), "kopma" (jet), "Z_st",
        "geometri", "kalibre_degil": bool, "uyarilar": [..], "mesafe": 0, "yayilma_hizi": None}

---------------------------------------------------------------------------------------------------------------
FİZİK (yarı-durağan, damla_motoru.py hızlı moduyla aynı mantık: kararlı hal + ışınım + Damköhler)
 Termokimya (çalışma anında, gaz_ozellikleri.json tablolarından; Cantera ön hesapta):
   ν = kg O2 / kg yakıt akımı,  Z_st = 1 / (1 + ν / Y_O2,∞)
   T_tam: Z_st karışımının tam yanma (CO2 + H2O + inert) adyabatik sıcaklığı (h tabloları, ikiye bölme)
   T_ad = T_tam - ΔT_ayr(T_tam, p): ayrışma düzeltmesi Cantera HP dengesine uydurulmuş (3920 nokta, ort. 16 K)
   Δh = yakıt akımının birim kütlesi başına alt ısıl değer
 Alev sıcaklığı (kayıplı):  T_f = T∞ + (T_ad - T∞)(1 - χ_r - χ_s)
   χ_r = Q_rad / (ṁ Δh),  Q_rad = C_rad · 4σ κ_P (T_f⁴ - T∞⁴) V_alev,  κ_P = p (X_CO2 a_CO2 + X_H2O a_H2O)
        (Planck ortalama; TNF/RADCAL eğrileri, Barlow ve ark.) — büyük alev = ışınımla sönme
        Geri emme (gaz_isinim.py): Q_rad × f(τ), f = (1-e^-τ)/τ, τ = (κ_P,alev + κ_P,ortam) L_m, L_m = 3.6 V/A
        (Hottel ortalama ışın yolu; Modest 2013 §10.6). BRE'de τ medyan 0.06 (en çok 0.29): etki %1-13.
   χ_s = Q_s / (ṁ Δh): kaynağa geri iletim (Stefan akışlı küresel iletim, damla kuramı; Law 2006 böl. 6):
        Q_s = k_s ṁ c_p (T_f - T_s) / (exp[ṁ c_p/(Ω λ) (1/R_s - 1/R_f)] - 1),  Ω = 4π (küre), 2π (yarım küre)
        küçük debi -> alev kaynağa yaklaşır -> χ_s büyür -> düşük debide sönme
 a) Küre (Flame Design / s-Flame / sızıntı):  R_f = ṁ / (4π ρD ln[1/(1-Z_st)])      (Irace ve ark. 2021, Eş. 8)
        ρD = ρ0D0 (T_ch/298)^½, T_ch = (298 + T_ad)/2, ρ0D0 = ortamın ρ·D_O2 (298 K; basınçtan bağımsız) (Eş. 9)
        V_alev = 4/3 π (R_f³ - R_s³)
 b) Düz brülör (BRE): yarım küre eşdeğeri R_h = ṁ / (2π ρD ln[1/(1-Z_st)]);  hacim-eşdeğer yarıçap
        R_eff = R_s + k_v R_h (Snegirev 2022: V = 2/3 π r_f² y_f = 2/3 π R_eff³), alev boyu y_f = k_y R_h;
        k_v, k_y BRE boyut ölçümlerinden (kapalı form; etiket kullanmaz). R_s = 2R_b/π: diskin iletkenliği
        4λR_b = yarım kürenin 2πλR_s (Carslaw & Jaeger 1959).
        Isı akısı q'' = Q_s / (π R_b²)  (Dehghani 2021: emüle edilen gazlaşma ısısı L = q''/m'')
        Denendi, geri alındı: düzlemsel üflemeli film (q'' = m''c_p ΔT/(e^(m''c_p y_f/λ)-1), V = 2/3π r_f² y_f):
        BRE içeride AUC 0.95 -> 0.88, q'' hatası %14 -> %68, X_r hatası 0.04 -> 0.09.
 c) Jet (gas_jet, SLICE / CLD / E-FIELD): Roper (1977) dairesel lüle alev boyu
        L_f = Q_F (T∞/T_F) / (4π D∞ ln(1 + 1/S)) · (T∞/T_ad)^0.67,  S = stokiyometrik oksitleyici/yakıt mol oranı
        µg alevleri 1 g'dekinden %28 uzun (Cao ve ark. 2014 PROCI 35, SLICE ölçümü) -> L = L_R (1 + 0.28 (1 - w)),
        w = r_g Ri/(1+Ri), Ri = g L (T_f-T∞)/T∞ / U²;  V = π L w_f²/6, w_f = L/3 (VARSAYIM: SLICE görüntüleri en/boy)
        Kopma / üflenme: taban Damköhler'i, a_taban = U / (K_taban d), K_taban = 10 (VARSAYIM; kalibre edilmedi).
 Sönme ölçütleri (ikisi de LİTERATÜR değerinde sabit; BRE verisinden belirlenemiyor, bkz. --profil):
   1) T_f < T_kr (kritik alev sıcaklığı): C2H4 1100, C3H8 1200, CH4 1300 K (Snegirev 2022, Flame Design + BRE
      ile; Irace 2021 ölçümü 1140 K), H2 1070 K (Lecoustre ve ark. 2012 PROCI 34 modeli). C2H6: C3H8 değeri.
   2) Damköhler (gerinim): Da = S_L(T_f)² / (α_hava a) / Da_q ;  Da_q metan-hava karşı akış sönme gerinimi
      a_q = 380 1/s'ye (Puri & Seshadri 1986, Combust. Flame 65:137) göre: Da_q = S_L,CH4² /(α_u a_q).
      S_L(T) = S_L,ref exp[-T_a/2 (1/T - 1/T_ref)] (p/1 atm)^-0.4 (Zeldovich; Law 2006); T_a = 15098 K
      (Westbrook & Dryer 1981, 30 kcal/mol — damla motoruyla aynı); S_L,ref stokiyometrik yakıt-hava:
      CH4 0.37, C2H4 0.68, C2H6 0.41, C3H8 0.43, H2 2.10 m/s (Law 2006 "Combustion Physics" Böl. 7 derlemesi).
      Gerinim: küre a = ṁ/(2π ρ_f R_f³), düz a = ṁ/(π ρ_f R_eff³), jet a = 2U/L_f; + kaldırma a_b.
   marj = min(ln Da, (T_f - T_kr)/100 K) ; yanma = σ(marj / s)
   sönme türü: yanmıyorsa ve ışınım kaybı çıkarılınca (χ_r = 0) alev yaşıyorsa "isinim", yoksa "kimyasal".
 d) g > 0 (kaldırma): küre ve düz alevde Nu/2 = 1 + 0.3 Pr^⅓ Gr^¼ (Ranz & Marshall 1952; Faeth 1977 PECS 3:191;
        damla motoruyla aynı biçim ve 1e-4..1e-2 g0 log rampası) ile R_f / (Nu/2); kaldırma gerinimi
        a_b = r_g √(g (T_f-T∞)/T∞ / ℓ) (Roper 1977; jet ℓ = L_f; küre/düz ℓ = max(R_f, r_g L_Roper): 1 g'de alev
        tüy gibi uzar). Jette yukarıdaki µg/1 g boy oranı.
        1 g için kalibre değil: literatür 1 g noktalarıyla AYRICA test edildi (--dogrula).

Kalibre sayılar (gaz_motoru_parametreleri.json): ln_Crad, ln_ks, s (+ geometri k_v, k_y). BRE 59 test.
    python3 gaz_motoru.py --kalibre       (scipy L-BFGS-B, fiziksel sınırlar, çok başlangıç)
    python3 gaz_motoru.py --dogrula       (deney / gün / basınç / yakıt seyreltmesi dışarıda; literatür kontrol)
    python3 gaz_motoru.py --grafik        (gaz_motoru.png)
"""
import argparse
import json
import math
import os
import re
import time
from pathlib import Path

import numpy as np

import gaz_isinim as gi_

KOK = Path(__file__).resolve().parent
OZELLIK_DOSYASI = KOK / "gaz_ozellikleri.json"
PARAM_DOSYASI = KOK / "gaz_motoru_parametreleri.json"
VERI = KOK / "gaz_veri"
P0 = 101325.0
R_U = 8314.462618
SIGMA = 5.670374e-8
T_INF = 298.15

# ------------------------------------------------------------------ yakıt verisi (literatür, bkz. üst açıklama)
YAKIT = {
    "CH4":  dict(nC=1, nH=4, S_L=0.37, Ta=15098.0, T_kr=1300.0),
    "C2H4": dict(nC=2, nH=4, S_L=0.68, Ta=15098.0, T_kr=1100.0),
    "C2H6": dict(nC=2, nH=6, S_L=0.41, Ta=15098.0, T_kr=1200.0),
    "C3H8": dict(nC=3, nH=8, S_L=0.43, Ta=15098.0, T_kr=1200.0),
    "H2":   dict(nC=0, nH=2, S_L=2.10, Ta=15098.0, T_kr=1070.0),
}
A_Q_CH4 = 380.0             # 1/s, metan-hava karşı akış sönme gerinimi (Puri & Seshadri 1986)
SL_BASINC_US = -0.4         # S_L ∝ p^-0.4 (Law 2006)
MUG_JET_UZAMA = 0.28        # µg jet alevi 1 g'dekinden %28 uzun (Cao ve ark. 2014, SLICE)
JET_EN_BOY = 3.0            # VARSAYIM
K_TABAN = 10.0              # VARSAYIM: jet tabanı gerinimi U/(K d)
K_UFLENME = 5.0             # VARSAYIM: kopmuş alev Da_taban < 1/K_UFLENME iken üflenir
G_RAMPA = (1e-4, 1e-2)      # damla_motoru ile aynı kaldırma rampası (g0)
CHI_MAKS = 0.97
# ışınım geri emme düzeltmesi (gaz_isinim.py: τ = κ_P L_m, Q × (1-e^-τ)/τ); GAZ_GERI_EMME=0 ile kapatılır
GERI_EMME = os.environ.get("GAZ_GERI_EMME", "1") == "1"

KALIBRE_YAKIT = {"C2H4"}    # etiketli kalibrasyon verisi olan yakıt (BRE)
GEOMETRI = {"kure": 0, "duz": 1, "jet": 2}
GEO_AD = {v: k for k, v in GEOMETRI.items()}
NUMUNE_GEO = {"porous_sphere": "kure", "sphere": "kure", "spherical": "kure", "kure": "kure", "leak": "kure",
              "sizinti": "kure", "s-flame": "kure", "flame_design": "kure",
              "flat_burner": "duz", "bre": "duz", "burner": "duz", "duz": "duz", "flat": "duz",
              "gas_jet": "jet", "jet": "jet", "coflow": "jet", "slice": "jet"}
VARSAYILAN_BOYUT_MM = {"kure": 6.4, "duz": 25.0, "jet": 3.2}
YAKIT_ADLARI = [("hydrogen", "H2"), ("hidrojen", "H2"), ("methane", "CH4"), ("metan", "CH4"),
                ("natural gas", "CH4"), ("ethylene", "C2H4"), ("etilen", "C2H4"), ("ethane", "C2H6"),
                ("etan", "C2H6"), ("propane", "C3H8"), ("propan", "C3H8"), ("butane", "C3H8"),
                ("bütan", "C3H8"), ("c2h4", "C2H4"), ("c2h6", "C2H6"), ("c3h8", "C3H8"), ("c4h10", "C3H8"),
                ("ch4", "CH4"), ("h2", "H2")]
YAKLASIK_YAKIT = ("butane", "bütan", "c4h10")
SEYRELTICI_TUR = {"n2": "N2", "nitrogen": "N2", "azot": "N2", "air": "N2", "he": "HE", "helium": "HE",
                  "helyum": "HE", "co2": "CO2", "ar": "AR", "argon": "AR"}


# ------------------------------------------------------------------ özellik tabloları
class Ozellik:
    def __init__(self, dosya=OZELLIK_DOSYASI):
        d = json.loads(Path(dosya).read_text(encoding="utf-8"))
        self.tur = d["turler"]
        self.i = {t: k for k, t in enumerate(self.tur)}
        self.ns = len(self.tur)
        self.M = np.array(d["M"])
        self.T = np.array(d["T"])
        self.cp, self.h = np.array(d["cp"]), np.array(d["h"])
        self.mu, self.lam = np.array(d["mu"]), np.array(d["lam"])
        self.D = np.array(d["D_1atm"])
        self.ay = d["ayrisma"]
        self.yakit_idx = np.array([self.i[y] for y in YAKIT])
        self.nC = np.zeros(self.ns)
        self.nH = np.zeros(self.ns)
        for y, v in YAKIT.items():
            self.nC[self.i[y]], self.nH[self.i[y]] = v["nC"], v["nH"]

    def _w(self, T):
        x = np.clip((np.asarray(T, float) - self.T[0]) / (self.T[1] - self.T[0]), 0, None)
        j = np.minimum(np.floor(x).astype(int), len(self.T) - 2)
        return j, x - j            # T ızgaranın üstünde: son aralıktan doğrusal öteleme

    def tab(self, arr, T):
        j, w = self._w(T)
        return arr[..., j] * (1 - w) + arr[..., j + 1] * w

    def X_Y(self, X):
        m = X * self.M[:, None]
        return m / m.sum(0), m.sum(0) / X.sum(0)

    def Y_X(self, Y):
        n = Y / self.M[:, None]
        return n / n.sum(0), 1.0 / n.sum(0)

    def h_mix(self, Y, T):
        return (Y * self.tab(self.h, T)).sum(0)

    def cp_mix(self, Y, T):
        return (Y * self.tab(self.cp, T)).sum(0)

    def lam_mix(self, X, T):           # Mathur, Tondon & Saxena (1967)
        l = self.tab(self.lam, T)
        return 0.5 * ((X * l).sum(0) + 1.0 / (X / l).sum(0))

    def mu_mix(self, X, T):            # Wilke (1950)
        mu = self.tab(self.mu, T)
        Mi, Mj = self.M[:, None, None], self.M[None, :, None]
        phi = (1 + np.sqrt(mu[:, None] / mu[None, :]) * (Mj / Mi) ** 0.25) ** 2 / np.sqrt(8 * (1 + Mi / Mj))
        return (X * mu / (X[None, :] * phi).sum(1)).sum(0)

    def D_O2(self, X, T, p):           # O2'nin karışımdaki difüzyon katsayısı (Blanc / Wilke)
        io = self.i["O2"]
        Dj = self.tab(self.D[io], T) * (P0 / p)
        Xo = np.where(np.arange(self.ns)[:, None] == io, 0.0, X)
        saf = Xo.sum(0) < 1e-6                     # saf O2 ortamı: öz-difüzyon
        Dm = np.clip(Xo.sum(0), 1e-9, None) / np.maximum((Xo / Dj).sum(0), 1e-30)
        return np.where(saf, Dj[io], Dm)


_OZ = None


def oz():
    global _OZ
    if _OZ is None:
        _OZ = Ozellik()
    return _OZ


def a_planck(T):
    """Planck ortalama soğurma katsayıları [1/(m atm)] (CO2, H2O): TNF workshop / RADCAL uydurması
    (Barlow ve ark.; damla_motoru.py ile aynı)."""
    u = 1000.0 / np.clip(T, 300.0, 2500.0)
    h2o = -0.23093 - 1.12390 * u + 9.41530 * u ** 2 - 2.99880 * u ** 3 + 0.51382 * u ** 4 - 1.86840e-5 * u ** 5
    co2 = 18.741 - 121.310 * u + 273.500 * u ** 2 - 194.050 * u ** 3 + 56.310 * u ** 4 - 5.8169 * u ** 5
    return np.clip(co2, 0, None), np.clip(h2o, 0, None)


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50, 50)))


# ------------------------------------------------------------------ bileşimler
def yakit_akimi(malzeme, yakit_orani=None, yakit_seyreltici=None):
    """malzeme metninden yakıt akımı mol oranları {tür: x}, notlar. '45% H2 with He', '50% C2H4',
    '30% h2 / 15% ch4 / 55% n2', 'methane' ..."""
    s = str(malzeme or "").lower().replace("–", "-").replace(",", " ")
    notlar = []
    if any(k in s for k in YAKLASIK_YAKIT):
        notlar.append("bütan tablolarda yok: propan özellikleriyle yaklaşıldı")
    seyr = None
    for k, t in SEYRELTICI_TUR.items():
        if re.search(rf"(?<![a-z0-9]){k}(?![a-z0-9])", s) and k != "air":
            seyr = t
    if yakit_seyreltici:
        seyr = SEYRELTICI_TUR.get(str(yakit_seyreltici).lower(), str(yakit_seyreltici).upper())
    X = {}
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*v?%\s*([a-z0-9\-]+)", s):
        val, ad = float(m.group(1)) / 100, m.group(2)
        hit = next((t for k, t in YAKIT_ADLARI if ad == k or ad.startswith(k) and k not in ("h2", "ch4")), None)
        if hit is None:
            hit = next((t for k, t in YAKIT_ADLARI if ad == k), None)
        if hit:
            X[hit] = X.get(hit, 0) + val
    if not X:
        hit = next((t for k, t in YAKIT_ADLARI if re.search(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])", s)
                    or (len(k) > 3 and k in s)), None)
        if hit is None:
            return None, notlar
        X[hit] = 1.0
        if yakit_orani is None and seyr is not None and "%" not in s:
            notlar.append("yakıt akımındaki seyreltici oranı verilmedi: saf yakıt varsayıldı")
    if yakit_orani is not None:
        t = sum(X.values())
        X = {k: v / t * float(yakit_orani) for k, v in X.items()}
    top = sum(X.values())
    if top > 1.0001:
        X = {k: v / top for k, v in X.items()}
        top = 1.0
    if top < 0.9999:
        X[seyr or "N2"] = X.get(seyr or "N2", 0) + 1 - top
    return X, notlar


def vektor(Xd):
    O = oz()
    v = np.zeros(O.ns)
    for t, x in Xd.items():
        v[O.i[t]] += x
    return v / v.sum()


def ortam(oksijen, seyreltici="n2", bilesim=None):
    if bilesim:
        d = {}
        for k, v in bilesim.items():
            t = "O2" if str(k).lower() == "o2" else SEYRELTICI_TUR.get(str(k).lower(), str(k).upper())
            if v and v > 0:
                d[t] = d.get(t, 0) + float(v)
        return vektor(d)
    t = SEYRELTICI_TUR.get(str(seyreltici or "n2").lower(), "N2")
    return vektor({"O2": float(oksijen) / 100, t: 1 - float(oksijen) / 100})


# ------------------------------------------------------------------ termokimya (vektörel, N durum)
def termokimya(XF, XO, p):
    """XF, XO: (ns, N) mol oranları; p: (N,) Pa. Z_st, T_tam, T_ad, Δh (J/kg yakıt akımı), ürünler."""
    O = oz()
    XF = np.where(XF[O.yakit_idx].sum(0) > 1e-9, XF, XF + 1e-9 * (np.arange(O.ns) == O.i["CH4"])[:, None])
    YF, MF = O.X_Y(XF)       # (yakıtsız akım: iz miktar CH4 -> yanma ~0, sıfıra bölme yok)
    YO, MO = O.X_Y(XO)
    io = O.i["O2"]
    nu = (YF * (O.nC + O.nH / 4)[:, None] * 31.998 / O.M[:, None]).sum(0)
    Zst = 1.0 / (1.0 + nu / np.clip(YO[io], 1e-9, None))
    Yst = Zst * YF + (1 - Zst) * YO
    Yp = Yst.copy()
    Yp[O.yakit_idx] = 0.0
    Yp[io] = 0.0
    yf = Yst[O.yakit_idx]
    Yp[O.i["CO2"]] += (yf * O.nC[O.yakit_idx, None] * 44.0095 / O.M[O.yakit_idx, None]).sum(0)
    Yp[O.i["H2O"]] += (yf * O.nH[O.yakit_idx, None] / 2 * 18.0153 / O.M[O.yakit_idx, None]).sum(0)
    Yp = Yp / Yp.sum(0)
    N = XF.shape[1]
    T0 = np.full(N, T_INF)
    h_r = O.h_mix(Yst, T0)
    dh = (h_r - O.h_mix(Yp, T0)) / Zst
    lo, hi = np.full(N, 300.0), np.full(N, 5000.0)
    for _ in range(40):
        T = 0.5 * (lo + hi)
        fazla = O.h_mix(Yp, T) > h_r
        hi = np.where(fazla, T, hi)
        lo = np.where(fazla, lo, T)
    T_tam = 0.5 * (lo + hi)
    a = O.ay
    x = np.clip(T_tam - a["T1"], 0, None)
    dT = np.clip(a["a0"] + a["a1"] * np.log10(p / P0), 0, None) * x ** 2 / (1 + a["b0"] * x)
    T_ad = T_tam - dT
    Xp, Mp = O.Y_X(Yp)
    return dict(YF=YF, YO=YO, MF=MF, MO=MO, nu=nu, Zst=Zst, Yp=Yp, Xp=Xp, Mp=Mp, T_tam=T_tam, T_ad=T_ad, dh=dh)


def yakit_karisim_ozellik(XF):
    """yakıt akımındaki yakıt türlerinin mol ağırlıklı S_L, T_a, T_kr (karışımlar için kaba)."""
    O = oz()
    xf = XF[O.yakit_idx]
    w = xf / np.clip(xf.sum(0), 1e-12, None)
    al = lambda k: (w * np.array([YAKIT[y][k] for y in YAKIT])[:, None]).sum(0)
    return al("S_L"), al("Ta"), al("T_kr"), w


_DAQ = None
_ALPHA_HAVA = None


def _alpha_hava():
    """havanın ısıl yayınımı, 298 K, 1 atm [m²/s]."""
    global _ALPHA_HAVA
    if _ALPHA_HAVA is None:
        O = oz()
        Xa = vektor({"O2": 0.21, "N2": 0.79})[:, None]
        Ya, Ma = O.X_Y(Xa)
        T = np.array([T_INF])
        _ALPHA_HAVA = float((O.lam_mix(Xa, T) / (P0 * Ma / (R_U * T) * O.cp_mix(Ya, T)))[0])
    return _ALPHA_HAVA


def Da_q():
    """ln Da_q: metan-hava, 1 atm, a_q = 380 1/s'de Da = 1 olacak şekilde."""
    global _DAQ
    if _DAQ is None:
        _DAQ = float(np.log(YAKIT["CH4"]["S_L"] ** 2 / (_alpha_hava() * A_Q_CH4)))
    return _DAQ


# ------------------------------------------------------------------ parametreler
PARAM_ADLARI = ["ln_Crad", "ln_ks", "s", "fv_ppm"]
SINIRLAR = {"ln_Crad": (math.log(0.03), math.log(30.0)), "ln_ks": (math.log(0.05), math.log(20.0)),
            "s": (0.03, 3.0), "fv_ppm": (0.0, 20.0)}
BASLANGIC = {"ln_Crad": 0.0, "ln_ks": 0.0, "s": 0.3, "fv_ppm": 0.0}
# Işınım modeli (GAZ_IS_MODELI):
#   "0"      : tek çarpan C_rad (gaz ışınımı × C_rad, is yok) — fv_ppm = 0 sabit
#   "1"      : gaz ışınımı C_gaz = 1 (saf kuram, sabit) + is ışınımı: f_v = fv_ppm·1e-6 · I_yakıt (I: smoke point,
#              gaz_isinim.IS_EGILIMI; yakıt akımındaki mol oranıyla ağırlıklı) ; fv_ppm yalnız etilen BRE'den
#   "serbest": "1" + C_gaz fiziksel aralıkta [0.7, 1.3] serbest
IS_MODELI = os.environ.get("GAZ_IS_MODELI", "0")
if IS_MODELI == "0":
    SINIRLAR["fv_ppm"] = (0.0, 0.0)
elif IS_MODELI == "1":
    SINIRLAR["ln_Crad"] = (0.0, 0.0)
else:
    SINIRLAR["ln_Crad"] = (math.log(0.7), math.log(1.3))
GEOMETRI_VARSAYILAN = {"k_v": 1.0, "k_y": 1.0}


def varsayilan_parametreler():
    if PARAM_DOSYASI.exists():
        d = json.loads(PARAM_DOSYASI.read_text(encoding="utf-8"))
        return {**d["parametreler"], **d["geometri"]}
    return {**BASLANGIC, **GEOMETRI_VARSAYILAN}


# ------------------------------------------------------------------ çekirdek hesap
def hesapla(par, geo, XF, XO, p, g, mdot, Rs, U, Ts, iter_sayisi=32):
    """Vektörel: geo (N,) int (0 küre, 1 düz, 2 jet); XF, XO (ns, N); p Pa; g g0; mdot kg/s (yakıt akımı);
    Rs m (küre yarıçapı / brülör yarıçapı / lüle yarıçapı); U m/s (jet çıkış hızı); Ts K (kaynak yüzeyi)."""
    O = oz()
    geo = np.asarray(geo, int)
    N = len(geo)
    p, g, mdot, Rs, U, Ts = (np.broadcast_to(np.asarray(v, float), (N,)).copy() for v in (p, g, mdot, Rs, U, Ts))
    yakitsiz = XF[O.yakit_idx].sum(0) <= 1e-9
    XF = np.where(yakitsiz, XF + 1e-9 * (np.arange(O.ns) == O.i["CH4"])[:, None], XF)
    tk = termokimya(XF, XO, p)
    T_ad, Zst, Xp, Yp = tk["T_ad"], tk["Zst"], tk["Xp"], tk["Yp"]
    q_ch = mdot * tk["dh"]
    SL0, Ta, T_kr, _w = yakit_karisim_ozellik(XF)
    # S_L referansı: aynı yakıt(lar) saf halde, havada, 1 atm
    xf = XF[O.yakit_idx]
    XFp = np.zeros_like(XF)
    XFp[O.yakit_idx] = xf / np.clip(xf.sum(0), 1e-12, None)
    Xair = np.repeat(vektor({"O2": 0.21, "N2": 0.79})[:, None], N, 1)
    T_ref = termokimya(XFp, Xair, np.full(N, P0))["T_ad"]
    T0 = np.full(N, T_INF)
    # ortam (oksitleyici) özellikleri
    rho_a = p * tk["MO"] / (R_U * T_INF)
    # kimyasal zaman τ_k = α_ref / S_L²: S_L,ref yakıt-HAVA değeri olduğundan α_ref de havanınki (p'de).
    # (S_L² ∝ α/τ_k: He gibi yüksek yayınımlı seyrelticide gerçek α ile bölmek τ_k'yi yapay büyütürdü.)
    alpha_u = _alpha_hava() * P0 / p
    rhoD0 = rho_a * O.D_O2(XO, T0, p)
    T_ch = 0.5 * (T_INF + T_ad)
    rhoD = rhoD0 * (T_ch / 298.0) ** 0.5
    Lz = np.log(1.0 / (1.0 - Zst))
    rho_F = p * tk["MF"] / (R_U * T_INF)
    kure, duz, jet = geo == 0, geo == 1, geo == 2
    R0 = np.where(kure, mdot / (4 * math.pi * rhoD * Lz), mdot / (2 * math.pi * rhoD * Lz))
    Rseq = np.where(duz, 2 * Rs / math.pi, Rs)     # disk iletkenliği 4λR_b = yarım küre 2πλr (Carslaw & Jaeger)
    # jet: Roper (1977)
    S_mol = (XF * (O.nC + O.nH / 4)[:, None]).sum(0) / np.clip(XO[O.i["O2"]], 1e-9, None)
    D_inf = O.D_O2(XO, T0, p)
    L_R0 = (mdot / rho_F) / (4 * math.pi * D_inf * np.log1p(1.0 / S_mol))
    # rampa
    lg = np.log10(np.maximum(g, 1e-12))
    r_g = np.clip((lg - math.log10(G_RAMPA[0])) / (math.log10(G_RAMPA[1]) - math.log10(G_RAMPA[0])), 0, 1)
    gg = g * 9.81
    # film özellikleri (kaldırma) ve iç bölge (iletim) için karışımlar
    Xin = 0.5 * (XF + Xp)
    Yin = 0.5 * (tk["YF"] + Yp)
    Crad, ks = math.exp(par["ln_Crad"]), math.exp(par["ln_ks"])
    k_v, k_y = par.get("k_v", 1.0), par.get("k_y", 1.0)
    kp_fac = (p / P0)
    Xfilm = 0.5 * (XO + Xp)
    Yfilm = 0.5 * (tk["YO"] + Yp)
    Om = np.where(kure, 4 * math.pi, 2 * math.pi)
    fv = par.get("fv_ppm", 0.0) * 1e-6
    I_is = (XF[O.yakit_idx] * np.array([gi_.IS_EGILIMI[y] for y in YAKIT])[:, None]).sum(0)

    def kayiplar(T_f):
        """T_f'de ışınım ve kaynak kaybı oranları + geometri."""
        Tfilm = 0.5 * (T_f + T_INF)
        rho_film = p * (Xfilm * O.M[:, None]).sum(0) / (R_U * Tfilm)
        mu_film = O.mu_mix(Xfilm, Tfilm)
        nu_k = mu_film / rho_film
        Pr = mu_film * O.cp_mix(Yfilm, Tfilm) / O.lam_mix(Xfilm, Tfilm)
        dTr = np.clip(T_f - T_INF, 0, None) / T_INF
        # küre: R_f = R0 (Irace Eş. 8);  düz: R_eff = R_s,eş + k_v R_h  (alev diski sarmak zorunda)
        Rb = np.where(duz, Rseq + k_v * R0, R0)
        Gr = gg * dTr * (2 * Rb) ** 3 / nu_k ** 2 * r_g ** 4
        nu2 = np.where(jet, 1.0, 1 + 0.3 * Pr ** (1 / 3) * Gr ** 0.25)
        R = np.where(duz, Rseq + (Rb - Rseq) / nu2, np.maximum(Rb / nu2, 1.02 * Rseq))
        L_R = L_R0 * (T_INF / T_ad) ** 0.67          # Roper: kayıpsız alev sıcaklığı (kayıplı T_f geri besleme yapar)
        Ri = gg * L_R * dTr / np.maximum(U, 1e-6) ** 2
        w = r_g * Ri / (1 + Ri)
        L_f = L_R * (1 + MUG_JET_UZAMA * (1 - w))
        Vk, Ak = gi_.kure_V_A(R, Rseq)
        Vd, Ad = gi_.yarim_kure_V_A(R)
        Vj, Aj = gi_.sferoid_V_A(L_f, L_f / JET_EN_BOY)
        V = np.where(kure, Vk, np.where(duz, Vd, Vj))
        A = np.where(kure, Ak, np.where(duz, Ad, Aj))
        kap_g = gi_.kappa_P(Xp[O.i["CO2"]], Xp[O.i["H2O"]], T_f, kp_fac)
        kap_o = gi_.kappa_P(XO[O.i["CO2"]], XO[O.i["H2O"]], T_f, kp_fac)
        if IS_MODELI == "0":       # eski biçim (birebir): Q = C_rad · Q_ince(κ_gaz) · f(τ_gaz)
            Q_r, tau_, _f = gi_.isinim_kaybi(T_f, kap_g, V, A, Crad, kap_o, T_INF, duzeltme=GERI_EMME)
        else:                      # gaz (C_gaz · κ_gaz) + is (κ_is = C_is f_v I T), ortak geri emme
            kap = Crad * kap_g + gi_.is_kappa(fv * I_is, T_f)
            Q_r, tau_, _f = gi_.isinim_kaybi(T_f, kap, V, A, 1.0, kap_o, T_INF, duzeltme=GERI_EMME)
        Tin = 0.5 * (Ts + T_f)
        cp_i = O.cp_mix(Yin, Tin)
        lam_i = O.lam_mix(Xin, Tin)
        Pe = mdot * cp_i / (Om * lam_i) * np.clip(1.0 / Rseq - 1.0 / R, 1e-9, None)
        Q_s = np.where(jet, 0.0, ks * mdot * cp_i * np.clip(T_f - Ts, 0, None) / np.expm1(np.clip(Pe, 1e-6, 50)))
        q = np.maximum(q_ch, 1e-30)
        return Q_r / q, Q_s / q, R, L_f, nu2, Q_s, tau_

    # enerji dengesi f(T) = T - T∞ - (T_ad - T∞)(1 - χ_r(T) - χ_s(T)): T'de artan, f(T∞) < 0 < f(T_ad) -> ikiye bölme
    lo, hi = np.full(N, T_INF), T_ad.copy()
    for _ in range(iter_sayisi):
        T = 0.5 * (lo + hi)
        cr, cs, *_ = kayiplar(T)
        f = T - T_INF - (T_ad - T_INF) * (1 - np.clip(cr + cs, 0, 1))
        hi = np.where(f > 0, T, hi)
        lo = np.where(f > 0, lo, T)
    T_f = 0.5 * (lo + hi)
    chi_r, chi_s, R, L_f, nu2, Q_s, tau = kayiplar(T_f)
    rho_f = p * tk["Mp"] / (R_U * T_f)
    # kaldırma gerinimi a_b = √(g ΔT/T∞ / ℓ): ℓ = alev boyu. Küre / düz alev 1 g'de tüy (plume) gibi uzar:
    # ℓ = max(R, r_g · L_Roper) (aynı debinin Roper alev boyu; Roper 1977 kaldırmalı alevler için de geçerli)
    L_Rk = L_R0 * (T_INF / T_ad) ** 0.67
    ell = np.where(jet, L_f, np.maximum(R, r_g * L_Rk))
    a_b = r_g * np.sqrt(gg * np.clip(T_f - T_INF, 0, None) / T_INF / np.maximum(ell, 1e-6))
    a = np.where(kure, mdot / (2 * math.pi * rho_f * R ** 3),
                 np.where(duz, mdot / (math.pi * rho_f * R ** 3), 2 * U / np.maximum(L_f, 1e-6))) + a_b
    pf = (p / P0) ** SL_BASINC_US

    def lnDa(T, a_):
        SL = SL0 * np.exp(-Ta / 2 * (1 / T - 1 / T_ref)) * pf
        return np.log(SL ** 2 / (alpha_u * np.maximum(a_, 1e-9))) - Da_q()

    lnDa_f = lnDa(T_f, a)
    marj = np.minimum(lnDa_f, (T_f - T_kr) / 100.0)
    # jet tabanı (kopma / üflenme)
    lnDa_taban = lnDa(T_ad, U / (K_TABAN * 2 * Rs))
    kopma = jet & (lnDa_taban < 0)
    marj = np.where(jet, np.minimum(marj, lnDa_taban + math.log(K_UFLENME)), marj)
    yanma = sigmoid(marj / par["s"])
    # sönme türü: ışınım kaybı olmasa yaşar mıydı?
    T_nr = T_INF + (T_ad - T_INF) * (1 - np.clip(chi_s, 0, CHI_MAKS))
    marj_nr = np.minimum(lnDa(T_nr, a), (T_nr - T_kr) / 100.0)
    if jet.any():
        marj_nr = np.where(jet, np.minimum(marj_nr, lnDa_taban + math.log(K_UFLENME)), marj_nr)
    tur = np.where(yanma >= 0.5, 0, np.where(marj_nr > 0, 1, 2))      # 0 yok, 1 isinim, 2 kimyasal
    q_flux = np.where(duz, Q_s / (math.pi * Rs ** 2) / 1e3, np.nan)
    return dict(yanma=yanma, marj=marj, T_f=T_f, T_ad=T_ad, Zst=Zst, chi_r=chi_r, chi_s=chi_s,
                R=np.where(jet, np.nan, R), y_f=np.where(duz, k_y * R0 / nu2, np.nan),
                L_f=np.where(jet, L_f, np.nan), q_flux=q_flux, lnDa=lnDa_f, a=a, tur=tur, kopma=kopma,
                T_kr=T_kr, R0=R0, nu2=nu2, tau=tau)


SONME_AD = {0: "yok", 1: "isinim", 2: "kimyasal"}


# ------------------------------------------------------------------ dış arayüz
def girdi_hazirla(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi, seyreltici="n2", debi_mg_s=None,
                  kutle_akisi_g_m2s=None, yakit_orani=None, yakit_seyreltici=None, brulor_sicakligi=300.0,
                  bilesim=None):
    geo_ad = NUMUNE_GEO.get(str(numune_tipi or "").lower().strip(), "jet")
    uyari = []
    if str(numune_tipi or "").lower().strip() not in NUMUNE_GEO:
        uyari.append(f"numune_tipi '{numune_tipi}' tanınmadı: gaz jeti varsayıldı")
    Xd, notlar = yakit_akimi(malzeme, yakit_orani, yakit_seyreltici)
    if Xd is None:
        return None, uyari + [f"yakıt tanınmadı: {malzeme}"]
    uyari += notlar
    XF = vektor(Xd)
    XO = ortam(oksijen, seyreltici, bilesim)
    p = float(basinc if basinc is not None else 101.325) * 1e3
    d_mm = float(kalinlik) if kalinlik is not None and kalinlik > 0 else VARSAYILAN_BOYUT_MM[geo_ad]
    Rs = d_mm / 2e3
    O = oz()
    MF = float((XF * O.M).sum())
    rhoF = p * MF / (R_U * T_INF)
    alan = {"kure": 4 * math.pi * Rs ** 2, "duz": math.pi * Rs ** 2, "jet": math.pi * Rs ** 2}[geo_ad]
    if debi_mg_s is not None:
        mdot = float(debi_mg_s) * 1e-6
    elif kutle_akisi_g_m2s is not None:
        mdot = float(kutle_akisi_g_m2s) * 1e-3 * math.pi * Rs ** 2
    elif akis is not None and akis > 0:
        mdot = rhoF * float(akis) / 100 * alan
    else:
        mdot = {"kure": 1.0e-6, "duz": 2.5e-3 * math.pi * Rs ** 2, "jet": rhoF * 0.30 * alan}[geo_ad]
        uyari.append("debi / akış verilmedi: varsayılan kullanıldı (küre 1 mg/s, düz 2.5 g/m²s, jet 30 cm/s)")
    U = mdot / (rhoF * alan)
    gi = dict(geo=np.array([GEOMETRI[geo_ad]]), XF=XF[:, None], XO=XO[:, None], p=np.array([p]),
              g=np.array([1e-4 if g is None or g <= 0 else float(g)]), mdot=np.array([mdot]),
              Rs=np.array([Rs]), U=np.array([U]), Ts=np.array([float(brulor_sicakligi)]))
    return (gi, geo_ad, Xd), uyari


def min_oksijen_bul(par, gi):
    """O2 mol oranı değiştirilir (ortamın diğer gazlarının oranı sabit); yanma >= 0.5 olan en düşük O2 (%)."""
    O = oz()
    o2 = np.arange(1.0, 60.0001, 0.25)
    n = len(o2)
    io = O.i["O2"]
    diger = gi["XO"][:, 0].copy()
    diger[io] = 0
    diger = diger / diger.sum()
    XO = diger[:, None] * (1 - o2 / 100)[None, :]
    XO[io] = o2 / 100
    r = hesapla(par, np.repeat(gi["geo"], n), np.repeat(gi["XF"], n, 1), XO, *(np.repeat(gi[k], n) for k in
                ("p", "g", "mdot", "Rs", "U", "Ts")))
    i = np.nonzero(r["yanma"] >= 0.5)[0]
    return float(o2[i[0]]) if len(i) else None


def gaz_motoru(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi, seyreltici="n2", debi_mg_s=None,
               kutle_akisi_g_m2s=None, yakit_orani=None, yakit_seyreltici=None, brulor_sicakligi=300.0,
               bilesim=None, parametreler=None, min_oksijen_hesapla=True):
    bos = {"yanma": None, "min_oksijen": None, "sicaklik": None, "alev_yaricapi": None, "alev_boyu": None,
           "sonme_turu": None, "mesafe": 0, "yayilma_hizi": None, "kalibre_degil": True}
    if oksijen is None:
        return {**bos, "uyarilar": ["oksijen verilmedi"]}
    hz, uyari = girdi_hazirla(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi, seyreltici, debi_mg_s,
                              kutle_akisi_g_m2s, yakit_orani, yakit_seyreltici, brulor_sicakligi, bilesim)
    if hz is None:
        return {**bos, "uyarilar": uyari}
    gi, geo_ad, Xd = hz
    par = parametreler or varsayilan_parametreler()
    r = hesapla(par, **gi)
    f = lambda k: float(r[k][0])
    yakitlar = {k for k in Xd if k in YAKIT}
    seyr_amb = {oz().tur[j] for j in np.nonzero(gi["XO"][:, 0] > 1e-6)[0]} - {"O2"}
    seyr_yak = {k for k in Xd if k not in YAKIT}
    neden = []
    if geo_ad == "jet":
        neden.append("jet geometrisi için etiketli PSI verisi yok (SLICE tablosu yok): kopma/üflenme literatür "
                     "varsayımı")
    if not yakitlar <= KALIBRE_YAKIT:
        neden.append(f"yakıt {sorted(yakitlar - KALIBRE_YAKIT)} etiketli veriyle kalibre edilmedi")
    if not (seyr_amb | seyr_yak) <= {"N2"}:
        neden.append(f"seyreltici {sorted((seyr_amb | seyr_yak) - {'N2'})} etiketli veriyle kalibre edilmedi")
    if gi["g"][0] > 1e-3:
        neden.append("g > 1e-3: kaldırma düzeltmesi literatürden, kalibre edilmedi (1 g kontrolü: --dogrula)")
    if gi["p"][0] < 0.5e5 or gi["p"][0] > 1.1e5:
        neden.append("basınç BRE aralığı (0.56-1.03 bar) dışında")
    if neden:
        uyari = uyari + ["KALİBRE DEĞİL: " + n for n in neden]
    sonuc = {"yanma": round(f("yanma"), 4),
             "min_oksijen": min_oksijen_bul(par, gi) if min_oksijen_hesapla else None,
             "sicaklik": round(f("T_f"), 1), "sicaklik_adyabatik": round(f("T_ad"), 1),
             "alev_yaricapi": None if geo_ad == "jet" else round(f("R") * 1e3, 2),
             "alev_boyu": (round(f("y_f") * 1e3, 2) if geo_ad == "duz" else
                           round(f("L_f") * 1e3, 2) if geo_ad == "jet" else None),
             "sonme_turu": SONME_AD[int(r["tur"][0])], "isinim_orani": round(f("chi_r"), 3),
             "kaynak_kaybi_orani": round(f("chi_s"), 3),
             "isi_akisi_kW_m2": round(f("q_flux"), 2) if geo_ad == "duz" else None,
             "kopma": bool(r["kopma"][0]) if geo_ad == "jet" else None, "Z_st": round(f("Zst"), 4),
             "debi_mg_s": round(float(gi["mdot"][0]) * 1e6, 4), "geometri": geo_ad, "mesafe": 0,
             "yayilma_hizi": None, "kalibre_degil": bool(neden), "uyarilar": uyari}
    return sonuc


# ------------------------------------------------------------------ veri okuyucular
def bre_oku():
    import pandas as pd
    t = pd.read_csv(VERI / "bre_dehghani2021_tablo2.csv")
    t["yanar"] = (t.sonuc == "FT").astype(int)
    t["gun"] = t.test.str[:2]
    t["R_eff_mm"] = (t.alev_boyu_y_f_mm * t.taban_yaricapi_r_f_mm ** 2) ** (1 / 3)
    return t


def bre_girdi(t):
    O = oz()
    N = len(t)
    XF = np.zeros((O.ns, N))
    XF[O.i["C2H4"]] = t.X_f.to_numpy(float)
    XF[O.i["N2"]] = 1 - t.X_f.to_numpy(float)
    XO = np.zeros((O.ns, N))
    XO[O.i["O2"]] = t.X_O2.to_numpy(float)
    XO[O.i["N2"]] = 1 - t.X_O2.to_numpy(float)
    Rb = 0.0125
    return dict(geo=np.ones(N, int), XF=XF, XO=XO, p=t.p_bar.to_numpy(float) * 1e5, g=np.full(N, 1e-4),
                mdot=t.m_akisi_g_m2s.to_numpy(float) * 1e-3 * math.pi * Rb ** 2, Rs=np.full(N, Rb),
                U=np.zeros(N), Ts=np.full(N, 300.0))


def irace_oku():
    import pandas as pd
    return pd.read_csv(VERI / "flame_design_irace2021.csv")


def kure_girdi(XF_list, XO_list, p, mdot, d_mm=6.4, g=1e-4):
    N = len(mdot)
    return dict(geo=np.zeros(N, int), XF=np.array(XF_list).T, XO=np.array(XO_list).T, p=np.asarray(p, float),
                g=np.full(N, g), mdot=np.asarray(mdot, float), Rs=np.full(N, d_mm / 2e3), U=np.zeros(N),
                Ts=np.full(N, 300.0))


def irace_girdi(t):
    XF, XO, md = [], [], []
    for x in t.itertuples():
        mC, mN = x.m_C2H4_mg_s, x.m_N2_mg_s
        nC, nN = mC / 28.054, mN / 28.014
        XF.append(vektor({"C2H4": nC / (nC + nN), "N2": nN / (nC + nN)} if nN > 0 else {"C2H4": 1.0}))
        XO.append(vektor({"O2": x.X_O2, "N2": 1 - x.X_O2}))
        md.append((mC + mN) * 1e-6)
    return kure_girdi(XF, XO, np.full(len(t), 1.0e5), md)


def psi10_oku():
    """PSI-10 Flame Design normal alev tablosu: sayısal satırlar (RAMP/RAMPED = rampalı akış, atlanır)."""
    import pandas as pd
    t = pd.read_csv(KOK / "PSI_SFLAME" / "PSI-10_Experimental table_Flame Design_Normal Flame.csv")
    t = t[pd.to_numeric(t["Xfuel"], errors="coerce").notna()].copy()
    for c in ["Xfuel", "mfuel (mg/s)", "mN2 (mg/s)", "mtot (mg/s)", "XO2 (init)", "XO2 (final)", "pinit (atm)",
              "pfinal (atm)", "pmean (atm)", "mean Zst", "Tad (K)"]:
        t[c] = pd.to_numeric(t[c], errors="coerce")
    t["XO2"] = t[["XO2 (init)", "XO2 (final)"]].mean(1)
    t["p_atm"] = t["pmean (atm)"].fillna(t["pinit (atm)"])
    return t.reset_index(drop=True)


def psi10_girdi(t):
    XF, XO = [], []
    for x in t.itertuples():
        XF.append(vektor({x.Fuel: x.Xfuel, "N2": 1 - x.Xfuel} if x.Xfuel < 1 else {x.Fuel: 1.0}))
        XO.append(vektor({"O2": x.XO2, "N2": 1 - x.XO2}))
    return kure_girdi(XF, XO, t.p_atm.to_numpy() * P0, t["mtot (mg/s)"].to_numpy() * 1e-6)


def _duzelt_otomatik_doldurma(s):
    """PSI özet tablolarındaki elektronik tablo otomatik doldurma artıkları: 'N3', 'N4'.. -> N2; 'CH5'.. -> CH4;
    'C2H5'.. -> C2H4 (aynı satırda 'Test Type' / bir üst satır azot ve ilgili yakıtı söylüyor)."""
    s = re.sub(r"\bN\d+\b", "N2", s)
    s = re.sub(r"\bCH\d+\b", "CH4", s)
    s = re.sub(r"\bC2H\d+\b", "C2H4", s)
    return s


def sflame_oku():
    """PSI-23 s-Flame: gün başına atmosfer + yakıt şişesi + tutuşan alev sayısı (yalnız pozitif)."""
    import pandas as pd
    t = pd.read_csv(KOK / "PSI_SFLAME" / "PSI-23_Experimental table_ACME s-Flame.csv")
    satir = []
    for x in t.itertuples():
        atm = _duzelt_otomatik_doldurma(str(x[6]))
        yak = _duzelt_otomatik_doldurma(str(x[7]))
        o2s = [float(v) for v in re.findall(r"~(\d+)%", atm)]
        seyr = "he" if "He" in atm else "n2"
        for o2 in o2s:
            satir.append(dict(gun=x[2], atmosfer=atm, yakit=yak, oksijen=o2, seyreltici=seyr, alev=int(x[8])))
    return pd.DataFrame(satir)


def bre_psi20_oku():
    """PSI-20 BRE özet: brülör çapı, yakıt şişesi, tutuşan alevlerin O2 değerleri (yalnız pozitif).
    '3400%' / '2100%' hücreleri tek değerin yüzde biçimlenmiş hali (34, 21). 0 tutuşmalı gün atlanır."""
    import pandas as pd
    t = pd.read_csv(KOK / "PSI_BRE" / "PSI-20_Experimental table_ACME BRE.csv")
    satir = []
    for x in t.itertuples():
        if int(x[7]) == 0:
            continue
        o2s = []
        for v in str(x[6]).split(";"):
            v = v.strip().replace("%", "")
            f = float(v)
            o2s.append(f / 100 if f > 100 else f)
        for o2 in o2s:
            satir.append(dict(tarih=f"{x[1]}-{x[2]}-{x[3]}", cap_mm=float(x[4]), yakit=str(x[5]), oksijen=o2,
                              alev=int(x[7])))
    return pd.DataFrame(satir)


def jet_psi_oku():
    """PSI-21 CLD ve PSI-22 E-FIELD: µg eş-akışlı / gaz jeti, hava (21/79), yakıt derişim aralığı (yalnız pozitif).
    CLD notu: en düşük derişime ulaşmadan sönen alevler listede ayrıca belirtilmiyor -> aralığın üstü kullanılır,
    alt uç ayrıca raporlanır."""
    import pandas as pd
    satir = []
    c = pd.read_csv(VERI / "PSI-21_Experimental table_CLD Flame.csv")
    for x in c.itertuples():
        yak = _duzelt_otomatik_doldurma(str(x[5]))
        tur = "CH4" if "CH4" in yak else "C2H4"
        ar = [float(v) for v in re.findall(r"(\d+)%", str(x[6]))]
        satir.append(dict(deney="CLD", gun=x[2], yakit=tur, x_ust=max(ar) / 100, x_alt=min(ar) / 100, alev=int(x[7])))
    e = pd.read_csv(VERI / "PSI-22_Experimental table_ACME E-FIELD Flames.csv")
    son = None
    for x in e.itertuples():
        if isinstance(x[7], str) and x[7].strip():
            son = (x[2], "CH4" if "CH4" in x[7] else "C2H4", str(x[1]))
        if son is None or not isinstance(x[8], str):
            continue
        v = float(x[8].replace("%", "")) / 100
        satir.append(dict(deney="E-FIELD", gun=son[0], yakit=son[1], x_ust=v, x_alt=v, alev=1,
                          burner="jet" if "gas-jet" in son[2] else "coflow"))
    return pd.DataFrame(satir)


def literatur_oku():
    """etiketli_gemma3.csv gaz noktaları (makalelerden; kalibrasyonda KULLANILMAZ)."""
    import pandas as pd
    v = pd.read_csv(KOK / "etiketli_gemma3.csv", low_memory=False)
    g = v[v.yakit_turu == "gaz"].copy().reset_index(drop=True)
    return g


# ------------------------------------------------------------------ kalibrasyon
SIG_XR, SIG_Q = 0.08, 0.30


def geometri_uydur(t, gi):
    """k_v, k_y: R_eff ve y_f ölçümlerine log-ortalama (µg, kaldırma yok -> R0 χ'den bağımsız)."""
    tk = termokimya(gi["XF"], gi["XO"], gi["p"])
    rhoD = oz().D_O2(gi["XO"], np.full(len(t), T_INF), gi["p"]) * gi["p"] * tk["MO"] / (R_U * T_INF) * \
        ((0.5 * (T_INF + tk["T_ad"])) / 298.0) ** 0.5
    R0 = gi["mdot"] / (2 * math.pi * rhoD * np.log(1 / (1 - tk["Zst"])))
    Rseq = 2 * gi["Rs"] / math.pi
    k_v = float(np.exp(np.mean(np.log(np.clip(t.R_eff_mm.to_numpy() / 1e3 - Rseq, 1e-4, None) / R0))))
    k_y = float(np.exp(np.mean(np.log(t.alev_boyu_y_f_mm.to_numpy() / 1e3 / R0))))
    return {"k_v": k_v, "k_y": k_y}


def kayip(v, adlar, sabit, t, gi, ayrinti=False):
    par = {**sabit, **dict(zip(adlar, v))}
    r = hesapla(par, **gi)
    y = t.yanar.to_numpy(float)
    q = np.clip(r["yanma"], 1e-6, 1 - 1e-6)
    bce = -np.sum(y * np.log(q) + (1 - y) * np.log(1 - q))
    # X_r ve q'' yalnız FT (kararlı) testlerde: SE alevlerinin ölçümü geçici rejimde, kararlı çözümleri yok
    ft = y == 1
    xr = t.isinim_orani_X_r.to_numpy(float)
    m = np.isfinite(xr) & ft
    kx = np.sum(((r["chi_r"][m] - xr[m]) / SIG_XR) ** 2)
    qc = t.q_merkez_kW_m2.to_numpy(float)
    mq = np.isfinite(qc) & (qc > 0) & ft
    kq = np.sum(((np.log(np.maximum(r["q_flux"][mq], 1e-3)) - np.log(qc[mq])) / SIG_Q) ** 2)
    top = bce + kx + kq
    return (top, {"bce": bce, "X_r": kx, "q": kq}) if ayrinti else top


def kalibre(t, baslangic_sayisi=8, tohum=0, sabit_ek=None):
    from scipy.optimize import minimize
    gi = bre_girdi(t)
    geo = geometri_uydur(t, gi)
    sabit = {**geo, **{a: SINIRLAR[a][0] for a in PARAM_ADLARI if SINIRLAR[a][0] == SINIRLAR[a][1]},
             **(sabit_ek or {})}
    adlar = [a for a in PARAM_ADLARI if a not in sabit]
    lo = np.array([SINIRLAR[a][0] for a in adlar])
    hi = np.array([SINIRLAR[a][1] for a in adlar])
    rng = np.random.default_rng(tohum)
    en = None
    sonuclar = []
    for k in range(baslangic_sayisi):
        x0 = np.clip(np.array([BASLANGIC[a] for a in adlar]), lo, hi) if k == 0 else lo + rng.random(len(lo)) * (hi - lo)
        r = minimize(kayip, x0, args=(adlar, sabit, t, gi), method="L-BFGS-B",
                     bounds=list(zip(lo, hi)), options={"maxiter": 300})
        sonuclar.append(float(r.fun))
        if en is None or r.fun < en.fun:
            en = r
    par = {**sabit, **dict(zip(adlar, map(float, en.x)))}
    return par, float(en.fun), sonuclar


def olcut(y, p_):
    from sklearn.metrics import roc_auc_score
    y = np.asarray(y, int)
    p_ = np.asarray(p_, float)
    auc = roc_auc_score(y, p_) if len(set(y)) == 2 else float("nan")
    return {"n": int(len(y)), "auc": float(auc), "dogruluk": float(((p_ >= 0.5).astype(int) == y).mean()),
            "yanan_orani": float(y.mean())}


def bre_olcutler(t, r):
    o = olcut(t.yanar, r["yanma"])
    ft = t.yanar.to_numpy() == 1
    xr = t.isinim_orani_X_r.to_numpy(float)
    m = np.isfinite(xr) & ft
    qc = t.q_merkez_kW_m2.to_numpy(float)
    o.update({"X_r_mutlak_hata_medyan_FT": float(np.median(np.abs(r["chi_r"][m] - xr[m]))) if m.any() else np.nan,
              "q_merkez_hata_medyan_yuzde_FT": float(np.median(np.abs(r["q_flux"][ft] / qc[ft] - 1)) * 100),
              "y_f_hata_medyan_yuzde": float(np.median(np.abs(r["y_f"] * 1e3 / t.alev_boyu_y_f_mm - 1)) * 100),
              "R_eff_hata_medyan_yuzde": float(np.median(np.abs(r["R"] * 1e3 / t.R_eff_mm - 1)) * 100)})
    return o


def kalibre_main():
    t = bre_oku()
    bas = time.time()
    par, kay, tum = kalibre(t)
    gi = bre_girdi(t)
    r = hesapla(par, **gi)
    _, parca = kayip([par.get(a, BASLANGIC[a]) for a in PARAM_ADLARI], PARAM_ADLARI,
                     {k: par[k] for k in ("k_v", "k_y")}, t, gi,
                     ayrinti=True)
    m = bre_olcutler(t, r)
    out = {"parametreler": {a: par.get(a, BASLANGIC[a]) for a in PARAM_ADLARI}, "is_modeli": IS_MODELI, "geometri": {k: par[k] for k in ("k_v", "k_y")},
           "kayip": kay, "kayip_parcalari": {k: float(v) for k, v in parca.items()},
           "baslangic_kayiplari": tum, "olcut_egitim_BRE": m,
           "sabit_literatur": {"T_kr_K": {y: v["T_kr"] for y, v in YAKIT.items()},
                               "S_L_ref_m_s": {y: v["S_L"] for y, v in YAKIT.items()},
                               "T_a_K": 15098.0, "a_q_CH4_1_s": A_Q_CH4},
           "veri": "gaz_veri/bre_dehghani2021_tablo2.csv (59 ISS BRE testi, Dehghani ve ark. 2021 Tablo 2)",
           "tarih": time.strftime("%Y-%m-%d %H:%M")}
    PARAM_DOSYASI.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Kalibrasyon ({time.time() - bas:.0f} s): kayıp {kay:.2f} {parca}")
    print("  başlangıç kayıpları:", [round(x, 2) for x in tum])
    for k, v in par.items():
        print(f"  {k:8s} {v:9.4f}" + (f"  (={math.exp(v):.3f})" if k.startswith("ln_") else ""))
    print("  eğitim (BRE, içeride):", {k: round(v, 3) for k, v in m.items()})


# ------------------------------------------------------------------ çekirdek sayısı (5. madde)
def bos_cekirdek(en_fazla=14):
    """pgrep ile python süreçleri bulunur; yalnız CPU kullananlar (%CPU > 20, örn. diğer oturumun damla işçileri)
    meşgul sayılır. İşçi = çekirdek - meşgul, en fazla 14 (damla işleri bitince)."""
    import subprocess
    try:
        pid = [x for x in subprocess.run(["pgrep", "python"], capture_output=True, text=True).stdout.split()
               if x.strip() and int(x) != os.getpid()]
        mesgul = 0
        if pid:
            ps = subprocess.run(["ps", "-o", "pcpu=", "-p", ",".join(pid)], capture_output=True, text=True).stdout
            mesgul = sum(1 for v in ps.split() if float(v) > 20.0)
    except Exception:
        mesgul = 0
    return max(1, min(en_fazla, (os.cpu_count() or 2) - mesgul))


def _cv_isci(arg):
    os.environ["OMP_NUM_THREADS"] = "1"
    ad, egitim_idx, test_idx, sabit_ek = arg
    t = bre_oku()
    par, _, _ = kalibre(t.iloc[egitim_idx].reset_index(drop=True), baslangic_sayisi=5, sabit_ek=sabit_ek)
    r = hesapla(par, **bre_girdi(t.iloc[test_idx].reset_index(drop=True)))
    return ad, test_idx, {k: np.asarray(v).tolist() for k, v in r.items()}, par


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--kalibre", action="store_true")
    ap.add_argument("--dogrula", action="store_true")
    ap.add_argument("--grafik", action="store_true")
    ap.add_argument("--profil", action="store_true")
    a = ap.parse_args()
    if a.kalibre:
        kalibre_main()
    elif a.dogrula:
        from gaz_dogrulama import dogrula_main
        dogrula_main()
    elif a.grafik:
        from gaz_dogrulama import grafik_main
        grafik_main()
    elif a.profil:
        from gaz_dogrulama import profil_main
        profil_main()
    else:
        for arg in [(1e-4, 34, 57, None, 25, "ethylene", "flat_burner"),
                    (1e-4, 28.4, 101.3, None, 6.4, "13.2% ethylene", "porous_sphere"),
                    (1.0, 21, 101.3, 30, 3.2, "methane", "gas_jet")]:
            print(arg, gaz_motoru(*arg))
