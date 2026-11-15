#!/usr/bin/env python3
"""Gaz yakıt (gözenekli küre brülör, 1B küresel simetrik) OpenFOAM vakası üreticisi — mikroyerçekimi.

Fiziksel model: yarıçapı r0 olan küre yüzeyinden sabit debiyle yakıt akımı (Flame Design / s-Flame / sızıntı); çevre hava (O2/N2), tek adım yanma
(Westbrook & Dryer 1981, HAFIZADAN), ateşleme kaynağı damlaAtesleme. Ağ, termo ve taşınım damla üreticisiyle (ofm_droplet_case.py) aynı kalıp;
yakıt janaf: GRI-Mech 3.0 (OpenFOAM tutorial), μ ve D: Chapman-Enskog (Lennard-Jones, GRI tran.dat), λ: değiştirilmiş Eucken.
Işınım YOK (OpenFOAM ışınım modeli açılmadı): ışınımla sönme yakalanmaz.
"""
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

import argparse
VERI = Path(__file__).resolve().parent / "ofm_droplet_data"
TABLO = VERI
ap = argparse.ArgumentParser()
ap.add_argument("cikti")
ap.add_argument("--yakit", required=True, help="CH4 C2H6 C3H8 C2H4 C2H2")
ap.add_argument("--d-mm", type=float, default=6.4, help="kure capi mm")
ap.add_argument("--akis", type=float, default=None, help="yakit akimi cikis hizi cm/s")
ap.add_argument("--debi-mg-s", type=float, default=None)
ap.add_argument("--yakit-orani", type=float, default=1.0, help="yakit akiminda yakit mol kesri (kalan N2)")
ap.add_argument("--Q", type=float, required=True, help="net isil deger J/kg")
ap.add_argument("--Tf", type=float, default=298.0, help="kure/yakit akimi sicakligi K")
ap.add_argument("--N", type=int, default=50)
ap.add_argument("--aci", type=float, default=2.5)
ap.add_argument("--bitis", type=float, default=2.0)
ap.add_argument("--dt", type=float, default=0.00001)
ap.add_argument("--T", type=float, default=298.0)
ap.add_argument("--p", type=float, default=101325.0)
ap.add_argument("--x-o2", type=float, default=0.21)
a_ = ap.parse_args()
cikti = Path(a_.cikti).resolve()
N, ACI, BITIS = a_.N, a_.aci, a_.bitis
YAKIT_ID = a_.yakit
D0 = a_.d_mm / 1000.0
R0 = 0.5 * D0
R = 60 * R0
P = a_.p
KIP, CAP, KUCULEN = "yanan", "sabit", False
GY = json.loads((VERI / "gaz_yakitlar.json").read_text(encoding="utf-8"))
if YAKIT_ID not in GY["yakitlar"]:
    raise SystemExit(f"gaz yakiti {YAKIT_ID} tabloda yok: {sorted(GY['yakitlar'])}")
YY = dict(GY["yakitlar"][YAKIT_ID])
YY["Q"] = a_.Q
kin = json.loads((VERI / "damla_kinetik.json").read_text(encoding="utf-8"))
T_INF = a_.T
X_INF = {"O2": a_.x_o2, "N2": 1.0 - a_.x_o2}
TURLER = [YAKIT_ID, "O2", "N2", "CO2", "H2O"]
A_SI = YY["A_cgs"] * 1000.0 ** (1 - YY["a"] - YY["b"])
TA = YY["Ea_cal"] / 1.987204
at = kin["atesleme"]
T_ATES, T_ATES_K, R_ATES, W_ATES, TAU_ATES = at["t"], at["T"], at["r_r0"], at["w_r0"], at["tau"]
TL0 = 300.0                      # DM:1223
P0 = 101325.0                    # DM:63
R_U = 8314.462618                # DM:61
DT = a_.dt
Tf = a_.Tf

