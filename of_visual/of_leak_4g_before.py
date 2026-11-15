#!/usr/bin/env python3
"""
scripts/of_leak.py — kabinde basınçlı hattan n-heptan sızıntısı/püskürmesi ve tutuşma (GÖSTERİM; deney verisiyle
doğrulanmadı).

Temel örnek: $FOAM_TUTORIALS/multicomponentFluid/aachenBomb (sprayCloud, ReitzDiwakar parçalanma, C7H16 sıvı
özellikleri, liquidEvaporationBoil, tek adım heptan kimyası, k-epsilon).

Vaka (of_kosular/sizinti/<uzay|mars>):
  - Kabin bölümü: 20 cm küp, 5 mm hücre (40³ = 64 000 hücre); 5 yüz duvar, üst yüz (+y) açık (1 atm).
    (Yerçekimi varken bütün yüzleri sabit basınçlı açık bırakmak hidrostatik uyumsuzlukla sahte akış yaratır.)
  - Ortam: %21 O2 (kütle 0.233) + N2, 1 atm, 300 K.
  - Sızıntı: (-80, 0, 0) mm'deki 0.3 mm delikten +x yönünde heptan; ~1 g/s, 0.2 s
    (Cd 0.7 -> ~30 m/s, ~3 bar basınç farkına karşılık), Rosin-Rammler damla dağılımı (ortalama 50 µm).
  - Tutuşturma kaynağı: püskürmenin 8 cm ilerisinde, sprey konisinin kenarında (0, 20, 0) mm, r = 10 mm küre: t = 0'da 1500 K
    (setFields) + ilk 0.01 s boyunca 300 W ısı kaynağı (heatSource; kıvılcım taklidi, ~3 J). Jet ekseninde
    alev üflenip söndüğü için tutuşturucu sprey konisinin kenarında (0, 20, 0) mm.
  - Koşular: "uzay" g = 0, "mars" g = (0, -3.73, 0) m/s² (püskürmeye dik).
Kullanım:
  python3 scripts/of_leak.py --kur
  python3 scripts/of_leak.py --test --sure 0.01         # kısa test, hız ve tahmini süre
  python3 scripts/of_leak.py --kos                      # uzay sonra mars (scripts/of_queue.sh tek damla koşularından SONRA çağırır)
  python3 scripts/of_leak.py --analiz                   # figures/of_leak.png + data/of_leak_result.csv
"""
import argparse
import re
import shutil
import time
from pathlib import Path

import of_single_droplet as ot

KOK = ot.KOK
VAKA_KOK = ot.OF_KOK / "sizinti"
ILERLEME = ot.OF_KOK / "sizinti_ilerleme.log"
VARYANTLAR = {"uzay": (0.0, 0.0, 0.0), "mars": (0.0, -3.73, 0.0)}
L = 0.20
KENAR_HUCRE = 40
SURE = 1.00                    # püskürme 0.2 s + yanma/kaldırma (ilk koşular 0.40 s idi; uzay 0.40 s'den devam etti)
YAZMA = 0.01
ENJ_POZ = (-0.08, 0.0, 0.0)
ENJ_SURE = 0.2
DEBI = 1.0e-3                 # kg/s
ATES_POZ, ATES_R, ATES_T = (0.0, 0.02, 0.0), 0.010, 1500.0
ATES_GUC, ATES_SURE = 300.0, 0.01   # W, s: tutuşturucu darbesi (kıvılcım taklidi, ~3 J) heatSource ile
CEKIRDEK = 15                  # nproc - 1
BOLME = "(5 3 1)"             # 15 alt bölge


def blockmesh(v):
    h = L / 2 * 1000
    n = KENAR_HUCRE
    yuz = {"disari": ["(3 7 6 2)"], "duvar": ["(0 4 7 3)", "(1 2 6 5)", "(0 1 5 4)", "(0 3 2 1)", "(4 5 6 7)"]}
    b = "".join(f"    {ad}\n    {{\n        type {'wall' if ad == 'duvar' else 'patch'};\n        faces\n        (\n"
                + "".join(f"            {f}\n" for f in fl) + "        );\n    }\n" for ad, fl in yuz.items())
    (v / "system/blockMeshDict").write_text(
        ot.baslik("dictionary", "blockMeshDict", "system") +
        f"units [mm];\n\nvertices\n(\n    ({-h} {-h} {-h})\n    ({h} {-h} {-h})\n    ({h} {h} {-h})\n"
        f"    ({-h} {h} {-h})\n    ({-h} {-h} {h})\n    ({h} {-h} {h})\n    ({h} {h} {h})\n    ({-h} {h} {h})\n);\n\n"
        f"blocks\n(\n    hex (0 1 2 3 4 5 6 7) ({n} {n} {n}) simpleGrading (1 1 1)\n);\n\nboundary\n(\n{b});\n")


def alan(ad, boyut, ic, duvar, disari, sinif="volScalarField"):
    return ot.baslik(sinif, ad, "0") + f"dimensions      {boyut};\n\ninternalField   {ic};\n\nboundaryField\n{{\n" \
        f"    duvar\n    {{\n{duvar}    }}\n    disari\n    {{\n{disari}    }}\n}}\n"


