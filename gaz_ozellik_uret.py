#!/usr/bin/env python3
"""
gaz_ozellik_uret.py — gaz_motoru.py için gaz özelliklerini Cantera ile ÖNCEDEN hesaplar (bir kez).

Çalışma anında Cantera YOK: gaz_motoru.py yalnız numpy + gaz_ozellikleri.json kullanır.
Bu betik Cantera'lı ayrı bir venv'de çalıştırıldı (sistem python3'üne Cantera kurulmadı):
    python3 -m venv <yer>/venv_cantera && <yer>/venv_cantera/bin/pip install cantera
    <yer>/venv_cantera/bin/python gaz_ozellik_uret.py

İçerik:
  1) Tür tabloları (T = 250..3500 K, 50 K): c_p [J/kg K], h [J/kg, oluşum entalpisi dahil, 298 K referans],
     μ [Pa s], λ [W/m K] (saf tür), ikili D_ij [m²/s, 1 atm; çalışmada 1/p].
     Türler ve parametreler: CH4, C2H4, C2H6, C3H8, H2, O2, N2, CO2, H2O, AR : GRI-Mech 3.0 (gri30.yaml)
                            HE : termodinamik nasa_gas.yaml (NASA Glenn, McBride ve ark. 2002); taşınım için
                          Lennard-Jones ε/k = 10.2 K, σ = 2.576 Å (Chemkin taşınım veritabanı, Kee ve ark.;
                          gri30'daki AR/N2 değerleriyle aynı kaynak)
  2) Ayrışma düzeltmesi: stokiyometrik difüzyon alevi karışımı (Z = Z_st) için
        T_tam  = tam yanma (yalnız CO2, H2O + inertler) adyabatik sıcaklığı,
        T_den  = Cantera HP kimyasal dengesi (GRI 3.0 türleri + HE),
     farkı ΔT = T_tam - T_den, (T_tam, log10 p) ızgarasında ortalanır -> çalışma anında
     T_ad = T_tam - ΔT(T_tam, p). Yakıt (5), yakıt seyrelticisi (N2/He), X_O2 (7), ortam seyrelticisi
     (N2/He/CO2/Ar), basınç (4) taranır; artıklar json'a yazılır.
"""
import itertools
import json
import math
import time
from pathlib import Path

import cantera as ct
import numpy as np

KOK = Path(__file__).resolve().parent
CIKTI = KOK / "gaz_ozellikleri.json"
T_IZGARA = np.arange(250.0, 3500.0 + 1, 50.0)
TURLER = ["CH4", "C2H4", "C2H6", "C3H8", "H2", "O2", "N2", "CO2", "H2O", "HE", "AR"]
YAKITLAR = ["CH4", "C2H4", "C2H6", "C3H8", "H2"]
T0 = 298.15


def gaz_kur():
    gri = ct.Solution("gri30.yaml")
    nasa = ct.Species.list_from_file("nasa_gas.yaml")
    he0 = [s for s in nasa if s.name.upper() == "HE"][0]
    he = ct.Species("HE", {"He": 1})
    he.thermo = he0.thermo
    he.transport = ct.GasTransportData()
    he.transport.set_customary_units("atom", 2.576, 10.2)      # Å, K (yapıcı SI bekler: m, J)
    turler = [s for s in ct.Species.list_from_file("gri30.yaml")] + [he]
    g = ct.Solution(thermo="ideal-gas", kinetics="none", species=turler, transport_model="mixture-averaged")
    return g


def tablolar(g):
    ns, nT = len(TURLER), len(T_IZGARA)
    cp, h, mu, lam = (np.zeros((ns, nT)) for _ in range(4))
    D = np.zeros((ns, ns, nT))
    idx = [g.species_index(t) for t in TURLER]
    for j, T in enumerate(T_IZGARA):
        for k, t in enumerate(TURLER):
            g.TPX = T, ct.one_atm, {t: 1.0}
            cp[k, j] = g.cp_mass
            h[k, j] = g.enthalpy_mass
            mu[k, j] = g.viscosity
            lam[k, j] = g.thermal_conductivity
        # ikili difüzyon: eşit karışımda (ikili D bileşime bağlı değil)
        g.TPX = T, ct.one_atm, {t: 1.0 for t in TURLER}
        Bd = g.binary_diff_coeffs
        D[:, :, j] = Bd[np.ix_(idx, idx)]
    M = [float(g.molecular_weights[i]) for i in idx]
    return M, cp, h, mu, lam, D


def akislar(yakit, Xf, yseyr, XO2, oseyr):
    """yakıt akımı (yakıt + seyreltici) ve oksitleyici akımı (O2 + seyreltici) mol oranları."""
    F = {yakit: Xf}
    if Xf < 1:
        F[yseyr] = F.get(yseyr, 0) + 1 - Xf
    O = {"O2": XO2, oseyr: 1 - XO2}
    return F, O