oz = json.loads((TABLO / "damla_ozellikleri.json").read_text(encoding="utf-8"))
TT = np.array(oz["T"])


def _cpR(a_lo, a_hi, T):
    a = a_lo if T <= 1000.0 else a_hi
    return a[0] + a[1] * T + a[2] * T ** 2 + a[3] * T ** 3 + a[4] * T ** 4


def _om_mu(Ts):
    return 1.16145 * Ts ** -0.14874 + 0.52487 * math.exp(-0.7732 * Ts) + 2.16178 * math.exp(-2.43787 * Ts)


def _om_d(Ts):
    return (1.06036 * Ts ** -0.1561 + 0.193 * math.exp(-0.47635 * Ts) + 1.03587 * math.exp(-1.52996 * Ts)
            + 1.76474 * math.exp(-3.89411 * Ts))


def gaz_yakit_ekle(oz, ad, g):
    """Gaz yakitini ozellik tablosuna ekler: cp (GRI janaf), mu (Chapman-Enskog), lam (Eucken), D_1atm (Chapman-Enskog; 1 atm, m2/s)."""
    Mw, Rs = g["M"], R_U / g["M"]
    TTl = list(oz["T"])
    cp = [Rs * _cpR(g["low"], g["high"], T) for T in TTl]
    mu = [2.6693e-6 * math.sqrt(Mw * T) / (g["sigma_A"] ** 2 * _om_mu(T / g["eps_K"])) for T in TTl]
    lam = [m * (c + 1.25 * Rs) for m, c in zip(mu, cp)]
    mix = GY["lj_ortam"]
    n_old = len(oz["turler"])
    Dyeni = []
    for j, tj in enumerate(oz["turler"]):
        if tj in mix:
            sg = 0.5 * (g["sigma_A"] + mix[tj]["sigma_A"])
            ep = math.sqrt(g["eps_K"] * mix[tj]["eps_K"])
            Mj = oz["M"][j]
            Dyeni.append([1.0e-4 * 0.001858 * T ** 1.5 * math.sqrt(1.0 / Mw + 1.0 / Mj) / (sg ** 2 * _om_d(T / ep)) for T in TTl])
        else:
            Dyeni.append([0.0] * len(TTl))
    for j in range(n_old):
        oz["D_1atm"][j].append(Dyeni[j])
    oz["D_1atm"].append(Dyeni + [[0.0] * len(TTl)])
    oz["turler"].append(ad)
    oz["M"].append(Mw)
    oz["cp"].append(cp)
    oz["mu"].append(mu)
    oz["lam"].append(lam)


gaz_yakit_ekle(oz, YAKIT_ID, YY)
ti = {t: k for k, t in enumerate(oz["turler"])}
M = {t: oz["M"][ti[t]] for t in TURLER}

Mf, MN2 = YY["M"], M["N2"]
xf = a_.yakit_orani
Ystr = np.zeros(len(TURLER))
Ystr[0] = xf * Mf / (xf * Mf + (1 - xf) * MN2)
Ystr[TURLER.index("N2")] = 1.0 - Ystr[0]
Mstr = xf * Mf + (1 - xf) * MN2
rho_str = P * Mstr / (R_U * Tf)
if a_.akis is not None:
    U_IN = a_.akis / 100.0
elif a_.debi_mg_s is not None:
    U_IN = (a_.debi_mg_s * 1.0e-6) / (4 * math.pi * R0 ** 2) / rho_str
else:
    raise SystemExit("--akis ya da --debi-mg-s gerekli")
MDOT = U_IN * rho_str * 4 * math.pi * R0 ** 2