def io(deger):
    return (f"        type            inletOutlet;\n        inletValue      uniform {deger};\n"
            f"        value           uniform {deger};\n")


ZG = "        type            zeroGradient;\n"


def sifir(v, g=(0.0, 0.0, 0.0)):
    kaldirma = any(abs(x) > 0 for x in g)
    s = {
        "p": alan("p", "[pressure]", "uniform 101325", ZG,
                  "        type            totalPressure;\n        p0              uniform 101325;\n"
                  "        value           uniform 101325;\n"),
        "U": alan("U", "[velocity]", "uniform (0 0 0)", "        type            noSlip;\n",
                  "        type            pressureInletOutletVelocity;\n        value           uniform (0 0 0);\n",
                  "volVectorField"),
        "T": alan("T", "[temperature]", "uniform 300", ZG, io(300)),
        "O2": alan("O2", "[]", "uniform 0.233", ZG, io(0.233)),
        "N2": alan("N2", "[]", "uniform 0.767", ZG, io(0.767)),
        "Ydefault": alan("Ydefault", "[]", "uniform 0", ZG, io(0)),
        "k": alan("k", "[0 2 -2 0 0 0 0]", "uniform 1e-5",
                  "        type            kqRWallFunction;\n        value           uniform 1e-5;\n", io(1e-5)),
        "epsilon": alan("epsilon", "[0 2 -3 0 0 0 0]", "uniform 1e-5",
                        "        type            epsilonWallFunction;\n        value           uniform 1e-5;\n",
                        io(1e-5)),
        "nut": alan("nut", "[0 2 -1 0 0 0 0]", "uniform 0",
                    "        type            nutkWallFunction;\n        value           uniform 0;\n",
                    "        type            calculated;\n        value           uniform 0;\n"),
        "alphat": alan("alphat", "[1 -1 -1 0 0 0 0]", "uniform 0",
                       "        type            compressible::alphatWallFunction;\n        value           uniform 0;\n",
                       "        type            calculated;\n        value           uniform 0;\n"),
    }
    if kaldirma:
        # OpenFOAM 14: gaz fazı kaldırması yalnızca 0/p_rgh varsa açılır (solvers::buoyancy::New).
        # Kurulum smallPoolFire3D örneğindeki gibi: p = p_rgh + rho*gh + pRef, hRef = tavan yüksekliği.
        s["p"] = alan("p", "[pressure]", "uniform 101325", "        type            calculated;\n"
                      "        value           uniform 101325;\n",
                      "        type            calculated;\n        value           uniform 101325;\n")
        s["p_rgh"] = alan("p_rgh", "[pressure]", "uniform 0",
                          "        type            fixedFluxPressure;\n        value           uniform 0;\n",
                          "        type            prghTotalHydrostaticPressure;\n        p0              uniform 0;\n"
                          "        gamma           1;\n        value           uniform 0;\n")
        s["ph_rgh"] = alan("ph_rgh", "[pressure]", "uniform 0",       # hidrostatik başlatma (smallPoolFire3D gibi)
                           "        type            fixedFluxPressure;\n        value           uniform 0;\n",
                           "        type            fixedValue;\n        value           uniform 0;\n")
    z = v / "0"
    if z.exists():
        shutil.rmtree(z)
    z.mkdir()
    for ad, icerik in s.items():
        (z / ad).write_text(icerik)
    if kaldirma:
        (v / "constant/pRef").write_text(ot.baslik("uniformDimensionedScalarField", "pRef", "constant") +
                                         "dimensions      [pressure];\nvalue           101325;\n")
        (v / "constant/hRef").write_text(ot.baslik("uniformDimensionedScalarField", "hRef", "constant") +
                                         f"dimensions      [length];\nvalue           {L / 2};\n")
        fs = v / "system/fvSolution"
        t = fs.read_text()
        if "p_rgh" not in t:
            t = t.replace("    pFinal\n", "    p_rgh\n    {\n        $p;\n    }\n\n    p_rghFinal\n    {\n        $p;\n"
                          "        relTol          0;\n    }\n\n    ph_rgh\n    {\n        $p;\n    }\n\n    pFinal\n", 1)
            t = t.replace("    momentumPredictor yes;\n", "    momentumPredictor yes;\n    hydrostaticInitialisation yes;\n"
                          "    nHydrostaticCorrectors 5;\n", 1)
            fs.write_text(t)


