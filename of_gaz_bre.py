#!/usr/bin/env python3
"""
of_gaz_bre.py — gaz motoru doğrulaması: ISS BRE deneyleri (Dehghani ve ark. 2021, CNF 228:315, Tablo 2; 59 test).
PİLOT AŞAMASI — OpenFOAM'un BRE'deki kendiliğinden sönmeyi (SE) yakalayıp yakalayamadığı ve koşu süresi sınanıyor.

Deney: 25 mm gözenekli düz brülör, C2H4/N2 yakıt karışımı (X_f), ortam O2/N2 (X_O2), basınç p, mikro yerçekimi.
  FT = akış kesildi (alev t_b boyunca kararlı yandı)  -> yandı = 1
  SE = kendiliğinden söndü (çoğunlukla ışınım kaybıyla) -> yandı = 0

Vaka (OpenFOAM 14, multicomponentFluid, counterFlowFlame2D tabanlı):
  - Eksenel simetrik 2B kama (5°), eksen y; r 0-150 mm, y 0-200 mm; brülör r < 12,5 mm (0,5 mm hücre), dışı
    derecelendirilmiş. g = 0 (p, p_rgh yok).
  - Taban: brülör (yakıt karışımı, U = m'' / rho, 300 K), çevresi duvar (300 K). Yan ve üst: açık (totalPressure).
  - Kimya: tek adım etilen, Westbrook & Dryer 1981: C2H4^0.1 + 3 O2^1.65 -> 2 CO2 + 2 H2O,
    A = 2,0e12 [(mol/cm^3)^-0,75/s], Ea = 30 kcal/mol (Ta = 15098 K). Laminer. seulex eps 0,05; hız sabitinde
    Tlow 200 / Thigh 5000 sınırı (yoksa tutuşmada ODE ara adımında T < 0 -> exp taşması -> SIGFPE).
  - Işınım: P1 + greyMeanReaction (CO2, H2O; is yok). EhrrCoeff = 0 (varsayılan): ışınım kesri kalibre EDİLMEZ;
    --xr ile ısı salımının bir kesri ışınım kaybı olarak eklenebilir (BRE'de is ışınımı baskın: ölçülen X_r 0,3-0,6;
    yalnız gaz ışınımı bunu düşük verir — pilotun sorularından biri bu).
  - Ateşleyici: brülör üstünde r < 10 mm, 2 < y < 8 mm bölgesi t=0'da 1500 K + ilk 0,5 s ~5 W ısı kaynağı (sıcak tel).
  - limitTemperature 250-3000 K.
Sonuç (sonuc.json): en yüksek T zaman serisi (cellMax); ateşlemeden (2 s) sonra en yüksek T < 1200 K -> söndü,
  t_sonme. Alev boyu (eksende T > 1400 K en uzak nokta) ve taban yarıçapı (brülör + 1 mm'de) son örnekten.

Kullanım:
  python3 of_gaz_bre.py --kur 87H1 94D1 [--sure 100] [--xr 0]   # vaka(lar)ı kur (OpenFOAM gerekir)
  bash of_kosular/gaz_bre/<test>/kos.sh <cekirdek>                # koşu (uygulama kuyruğundan da)
  python3 of_gaz_bre.py --analiz of_kosular/gaz_bre/<test>
  python3 of_gaz_bre.py --ozet
"""
import argparse
import csv
import json
import math
import re
import shutil
import statistics
import sys
import time
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))
import of_tek_damla as TD  # noqa: E402  (kabuk, baslik, guvenli_sil, cellmax_oku, foam_tut)

BRE_CSV = KOK / "gaz_veri" / "bre_dehghani2021_tablo2.csv"
GB_KOK = TD.OF_KOK / "gaz_bre"
R_BRULOR = 0.0125
R_ALAN, H_ALAN = 0.150, 0.200
KAMA = 5.0                         # derece
DX = 0.0005                        # brülör üstünde hücre (m)
N_BR = 25                          # brülör yarıçapında hücre
N_DIS, N_Y = 60, 140
T_ESIK_SONME = 1200.0
YAZMA = 1.0                        # s: alan yazma (pilot: alev şekli için)
ATES_BAS = 2.0                     # s: bu andan sonraki T düşüşü sönme sayılır
ATES_Q = 2.6e6                     # W/m3: bölge tam 3B'de ~1,9e-6 m3 -> ~5 W (FLEX/BRE sıcak tel düzeyi)
ATES_SURE = 0.5
A_CARPAN = 1.0                     # CO2/H2O soğurma katsayısı çarpanı (--a-carpan)
ARKA_A = 0.1                       # 1/m/atm: O2/N2 arka plan soğurması (P1 kararlılığı)
M = {"O2": 31.9988, "N2": 28.0134, "C2H4": 28.0542}
RU = 8314.46