# alev yarıçapı tahmini (Irace vd. 2021 Eş. 8, küre): R_f = mdot / (4 pi rhoD ln(1/(1-Z_st))), rhoD ~ rho0 D0 sqrt(T_ch/298)
nu_str = xf * YY["nO2"] * 31.999 / Mstr                       # kg O2 / kg yakit akimi
Zst = 1.0 / (1.0 + nu_str / (X_INF["O2"] * 31.999 / (X_INF["O2"] * 31.999 + X_INF["N2"] * M["N2"])))
RHOD = 1.2 * 2.0e-5 * math.sqrt((298.0 + 2200.0) / 2.0 / 298.0)
RF_TAHMIN = MDOT / (4 * math.pi * RHOD * math.log(1.0 / (1.0 - Zst)))
if 0.8 * RF_TAHMIN > 2.5 * R0:
    LD = (0.8 * RF_TAHMIN - R0) / math.log(1.0 / Zst)
    R_IGN = 0.8 * RF_TAHMIN
else:
    LD, R_IGN = 0.3 * R0, 2.5 * R0
W_IGN = max(0.8 * R0, 0.6 * LD)
yakit_sozluk = None


def f(x):
    """düz ondalık"""
    return np.format_float_positional(float(x), unique=True, trim="-")


def fl(xs):
    return "(" + " ".join(f(x) for x in xs) + ")"


def yaz(yol, metin):
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    tmp = yol.with_name(yol.name + ".tmp")
    tmp.write_text(metin, encoding="utf-8")
    os.replace(tmp, yol)


def baslik(sinif, nesne, konum=None):
    k = f'    location    "{konum}";\n' if konum else ""
    return ("FoamFile\n{\n    format      ascii;\n"
            f"    class       {sinif};\n{k}    object      {nesne};\n}}\n\n")


# ------------------------------------------------------------------ ağ
eta = np.linspace(0, 1, N + 1)
xi = (np.exp(6.5 * eta) - 1) / (np.exp(6.5) - 1)
rf = R0 + (R - R0) * xi
t = math.tan(math.radians(ACI))
kose = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
pts = np.array([[r, sy * r * t, sz * r * t] for r in rf for sy, sz in kose])


def merkez(ids):
    return pts[ids].mean(0)


def normal(ids):
    p = pts[ids]
    return np.cross(p[1] - p[0], p[2] - p[0]) + np.cross(p[2] - p[0], p[3] - p[0])


def hucre_merkez(i):
    return pts[4 * i:4 * i + 8].mean(0)


def yonlu(ids, hucre):
    """yüz normali sahip hücreden dışarı baksın"""
    if np.dot(normal(ids), merkez(ids) - hucre_merkez(hucre)) < 0:
        ids = [ids[0]] + ids[1:][::-1]
    return ids


faces, owner, neigh = [], [], []
for i in range(1, N):
    faces.append(yonlu([4 * i + c for c in range(4)], i - 1))
    owner.append(i - 1)
    neigh.append(i)
patches = []
patches.append(("damla", "patch", [(yonlu([c for c in range(4)], 0), 0)]))
patches.append(("dis", "patch", [(yonlu([4 * N + c for c in range(4)], N - 1), N - 1)]))
# yan yüzler: köşe çiftleri (0,3) y-, (1,2) y+, (0,1) z-, (3,2) z+
for ad, (a, b) in [("yan_ym", (0, 3)), ("yan_yp", (1, 2)), ("yan_zm", (0, 1)), ("yan_zp", (3, 2))]:
    lst = []
    for i in range(N):
        ids = [4 * i + a, 4 * i + b, 4 * (i + 1) + b, 4 * (i + 1) + a]
        lst.append((yonlu(ids, i), i))
    patches.append((ad, "symmetryPlane", lst))

bnd = []
for ad, tip, lst in patches:
    bnd.append((ad, tip, len(faces), len(lst)))
    for ids, o in lst:
        faces.append(ids)
        owner.append(o)

pm = cikti / "constant" / "fluid" / "polyMesh"
nota = f'    note        "nPoints:{len(pts)} nCells:{N} nFaces:{len(faces)} nInternalFaces:{N - 1}";\n'
yaz(pm / "points", baslik("vectorField", "points") + f"{len(pts)}\n(\n"
    + "".join(f"({f(p[0])} {f(p[1])} {f(p[2])})\n" for p in pts) + ")\n")