def bulut(v):
    p = v / "constant/cloudProperties"
    s = p.read_text()
    s = re.sub(r"massTotal\s+[\d.e+-]+;", f"massTotal       {DEBI * ENJ_SURE:.3e};", s)
    s = re.sub(r"duration\s+[\d.e+-]+;", f"duration        {ENJ_SURE};", s)
    s = re.sub(r"position\s+\([^)]*\);", f"position        ({ENJ_POZ[0]} {ENJ_POZ[1]} {ENJ_POZ[2]});", s)
    s = re.sub(r"direction\s+\([^)]*\);", "direction       (1 0 0);", s)
    s = re.sub(r"dOuter\s+[\d.e+-]+;", "dOuter          3.0e-4;", s)
    s = re.sub(r"parcelsPerSecond\s+[\d.e+-]+;", "parcelsPerSecond 100000;", s)
    s = re.sub(r"flowRateProfile\s+table\s*\(.*?\n\s*\);", "flowRateProfile constant 1;", s, flags=re.S)
    s = re.sub(r"Cd\s+constant\s+[\d.]+;", "Cd              constant 0.7;", s)
    s = re.sub(r"thetaOuter\s+constant\s+[\d.]+;", "thetaOuter      constant 15.0;", s)
    s = re.sub(r"(sizeDistribution\s*\{.*?)min\s+[\d.e+-]+;(.*?)max\s+[\d.e+-]+;(.*?)\bd\s+[\d.e+-]+;",
               r"\1min             5e-06;\2max             0.0003;\3d               5e-05;", s, flags=re.S)
    s = re.sub(r"T0\s+[\d.e+-]+;", "T0              300;", s)
    s = re.sub(r"rho0\s+[\d.e+-]+;", "rho0            684;", s)
    s = re.sub(r"Cp0\s+[\d.e+-]+;", "Cp0             2240;", s)
    s = re.sub(r"type\s+rebound;", "type            stick;", s)
    p.write_text(s)


def kontrol(v, bitis):
    (v / "system/controlDict").write_text(
        ot.baslik("dictionary", "controlDict", "system") +
        f"solver          multicomponentFluid;\n\nstartFrom       latestTime;\nstartTime       0;\n"
        f"stopAt          endTime;\nendTime         {bitis};\ndeltaT          1e-06;\n"
        f"writeControl    adjustableRunTime;\nwriteInterval   {min(YAZMA, bitis / 2)};\npurgeWrite      0;\n"
        "writeFormat     binary;\nwritePrecision  6;\nwriteCompression off;\ntimeFormat      general;\n"
        "timePrecision   6;\nadjustTimeStep  yes;\nmaxCo           0.3;\nmaxDeltaT       1e-3;\n"
        "runTimeModifiable yes;\n")
    (v / "system/functions").write_text(
        ot.baslik("dictionary", "functions", "system") +
        "#includeFunc Qdot(executeControl=timeStep)\n#includeFunc cellMax(T)\n#includeFunc volIntegrate(Qdot)\n"
        "#includeFunc cutPlaneSurface(point=(0 0 0), normal=(0 0 1), fields=(T C7H16), surfaceFormat=raw, "
        "name=kesit)\n")


def kur_varyant(ad, g):
    tut = ot.foam_tut() / "multicomponentFluid/aachenBomb"
    v = VAKA_KOK / ad
    ot.guvenli_sil(v)
    shutil.copytree(tut, v)
    for f in ("Allrun", "Allrun-parallel", "Allclean", "constant/dynamicMeshDict"):
        (v / f).unlink(missing_ok=True)
    blockmesh(v)
    sifir(v, g)
    bulut(v)
    fvm = (v / "constant/fvModels").read_text()
    fvm += ("\natesleyici\n{\n    type            heatSource;\n    cellZone\n    {\n        type    sphere;\n"
            f"        centre  ({ATES_POZ[0]} {ATES_POZ[1]} {ATES_POZ[2]});\n        radius  {ATES_R};\n    }}\n"
            f"    Q               table ((0 {ATES_GUC}) ({ATES_SURE} {ATES_GUC}) ({ATES_SURE + 1e-4} 0) (1000 0));\n}}\n")
    (v / "constant/fvModels").write_text(fvm)
    (v / "constant/g").write_text(ot.baslik("uniformDimensionedVectorField", "g", "constant") +
                                  f"dimensions      [acceleration];\nvalue           ({g[0]} {g[1]} {g[2]});\n")
    (v / "system/setFieldsDict").write_text(
        ot.baslik("dictionary", "setFieldsDict", "system") +
        "zones\n{\n    ateslemeKaynagi\n    {\n        type        sphere;\n"
        f"        centre      ({ATES_POZ[0]} {ATES_POZ[1]} {ATES_POZ[2]});\n        radius      {ATES_R};\n"
        f"        values\n        {{\n            T {ATES_T};\n        }}\n    }}\n}}\n")
    (v / "system/decomposeParDict").write_text(
        ot.baslik("dictionary", "decomposeParDict", "system") +
        f"numberOfSubdomains {CEKIRDEK};\n\ndecomposer      simple;\n\nsimple\n{{\n    n           {BOLME};\n}}\n")
    kontrol(v, SURE)
    return v