def bre_testleri():
    out = {}
    for a in csv.DictReader(open(BRE_CSV, encoding="utf-8-sig")):
        out[a["test"]] = {"test": a["test"], "x_o2": float(a["X_O2"]), "x_f": float(a["X_f"]), "p_bar": float(a["p_bar"]),
                          "m_akisi_g_m2s": float(a["m_akisi_g_m2s"]), "sonuc": a["sonuc"], "yanar": 1 if a["sonuc"] == "FT" else 0,
                          "t_b_s": float(a["sure_t_b_s"]) if a["sure_t_b_s"] else None,
                          "y_f_mm": float(a["alev_boyu_y_f_mm"]) if a["alev_boyu_y_f_mm"] else None,
                          "r_f_mm": float(a["taban_yaricapi_r_f_mm"]) if a["taban_yaricapi_r_f_mm"] else None,
                          "X_r": float(a["isinim_orani_X_r"]) if a["isinim_orani_X_r"] else None}
    return out


def kutle(x):
    """mol kesirleri -> kütle kesirleri."""
    m = sum(x[k] * M[k] for k in x)
    return {k: x[k] * M[k] / m for k in x}


def oran(L, n, ilk):
    """blockMesh simpleGrading oranı (son/ilk hücre): n hücre, ilk hücre 'ilk', toplam L."""
    if abs(L - n * ilk) < 1e-12:
        return 1.0
    lo, hi = 1.000001, 1.5
    for _ in range(200):
        r = (lo + hi) / 2
        if ilk * (r ** n - 1) / (r - 1) > L:
            hi = r
        else:
            lo = r
    return r ** (n - 1)


# ------------------------------------------------------------------ dosyalar
def blockmesh(v):
    t = math.tan(math.radians(KAMA / 2))
    rb, R, H = R_BRULOR, R_ALAN, H_ALAN
    gx, gy = oran(R - rb, N_DIS, DX), oran(H, N_Y, DX)
    p = [(0, 0, 0), (rb, 0, -rb * t), (rb, H, -rb * t), (0, H, 0), (rb, 0, rb * t), (rb, H, rb * t),
         (R, 0, -R * t), (R, H, -R * t), (R, 0, R * t), (R, H, R * t)]
    vs = "\n".join(f"    ({a:.7g} {b:.7g} {c:.7g})" for a, b, c in p)
    (v / "system/blockMeshDict").write_text(TD.baslik("dictionary", "blockMeshDict", "system") + f"""convertToMeters 1;

vertices
(
{vs}
);

blocks
(
    hex (0 1 2 3 0 4 5 3) ({N_BR} {N_Y} 1) simpleGrading (1 {gy:.6g} 1)
    hex (1 6 7 2 4 8 9 5) ({N_DIS} {N_Y} 1) simpleGrading ({gx:.6g} {gy:.6g} 1)
);

boundary
(
    brulor   {{ type patch; faces ((0 1 4 0)); }}
    taban    {{ type wall;  faces ((1 6 8 4)); }}
    dis      {{ type patch; faces ((6 7 9 8)); }}
    ust      {{ type patch; faces ((3 2 5 3) (2 7 9 5)); }}
    on       {{ type wedge; faces ((0 1 2 3) (1 6 7 2)); }}
    arka     {{ type wedge; faces ((0 3 5 4) (4 5 9 8)); }}
    eksen    {{ type empty; faces ((0 3 3 0)); }}
);
""")


def alan_dosyasi(ad, boyut, ic, sinirlar, sinif="volScalarField"):
    s = TD.baslik(sinif, ad, "0") + f"dimensions      {boyut};\n\ninternalField   {ic};\n\nboundaryField\n{{\n"
    for patch, icerik in sinirlar.items():
        s += f"    {patch}\n    {{\n{icerik}    }}\n"
    s += "    on\n    {\n        type            wedge;\n    }\n    arka\n    {\n        type            wedge;\n    }\n"
    s += "    eksen\n    {\n        type            empty;\n    }\n}\n"
    return s