yaz(pm / "faces", baslik("faceList", "faces") + f"{len(faces)}\n(\n"
    + "".join(f"4({' '.join(map(str, q))})\n" for q in faces) + ")\n")
yaz(pm / "owner", baslik("labelList", "owner").replace("}\n\n", nota + "}\n\n", 1)
    + f"{len(owner)}\n(\n" + "".join(f"{o}\n" for o in owner) + ")\n")
yaz(pm / "neighbour", baslik("labelList", "neighbour").replace("}\n\n", nota + "}\n\n", 1)
    + f"{len(neigh)}\n(\n" + "".join(f"{o}\n" for o in neigh) + ")\n")
yaz(pm / "boundary", baslik("polyBoundaryMesh", "boundary") + f"{len(bnd)}\n(\n"
    + "".join(f"    {ad}\n    {{\n        type {tip};\n        nFaces {n};\n        startFace {s};\n    }}\n"
              for ad, tip, s, n in bnd) + ")\n")

# ------------------------------------------------------------------ termo uydurma
rapor = []


def janaf(cp, Mw, hf=0.0):
    """cp [J/kg/K] tablosu → janaf 7+7 katsayı (Tcommon 1000). a5, a6 süreklilikten."""
    Rs = R_U / Mw
    y = cp / Rs
    out = {}
    for ad, m in (("low", TT <= 1000.0), ("high", TT >= 1000.0)):
        A = np.vstack([TT[m] ** k for k in range(5)]).T
        out[ad] = np.linalg.lstsq(A, y[m], rcond=None)[0]
    lo, hi = out["low"], out["high"]

    def H(a, T):   # H/R (a5 hariç)
        return sum(a[k] * T ** (k + 1) / (k + 1) for k in range(5))

    def S(a, T):   # S/R (a6 hariç)
        return a[0] * math.log(T) + sum(a[k] * T ** k / k for k in range(1, 5))

    # ha(298.15) = hf: yanmada yakıt hf = Q, diğerleri 0 (SPEC §4d); yanmasızda hf 0
    a5l, a6l = hf / Rs - H(lo, 298.15), 0.0
    a5h = H(lo, 1000.0) + a5l - H(hi, 1000.0)
    a6h = S(lo, 1000.0) - S(hi, 1000.0)
    low = list(lo) + [a5l, a6l]
    high = list(hi) + [a5h, a6h]

    def cpfit(T):
        a = lo if T <= 1000 else hi
        return Rs * sum(a[k] * T ** k for k in range(5))
    hata = max(abs(cpfit(T) - c) / c for T, c in zip(TT, cp) if T <= 1500)
    return low, high, hata


def sutherland(mu):
    """mu = As sqrt(T)/(1 + Ts/T): sqrt(T)/mu = (1/As) + (Ts/As)/T, 250-1500 K"""
    m = TT <= 1500.0
    A = np.vstack([np.ones(m.sum()), 1.0 / TT[m]]).T
    c = np.linalg.lstsq(A, np.sqrt(TT[m]) / mu[m], rcond=None)[0]
    As, Ts = 1.0 / c[0], c[1] / c[0]
    mufit = As * np.sqrt(TT) / (1 + Ts / TT)
    return As, Ts, max(abs(mufit[m] - mu[m]) / mu[m])