def zst_karisim(g, F, O):
    """Z_st ve stokiyometrik karışımın mol oranları (iki akım 298 K)."""
    g.TPX = T0, ct.one_atm, F
    YF, MF = g.mass_fraction_dict(), g.mean_molecular_weight
    g.TPX = T0, ct.one_atm, O
    YO, MO = g.mass_fraction_dict(), g.mean_molecular_weight
    nu_O2 = 0.0     # kg O2 / kg yakıt akımı
    for t, y in YF.items():
        if t in YAKITLAR:
            sp = g.species(t)
            nC, nH = sp.composition.get("C", 0), sp.composition.get("H", 0)
            nu_O2 += y * (nC + nH / 4) * 31.998 / g.molecular_weights[g.species_index(t)]
    Zst = 1.0 / (1.0 + nu_O2 / YO["O2"])
    Y = {}
    for t, y in YF.items():
        Y[t] = Y.get(t, 0) + Zst * y
    for t, y in YO.items():
        Y[t] = Y.get(t, 0) + (1 - Zst) * y
    return Zst, Y


def tam_urunler(g, Y):
    """stokiyometrik karışımın tam yanma ürünleri (kütle kesri)."""
    g.TPY = T0, ct.one_atm, Y
    X = g.mole_fraction_dict()
    n = {}
    for t, x in X.items():
        if t in YAKITLAR:
            c = g.species(t).composition
            n["CO2"] = n.get("CO2", 0) + x * c.get("C", 0)
            n["H2O"] = n.get("H2O", 0) + x * c.get("H", 0) / 2
        elif t != "O2":
            n[t] = n.get(t, 0) + x
    return n


def denge_taramasi(g_tr):
    gq = ct.Solution(thermo="ideal-gas", kinetics="none", species=g_tr.species())
    kayit = []
    for yakit, Xf, yseyr, XO2, oseyr, p in itertools.product(
            YAKITLAR, [1.0, 0.5, 0.25, 0.12], ["N2", "HE"], [0.15, 0.18, 0.21, 0.25, 0.30, 0.40, 0.50],
            ["N2", "HE", "CO2", "AR"], [0.3, 0.56, 1.0, 2.0]):
        if Xf == 1.0 and yseyr == "HE":
            continue
        F, O = akislar(yakit, Xf, yseyr, XO2, oseyr)
        Zst, Y = zst_karisim(gq, F, O)
        P = p * ct.one_atm
        gq.TPY = T0, P, Y
        H = gq.enthalpy_mass
        n = tam_urunler(gq, Y)
        gq.TPX = 1500.0, P, n
        gq.HP = H, P
        T_tam = gq.T
        gq.TPY = T0, P, Y
        gq.equilibrate("HP")
        kayit.append(dict(yakit=yakit, Xf=Xf, yseyr=yseyr, XO2=XO2, oseyr=oseyr, p_atm=p, Zst=Zst,
                          T_tam=T_tam, T_den=gq.T))
    return kayit


def ayrisma_tablosu(kayit):
    Tt = np.array([k["T_tam"] for k in kayit])
    dT = np.array([k["T_tam"] - k["T_den"] for k in kayit])
    lp = np.log10([k["p_atm"] for k in kayit])
    # ΔT = (a0 + a1 log10 p) x² / (1 + b0 x),  x = max(T_tam - T1, 0): T1, b0 ızgarada, a0/a1 en küçük kareler
    en = None
    for T1 in np.arange(1000.0, 2001.0, 20.0):
        x = np.clip(Tt - T1, 0, None)
        for b0 in np.geomspace(1e-5, 1e-1, 60):
            f = x ** 2 / (1 + b0 * x)
            A = np.c_[f, f * lp]
            a, *_ = np.linalg.lstsq(A, dT, rcond=None)
            e = float(np.sum((A @ a - dT) ** 2))
            if en is None or e < en[0]:
                en = (e, T1, b0, a)
    _, T1, b0, a = en
    x = np.clip(Tt - T1, 0, None)
    art = (a[0] + a[1] * lp) * x ** 2 / (1 + b0 * x) - dT
    return {"bicim": "dT = (a0 + a1 log10 p_atm) x^2 / (1 + b0 x),  x = max(T_tam - T1, 0)",
            "T1": float(T1), "a0": float(a[0]), "a1": float(a[1]), "b0": float(b0),
            "artik_ort_mutlak_K": float(np.mean(np.abs(art))), "artik_maks_K": float(np.max(np.abs(art))),
            "n": int(len(kayit))}


def main():
    bas = time.time()
    g = gaz_kur()
    M, cp, h, mu, lam, D = tablolar(g)
    print(f"tablolar: {time.time() - bas:.1f} s")
    kayit = denge_taramasi(g)
    ay = ayrisma_tablosu(kayit)
    print(f"denge: {len(kayit)} nokta, {time.time() - bas:.1f} s; ayrışma uydurması {ay}")
    out = {"aciklama": __doc__.strip().splitlines()[0], "cantera": ct.__version__,
           "turler": TURLER, "M": M, "T": T_IZGARA.tolist(),
           "cp": cp.tolist(), "h": h.tolist(), "mu": mu.tolist(), "lam": lam.tolist(), "D_1atm": D.tolist(),
           "ayrisma": ay, "denge_kayitlari": kayit}
    CIKTI.write_text(json.dumps(out), encoding="utf-8")
    print("yazıldı:", CIKTI, f"{CIKTI.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