def sifir(v, b):
    p = b["p_bar"] * 1e5
    yo = kutle({"O2": b["x_o2"], "N2": 1 - b["x_o2"]})
    yf = kutle({"C2H4": b["x_f"], "N2": 1 - b["x_f"]})
    M_f = b["x_f"] * M["C2H4"] + (1 - b["x_f"]) * M["N2"]
    rho_f = p * M_f / (RU * 300.0)
    Ub = b["m_akisi_g_m2s"] * 1e-3 / rho_f
    sab = lambda x: f"        type            fixedValue;\n        value           uniform {x};\n"   # noqa: E731
    zg = "        type            zeroGradient;\n"
    io = lambda x: (f"        type            inletOutlet;\n        inletValue      uniform {x};\n"  # noqa: E731
                    f"        value           uniform {x};\n")
    s = {
        "p": alan_dosyasi("p", "[pressure]", f"uniform {p:.1f}", {
            "brulor": zg, "taban": zg,
            "dis": f"        type            totalPressure;\n        p0              uniform {p:.1f};\n        value           uniform {p:.1f};\n",
            "ust": f"        type            totalPressure;\n        p0              uniform {p:.1f};\n        value           uniform {p:.1f};\n"}),
        "U": alan_dosyasi("U", "[velocity]", "uniform (0 0 0)", {
            "brulor": f"        type            fixedValue;\n        value           uniform (0 {Ub:.6g} 0);\n",
            "taban": "        type            noSlip;\n",
            "dis": "        type            pressureInletOutletVelocity;\n        value           uniform (0 0 0);\n",
            "ust": "        type            pressureInletOutletVelocity;\n        value           uniform (0 0 0);\n"},
            "volVectorField"),
        "T": alan_dosyasi("T", "[temperature]", "uniform 300", {"brulor": sab(300), "taban": sab(300), "dis": io(300), "ust": io(300)}),
        "G": alan_dosyasi("G", "[heatFluxDensity]", "uniform 0", {
            k: "        type            MarshakRadiation;\n        T               T;\n        emissivityMode  lookup;\n"
               "        emissivity      uniform 1.0;\n        value           uniform 0;\n" for k in ("brulor", "taban", "dis", "ust")}),
        "Ydefault": alan_dosyasi("Ydefault", "[]", "uniform 0", {"brulor": sab(0), "taban": zg, "dis": io(0), "ust": io(0)}),
    }
    for sp in ("C2H4", "O2", "N2"):
        amb, fuel = {"O2": yo["O2"], "N2": yo["N2"], "C2H4": 0.0}[sp], {"O2": 0.0, "N2": yf["N2"], "C2H4": yf["C2H4"]}[sp]
        s[sp] = alan_dosyasi(sp, "[]", f"uniform {amb:.6f}", {"brulor": sab(f"{fuel:.6f}"), "taban": zg, "dis": io(f"{amb:.6f}"), "ust": io(f"{amb:.6f}")})
    z = v / "0"
    if z.exists():
        shutil.rmtree(z)
    z.mkdir()
    for ad, icerik in s.items():
        (z / ad).write_text(icerik)
    return {"p_Pa": p, "U_brulor_m_s": Ub, "rho_yakit": rho_f, "Y_ortam": yo, "Y_yakit": yf}


def termo(v):
    """counterFlowFlame2D termosundaki CH4 -> C2H4 (JANAF, thermoData) + Sutherland (mu(300 K) ≈ 1,03e-5 Pa s)."""
    f = v / "constant/thermo.compressibleGas"
    s = f.read_text()
    s = re.sub(r"\n\s*CH4\n", "\n    C2H4\n", s, count=1)                       # species listesi
    a = s.index("\nCH4\n")
    b = s.index("\n}\n", s.index("transport", a)) + 3
    c2h4 = """
C2H4
{
    specie
    {
        molWeight       28.0542;
    }
    thermodynamics
    {
        Tlow            200;
        Thigh           6000;
        Tcommon         1000;
        highCpCoeffs    ( 3.99183 0.0104834 -3.71721e-06 5.94628e-10 -3.5363e-14 4268.66 -0.269082 );
        lowCpCoeffs     ( 3.9592 -0.00757051 5.7099e-05 -6.91588e-08 2.69884e-11 5089.78 4.0973 );
    }
    transport
    {
        As              1.04e-06;
        Ts              225;
    }
}
"""
    f.write_text(s[:a] + c2h4 + s[b:])