def kur(sadece=None):
    VAKA_KOK.mkdir(parents=True, exist_ok=True)
    for ad, g in VARYANTLAR.items():
        if sadece and ad not in sadece:
            continue
        v = kur_varyant(ad, g)
        log = ot.OF_KOK / f"sizinti_{ad}_hazirlik.log"
        log.unlink(missing_ok=True)
        for cmd in ("chemkinToFoam chemkin/chem.inp chemkin/therm.dat chemkin/transportProperties "
                    "constant/reactions constant/speciesThermo", "blockMesh", "setFields"):
            if ot.kabuk(cmd, v, log=log) != 0:
                raise SystemExit(f"{ad}: '{cmd.split()[0]}' başarısız, bkz. {log}")
        print(f"Kuruldu: {v}")


def ilerleme_yaz(m):
    with open(ILERLEME, "a") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + m + "\n")


def kos_varyant(ad, bitis, cekirdek, hedef=None):
    import subprocess
    v = hedef or VAKA_KOK / ad
    log = ot.OF_KOK / f"sizinti_{ad}.log"
    kontrol(v, bitis)
    if not any(v.glob("processor*")):
        if ot.kabuk("decomposePar -force", v, log=ot.OF_KOK / f"sizinti_{ad}_hazirlik.log") != 0:
            raise SystemExit(f"{ad}: decomposePar başarısız")
    ilerleme_yaz(f"{ad}: başladı (bitiş {bitis} s), log {log.name}")
    bas = time.time()
    t0 = max([float(d.name) for d in (v / "processor0").iterdir() if re.match(r"^[\d.e+-]+$", d.name)] or [0.0])
    p = subprocess.Popen(["bash", "-c", f"source {ot.BASHRC} >/dev/null 2>&1; "
                                        f"exec mpirun --oversubscribe -np {cekirdek} foamRun -parallel"],
                         cwd=v, stdout=open(log, "a"), stderr=subprocess.STDOUT)
    (ot.OF_KOK / f"sizinti_{ad}.pid").write_text(str(p.pid))
    while p.poll() is None:
        time.sleep(30)
        z = re.findall(r"^Time = ([\d.e+-]+)", Path(log).read_text(errors="replace")[-50000:], flags=re.M)
        if z:
            t = float(z[-1])
            gec = time.time() - bas
            ilerleme_yaz(f"{ad}: t = {t:.5f} s | geçen {gec / 60:.1f} dk | kalan ~"
                         f"{gec / max(t - t0, 1e-9) * (bitis - t) / 3600:.2f} sa")
    ilerleme_yaz(f"{ad}: bitti rc={p.returncode} süre {(time.time() - bas) / 3600:.2f} sa")
    return p.returncode, time.time() - bas


def test(sure, cekirdek, kaynak="uzay"):
    hedef = VAKA_KOK / "test"
    ot.guvenli_sil(hedef)
    shutil.copytree(VAKA_KOK / kaynak, hedef, ignore=shutil.ignore_patterns("processor*", "postProcessing"))
    log = ot.OF_KOK / "sizinti_test.log"
    log.unlink(missing_ok=True)
    rc, gec = kos_varyant("test", sure, cekirdek, hedef=hedef)
    metin = log.read_text(errors="replace")
    z = re.findall(r"^Time = ([\d.e+-]+)", metin, flags=re.M)
    par = re.findall(r"Current number of parcels\s*=\s*(\d+)", metin)
    print(f"Test: {sure} s, rc={rc}, duvar süresi {gec:.0f} s, ulaşılan t={z[-1] if z else None}, "
          f"adım {len(z)}, parsel {par[-1] if par else None}")
    if z and float(z[-1]) > 0:
        print(f"  -> {SURE} s için doğrusal tahmin {gec / float(z[-1]) * SURE / 3600:.1f} saat/koşu "
              "(püskürme sürdükçe parsel sayısı arttığı için gerçek süre daha uzun olabilir)")


def kos(cekirdek, bitis, sadece=None):
    for ad in VARYANTLAR:
        if sadece and ad not in sadece:
            continue
        kos_varyant(ad, bitis, cekirdek)


# ------------------------------------------------------------------ analiz
def dat_oku(v, ad):
    t, y = [], []
    for f in sorted(v.glob(f"postProcessing/{ad}/*/volFieldValue.dat")):
        for s in open(f, errors="replace"):
            if s.startswith("#") or not s.strip():
                continue
            p = s.split()
            try:
                t.append(float(p[0]))
                y.append(float(p[1]))
            except (ValueError, IndexError):
                pass
    return t, y


def kesit_oku(v, zaman=None):
    """postProcessing/kesit/<t>/*.raw (x y z T C7H16). zaman=None -> en son."""
    import numpy as np
    dirs = [d for d in v.glob("postProcessing/kesit/*") if re.match(r"^[\d.e+-]+$", d.name)]
    if not dirs:
        return None, None
    d = min(dirs, key=lambda x: abs(float(x.name) - zaman)) if zaman is not None else \
        max(dirs, key=lambda x: float(x.name))
    f = next(iter(sorted(d.glob("*.xy")) + sorted(d.glob("*.raw")) + sorted(d.glob("*T*"))), None)
    if f is None:
        return None, None
    a = np.loadtxt(f, comments="#")
    return float(d.name), a