termo = []
for tur in TURLER:
    k = ti[tur]
    cp = np.array(oz["cp"][k])
    mu = np.array(oz["mu"][k])
    lam = np.array(oz["lam"][k])
    hf = YY["Q"] if (KIP == "yanan" and tur == YAKIT_ID) else 0.0
    low, high, hcp = janaf(cp, M[tur], hf)
    As, Ts, hmu = sutherland(mu)
    # OpenFOAM sutherland kappa: mu Cv (1.32 + 1.77 R/Cv) (değiştirilmiş Eucken)
    Rs = R_U / M[tur]
    sat = []
    for Tq in (300.0, 500.0, 800.0):
        j = int(round((Tq - TT[0]) / (TT[1] - TT[0])))
        cv = cp[j] - Rs
        muf = As * math.sqrt(Tq) / (1 + Ts / Tq)
        kap = muf * cv * (1.32 + 1.77 * Rs / cv)
        sat.append(f"{Tq:.0f} K: kappa_OF {kap:.5f} tablo {lam[j]:.5f} oran {kap / lam[j]:.3f}")
    rapor.append(f"{tur}: cp uyum en büyük bağıl hata (250-1500 K) {hcp:.5f}; mu uyum {hmu:.5f}; As {f(As)} Ts {f(Ts)}")
    rapor.append("    " + "; ".join(sat))
    termo.append(f"""{tur}
{{
    specie
    {{
        molWeight       {f(M[tur])};
    }}
    thermodynamics
    {{
        Tlow            250;
        Thigh           3000;
        Tcommon         1000;
        highCpCoeffs    {fl(high)};
        lowCpCoeffs     {fl(low)};
    }}
    transport
    {{
        As              {f(As)};
        Ts              {f(Ts)};
    }}
}}
""")

cf = cikti / "constant" / "fluid"
yaz(cf / "physicalProperties", baslik("dictionary", "physicalProperties", "constant/fluid") + f"""thermoType
{{
    type            heRhoThermo;
    mixture         coefficientWilkeMulticomponentMixture;
    transport       sutherland;
    thermo          janaf;
    energy          sensibleEnthalpy;
    equationOfState perfectGas;
    specie          specie;
}}

defaultSpecie N2;

species ({' '.join(TURLER)});

// janaf / sutherland katsayıları testler/vaka_uret.py ile damla_ozellikleri.json'dan uyduruldu
""" + "\n".join(termo))

# ikili D: uniformTable (p, T); satır p, sütun T
plo, phi_ = 90000.0, 115000.0
Dsat = []
for a in range(len(TURLER)):
    for b in range(a, len(TURLER)):
        ad = f"{TURLER[a]}-{TURLER[b]}"
        if a == b:
            Dsat.append(f"        {ad} 0;\n")
            continue
        D1 = np.array(oz["D_1atm"][ti[TURLER[a]]][ti[TURLER[b]]])
        sat1 = fl(D1 * P0 / plo)
        sat2 = fl(D1 * P0 / phi_)
        Dsat.append(f"""        {ad}
        {{
            type    uniformTable;
            low     ({f(plo)} {f(TT[0])});
            high    ({f(phi_)} {f(TT[-1])});
            values  2 {len(TT)}
            (
                {sat1}
                {sat2}
            );
        }}
""")
yaz(cf / "thermophysicalTransport", baslik("dictionary", "thermophysicalTransport", "constant/fluid") + """laminar
{
    model                         FickianFourier;
    mixtureDiffusionCoefficients  no;

    // D_ij = D_1atm(T) P0/p (DM:200-201), damla_ozellikleri.json
    D
    {
""" + "".join(Dsat) + """    }
}
""")
yaz(cf / "momentumTransport", baslik("dictionary", "momentumTransport", "constant/fluid") + "simulationType laminar;\n")
yaz(cf / "fvModels", baslik("dictionary", "fvModels", "constant/fluid") + f"""atesleme
{{
    type            damlaAtesleme;
    libs            ("libFlameInFreefallDroplet.so");
    // DM:1164 T_ATES, T_ATES_K, R_ATES r0, W_ATES r0, TAU_ATES
    tAtes           {f(T_ATES)};
    TAtes           {f(T_ATES_K)};
    rAtes           {f(R_IGN)};
    wAtes           {f(W_IGN)};
    tau             {f(TAU_ATES)};
}}
""")
if KUCULEN:
    yaz(cf / "dynamicMeshDict", baslik("dictionary", "dynamicMeshDict", "constant/fluid") + """mover
{
    type            damlaIzgaraHareketi;
    libs            ("libFlameInFreefallDroplet.so");
    d0              """ + f(D0) + """;
    merkez          (0 0 0);
}
""")
if T_ATES_K is not None:
    yaz(cf / "reactionProperties", baslik("dictionary", "reactionProperties", "constant/fluid") + "reactionModel laminar;\n")
    yaz(cf / "chemistryProperties", baslik("dictionary", "chemistryProperties", "constant/fluid") + """chemistryType
{
    solver          ode;
}
chemistry       on;
initialChemicalTimeStep 0.0000001;
ode
{
    solver          seulex;
    absTol          0.00000001;
    relTol          0.01;
}
#include "reactions"
""")
    yaz(cf / "reactions", baslik("dictionary", "reactions", "constant/fluid") + f"""// Westbrook-Dryer tek adım (DM:1188-1189, DM:1336); A SI kmol/m3/s, Ta parametre kümesinden
reactions
{{
    tekAdim
    {{
        type     irreversibleArrhenius;
        reaction "{YAKIT_ID}^{f(YY['a'])} + {f(YY['nO2'])}O2^{f(YY['b'])} = {f(YY['nC'])}CO2 + {f(YY['nH'] / 2)}H2O";
        A        {f(A_SI)};
        beta     0;
        Ta       {f(TA)};
    }}
}}

Tlow    250;
Thigh   3000;
""")