def isinim(v, xr):
    blok = ""
    k = {"CO2": "18.741 -121.31e3 273.5e6 -194.05e9 56.31e12 -5.8169e15",
         "H2O": "-0.23093 -1.12390e3 9.41530e6 -2.99880e9 0.51382e12 -1.86840e10"}
    # O2/N2'ye küçük sabit soğurma (ARKA_A, 1/m/atm): a = 0 olan ortamda P1 difüzyon katsayısı 1/(3a) sonsuza gidip
    # G denklemi ıraksıyordu (1000 iterasyon, kalan 10; sonra G = 0 kaldı -> geri soğurma yok, alev tutuşamadı).
    # A_CARPAN: gri gaz Planck ortalaması öz soğurmayı (CO2 4,3 um) hesaba katmaz, kaybı 2-3 kat büyük verir;
    # CO2/H2O katsayıları bu çarpanla ölçeklenir (87H1'in ölçülen X_r'sine göre ayarlanır).
    k = {t: " ".join(f"{float(c) * A_CARPAN:g}" for c in v.split()) for t, v in k.items()}
    k = {**k, "O2": f"{ARKA_A:g} 0 0 0 0 0", "N2": f"{ARKA_A:g} 0 0 0 0 0"}
    for tur in ("CO2", "H2O", "O2", "N2", "C2H4"):
        blok += (f"    {tur}\n    {{\n        Tcommon 200;\n        invTemp true;\n        Tlow 200;\n        Thigh 2500;\n"
                 f"        loTcoeffs (0 0 0 0 0 0);\n        hiTcoeffs ({k.get(tur, '0 0 0 0 0 0')});\n    }}\n")
    (v / "constant/radiationProperties").write_text(
        TD.baslik("dictionary", "radiationProperties", "constant") +
        "radiation on;\nradiationModel  P1;\nsolverFreq 5;\nabsorptionEmissionModel greyMeanReaction;\n"
        f"greyMeanReaction\n{{\n    lookUpTableFileName none;\n    EhrrCoeff {xr};\n" + blok + "}\n"
        "scatterModel    none;\nsootModel       none;\n")


