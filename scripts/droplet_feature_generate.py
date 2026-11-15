#!/usr/bin/env python3
"""
scripts/droplet_feature_generate.py — scripts/droplet_engine.py için gaz özelliklerini Cantera ile ÖNCEDEN hesaplar.

Sadece bir kez, Cantera kurulu venv'de çalıştırılır:
    .venv_cantera/bin/python scripts/droplet_feature_generate.py
Çıktı: data/droplet_features.json  (scripts/droplet_engine.py çalışırken Cantera'yı import ETMEZ, sadece bunu okur)

İçerik (T ızgarası 250-3000 K, 50 K adım, 1 atm):
  - her tür için viskozite μ_i(T) [Pa s], ısıl iletkenlik λ_i(T) [W/m K], c_p,i(T) [J/kg K], M_i [kg/kmol]
  - ikili difüzyon katsayıları D_ij(T) [m²/s] (1 atm; çalışmada 1/p ile ölçeklenir)
Kinetik teori (Chapman-Enskog, Stockmayer çarpışma integralleri) Cantera'nın "mixture-averaged" modelinden.

Tür parametreleri:
  O2, N2, CO2, H2O, AR, CH3OH : GRI-Mech 3.0 (Cantera gri30.yaml)
  HE                          : Alzueta 2023 (Cantera ammonia-CO-H2-Alzueta-2023.yaml)
  NC7H16, C2H5OH, NC10H22, NC3H7OH : Lennard-Jones parametreleri Tee-Gotoh-Stewart (1966) korelasyonu ile
        ε/k = (0.7915 + 0.1693 ω) Tc ,  σ = (2.3551 - 0.0874 ω) (Tc/Pc[atm])^(1/3) Å
        (kritik veriler: NIST WebBook / Poling-Prausnitz-O'Connell 2001). Kontrol: n-heptan 459.5 K / 6.31 Å
        (LLNL: 459.98 / 6.253), n-dekan 540.2 / 7.16 (LLNL: 540.98 / 7.15).
        c_p(T): NIST ideal gaz değerlerine (yaklaşık, ±%3) 3. derece polinom uydurması.
  XE : ε/k = 231 K, σ = 4.047 Å (Hirschfelder, Curtiss & Bird 1954), c_p = 5/2 R.
"""
import json
from pathlib import Path

import cantera as ct
import numpy as np

KOK = Path(__file__).resolve().parent.parent
CIKTI = KOK / "data/droplet_features.json"
T_IZGARA = np.arange(250.0, 3000.0 + 1, 50.0)
R = 8.314462618

# ad: (bileşim, Tc K, Pc bar, ω, [(T K, c_p J/mol K), ...])
OZEL_YAKIT = {
    "NC7H16": ({"C": 7, "H": 16}, 540.2, 27.4, 0.349,
               [(298, 165.2), (500, 252.0), (800, 342.0), (1000, 376.0), (1500, 430.0), (3000, 480.0)]),
    "C2H5OH": ({"C": 2, "H": 6, "O": 1}, 514.0, 61.4, 0.644,
               [(298, 65.6), (500, 89.0), (800, 114.0), (1000, 126.0), (1500, 143.0), (3000, 160.0)]),
    "NC10H22": ({"C": 10, "H": 22}, 617.7, 21.1, 0.490,
                [(298, 233.1), (500, 354.0), (800, 476.0), (1000, 527.0), (1500, 600.0), (3000, 668.0)]),
    "NC3H7OH": ({"C": 3, "H": 8, "O": 1}, 536.8, 51.7, 0.622,
                [(298, 85.6), (500, 124.0), (800, 160.0), (1000, 177.0), (1500, 202.0), (3000, 226.0)]),
}
TURLER = ["NC7H16", "CH3OH", "C2H5OH", "NC10H22", "NC3H7OH", "O2", "N2", "CO2", "H2O", "HE", "AR", "XE"]


def tee_gotoh(tc, pc_bar, w):
    pc_atm = pc_bar / 1.01325
    return (0.7915 + 0.1693 * w) * tc, (2.3551 - 0.0874 * w) * (tc / pc_atm) ** (1 / 3)


