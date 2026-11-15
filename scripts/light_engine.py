#!/usr/bin/env python3
"""
scripts/light_engine.py — yarı-ampirik, milisaniyelik fizik motoru (scripts/engine.py ile aynı arayüz).

    from light_engine import motor
    motor(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi, seyreltici="n2")
      -> {"yanma": 0-1, "min_oksijen": %, "yayilma_hizi": mm/s (damla/gaz için None), "sicaklik": K}

Komut satırı:
    python3 scripts/light_engine.py --kalibre     # psi_labeled*.csv ile kalibre et -> data/light_engine_parameters.json
    python3 scripts/light_engine.py --dogrula     # deney ailesi bazında 5'li çapraz doğrulama
    python3 scripts/light_engine.py --u-grafik    # figures/light_engine_U.png (PMMA ince levha, uzay)

FİZİK (her adımın kaynağı ilgili satırda):
 1) Alev sıcaklığı: Burke-Schumann difüzyon alevi, saf yakıt akımı:
        T_ad - T∞ = Y_O2 · (ΔH_c/r) / (c_p · (1 + Y_O2/r))
    ΔH_c/r = oksijen başına açığa çıkan ısı (Huggett 1980, ~13.1 MJ/kg O2; malzemeye göre tablo),
    r = stokiyometrik O2/yakıt kütle oranı. Yüksek sıcaklıkta ayrışma T_ad'yi sınırlar (Turns,
    "An Introduction to Combustion", 3. bs., Bölüm 2): 2000 K üstü yumuşak tavanla ~2600 K'de doyar.
 2) Etkin akış: V = sqrt(V_zorlanmış² + U_b² + V_dif²)
        U_b   = (g · α · ΔT/T∞)^(1/3)        kaldırma kuvveti hızı (Fernandez-Pello 1984; T'ien 1986)
        V_dif = α / L                        difüzyon hızı; damla/çubuk/küre için L = çap, levha için 5 cm
    α (ısıl yayınım, ν yerine; Pr ~ 0.7) basınçla ters orantılı, seyrelticiye göre ölçeklenir.
 3) Yayılma hızı (de Ris 1969):
        ince : V_f = √2 · k_g (T_f - T_v) / (ρ_s c_s τ (T_v - T∞))          τ = yarı kalınlık
        kalın: V_f = V · (kρc)_g (T_f - T_v)² / ((kρc)_s (T_v - T∞)²)
    kalınlık eşiği (tau_esik, mm) kalibre edilir. Damla ve gaz için yayılma tanımsız (None).
 4) Sönme:
    a) Üfleme (Damköhler; Fernandez-Pello, Ray & Glassman 1981):
        Da = t_kalış / t_kimya,  t_kalış = α / V²,  t_kimya = exp(Ta/T_f) / ((p/p0) · Y_O2 · A)
       ln A ile ln Da_kritik ayrı ayrı belirlenemez; ikisi tek bir "lnA" parametresinde birleşik.
    b) Işınımsal soğuma (T'ien 1986; Chao, Law & T'ien 1990):
        katılar   : R = ε σ (T_v⁴ - T∞⁴) / (ρ c_p V (T_f - T_v))     yüzey ışınımı / alevden gelen ısı
        damla/gaz : R = ε σ (T_rad⁴ - T∞⁴) / (ρ c_p V (T_f - T∞)),  T_rad = 2000 K sabit
       İstenen formüldeki T_f⁴ ile oksijen artınca ışınım oranı da artıyor, yani yüksek O2 sönmeyi
       artırıyordu (fiziksel değil; kalibrasyon ışınım yolunu tamamen kapattı). Bu yüzden katılarda
       yüzey sıcaklığı T_v, damlalarda sabit T_rad kullanıldı: R artık oksijenle azalır, damla çapıyla
       (V = α/d) artar — büyük damlaların ışınımla sönmesi (Chao, Law & T'ien 1990).
       ε sabit (0.9 yüzey, 0.2 alev); ε ile R_kritik ayrı belirlenemez.
    yanma = σ(ln Da / s) · σ(-(ln R - ln R_kritik) / s)      (s: yumuşaklık, kalibre edilir)
 5) min_oksijen: diğer koşullar sabit, O2 %1-60 aralığında 0.25 adımla taranır; yanma'nın 0.5'i ilk
    geçtiği nokta (doğrusal ara değerleme). Hiç geçmezse None.

Gruplar ve parametreleri (grup başına 3-4): ince_kati, kumas, kalin_kati -> lnA, Ta, lnRk, Tv;
sivi_damla -> lnA, Ta, lnRk; gaz -> veri yok, sivi_damla'nınkiler kullanılır (KALİBRE EDİLMEDİ).
Genel: s, tau_esik, kappa_seyreltici (seyreltici etkisinin ağırlığı, 0-1; ampirik).
Malzeme zorluğu (etkin alev sıcaklığı düşüşü, K): nomex, silicone (0..800); damla grubu içinde malzemeleri
ayırmak için methanol, n-heptane, 1-propanol (-400..800).
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np

KOK = Path(__file__).resolve().parent.parent
PARAM_DOSYASI = KOK / "data/light_engine_parameters.json"
U_PNG = KOK / "figures/light_engine_U.png"

T_INF = 300.0
SIGMA = 5.670e-8
ALPHA0 = 1.0e-4          # m²/s, havanın film sıcaklığında (~1000 K) ısıl yayınımı, 1 atm (Incropera, Tablo A.4)
CP_O2 = 1090.0           # J/kgK, 300-2000 K ortalaması (JANAF)
EPS_YUZEY, EPS_ALEV = 0.9, 0.2
T_RAD = 2000.0           # K, damla/gaz alev ışınımı için sabit sıcaklık (bkz. 4b)
L_LEVHA = 0.05           # m, levha/kumaş için difüzyon uzunluğu (tahmin, numune genişliği mertebesi)
G_UZAY = 1e-4            # g; veride/dashboard'da "uzay" bu değerle yazılıyor
G_ALT = 1e-6             # g; ISS yarı-durağan artık ivmesi ~1e-6 g (NASA ISS mikro-g ortamı); veride 0 ya da 1e-4 yazan uzay noktaları da buraya iner
O2_TARAMA = np.arange(1.0, 60.0001, 0.25)

# seyreltici: molar kütle (g/mol), c_p (J/kgK, 300-2000 K ort.), ısıl yayınım / N2 (300 K) — Incropera Tablo A.4
SEYRELTICI = {"n2": (28.0, 1180.0, 1.00), "co2": (44.0, 1150.0, 0.50), "he": (4.0, 5193.0, 8.00),
              "ar": (39.9, 520.0, 1.00), "xe": (131.3, 158.0, 0.25)}

# malzeme: (faz, ρ_s kg/m³, c_s J/kgK, k_s W/mK, T_v K, r = O2/yakıt kütle, ΔH_c/r MJ/kg O2, varsayılan kalınlık mm)
# ΔH_c/r: Huggett 1980 (PMMA 13.02, selüloz 13.59, PE 12.65, n-heptan 12.68, metan 12.54); diğerleri ~13 (tahmin)
# T_v: polimerlerde piroliz, sıvılarda kaynama sıcaklığı.
MALZEME = {
    "pmma":         ("kati", 1190, 1460, 0.19, 660, 1.92, 13.02, 3.0),
    "cellulose":    ("kati",  650, 1260, 0.10, 600, 1.185, 13.59, 0.1),
    "cotton":       ("kati",  500, 1260, 0.07, 600, 1.185, 13.59, 0.37),
    "sibal":        ("kati",  490, 1120, 0.07, 600, 1.185, 13.59, 0.37),   # 0.182 kg/m² / 0.37 mm
    "nomex":        ("kati",  400, 1200, 0.05, 700, 2.0, 13.0, 0.37),
    "silicone":     ("kati", 1100, 1300, 0.20, 700, 1.5, 13.0, 1.0),
    "ultem":        ("kati", 1270, 1400, 0.22, 800, 2.1, 13.0, 0.2),
    "polyethylene": ("kati",  950, 2300, 0.40, 640, 3.43, 12.65, 1.0),
    "n-heptane":    ("sivi",  684, 2240, 0.12, 371, 3.52, 12.68, 1.0),
    "n-decane":     ("sivi",  730, 2210, 0.13, 447, 3.48, 12.7, 1.0),
    "methanol":     ("sivi",  792, 2530, 0.20, 338, 1.50, 13.3, 1.0),
    "ethanol":      ("sivi",  789, 2440, 0.17, 351, 2.09, 12.9, 1.0),
    "1-propanol":   ("sivi",  803, 2390, 0.15, 370, 2.40, 12.9, 1.0),
    "methane":      ("gaz",     0,    0, 0.0,  112, 4.00, 12.54, None),
    "ethylene":     ("gaz",     0,    0, 0.0,  170, 3.43, 12.9, None),
    "propane":      ("gaz",     0,    0, 0.0,  231, 3.64, 12.8, None),
}
VARSAYILAN_MALZEME = "pmma"

GRUPLAR = ["ince_kati", "kumas", "kalin_kati", "sivi_damla", "gaz"]
KATI_GRUPLAR = ["ince_kati", "kumas", "kalin_kati"]
ZORLUK_MALZEMELER = ["nomex", "silicone", "methanol", "n-heptane", "1-propanol"]
ZORLUK_SINIR = {"nomex": (0.0, 800.0), "silicone": (0.0, 800.0)}   # sıvılar: (-400, 800)

# parametre vektörü: [katı grupları × (lnA, Ta, lnRk, Tv)] + [damla × (lnA, Ta, lnRk)] + [s, tau_esik] + zorluklar
SINIRLAR = ([(0.0, 40.0), (5000.0, 25000.0), (math.log(0.01), math.log(100.0)), (550.0, 800.0)] * 3
            + [(0.0, 40.0), (5000.0, 25000.0), (math.log(0.01), math.log(100.0))]
            + [(0.2, 3.0), (0.1, 5.0), (0.0, 1.0)]
            + [ZORLUK_SINIR.get(m, (-400.0, 800.0)) for m in ZORLUK_MALZEMELER])
BASLANGIC = ([20.0, 15000.0, 0.0, 660.0] * 3 + [20.0, 15000.0, 0.0] + [0.7, 1.0, 1.0]
             + [100.0 if m in ZORLUK_SINIR else 0.0 for m in ZORLUK_MALZEMELER])
PARAM_ADLARI = ([f"{g}.{p}" for g in KATI_GRUPLAR for p in ("lnA", "Ta", "lnRk", "Tv")]
                + ["sivi_damla.lnA", "sivi_damla.Ta", "sivi_damla.lnRk", "s", "tau_esik_mm", "kappa_seyreltici"]
                + [f"zorluk.{m}" for m in ZORLUK_MALZEMELER])


# ------------------------------------------------------------------ yardımcılar
def _malzeme_ana(ad):
    try:
        from risk_model import malzeme_ana
        return malzeme_ana(ad)
    except Exception:
        return str(ad).lower().strip()


_ANA_ONBELLEK = {}


def malzeme_bul(ad):
    if ad is None:
        return VARSAYILAN_MALZEME, False
    a = str(ad).lower().strip()
    if a not in _ANA_ONBELLEK:
        ana = _malzeme_ana(a)
        _ANA_ONBELLEK[a] = ana if ana in MALZEME else (a if a in MALZEME else None)
    m = _ANA_ONBELLEK[a]
    return (m, True) if m else (VARSAYILAN_MALZEME, False)


def grup_bul(malzeme, numune_tipi, kalinlik, tau_esik):
    faz = MALZEME[malzeme][0]
    if faz == "sivi":
        return "sivi_damla"
    if faz == "gaz":
        return "gaz"
    t = str(numune_tipi or "").lower()
    if t == "fabric" or malzeme in ("sibal", "cotton", "nomex"):
        return "kumas"
    if t in ("thick_sheet", "rod", "sphere", "cylinder"):
        return "kalin_kati"
    if t == "thin_sheet":
        return "ince_kati"
    return "ince_kati" if (kalinlik or MALZEME[malzeme][7] or 1) <= tau_esik else "kalin_kati"


def param_sozluk(v):
    v = list(v)
    p = {}
    for i, g in enumerate(KATI_GRUPLAR):
        p[g] = dict(zip(("lnA", "Ta", "lnRk", "Tv"), v[4 * i:4 * i + 4]))
    p["sivi_damla"] = dict(zip(("lnA", "Ta", "lnRk"), v[12:15]))
    p["gaz"] = dict(p["sivi_damla"])
    p["s"], p["tau_esik_mm"], p["kappa_seyreltici"] = v[15], v[16], v[17]
    p["zorluk"] = dict(zip(ZORLUK_MALZEMELER, v[18:]))
    return p


def _sig(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50, 50)))


# ------------------------------------------------------------------ çekirdek (vektörel)
def hazirla(satirlar, tau_esik):
    """satirlar: (g, O2, p, akis, kalinlik, malzeme, numune_tipi, seyreltici) listesi -> sabit diziler."""
    n = len(satirlar)
    a = {k: np.zeros(n) for k in ("g", "o2", "p", "u", "kal", "rho_s", "c_s", "k_s", "Tv0", "r", "q",
                                   "M_d", "cp_d", "a_d", "L", "zorluk_idx")}
    grup, faz = [], []
    for i, (g, o2, p, u, kal, mal, tip, sey) in enumerate(satirlar):
        m, _ = malzeme_bul(mal)
        f, rho_s, c_s, k_s, Tv, r, q, kal0 = MALZEME[m]
        kal = kal if (kal is not None and not (isinstance(kal, float) and math.isnan(kal)) and kal > 0) else kal0
        gr = grup_bul(m, tip, kal, tau_esik)
        Md, cpd, ad = SEYRELTICI.get(str(sey or "n2").lower(), SEYRELTICI["n2"])
        g = 1.0 if g is None or (isinstance(g, float) and math.isnan(g)) else g
        a["g"][i] = G_ALT if g <= G_UZAY else g     # "uzay" etiketli (<= 1e-4 g) koşullar ISS yarı-durağan ivmesine
        a["o2"][i] = 20.95 if o2 is None else o2
        a["p"][i] = 101.3 if p is None or (isinstance(p, float) and math.isnan(p)) else max(p, 1.0)
        a["u"][i] = 0.0 if u is None or (isinstance(u, float) and math.isnan(u)) else max(u, 0.0)
        a["kal"][i] = kal if kal else 1.0
        a["rho_s"][i], a["c_s"][i], a["k_s"][i], a["Tv0"][i], a["r"][i], a["q"][i] = rho_s, c_s, k_s, Tv, r, q * 1e6
        a["M_d"][i], a["cp_d"][i], a["a_d"][i] = Md, cpd, ad
        tip_s = str(tip or "").lower()
        a["L"][i] = (a["kal"][i] / 1000.0) if (gr in ("sivi_damla", "gaz") or tip_s in ("rod", "sphere", "droplet")) \
            else L_LEVHA
        a["zorluk_idx"][i] = ZORLUK_MALZEMELER.index(m) if m in ZORLUK_MALZEMELER else -1
        grup.append(gr)
        faz.append(f)
    a["grup"] = np.array(grup)
    a["kati"] = np.array([f == "kati" for f in faz])
    return a


def hesap(p, a, o2=None):
    """p: param_sozluk; a: hazirla() çıktısı; o2: isteğe bağlı O2 dizisi (tarama için).
    -> dict(yanma, Tf, Vf (m/s, katılar), lnDa, lnR)"""
    X = (a["o2"] if o2 is None else o2) / 100.0
    # seyreltici özellikleri: N2 ile gerçek seyreltici arasında geometrik ara değer (kappa = 1 tam etki, 0 = N2 gibi).
    # Ampirik düzeltme: saf termodinamik CO2/He etkisini verideki sönme sınırı farkından çok daha büyük veriyor.
    kp = p.get("kappa_seyreltici", 1.0)
    Md = 28.0 ** (1 - kp) * a["M_d"] ** kp
    cpd = 1180.0 ** (1 - kp) * a["cp_d"] ** kp
    ad = a["a_d"] ** kp
    # 1) alev sıcaklığı (Burke-Schumann + Huggett)
    Y = X * 32.0 / (X * 32.0 + (1.0 - X) * Md)
    cp = Y * CP_O2 + (1.0 - Y) * cpd
    dT = Y * a["q"] / (cp * (1.0 + Y / a["r"]))
    Tad = T_INF + dT
    asim = np.maximum(Tad - 2000.0, 0.0)
    Tf = np.where(Tad > 2000.0, 2000.0 + asim / (1.0 + asim / 600.0), Tad)       # ayrışma tavanı (Turns, Bl. 2)
    z = np.array([p["zorluk"][m] for m in ZORLUK_MALZEMELER] + [0.0])
    Tf = Tf - z[a["zorluk_idx"].astype(int)]
    Tf = np.maximum(Tf, T_INF + 50.0)

    # grup parametreleri
    n = len(a["grup"])
    lnA, Ta, lnRk, Tv = np.zeros(n), np.zeros(n), np.zeros(n), a["Tv0"].copy()
    for g in GRUPLAR:
        k = a["grup"] == g
        if k.any():
            lnA[k], Ta[k], lnRk[k] = p[g]["lnA"], p[g]["Ta"], p[g]["lnRk"]
            if "Tv" in p[g]:
                Tv[k] = p[g]["Tv"]
    Tv = np.minimum(Tv, Tf - 10.0)

    # 2) etkin akış
    alpha = ALPHA0 * (101.3 / a["p"]) * (X + (1.0 - X) * ad)
    Ub = (9.81 * a["g"] * alpha * (Tf - T_INF) / T_INF) ** (1.0 / 3.0)
    V = np.sqrt((a["u"] / 100.0) ** 2 + Ub ** 2 + (alpha / a["L"]) ** 2)

    # gaz yoğunluğu (film sıcaklığı), c_p
    M = 1.0 / (Y / 32.0 + (1.0 - Y) / Md)
    Tfilm = 0.5 * (Tf + T_INF)
    rho = a["p"] * 1000.0 * M / 1000.0 / (8.314 * Tfilm)

    # 4a) Damköhler
    lnDa = np.log(alpha / V ** 2) + np.log(a["p"] / 101.3 * Y) + lnA - Ta / Tf
    # 4b) ışınım
    yuzey = EPS_YUZEY * SIGMA * (Tv ** 4 - T_INF ** 4) / (rho * cp * V * (Tf - Tv))
    Tr = Tf if T_RAD is None else T_RAD
    alev = EPS_ALEV * SIGMA * (Tr ** 4 - T_INF ** 4) / (rho * cp * V * (Tf - T_INF))
    lnR = np.log(np.where(a["kati"], yuzey, alev))
    s = p["s"]
    yanma = _sig(lnDa / s) * _sig(-(lnR - lnRk) / s)

    # 3) yayılma (de Ris 1969)
    kg = alpha * rho * cp
    tau = a["kal"] / 2000.0
    ince = math.sqrt(2.0) * kg * (Tf - Tv) / (a["rho_s"] * a["c_s"] * tau * (Tv - T_INF) + 1e-30)
    kalin = V * (kg * rho * cp) * (Tf - Tv) ** 2 / (a["k_s"] * a["rho_s"] * a["c_s"] * (Tv - T_INF) ** 2 + 1e-30)
    Vf = np.where(a["kal"] <= p["tau_esik_mm"], ince, kalin)
    Vf = np.where(a["kati"], Vf, np.nan)
    return {"yanma": yanma, "Tf": Tf, "Vf": Vf, "lnDa": lnDa, "lnR": lnR}


# ------------------------------------------------------------------ parametreler
_P = None


def parametreler():
    global _P
    if _P is None:
        if PARAM_DOSYASI.exists():
            _P = param_sozluk(json.loads(PARAM_DOSYASI.read_text(encoding="utf-8"))["vektor"])
        else:
            _P = param_sozluk(BASLANGIC)
    return _P


def motor(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi, seyreltici="n2"):
    p = parametreler()
    a = hazirla([(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi, seyreltici)], p["tau_esik_mm"])
    h = hesap(p, a)
    yanma = float(h["yanma"][0])
    tarama = hesap(p, {k: (np.repeat(v, len(O2_TARAMA)) if isinstance(v, np.ndarray) else v) for k, v in a.items()},
                   o2=O2_TARAMA)["yanma"]
    ust = np.nonzero(tarama >= 0.5)[0]
    if len(ust) == 0:
        min_o2 = None
    elif ust[0] == 0:
        min_o2 = float(O2_TARAMA[0])
    else:
        i = ust[0]
        y0, y1 = tarama[i - 1], tarama[i]
        min_o2 = float(O2_TARAMA[i - 1] + (0.5 - y0) / (y1 - y0) * (O2_TARAMA[i] - O2_TARAMA[i - 1]))
    vf = h["Vf"][0]
    yayilma = None if np.isnan(vf) else (float(vf) * 1000.0 if yanma >= 0.5 else 0.0)
    return {"yanma": yanma, "min_oksijen": min_o2, "yayilma_hizi": yayilma, "sicaklik": float(h["Tf"][0])}


# ------------------------------------------------------------------ veri ve kalibrasyon
def veri_oku():
    import pandas as pd
    parcalar = [pd.read_csv(f) for f in sorted((KOK / "data").glob("psi_labeled*.csv"))]
    d = pd.concat(parcalar, ignore_index=True)
    d = d[d.etiket_kaynagi.isin(["psi", "makale_elle"]) & d.yanar.isin([0, 1])].reset_index(drop=True)
    from risk_model import deney_grubu
    d["aile"] = d.makale_id.map(deney_grubu)
    return d


def satirlar(d):
    sayi = lambda v: None if v != v else float(v)
    return [(sayi(x.g_seviyesi), sayi(x.oksijen_yuzde), sayi(x.basinc_kpa), sayi(x.akis_hizi_cm_s),
             sayi(x.kalinlik_mm), x.malzeme_sade, None if x.numune_tipi != x.numune_tipi else x.numune_tipi,
             None if x.seyreltici != x.seyreltici else x.seyreltici) for x in d.itertuples()]


HIZ_AGIRLIGI = 5.0     # her yayılma ölçümünün (log10)² hatası bu kadar etiket ağırlığında


def kayip(v, a, y, hiz_idx, hiz_log):
    p = param_sozluk(v)
    h = hesap(p, a)
    q = np.clip(h["yanma"], 1e-6, 1 - 1e-6)
    nll = -np.sum(y * np.log(q) + (1 - y) * np.log(1 - q))
    if len(hiz_idx):
        vf = np.clip(h["Vf"][hiz_idx] * 1000.0, 1e-6, None)
        nll += HIZ_AGIRLIGI * np.sum((np.log10(vf) - hiz_log) ** 2)
    return nll


def kalibre_et(d, baslangic_sayisi=6, tohum=0):
    from scipy.optimize import minimize
    rng = np.random.default_rng(tohum)
    # tau_esik grup atamasını etkilediğinden diziler tau_esik'e bağlı; kalınlık eşiği sadece yayılma
    # formülünü seçer (grup numune_tipi'nden gelir), bu yüzden hazırlık bir kez yapılabilir
    a = hazirla(satirlar(d), 1.0)
    y = d.yanar.to_numpy(float)
    hiz = d.get("alev_yayilma_hizi_mm_s")
    hiz_idx = np.nonzero(hiz.notna().to_numpy() & (hiz > 0).to_numpy())[0] if hiz is not None else np.array([], int)
    hiz_log = np.log10(hiz.to_numpy(float)[hiz_idx]) if len(hiz_idx) else np.array([])
    lo = np.array([b[0] for b in SINIRLAR]); hi = np.array([b[1] for b in SINIRLAR])
    en_iyi = None
    for k in range(baslangic_sayisi):
        x0 = np.array(BASLANGIC, float) if k == 0 else lo + rng.random(len(lo)) * (hi - lo)
        r = minimize(kayip, x0, args=(a, y, hiz_idx, hiz_log), method="L-BFGS-B", bounds=SINIRLAR,
                     options={"maxiter": 3000})
        if en_iyi is None or r.fun < en_iyi.fun:
            en_iyi = r
    return en_iyi


def kalibre_main():
    import time
    d = veri_oku()
    t = time.time()
    r = kalibre_et(d)
    p = param_sozluk(r.x)
    cikti = {"vektor": [float(x) for x in r.x], "adlar": PARAM_ADLARI, "parametreler": p,
             "kayip": float(r.fun), "nokta": int(len(d)),
             "yayilma_olcumu": int(d.alev_yayilma_hizi_mm_s.notna().sum()),
             "veri": "psi_labeled*.csv (etiket_kaynagi psi + makale_elle), Gemma verisi kullanılmadı",
             "sabitler": {"T_INF": T_INF, "ALPHA0": ALPHA0, "EPS_YUZEY": EPS_YUZEY, "EPS_ALEV": EPS_ALEV,
                          "L_LEVHA": L_LEVHA, "G_ALT": G_ALT, "HIZ_AGIRLIGI": HIZ_AGIRLIGI},
             "not": "gaz grubu için veri yok: sivi_damla parametreleri kopyalandı (kalibre edilmedi)"}
    PARAM_DOSYASI.write_text(json.dumps(cikti, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Kalibrasyon: {len(d)} nokta, kayıp {r.fun:.1f}, {time.time() - t:.0f} s -> {PARAM_DOSYASI.name}")
    for ad, v in zip(PARAM_ADLARI, r.x):
        print(f"  {ad:22s} {v:10.3f}")


# ------------------------------------------------------------------ doğrulama
AILE_ADI = {"PSI-25": "BASS-II (PSI-25)", "PSI-26": "BASS (PSI-26)", "PSI-69": "FLEX (PSI-69)",
            "SAFFIRE": "Saffire (PSI-98/99/100)"}


def dogrula_main():
    import pandas as pd
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GroupKFold
    import engine as motor_modulu
    d = veri_oku()
    tahmin = np.full(len(d), np.nan)
    hiz = np.full(len(d), np.nan)
    for kat, (eg, te) in enumerate(GroupKFold(n_splits=5).split(d, d.yanar, d.aile)):
        r = kalibre_et(d.iloc[eg].reset_index(drop=True), baslangic_sayisi=4, tohum=kat)
        p = param_sozluk(r.x)
        h = hesap(p, hazirla(satirlar(d.iloc[te]), p["tau_esik_mm"]))
        tahmin[te], hiz[te] = h["yanma"], h["Vf"] * 1000.0
        print(f"  kat {kat + 1}: test aileleri {sorted(d.aile.iloc[te].unique())}")
    d["hafif"], d["hafif_hiz"] = tahmin, hiz
    d["sentetik"] = [motor_modulu._sentetik(*s[:7])["yanma"] for s in satirlar(d)]

    def olc(x, sutun):
        y = x.yanar.to_numpy()
        auc = roc_auc_score(y, x[sutun]) if len(set(y)) == 2 else float("nan")
        return auc, float(((x[sutun] > 0.5).astype(int) == y).mean())

    satir = []
    for ad, x in [("HEPSİ", d)] + [(AILE_ADI.get(a, "makale " + a), x) for a, x in d.groupby("aile")]:
        auc, acc = olc(x, "hafif")
        sauc, sacc = olc(x, "sentetik")
        h = x[x.alev_yayilma_hizi_mm_s.notna() & (x.alev_yayilma_hizi_mm_s > 0) & (x.hafif_hiz > 0)] \
            if "alev_yayilma_hizi_mm_s" in x else x.iloc[:0]
        kat = (10 ** np.abs(np.log10(h.hafif_hiz / h.alev_yayilma_hizi_mm_s))).median() if len(h) else np.nan
        satir.append({"aile": ad, "nokta": len(x), "yanan_orani": x.yanar.mean(), "auc": auc, "dogruluk": acc,
                      "hiz_hata_kati": kat, "hiz_n": len(h), "sentetik_auc": sauc, "sentetik_dogruluk": sacc})
    t = pd.DataFrame(satir)
    pd.set_option("display.width", 200)
    print(t.round(3).to_string(index=False))
    t.to_csv(KOK / "data/light_engine_validation.csv", index=False, encoding="utf-8-sig")
    d[["makale_id", "aile", "malzeme_sade", "numune_tipi", "oksijen_yuzde", "akis_hizi_cm_s", "yanar", "hafif",
       "hafif_hiz", "alev_yayilma_hizi_mm_s"]].to_csv(KOK / "data/light_engine_validation_points.csv", index=False,
                                                     encoding="utf-8-sig")


def u_grafik_main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    p = parametreler()
    akis = np.logspace(-1, 2, 120)
    o2 = np.linspace(10, 40, 121)
    A, O = np.meshgrid(akis, o2)
    s = [(1e-4, float(o), 101.3, float(u), 0.2, "pmma", "thin_sheet", "n2") for o, u in zip(O.ravel(), A.ravel())]
    Z = hesap(p, hazirla(s, p["tau_esik_mm"]))["yanma"].reshape(O.shape)
    fig, ax = plt.subplots(figsize=(7, 4.8))
    c = ax.pcolormesh(A, O, Z, cmap="RdYlBu_r", vmin=0, vmax=1, shading="auto")
    ax.contour(A, O, Z, levels=[0.5], colors="k", linewidths=1.2)
    ax.axhline(21, color="w", ls="--", lw=0.8)
    ax.set_xscale("log")
    ax.set_xlabel("zorlanmış akış [cm/s]"); ax.set_ylabel("oksijen [%]")
    ax.set_title("Hafif motor: PMMA ince levha (0.2 mm), uzay (1e-4 g), 101.3 kPa")
    fig.colorbar(c, label="yanma")
    fig.tight_layout(); fig.savefig(U_PNG, dpi=130)
    satir21 = [(u, motor(1e-4, 21, 101.3, u, 0.2, "pmma", "thin_sheet")["yanma"]) for u in (0.1, 0.3, 1, 3, 10, 30, 100)]
    print("PMMA ince, uzay, %21:", "  ".join(f"{u:g} cm/s -> {y:.2f}" for u, y in satir21))
    print(f"-> {U_PNG.name}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--kalibre", action="store_true")
    ap.add_argument("--dogrula", action="store_true")
    ap.add_argument("--u-grafik", action="store_true")
    k = ap.parse_args()
    if k.kalibre:
        kalibre_main()
    if k.dogrula:
        dogrula_main()
    if k.u_grafik:
        u_grafik_main()
    if not (k.kalibre or k.dogrula or k.u_grafik):
        for ad, g in (("ISS", 1e-4), ("Ay", 0.165), ("Mars", 0.38), ("Dünya", 1.0)):
            print(ad, motor(g, 21, 101.3, 0, 0.2, "pmma", "thin_sheet"))