DARBE_SON = 0.03      # tutuşturucu darbesi (0.01 s) + sönümlenme; bu süreden önceki Tmax fiziksel değil

METIN_S = {
    "tr": {"baslik": "Kabinde n-heptan sızıntısı + tutuşma: uzay (g = 0) ve Mars (g = 3,73 m/s²) — OpenFOAM, kaba ızgara",
           "ad": {"uzay": "uzay (g = 0)", "mars": "Mars (g = 3,73 m/s²)"},
           "kesit": "{ad}: z = 0 kesiti, t = {t} s", "x": "x (mm)", "y": "y (mm, yukarı)",
           "Tm": "en yüksek sıcaklık", "Tmy": "en yüksek T (K)", "Q": "ısı salım hızı (∫Qdot dV)",
           "Qy": "toplam ısı salımı (kW)", "h": "alev merkezinin yüksekliği (sıcaklık ağırlıklı y ortalaması)",
           "hy": "y_alev (mm)", "darbe": "tutuşturucu darbesi",
           "hnot": "ANA SONUÇ (t = 0,40–0,65 s): alev merkezi Mars'ta\n"
                   "uzaya göre {fm} mm {yon}  (t = {tm} s; uzay {wu} mm, Mars {wm} mm)\n\n"
                   "Tavanda havalandırma çıkışı (açık basınç sınırı); Mars'ta sıcak gaz\n"
                   "0,65 s sonrası buradan tahliye oluyor, uzayda kaldırma olmadığı\n"
                   "için kabinde kalıyor.\n\n"
                   "Son an t = {t} s (tahliye sonrası, ana sonuç değil):\n"
                   "  uzay {u} mm, Mars {m} mm\n"
                   "Mars koşusunda gaz fazı kaldırması açık (p_rgh); uzayda g = 0.",
           "pencere": "ana sonuç aralığı",
           "bolge_b": "Bölge ortalama sıcaklıkları (z = 0 kesiti, K): üst y > 50 mm, orta −50…50 mm, alt y < −50 mm",
           "bolge_s": ["t (s)", "uzay: üst", "uzay: orta", "uzay: alt", "Mars: üst", "Mars: orta", "Mars: alt"],
           "yukari": "daha yukarıda", "asagi": "daha aşağıda",
           "sutun": ["koşu", "g (m/s²)", "tutuşma (s)", "T maks, t>0,03 s (K)", "T maks, darbe dahil (K)",
                     "Q maks (kW)", "y_alev maks fark\n0,40–0,65 s (mm)", "y_alev, son (mm)"],
           "uyari": "GÖSTERİM — deney verisiyle doğrulanmadı", "dosya": "figures/of_leak.png"},
    "en": {"baslik": "n-Heptane leak + ignition in a cabin: space (g = 0) vs Mars (g = 3.73 m/s²) — OpenFOAM, coarse grid",
           "ad": {"uzay": "space (g = 0)", "mars": "Mars (g = 3.73 m/s²)"},
           "kesit": "{ad}: z = 0 slice, t = {t} s", "x": "x (mm)", "y": "y (mm, up)",
           "Tm": "maximum temperature", "Tmy": "max T (K)", "Q": "heat release rate (∫Qdot dV)",
           "Qy": "total heat release (kW)", "h": "flame centre height (temperature-weighted mean y)",
           "hy": "y_flame (mm)", "darbe": "igniter pulse",
           "hnot": "MAIN RESULT (t = 0.40–0.65 s): the flame centre on Mars is\n"
                   "{fm} mm {yon} than in space  (t = {tm} s; space {wu} mm, Mars {wm} mm)\n\n"
                   "Ventilation outlet in the ceiling (open pressure boundary); on Mars\n"
                   "the hot gas is vented through it after 0.65 s, in space it stays\n"
                   "in the cabin because there is no buoyancy.\n\n"
                   "Last time t = {t} s (after venting, not the main result):\n"
                   "  space {u} mm, Mars {m} mm\n"
                   "Gas-phase buoyancy is on in the Mars run (p_rgh); space has g = 0.",
           "pencere": "main-result window",
           "bolge_b": "Mean temperature by region (z = 0 slice, K): upper y > 50 mm, middle −50…50 mm, lower y < −50 mm",
           "bolge_s": ["t (s)", "space: upper", "space: middle", "space: lower", "Mars: upper", "Mars: middle", "Mars: lower"],
           "yukari": "higher", "asagi": "lower",
           "sutun": ["run", "g (m/s²)", "ignition (s)", "T max, t>0.03 s (K)", "T max incl. pulse (K)",
                     "Q max (kW)", "y_flame max diff.\n0.40–0.65 s (mm)", "y_flame, end (mm)"],
           "uyari": "DEMONSTRATION — not validated against experimental data", "dosya": "figures/of_leak_en.png"},
}
RENK_S = {"uzay": "#1565C0", "mars": "#C62828"}
Q_CARPAN = 1.0                 # ince (yarım alan) koşuda 2: hacim integrali tam kabine çevrilir
CSV_AD = "data/of_leak_result.csv"