def nasa7_cp(veri):
    T, cp = np.array(veri, float).T
    a = np.polyfit(T, cp / R, 3)[::-1]           # a1 + a2 T + a3 T² + a4 T³
    k = [float(a[0]), float(a[1]), float(a[2]), float(a[3]), 0.0, 0.0, 0.0]
    return k


def ozel_tur(ad):
    bil, tc, pc, w, cp = OZEL_YAKIT[ad]
    eps, sig = tee_gotoh(tc, pc, w)
    k = nasa7_cp(cp)
    d = {"name": ad, "composition": bil,
         "thermo": {"model": "NASA7", "temperature-ranges": [200.0, 1000.0, 3500.0], "data": [k, k]},
         "transport": {"model": "gas", "geometry": "nonlinear", "well-depth": round(eps, 2),
                       "diameter": round(sig, 3), "rotational-relaxation": 1.0}}
    return ct.Species.from_yaml(json.dumps(d)), (eps, sig)


def xe_tur():
    k = [2.5, 0, 0, 0, 0, -745.375, 6.167]
    d = {"name": "XE", "composition": {"Xe": 1},
         "thermo": {"model": "NASA7", "temperature-ranges": [200.0, 1000.0, 6000.0], "data": [k, k]},
         "transport": {"model": "gas", "geometry": "atom", "well-depth": 231.0, "diameter": 4.047}}
    return ct.Species.from_yaml(json.dumps(d))


def main():
    gri = {s.name: s for s in ct.Species.list_from_file("gri30.yaml")}
    alz = {s.name.upper(): s for s in ct.Species.list_from_file("example_data/ammonia-CO-H2-Alzueta-2023.yaml")}
    turler, lj = [], {}
    for ad in TURLER:
        if ad in OZEL_YAKIT:
            s, lj[ad] = ozel_tur(ad)
        elif ad == "XE":
            s = xe_tur()
        elif ad == "HE":
            s = alz["HE"]
        else:
            s = gri[ad]
        turler.append(s)
    gaz = ct.Solution(thermo="ideal-gas", kinetics="none", transport_model="mixture-averaged", species=turler)
    n, nt = len(TURLER), len(T_IZGARA)
    mu, lam, cp = np.zeros((n, nt)), np.zeros((n, nt)), np.zeros((n, nt))
    D = np.zeros((n, n, nt))
    for j, T in enumerate(T_IZGARA):
        gaz.TPX = T, ct.one_atm, {TURLER[0]: 1.0}
        mu[:, j] = gaz.species_viscosities
        D[:, :, j] = gaz.binary_diff_coeffs
        cp[:, j] = gaz.standard_cp_R * R / gaz.molecular_weights * 1000.0
        for i, ad in enumerate(TURLER):
            gaz.TPX = T, ct.one_atm, {ad: 1.0}
            lam[i, j] = gaz.thermal_conductivity
    cikti = {"aciklama": "scripts/droplet_feature_generate.py ile Cantera " + ct.__version__ + " kullanılarak üretildi; "
                          "1 atm saf tür özellikleri ve ikili difüzyon katsayıları",
             "turler": TURLER, "M": [float(x) for x in gaz.molecular_weights],
             "T": T_IZGARA.tolist(),
             "mu": mu.round(10).tolist(), "lam": lam.round(7).tolist(), "cp": cp.round(3).tolist(),
             "D_1atm": D.round(12).tolist(),
             "lj_tee_gotoh": {k: [round(v[0], 2), round(v[1], 3)] for k, v in lj.items()}}
    CIKTI.write_text(json.dumps(cikti), encoding="utf-8")
    # kısa kontrol çıktısı
    i = {a: k for k, a in enumerate(TURLER)}
    j = int(np.argmin(abs(T_IZGARA - 300)))
    for a in ("N2", "HE", "CO2", "NC7H16", "CH3OH"):
        print(f"{a:8s} 300 K: μ {mu[i[a], j]:.3e}  λ {lam[i[a], j]:.4f}  cp {cp[i[a], j]:.0f}  "
              f"D(O2) {D[i[a], i['O2'], j]:.3e}")
    print("LJ (Tee-Gotoh):", cikti["lj_tee_gotoh"])
    print(f"Kaydedildi: {CIKTI.name} ({CIKTI.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