# ------------------------------------------------------------------ system
sy = cikti / "system"
yaz(sy / "controlDict", baslik("dictionary", "controlDict", "system") + f"""libs ("libFlameInFreefallDroplet.so");

regionSolvers
{{
    fluid           multicomponentFluid;
}}

startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {f(BITIS)};
deltaT          {f(DT)};
writeControl    adjustableRunTime;
writeInterval   0.1;
purgeWrite      0;
writeFormat     ascii;
writePrecision  12;
writeCompression off;
timeFormat      general;
timePrecision   8;
runTimeModifiable false;
adjustTimeStep  no;

functions
{{
    gazMax
    {{
        type            volFieldValue;
        libs            ("libfieldFunctionObjects.so");
        region          fluid;
        writeControl    timeStep;
        writeInterval   200;
        writeFields     no;
        cellZone        all;
        operation       max;
        fields          (T);
    }}
}}
""")
yaz(sy / "fvSolution", baslik("dictionary", "fvSolution", "system") + "PIMPLE\n{\n    nOuterCorrectors 1;\n}\n")
yaz(sy / "fluid" / "fvSchemes", baslik("dictionary", "fvSchemes", "system/fluid") + """ddtSchemes
{
    default         Euler;
}
gradSchemes
{
    default         Gauss linear;
}
divSchemes
{
    default         none;
    div(phi,U)      Gauss limitedLinearV 1;
    div(phi,Yi_h)   Gauss limitedLinear 1;
    div(phi,K)      Gauss limitedLinear 1;
    div(phi,(p|rho)) Gauss linear;
    div(rho*nuEff*dev2(T(grad(U)))) Gauss linear;
}
laplacianSchemes
{
    default         Gauss linear corrected;
}
interpolationSchemes
{
    default         linear;
}
snGradSchemes
{
    default         corrected;
}
""")
yaz(sy / "fluid" / "fvSolution", baslik("dictionary", "fvSolution", "system/fluid") + """solvers
{
    "rho.*"
    {
        solver          diagonal;
    }
    "p.*"
    {
        solver          PCG;
        preconditioner  DIC;
        tolerance       0.000000000001;
        relTol          0;
        minIter         1;
    }
    "(U|h|Yi).*"
    {
        solver          PBiCGStab;
        preconditioner  DILU;
        tolerance       0.000000000001;
        relTol          0;
        minIter         1;
    }
}
PIMPLE
{
    momentumPredictor yes;
    nOuterCorrectors  1;
    nCorrectors       2;
    nNonOrthogonalCorrectors 0;
}
""")