def ince_ayarla():
    """--ince: scripts/of_leak3d.py'nin ayrıntılı 3B yarım alan koşuları (of_kosular/sizinti3d_ince) için etiket/dosya adları."""
    global VAKA_KOK, Q_CARPAN, CSV_AD
    VAKA_KOK = ot.OF_KOK / "sizinti3d_ince"
    Q_CARPAN = 2.0
    CSV_AD = "data/of_leak_thin_result.csv"
    tr, en = METIN_S["tr"], METIN_S["en"]
    tr["baslik"] = ("Kabinde n-heptan sızıntısı + tutuşma: uzay (g = 0) ve Mars (g = 3,73 m/s²) — OpenFOAM, "
                    "İNCE IZGARA (2,5 mm, 3B yarım alan)")
    en["baslik"] = ("n-Heptane leak + ignition in a cabin: space (g = 0) vs Mars (g = 3.73 m/s²) — OpenFOAM, "
                    "FINE GRID (2.5 mm, 3D half domain)")
    tr["kesit"] = "{ad}: simetri düzlemi (z = 1 mm), t = {t} s"
    en["kesit"] = "{ad}: symmetry plane (z = 1 mm), t = {t} s"
    tr["Qy"] = "toplam ısı salımı, tam kabin (kW)"
    en["Qy"] = "total heat release, full cabin (kW)"
    tr["hnot"] = tr["hnot"].replace("Tavanda havalandırma çıkışı (açık basınç sınırı); Mars'ta sıcak gaz\n"
                                    "0,65 s sonrası buradan tahliye oluyor, uzayda kaldırma olmadığı\n"
                                    "için kabinde kalıyor.",
                                    "Tavanda havalandırma çıkışı (açık basınç sınırı). Ana sonuç aralığı\n"
                                    "kaba ızgarayla karşılaştırma için aynı tutuldu; tahliyenin\n"
                                    "zamanı için alttaki bölge sıcaklıkları tablosuna bakın.")
    en["hnot"] = en["hnot"].replace("Ventilation outlet in the ceiling (open pressure boundary); on Mars\n"
                                    "the hot gas is vented through it after 0.65 s, in space it stays\n"
                                    "in the cabin because there is no buoyancy.",
                                    "Ventilation outlet in the ceiling (open pressure boundary). The main-\n"
                                    "result window is kept as on the coarse grid for comparison; see the\n"
                                    "regional temperature table below for when the gas is vented.")
    tr["dosya"], en["dosya"] = "figures/of_leak_thin.png", "figures/of_leak_thin_en.png"
    tr["bolge_b"] = tr["bolge_b"].replace("z = 0 kesiti", "simetri düzlemi")
    en["bolge_b"] = en["bolge_b"].replace("z = 0 slice", "symmetry plane")


def alev_yuksekligi(v):
    """Her kesit zamanı için y_alev = Σ y·(T−300) / Σ (T−300)  (z=0 kesiti, düzgün ızgara noktaları)."""
    import numpy as np
    sonuc = []
    for d in v.glob("postProcessing/kesit/*"):
        if not re.match(r"^[\d.e+-]+$", d.name):
            continue
        f = next(iter(sorted(d.glob("*.xy")) + sorted(d.glob("*.raw"))), None)
        if f is None:
            continue
        a = np.loadtxt(f, comments="#")
        w = np.clip(a[:, 3] - 300.0, 0, None)
        if w.sum() > 0:
            sonuc.append((float(d.name), float((a[:, 1] * w).sum() / w.sum()) * 1e3))
    return sorted(sonuc)


PENCERE = (0.40, 0.65)   # ana sonuç: tavandan tahliye başlamadan önceki kaldırma aralığı
BOLGE_T = (0.11, 0.21, 0.32, 0.42, 0.53, 0.63, 0.74, 0.84, 1.00)


def bolge_sicakliklari(v):
    """z = 0 kesitinde üst (y>50 mm) / orta / alt (y<-50 mm) ortalama T; {t: (üst, orta, alt)}."""
    import numpy as np
    sonuc = {}
    for d in v.glob("postProcessing/kesit/*"):
        if not re.match(r"^[\d.e+-]+$", d.name):
            continue
        f = next(iter(sorted(d.glob("*.xy")) + sorted(d.glob("*.raw"))), None)
        if f is None:
            continue
        a = np.loadtxt(f, comments="#")
        y, T = a[:, 1], a[:, 3]
        sonuc[float(d.name)] = (T[y > 0.05].mean(), T[(y >= -0.05) & (y <= 0.05)].mean(), T[y < -0.05].mean())
    return sonuc


def pencere_farki(hu, hm):
    """PENCERE içinde |Mars − uzay| en büyük olan an: (t, fark, uzay, Mars) ya da None."""
    ortak = [z for z in sorted(set(hu) & set(hm)) if PENCERE[0] - 1e-6 <= z <= PENCERE[1] + 1e-6]
    if not ortak:
        return None
    tm = max(ortak, key=lambda z: abs(hm[z] - hu[z]))
    return tm, hm[tm] - hu[tm], hu[tm], hm[tm]