def kur_vaka(b, sure, xr):
    v = GB_KOK / b["test"]
    TD.guvenli_sil(v)
    shutil.copytree(TD.foam_tut() / "multicomponentFluid/counterFlowFlame2D", v)
    for f in ("Allrun", "Allclean"):
        (v / f).unlink(missing_ok=True)
    for f in (v / "0").glob("*"):
        f.unlink()
    blockmesh(v)
    bilgi = sifir(v, b)
    termo(v)
    (v / "constant/reactions").write_text(TD.baslik("dictionary", "reactions", "constant") + """reactions
{
    etilen
    {
        type     irreversibleArrhenius;
        reaction "C2H4^0.1 + 3O2^1.65 = 2CO2 + 2H2O";
        A        2.0e12 [(mol/cm^3)^-0.75/s];
        beta     0;
        Ta       15098;
    }
}

// Hız sabitindeki T sınırı (reverseBurner örneğindeki gibi): kimya ODE'sinin ara adımında T eksiye/çok yükseğe
// gidince exp(-Ta/T) taşıyıp SIGFPE veriyordu (önceki metan denemeleri de buradan çöktü).
Tlow    200;
Thigh   5000;
""")
    (v / "constant/chemistryProperties").write_text(
        TD.baslik("dictionary", "chemistryProperties", "constant") +
        "initialChemicalTimeStep 1e-07;\n\node\n{\n    solver          seulex;\n    eps             0.05;\n}\n\n"
        '#include "reactions"\n')
    (v / "constant/momentumTransport").write_text(TD.baslik("dictionary", "momentumTransport", "constant") +
                                                  "simulationType  laminar;\n")
    isinim(v, xr)
    (v / "constant/fvModels").write_text(
        TD.baslik("dictionary", "fvModels", "constant") +
        'radiation\n{\n    type    radiation;\n    libs    ("libradiationModels.so");\n}\n'
        "atesleyici\n{\n    type            heatSource;\n"
        "    cellZone\n    {\n        type        box;\n        zoneType    cell;\n"
        "        box         (0 0.002 -1) (0.010 0.008 1);\n    }\n"
        f"    q               table ((0 {ATES_Q:g}) ({ATES_SURE} {ATES_Q:g}) ({ATES_SURE + 0.01:.2f} 0) (100000 0));\n}}\n")
    (v / "system/fvConstraints").write_text(                # OpenFOAM 14: system/ altında (constant/ okunmaz)
        TD.baslik("dictionary", "fvConstraints", "system") +
        "sinirT\n{\n    type            limitTemperature;\n    min             250;\n    max             3000;\n    cellZone        all;\n}\n")
    (v / "system/setFieldsDict").write_text(
        TD.baslik("dictionary", "setFieldsDict", "system") +
        "zones\n{\n    sicak\n    {\n        type        box;\n        box         (0 0.002 -1) (0.010 0.008 1);\n"
        "        values\n        {\n            T 1500;\n        }\n    }\n}\n")
    (v / "system/decomposeParDict").write_text(TD.baslik("dictionary", "decomposeParDict", "system") +
                                               "numberOfSubdomains 4;\n\ndecomposer      scotch;\n")
    fs = v / "system/fvSolution"
    s = fs.read_text()
    if '"G.*"' not in s:
        s = s.replace("solvers\n{", 'solvers\n{\n    "G.*"\n    {\n        solver          GAMG;\n'
                      "        smoother        GaussSeidel;\n        tolerance       1e-5;\n        relTol          0.1;\n    }\n", 1)
    fs.write_text(s)
    h = H_ALAN
    (v / "system/controlDict").write_text(
        TD.baslik("dictionary", "controlDict", "system") +
        f"solver          multicomponentFluid;\n\nstartFrom       latestTime;\nstartTime       0;\n"
        f"stopAt          endTime;\nendTime         {sure};\ndeltaT          1e-05;\n"
        f"writeControl    adjustableRunTime;\nwriteInterval   {YAZMA};\npurgeWrite      0;\n"
        "writeFormat     binary;\nwritePrecision  6;\nwriteCompression off;\ntimeFormat      general;\n"
        "timePrecision   6;\nadjustTimeStep  yes;\nmaxCo           0.4;\nmaxDeltaT       2e-3;\n"
        "runTimeModifiable yes;\n")
    (v / "system/functions").write_text(
        TD.baslik("dictionary", "functions", "system") +
        "#includeFunc cellMax(T)\n"
        f"#includeFunc graphCell(start=(1e-5 1e-5 0), end=(1e-5 {h - 1e-5} 0), fields=(T C2H4 O2), name=eksen)\n"
        f"#includeFunc graphCell(start=(1e-5 0.001 0), end=({R_ALAN - 1e-5} 0.001 0), fields=(T), name=taban)\n")
    log = v / "log.hazirlik"
    log.unlink(missing_ok=True)
    for cmd in ("blockMesh", "setFields"):
        rc = TD.kabuk(cmd, v, log=log)
        if rc != 0:
            raise SystemExit(f"{b['test']}: '{cmd}' başarısız (rc={rc}), bkz. {log}")
    betik = KOK / "of_gaz_bre.py"
    (v / "kos.sh").write_text(
        "#!/bin/bash\n# Uygulamanın koşu kuyruğundan: bash kos.sh <cekirdek>. Çıktı log.run'a gider.\n"
        'N=${1:-8}\ncd "$(dirname "$0")"\n'
        # WSL (221): ParaView sürüm sorgusu bashrc'yi, hwloc'un GL eklentisi (X ekranına bağlanır) mpirun'u kilitliyor
        f"source {TD.BASHRC} ParaView_TYPE=none >/dev/null 2>&1\n"
        "export HWLOC_COMPONENTS=-gl\n"
        'sed -i "s/^numberOfSubdomains .*/numberOfSubdomains $N;/" system/decomposeParDict\n'
        "if ! ls -d processor* >/dev/null 2>&1; then\n"
        '  decomposePar -force > log.decomposePar 2>&1 || { echo "decomposePar başarısız"; exit 1; }\n'
        "fi\n"
        'echo "AHUT gaz BRE: $N çekirdek, $(date)"\n'
        # Erken durdurma: t > 3 s ve en yüksek T < 1100 K (alev açıkça söndü) -> endTime o ana çekilir
        # (runTimeModifiable). Sönen vakalar bitiş süresini beklemez.
        "( while sleep 20; do\n"
        '    f=$(ls -d postProcessing/cellMax\\(T\\)/*/volFieldValue.dat 2>/dev/null | sort -V | tail -1); [ -z "$f" ] && continue\n'
        '    read t T < <(tail -1 "$f")\n'
        "    if awk -v t=\"$t\" -v T=\"$T\" 'BEGIN{exit !(t+0>3 && T+0<1100)}'; then\n"
        '      sed -i "s/^endTime .*/endTime         $t;/" system/controlDict; echo "ERKEN DURDURMA: t=$t T=$T"; break; fi\n'
        "  done ) &\nIZLE=$!\n"
        "mpirun --oversubscribe -np $N foamRun -parallel\n"
        "rc=$?\nkill $IZLE 2>/dev/null\n"
        f'python3 "{betik}" --analiz "$PWD" || echo "analiz başarısız"\n'
        "exit $rc\n")
    (v / "BILGI.json").write_text(json.dumps({**b, **bilgi, "bitis_s": sure, "EhrrCoeff": xr, "a_carpan": A_CARPAN, "kama_derece": KAMA,
                                              "kurulum": time.strftime("%Y-%m-%d %H:%M")}, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
    return v


# ------------------------------------------------------------------ analiz
def _graph_son(v, ad):
    d = sorted((x for x in v.glob(f"postProcessing/{ad}/*") if re.match(r"^[\d.e+-]+$", x.name)), key=lambda x: float(x.name))
    if not d:
        return None, []
    f = next(iter(sorted(d[-1].glob("*"))), None)
    if f is None:
        return None, []
    rows = []
    for s in open(f, errors="replace"):
        if s.startswith("#") or not s.strip():
            continue
        p = s.split()
        try:
            rows.append([float(x) for x in p])
        except ValueError:
            pass
    return float(d[-1].name), rows


def analiz(v):
    v = Path(v).resolve()
    b = json.loads((v / "BILGI.json").read_text(encoding="utf-8"))
    t, T = TD.cellmax_oku(v)
    sonra = [(tt, x) for tt, x in zip(t, T) if tt >= ATES_BAS]
    t_sonme = next((tt for tt, x in sonra if x < T_ESIK_SONME), None)
    t_son = max(t) if t else None
    yanar = None if not sonra else (0 if t_sonme is not None else 1)
    te, eks = _graph_son(v, "eksen")
    yf = max((r[0] * 1000 for r in eks if len(r) > 1 and r[1] > 1400), default=None)
    _, tb = _graph_son(v, "taban")
    rf = max((r[0] * 1000 for r in tb if len(r) > 1 and r[1] > 1400), default=None)
    r = {"test": b["test"], "t_son_s": t_son, "bitis_s": b["bitis_s"], "t_sonme_s": t_sonme, "yanar_of": yanar,
         "T_maks_son_K": T[-1] if T else None, "T_maks_K": max(T) if T else None,
         "y_f_of_mm": yf, "r_f_of_mm": rf, "profil_t_s": te,
         "deney": {k: b[k] for k in ("sonuc", "yanar", "t_b_s", "y_f_mm", "r_f_mm", "X_r")},
         "not": "t_son < deney t_b ise FT için 'yandı' kararı yalnız t_son'a kadar geçerli.",
         "analiz": time.strftime("%Y-%m-%d %H:%M")}
    (v / "sonuc.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False))
    return r


def ozet():
    out = []
    for f in sorted(GB_KOK.glob("*/BILGI.json")):
        b = json.loads(f.read_text(encoding="utf-8"))
        s = f.parent / "sonuc.json"
        out.append({"test": b["test"], "deney": b["sonuc"], "durum": "bitti" if s.exists() else "kuruldu",
                    **(json.loads(s.read_text(encoding="utf-8")) if s.exists() else {})})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kur", nargs="+", metavar="TEST")
    ap.add_argument("--sure", type=float, default=100.0)
    ap.add_argument("--xr", type=float, default=0.0)
    ap.add_argument("--a-carpan", type=float, default=1.0, help="CO2/H2O soğurma katsayısı çarpanı")
    ap.add_argument("--analiz", metavar="VAKA")
    ap.add_argument("--ozet", action="store_true")
    a = ap.parse_args()
    global A_CARPAN
    A_CARPAN = a.a_carpan
    if a.kur:
        tt = bre_testleri()
        for ad in a.kur:
            if ad not in tt:
                raise SystemExit(f"test yok: {ad}")
            print("Kuruldu:", kur_vaka(tt[ad], a.sure, a.xr))
    if a.analiz:
        analiz(a.analiz)
    if a.ozet:
        for x in ozet():
            print(json.dumps(x, ensure_ascii=False))


if __name__ == "__main__":
    main()