# ------------------------------------------------------------------ 0/fluid (DM:1210-1223)
rc = 0.5 * (rf[1:] + rf[:-1])
XinfV = np.array([X_INF.get(tt, 0.0) for tt in TURLER])
Mv = np.array([M[tt] for tt in TURLER])
Yinf = XinfV * Mv / (XinfV * Mv).sum()
YF = np.exp(-(rc - R0) / LD)
Yc = Yinf[:, None] * (1 - YF)[None, :] + Ystr[:, None] * YF[None, :]
Yfs0 = Ystr[0]

yanlar = "".join(f"    {ad}\n    {{\n        type symmetryPlane;\n    }}\n" for ad in ("yan_ym", "yan_yp", "yan_zm", "yan_zp"))


def alan(ad, sinif, boyut, ic, damla, dis):
    return (baslik(sinif, ad, "0/fluid") + f"dimensions {boyut};\n\ninternalField {ic};\n\n"
            "boundaryField\n{\n" + f"    damla\n    {{\n{damla}    }}\n    dis\n    {{\n{dis}    }}\n" + yanlar + "}\n")


def nonuni(v):
    return f"nonuniform List<scalar>\n{len(v)}\n(\n" + "".join(f"{f(x)}\n" for x in v) + ")"


z = cikti / "0" / "fluid"
Tic = f"uniform {f(T_INF)}"   # DM:1215
yaz(z / "T", alan("T", "volScalarField", "[0 0 0 1 0 0 0]", Tic,
                  f"        type fixedValue;\n        value uniform {f(Tf)};\n",
                  f"        type fixedValue;\n        value uniform {f(T_INF)};\n"))
yaz(z / "U", alan("U", "volVectorField", "[0 1 -1 0 0 0 0]", "uniform (0 0 0)",
                  f"        type surfaceNormalFixedValue;\n        refValue uniform {f(-U_IN)};\n",
                  "        type pressureInletOutletVelocity;\n        value uniform (0 0 0);\n"))
yaz(z / "p", alan("p", "volScalarField", "[1 -1 -2 0 0 0 0]", f"uniform {f(P)}",
                  "        type zeroGradient;\n",
                  f"        type fixedValue;\n        value uniform {f(P)};\n"))
for k, tur in enumerate(TURLER):
    yaz(z / tur, alan(tur, "volScalarField", "[0 0 0 0 0 0 0]", nonuni(Yc[k]),
                      f"        type fixedValue;\n        value uniform {f(Ystr[k])};\n",
                      f"        type fixedValue;\n        value uniform {f(Yinf[k])};\n"))

yaz(cikti / "hucre_r.json", json.dumps({"r0_m": R0, "R_m": R, "rc_m": [float(x) for x in rc], "mdot_kg_s": MDOT, "u_in_m_s": U_IN, "yakit": YAKIT_ID}))
rapor.insert(0, f"gaz vaka {cikti}: N {N}, yarım açı {ACI} derece, r0 {f(R0)} m, R {f(R)} m, "
                f"ilk hücre {f(rf[1] - rf[0])} m, bitiş {BITIS} s, dt {f(DT)} s")
rapor.insert(1, f"Y_inf: " + ", ".join(f"{tt} {Yinf[k]:.6f}" for k, tt in enumerate(TURLER))
             + f"; yakit akimi Y_F {Yfs0:.6f}, cikis hizi {U_IN:.6f} m/s, debi {MDOT * 1e6:.4f} mg/s; alev yaricapi tahmini {RF_TAHMIN * 1e3:.2f} mm, ateşleme r {R_IGN * 1e3:.2f} mm")
yaz(cikti / "vaka_uret_rapor.txt", "\n".join(rapor) + "\n")
print("\n".join(rapor))