def analiz():
    import numpy as np
    import pandas as pd
    veri, satir = {}, []
    for ad in VARYANTLAR:
        v = VAKA_KOK / ad
        t, Tm = dat_oku(v, "cellMax(T)")
        tq, Q = dat_oku(v, "volIntegrate(Qdot)")
        Q = [q * Q_CARPAN for q in Q]
        tut = next((a for a, b in zip(tq, Q) if b > 50.0), None)     # ısı salımı ilk kez 50 W'ı geçtiği an
        h = alev_yuksekligi(v)
        zt, kes = kesit_oku(v)
        T_sonra = [b for a, b in zip(t, Tm) if a > DARBE_SON]
        satir.append({"kosu": ad, "g_m_s2": abs(VARYANTLAR[ad][1]), "son_t_s": t[-1] if t else None,
                      "tutusma_suresi_s": tut,
                      "en_yuksek_T_darbe_sonrasi_K": max(T_sonra) if T_sonra else None,
                      "en_yuksek_T_K": max(Tm) if Tm else None,
                      "en_yuksek_isi_salimi_kW": max(Q) / 1e3 if Q else None,
                      "alev_yuksekligi_son_mm": h[-1][1] if h else None})
        veri[ad] = dict(t=t, Tm=Tm, tq=tq, Q=Q, h=h, zt=zt, kes=kes, bolge=bolge_sicakliklari(v))
    pf = pencere_farki(dict(veri["uzay"]["h"]), dict(veri["mars"]["h"]))
    for s_ in satir:
        s_["alev_yuksekligi_maks_fark_040_065_mm"] = pf[1] if pf else None
        s_["alev_yuksekligi_maks_fark_t_s"] = pf[0] if pf else None
    tab = pd.DataFrame(satir)
    for dil in ("tr", "en"):
        _ciz_s(dil, tab, veri)
    tab.to_csv(KOK / CSV_AD, index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 200)
    print(tab.to_string(index=False))
    print(f"Kaydedildi: {METIN_S['tr']['dosya']}, {METIN_S['en']['dosya']}, {CSV_AD}  "
          "(GÖSTERİM — deney verisiyle doğrulanmadı)")


def _ciz_s(dil, tab, veri):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    M = METIN_S[dil]
    def sayi(z, n=1):
        if z is None or z != z:                       # None / NaN (ör. koşu aralığa ulaşmamış)
            return "—"
        m = f"{z:.{n}f}"
        return m.replace(".", ",") if dil == "tr" else m
    fig = plt.figure(figsize=(18, 15.5))
    gs = fig.add_gridspec(4, 3, height_ratios=[1.15, 1.0, 0.42, 0.9], hspace=0.3, wspace=0.42)
    # üst: iki kesit + alev yüksekliği
    for j, ad in enumerate(VARYANTLAR):
        ax = fig.add_subplot(gs[0, j])
        d = veri[ad]
        a = d["kes"]
        if a is not None and a.ndim == 2 and a.shape[1] >= 4:
            tc = ax.tricontourf(a[:, 0] * 1000, a[:, 1] * 1000, a[:, 3], levels=np.linspace(300, 2600, 24),
                                cmap="inferno", extend="both")
            fig.colorbar(tc, ax=ax, label="T (K)", fraction=0.046, pad=0.03)
            ax.plot(ENJ_POZ[0] * 1000, ENJ_POZ[1] * 1000, ">", color="cyan", ms=8)
            ax.add_patch(plt.Circle((ATES_POZ[0] * 1000, ATES_POZ[1] * 1000), ATES_R * 1000, fill=False,
                                    color="cyan", ls="--"))
            if d["h"]:
                ax.axhline(d["h"][-1][1], color="white", ls=":", lw=1.2)
            ax.set_title(M["kesit"].format(ad=M["ad"][ad], t=sayi(d["zt"], 2)), fontsize=10)
        ax.set(xlabel=M["x"], ylabel=M["y"])
        ax.set_aspect("equal")
    axh = fig.add_subplot(gs[0, 2])
    axT = fig.add_subplot(gs[1, 0])
    axQ = fig.add_subplot(gs[1, 1])
    for ad in VARYANTLAR:
        d = veri[ad]
        if d["t"]:
            axT.plot(d["t"], d["Tm"], color=RENK_S[ad], lw=1.2, label=M["ad"][ad])
        if d["tq"]:
            axQ.plot(d["tq"], np.asarray(d["Q"]) / 1e3, color=RENK_S[ad], lw=1.2, label=M["ad"][ad])
        if d["h"]:
            axh.plot([a for a, b in d["h"]], [b for a, b in d["h"]], "o-", ms=3, color=RENK_S[ad],
                     label=M["ad"][ad])
    axh.axvspan(*PENCERE, color="#FFD54F", alpha=0.35, lw=0, label=M["pencere"])
    for a_ in (axT, axQ, axh):
        a_.axvspan(0, DARBE_SON, color="0.6", alpha=0.35, lw=0, label=M["darbe"])
        a_.set_xlabel("t (s)")
        a_.set_xlim(0, max([max(veri[k]["t"]) for k in veri if veri[k]["t"]] or [SURE]))
        a_.legend(fontsize=8)
    axT.set(ylabel=M["Tmy"], title=M["Tm"])
    axQ.set(ylabel=M["Qy"], title=M["Q"])
    axh.set(ylabel=M["hy"], title=M["h"])
    axh.title.set_fontsize(10)
    axu = fig.add_subplot(gs[1, 2])
    axu.axis("off")
    hu, hm = dict(veri["uzay"]["h"]), dict(veri["mars"]["h"])
    ortak = sorted(set(hu) & set(hm))
    pf = pencere_farki(hu, hm)
    if ortak and pf:
        tson = ortak[-1]
        tm, fw, wu, wm = pf
        axu.text(0.0, 0.64, M["hnot"].format(t=sayi(tson, 2), u=sayi(hu[tson]), m=sayi(hm[tson]),
                                             fm=sayi(abs(fw)), tm=sayi(tm, 2), wu=sayi(wu), wm=sayi(wm),
                                             yon=M["yukari"] if fw > 0 else M["asagi"]),
                 transform=axu.transAxes, fontsize=9.3, va="center", ha="left", family="DejaVu Sans",
                 bbox=dict(boxstyle="round,pad=0.6", fc="#E3F2FD", ec="#1565C0"))
    axu.text(0.5, 0.06, M["uyari"], transform=axu.transAxes, ha="center", va="center", fontsize=12.5,
             fontweight="bold", color="#C62828", wrap=True,
             bbox=dict(boxstyle="round,pad=0.8", fc="#FFEBEE", ec="#C62828"))
    axt = fig.add_subplot(gs[2, :])
    axt.axis("off")
    kol = ["kosu", "g_m_s2", "tutusma_suresi_s", "en_yuksek_T_darbe_sonrasi_K", "en_yuksek_T_K",
           "en_yuksek_isi_salimi_kW", "alev_yuksekligi_maks_fark_040_065_mm", "alev_yuksekligi_son_mm"]
    hucre = []
    for r in tab[kol].itertuples(index=False):
        hucre.append([M["ad"][r[0]], sayi(r[1], 2), sayi(r[2], 4), f"{r[3]:.0f}", f"{r[4]:.0f}",
                      sayi(r[5], 1), (sayi(r[6], 1) if r[0] == "mars" else "—"), sayi(r[7], 1)])
    tb = axt.table(cellText=hucre, colLabels=M["sutun"], bbox=[0.02, 0.05, 0.96, 0.9])
    tb.auto_set_font_size(False)
    tb.set_fontsize(9.5)
    # bölge ortalama sıcaklıkları tablosu
    axb = fig.add_subplot(gs[3, :])
    axb.axis("off")
    bu, bm = veri["uzay"]["bolge"], veri["mars"]["bolge"]
    zor = sorted(set(bu) & set(bm))
    satirlar, renkler = [], []
    for hedef in BOLGE_T:
        if not zor:
            break
        z = min(zor, key=lambda q: abs(q - hedef))
        if satirlar and satirlar[-1][0] == sayi(z, 2):
            continue
        satirlar.append([sayi(z, 2)] + [f"{x:.0f}" for x in bu[z]] + [f"{x:.0f}" for x in bm[z]])
        ic = PENCERE[0] - 1e-6 <= z <= PENCERE[1] + 0.02
        renkler.append(["#FFF8E1" if ic else "white"] * 7)
    if satirlar:
        tb2 = axb.table(cellText=satirlar, colLabels=M["bolge_s"], cellColours=renkler,
                        bbox=[0.12, 0.0, 0.76, 0.86])
        tb2.auto_set_font_size(False)
        tb2.set_fontsize(9.5)
        axb.set_title(M["bolge_b"], fontsize=10.5, y=0.88)
    fig.suptitle(M["baslik"], fontsize=13, y=0.93)
    fig.savefig(KOK / M["dosya"], dpi=200, bbox_inches="tight")
    plt.close(fig)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--kur", action="store_true")
    a.add_argument("--test", action="store_true")
    a.add_argument("--kos", action="store_true")
    a.add_argument("--analiz", action="store_true")
    a.add_argument("--ince", action="store_true", help="--analiz: ayrıntılı 3B koşular (of_kosular/sizinti3d_ince)")
    a.add_argument("--sure", type=float)
    a.add_argument("--cekirdek", type=int, default=CEKIRDEK)
    a.add_argument("--varyant", nargs="+", choices=list(VARYANTLAR), help="--kur/--kos/--test için koşu(lar)")
    k = a.parse_args()
    if k.kur:
        kur(k.varyant)
    if k.test:
        test(k.sure or 0.01, k.cekirdek, (k.varyant or ["uzay"])[0])
    if k.kos:
        kos(k.cekirdek, k.sure or SURE, k.varyant)
    if k.analiz:
        if k.ince:
            ince_ayarla()
        analiz()


if __name__ == "__main__":
    main()
