#!/usr/bin/env python3
"""
of_gaz.py — kabinde metan (gaz) sızıntısı ve alev: OpenFOAM 3B (uzay, Mars) ve 2B (4 yerçekimi) koşuları.
GÖSTERİM — deney verisiyle doğrulanmadı.

Kabin of_sizinti3d.py ile aynı: 20 cm küp, 5 duvar + tavan (+y) havalandırma çıkışı (1 atm), %21 O2 / N2, 300 K;
3B'de YARIM ALAN (z >= 0, z = 0 symmetryPlane), 5 mm taban + alev kutusunda 2,5 mm inceltme; Mars'ta
g = (0, -3,73, 0), p_rgh + hidrostatik başlatma. Fark: sprey yerine (-80, 0, 0) mm'deki 5 x 5 mm kare delikten
+x yönünde METAN GAZI (fvModels massSource: hücre bölgesine kütle + hız + bileşim). Toplam 3,0 mg/s (~150 W);
yarım alanda yarısı (1,5 mg/s, deliğin z > 0 yarısı). Çıkış hızı 18,3 cm/s, Re ≈ 65 (laminer).

Debi / delik seçimi (gaz_motoru.py jet modeli, Roper 1977 + µg %28 uzama; KALİBRE DEĞİL):
  5 x 5 mm (eşdeğer çap 5,64 mm), 3,0 mg/s:  µg L_f ≈ 59 mm, Mars ≈ 47 mm, 1 g ≈ 46 mm; yanma 0,98 / 0,94.
  Deliğin önünde 180 mm, üstünde 100 mm var -> alev ucu x ≈ -21 mm, sığar. 5 mg/s'de model µg alevinin
  ışınımla söneceğini öngörüyor (yanma 0,27) -> daha büyük debi seçilmedi. Delik 2,5 mm ızgarada 2 hücre.

Kurulum (OpenFOAM 14):
  - temel: smallPoolFire3D (CH4 / O2 / N2 / CO2 / H2O termo, fvDOM ışınımı + greyMeanReaction, p_rgh
    fvSolution / fvSchemes) ve KİMYASI: infinitelyFastChemistry (CH4 + 2O2 -> CO2 + 2H2O, C = 5). Akış laminer
    (Re ≈ 65; LES gereksiz).
    v1'de counterFlowFlame2D'nin sonlu hızlı tek adım Arrhenius'u (A = 5,2e16, Ta = 14906 K) denendi: bütün
    koşular tutuşma anında (t ≈ 0,04-0,1 s) kimya ODE'sinde SIGFPE ile çöktü (exp(-Ta/T), ODE içinde T < 0);
    seulex / rodas23, sıkı tolerans, maxDeltaT 1e-4 ve 2e-5 hiçbiri düzeltmedi (of_kosular/gaz_denemeler/).
    SONUÇ: alev karışımla sınırlı (Roper / gaz_motoru varsayımıyla aynı); sönme ve tutuşma gecikmesi YOK,
    tutuşturucu yalnız görsel / başlangıç ısısı.
  - Bütün varyantlarda p_rgh biçimi (uzayda g = 0): varyantlar arasında yalnız g değişir.
  - Tutuşturucu: (-65, 4, 0) mm, r = 6 mm küre, t = 0'da 1500 K (setFields) + 0-0,10 s ısı kaynağı (3B yarım
    alanda 2 W < iletim kaybı ~3,6 W, 2B'de hacim oranıyla), sonra kapanır. Metan cephesi ~0,05 s'de ulaşır.
  - fvConstraints limitTemperature 250-2800 K (alevin ~2300 K'ine dokunmaz; kaçak ısınmayı keser).
2B (of_kosular/gaz2d/<g>): aynı x-y kesiti, z'de tek hücre (1,25 mm, empty), 1,25 mm ızgara (160 x 160);
  delik 5 mm yarık, aynı çıkış hızı; 4 yerçekimi 0 / 1,62 / 3,73 / 9,81 m/s².

Kullanım:
  python3 of_gaz.py --kur [--vaka 3b_uzay 3b_mars 2b_0 2b_1.62 2b_3.73 2b_9.81] [--h2 1.25]
  python3 of_gaz.py --test --vaka 3b_uzay --sure 0.02         # kısa koşu: hız, Co, p_rgh, disk
  python3 of_gaz.py --kos --vaka 3b_uzay
  python3 of_gaz.py --buda <vaka klasörü>                     # bekçi: eski zamanlardan gereksiz alanlar
  python3 of_gaz.py --analiz                                   # PNG + CSV + gaz_motoru karşılaştırması
"""
import argparse
import json
import math
import re
import shutil
import subprocess
import time
from pathlib import Path

import of_tek_damla as ot

KOK = ot.KOK
OFK = ot.OF_KOK
K3 = OFK / "gaz3d_ince"
K2 = OFK / "gaz2d"
L = 0.20
N_TABAN = 40                       # 5 mm
KUTU3 = ((-0.095, -0.045, 0.0), (0.030, 0.100, 0.045))     # 2,5 mm inceltme (delik + alev + Mars tüyü)
SURE = 1.0
YAZMA = 0.01                       # 101 kare -> 10 s video (sıvı sızıntısı videolarıyla aynı)
CEKIRDEK = 15
DELIK = (-0.080, 0.0, 0.0)
DELIK_KENAR = 0.005                # m, kare
DEBI_TOPLAM = 3.0e-6               # kg/s CH4 (tam delik)
RHO_CH4 = 101325 * 16.04 / (8314.46 * 300.0)
U_CIKIS = DEBI_TOPLAM / (RHO_CH4 * DELIK_KENAR ** 2)   # m/s
ATES_POZ, ATES_R, ATES_T = (-0.065, 0.004, 0.0), 0.006, 1500.0
ATES_GUC3, ATES_SURE = 2.0, 0.10                        # W (3B yarım alan), s
# v1'de 10 W / 0,15 s idi: iletim kaybı (~4πkRΔT ≈ 3,6 W yarım alanda, 1500 K) aşıldığı için çekirdek durmadan ısındı
# (0,06 s'de 2714 K > T_ad), metan gelince kimya ODE'si SIGFPE ile çöktü (bkz. of_kosular/gaz_3b_uzay.log, v1).
T_SINIR = (250.0, 2800.0)                               # fvConstraints limitTemperature (kaçak ısınmaya karşı)
G2 = {"0": 0.0, "1.62": -1.62, "3.73": -3.73, "9.81": -9.81}
VAKALAR = {"3b_uzay": (K3 / "uzay", 0.0), "3b_mars": (K3 / "mars", -3.73),
           "3b_ay": (K3 / "ay", -1.62), "3b_dunya": (K3 / "dunya", -9.81),          # 4 yerçekimli 3B video için
           **{f"2b_{k}": (K2 / k, v) for k, v in G2.items()}}
GEREKLI = {"T", "CH4", "O2", "U", "Qdot", "uniform"}     # analiz / video / görüntüleyici (p_rgh, rho gerekmiyor:
#   of_gorsel_veri yalnız Qdot yoksa rho kullanır; Qdot her yazmada var)
TUT = Path("/opt/openfoam14/tutorials/multicomponentFluid")
NOT_TR = "GÖSTERİM — deney verisiyle doğrulanmadı"
NOT_EN = "DEMONSTRATION — not validated against experimental data"


def vaka_yolu(ad):
    return VAKALAR[ad][0]


def log_yolu(ad):
    return OFK / f"gaz_{ad}.log"


# ------------------------------------------------------------------ ızgara
def blockmesh(v, iki_b, h2):
    h = L / 2 * 1000
    if iki_b:
        n = int(round(L / (h2 * 1e-3)))
        z1 = h2
        yuz = {"disari": ["(3 7 6 2)"], "onarka": ["(0 3 2 1)", "(4 5 6 7)"],
               "duvar": ["(0 4 7 3)", "(1 2 6 5)", "(0 1 5 4)"]}
        tip = {"disari": "patch", "onarka": "empty", "duvar": "wall"}
        bl = f"hex (0 1 2 3 4 5 6 7) ({n} {n} 1) simpleGrading (1 1 1)"
    else:
        n = N_TABAN
        z1 = h
        yuz = {"disari": ["(3 7 6 2)"], "simetri": ["(0 3 2 1)"],
               "duvar": ["(0 4 7 3)", "(1 2 6 5)", "(0 1 5 4)", "(4 5 6 7)"]}
        tip = {"disari": "patch", "simetri": "symmetryPlane", "duvar": "wall"}
        bl = f"hex (0 1 2 3 4 5 6 7) ({n} {n} {n // 2}) simpleGrading (1 1 1)"
    b = "".join(f"    {ad}\n    {{\n        type {tip[ad]};\n        faces\n        (\n"
                + "".join(f"            {f}\n" for f in fl) + "        );\n    }\n" for ad, fl in yuz.items())
    (v / "system/blockMeshDict").write_text(
        ot.baslik("dictionary", "blockMeshDict", "system") +
        f"units [mm];\n\nvertices\n(\n    ({-h} {-h} 0)\n    ({h} {-h} 0)\n    ({h} {h} 0)\n"
        f"    ({-h} {h} 0)\n    ({-h} {-h} {z1})\n    ({h} {-h} {z1})\n    ({h} {h} {z1})\n    ({-h} {h} {z1})\n);\n\n"
        f"blocks\n(\n    {bl}\n);\n\nboundary\n(\n{b});\n")


def refine_dict(v):
    a, b = KUTU3
    (v / "system/refineMeshDict").write_text(
        ot.baslik("dictionary", "refineMeshDict", "system") +
        "coordinates\n{\n    type            global;\n    e1              (1 0 0);\n    e2              (0 1 0);\n"
        "    directions      (e1 e2 e3);\n}\n\n"
        f"zone\n{{\n    type            box;\n    box             ({a[0]} {a[1]} {a[2] - 0.001}) ({b[0]} {b[1]} {b[2]});\n}}\n")


# ------------------------------------------------------------------ alanlar
def _sinir(duvar, disari, ozel):
    """ozel: 'simetri' (symmetryPlane) ya da 'onarka' (empty)."""
    tip = "symmetryPlane" if ozel == "simetri" else "empty"
    return f"    duvar\n    {{\n{duvar}    }}\n    disari\n    {{\n{disari}    }}\n" \
           f"    {ozel}\n    {{\n        type            {tip};\n    }}\n"


def _alan(ad, boyut, ic, duvar, disari, ozel, kaynak=None, sinif="volScalarField"):
    s = ot.baslik(sinif, ad, "0") + f"dimensions      {boyut};\n\ninternalField   {ic};\n\nboundaryField\n{{\n" \
        + _sinir(duvar, disari, ozel) + "}\n"
    if kaynak is not None:
        s += (f"\nsources\n{{\n    sizinti\n    {{\n        type            uniformInletOutlet;\n"
              f"        uniformInletValue {kaynak};\n    }}\n}}\n")
    return s


def _io(d):
    return f"        type            inletOutlet;\n        inletValue      uniform {d};\n        value           uniform {d};\n"


ZG = "        type            zeroGradient;\n"


def sifir(v, ozel):
    Y = {"O2": 0.233, "N2": 0.767, "CH4": 0.0, "CO2": 0.0, "H2O": 0.0}
    kY = {"CH4": 1, "O2": 0, "N2": 0, "CO2": 0, "H2O": 0}
    s = {
        "T": _alan("T", "[temperature]", "uniform 300", ZG, _io(300), ozel, kaynak=300),
        "U": _alan("U", "[velocity]", "uniform (0 0 0)", "        type            noSlip;\n",
                   "        type            pressureInletOutletVelocity;\n        value           uniform (0 0 0);\n",
                   ozel, kaynak=f"({U_CIKIS:.5f} 0 0)", sinif="volVectorField"),
        "p": _alan("p", "[pressure]", "uniform 101325", "        type            calculated;\n        value           uniform 101325;\n",
                   "        type            calculated;\n        value           uniform 101325;\n", ozel),
        "p_rgh": _alan("p_rgh", "[pressure]", "uniform 0",
                       "        type            fixedFluxPressure;\n        value           uniform 0;\n",
                       "        type            prghTotalHydrostaticPressure;\n        p0              uniform 0;\n"
                       "        gamma           1;\n        value           uniform 0;\n", ozel),
        "ph_rgh": _alan("ph_rgh", "[pressure]", "uniform 0",
                        "        type            fixedFluxPressure;\n        value           uniform 0;\n",
                        "        type            fixedValue;\n        value           uniform 0;\n", ozel),
        "G": _alan("G", "[heatFluxDensity]", "uniform 0",
                   "        type            MarshakRadiation;\n        emissivityMode  lookup;\n"
                   "        emissivity      uniform 1;\n        value           uniform 0;\n",
                   "        type            MarshakRadiation;\n        emissivityMode  lookup;\n"
                   "        emissivity      uniform 1;\n        value           uniform 0;\n", ozel),
        "IDefault": _alan("IDefault", "[heatFluxDensity]", "uniform 0",
                          "        type            greyDiffusiveRadiation;\n        emissivityMode  lookup;\n"
                          "        emissivity      uniform 1;\n        value           uniform 0;\n",
                          "        type            greyDiffusiveRadiation;\n        emissivityMode  lookup;\n"
                          "        emissivity      uniform 1;\n        value           uniform 0;\n", ozel),
        "Ydefault": _alan("Ydefault", "[]", "uniform 0", ZG, _io(0), ozel, kaynak=0),
    }
    for t, y in Y.items():
        s[t] = _alan(t, "[]", f"uniform {y}", ZG, _io(y), ozel, kaynak=kY[t])
    z = v / "0"
    if z.exists():
        shutil.rmtree(z)
    z.mkdir()
    for ad, icerik in s.items():
        (z / ad).write_text(icerik)


# ------------------------------------------------------------------ sabitler / sistem
def sabit_sistem(v, g, iki_b, h2):
    sp, cf = TUT / "smallPoolFire3D", TUT / "counterFlowFlame2D"
    (v / "constant").mkdir(parents=True, exist_ok=True)
    (v / "system").mkdir(parents=True, exist_ok=True)
    for f in ("physicalProperties", "thermo.compressibleGas", "radiationProperties"):
        shutil.copy(sp / "constant" / f, v / "constant" / f)
    for f in ("reaction", "reactionProperties"):                    # infinitelyFastChemistry (smallPoolFire3D)
        shutil.copy(sp / "constant" / f, v / "constant" / f)
    shutil.copy(cf / "constant" / "momentumTransport", v / "constant" / "momentumTransport")   # laminer
    for f in ("fvSchemes", "fvSolution"):
        shutil.copy(sp / "system" / f, v / "system" / f)
    (v / "constant/pRef").write_text(ot.baslik("uniformDimensionedScalarField", "pRef", "constant") +
                                     "dimensions      [pressure];\nvalue           101325;\n")
    (v / "constant/hRef").write_text(ot.baslik("uniformDimensionedScalarField", "hRef", "constant") +
                                     f"dimensions      [length];\nvalue           {L / 2};\n")
    (v / "constant/g").write_text(ot.baslik("uniformDimensionedVectorField", "g", "constant") +
                                  f"dimensions      [acceleration];\nvalue           (0 {g} 0);\n")
    # kütle kaynağı (delik) + tutuşturucu
    hz = 1.0 * (h2 * 1e-3) if iki_b else None
    if iki_b:
        a0 = (DELIK[0] - h2 * 1e-3 + 1e-5, -DELIK_KENAR / 2 + 1e-5, 0.0)
        a1 = (DELIK[0] - 1e-5, DELIK_KENAR / 2 - 1e-5, hz)
        debi = RHO_CH4 * U_CIKIS * DELIK_KENAR * hz          # yarık: aynı çıkış hızı
        atv = math.pi * ATES_R ** 2 * hz                       # 2B'de tutuşturucu hacmi (disk x kalınlık)
        guc = ATES_GUC3 * atv / (2 / 3 * math.pi * ATES_R ** 3)
    else:
        a0 = (DELIK[0] - 0.0025 + 1e-5, -DELIK_KENAR / 2 + 1e-5, 0.0)
        a1 = (DELIK[0] - 1e-5, DELIK_KENAR / 2 - 1e-5, DELIK_KENAR / 2 - 1e-5)
        debi = DEBI_TOPLAM / 2                                 # yarım alan: deliğin z > 0 yarısı
        guc = ATES_GUC3
    a = ATES_POZ
    (v / "constant/fvModels").write_text(
        ot.baslik("dictionary", "fvModels", "constant") +
        "radiation\n{\n    type    radiation;\n    libs    (\"libradiationModels.so\");\n}\n\n"
        "sizinti\n{\n    type            massSource;\n    cellZone\n    {\n        type    box;\n"
        f"        box     ({a0[0]:.6f} {a0[1]:.6f} {a0[2]:.6f}) ({a1[0]:.6f} {a1[1]:.6f} {a1[2]:.6f});\n    }}\n"
        f"    massFlowRate    {debi:.6e};\n}}\n\n"
        "atesleyici\n{\n    type            heatSource;\n    cellZone\n    {\n        type    sphere;\n"
        f"        centre  ({a[0]} {a[1]} {a[2]});\n        radius  {ATES_R};\n    }}\n"
        f"    Q               table ((0 {guc:.4g}) ({ATES_SURE} {guc:.4g}) ({ATES_SURE + 1e-4} 0) (1000 0));\n}}\n")
    (v / "system/fvConstraints").write_text(
        ot.baslik("dictionary", "fvConstraints", "system") +
        f"limitT\n{{\n    type            limitTemperature;\n    cellZone        all;\n    min             {T_SINIR[0]};\n"
        f"    max             {T_SINIR[1]};\n}}\n")
    (v / "system/setFieldsDict").write_text(
        ot.baslik("dictionary", "setFieldsDict", "system") +
        "zones\n{\n    ateslemeKaynagi\n    {\n        type        sphere;\n"
        f"        centre      ({a[0]} {a[1]} {a[2]});\n        radius      {ATES_R};\n"
        f"        values\n        {{\n            T {ATES_T};\n        }}\n    }}\n}}\n")
    (v / "system/decomposeParDict").write_text(
        ot.baslik("dictionary", "decomposeParDict", "system") +
        f"numberOfSubdomains {CEKIRDEK};\n\ndecomposer      scotch;\n")
    return debi, guc


def kontrol(v, bitis, yazma=YAZMA, iki_b=False, h2=1.25):
    (v / "system/controlDict").write_text(
        ot.baslik("dictionary", "controlDict", "system") +
        f"solver          multicomponentFluid;\n\nstartFrom       latestTime;\nstartTime       0;\n"
        f"stopAt          endTime;\nendTime         {bitis};\ndeltaT          1e-05;\n"
        f"writeControl    adjustableRunTime;\nwriteInterval   {min(yazma, bitis / 2)};\npurgeWrite      0;\n"
        "writeFormat     binary;\nwritePrecision  6;\nwriteCompression off;\ntimeFormat      general;\n"
        "timePrecision   6;\nadjustTimeStep  yes;\nmaxCo           0.4;\nmaxDeltaT       5e-4;\n"
        "runTimeModifiable yes;\n")
    zk = (h2 * 1e-3 / 2) if iki_b else 0.001
    (v / "system/functions").write_text(
        ot.baslik("dictionary", "functions", "system") +
        "#includeFunc Qdot(executeControl=timeStep)\n#includeFunc cellMax(T)\n#includeFunc volIntegrate(Qdot)\n"
        f"#includeFunc cutPlaneSurface(point=(0 0 {zk}), normal=(0 0 1), fields=(T CH4 O2 Qdot), "
        "surfaceFormat=raw, writeControl=writeTime, name=kesit)\n")


def kur_vaka(ad, h2=1.25):
    v, g = VAKALAR[ad]
    iki_b = ad.startswith("2b")
    ot.guvenli_sil(v)
    v.mkdir(parents=True)
    debi, guc = sabit_sistem(v, g, iki_b, h2)
    blockmesh(v, iki_b, h2)
    sifir(v, "onarka" if iki_b else "simetri")
    if not iki_b:
        refine_dict(v)
    kontrol(v, SURE, iki_b=iki_b, h2=h2)
    log = OFK / f"gaz_{ad}_hazirlik.log"
    log.unlink(missing_ok=True)
    adimlar = ["blockMesh"] + ([] if iki_b else ["refineMesh -dict system/refineMeshDict -overwrite"]) + \
              ["setFields", "checkMesh -constant"]
    for cmd in adimlar:
        if ot.kabuk(cmd, v, log=log) != 0:
            raise SystemExit(f"{ad}: '{cmd.split()[0]}' başarısız, bkz. {log}")
    (v / f"{v.name}.foam").touch()
    m = re.findall(r"^\s*cells:\s+(\d+)", log.read_text(), flags=re.M)
    bilgi = {"vaka": ad, "g": g, "hucre": int(m[-1]) if m else None, "debi_kg_s": debi, "u_cikis_m_s": U_CIKIS,
             "atesleyici_W": guc, "h2_mm": h2 if iki_b else None}
    (v / "bilgi.json").write_text(json.dumps(bilgi, ensure_ascii=False, indent=1))
    print(f"Kuruldu: {ad}  {bilgi}")
    return bilgi


# ------------------------------------------------------------------ koşu
def kos(ad, bitis=SURE, cekirdek=CEKIRDEK, hedef=None, log=None):
    v = hedef or vaka_yolu(ad)
    log = log or log_yolu(ad)
    s = (v / "system/controlDict").read_text()
    (v / "system/controlDict").write_text(re.sub(r"endTime\s+[\d.e+-]+;", f"endTime         {bitis};", s))
    d = (v / "system/decomposeParDict").read_text()
    (v / "system/decomposeParDict").write_text(re.sub(r"numberOfSubdomains\s+\d+;", f"numberOfSubdomains {cekirdek};", d))
    if not any(v.glob("processor*")):
        if ot.kabuk("decomposePar -force", v, log=OFK / f"gaz_{ad}_hazirlik.log") != 0:
            raise SystemExit(f"{ad}: decomposePar başarısız")
    if not zaman_klasorleri(v) and Path(log).exists():
        # sıfırdan başlıyor: eski koşunun logu kenara (bekçi eski logun zamanını "log yazılmıyor" sanmasın)
        Path(log).replace(Path(str(log) + ".onceki"))
    bas = time.time()
    p = subprocess.Popen(["bash", "-c", f"source {ot.BASHRC} >/dev/null 2>&1; "
                                        f"exec mpirun --oversubscribe -np {cekirdek} foamRun -parallel"],
                         cwd=v, stdout=open(log, "a"), stderr=subprocess.STDOUT)
    (OFK / f"gaz_{ad}.pid").write_text(str(p.pid))
    p.wait()
    return p.returncode, time.time() - bas


def bitti_mi(v, log, bitis):
    """Koşu GERÇEKTEN bitti mi: son yazılmış zaman = endTime ve log'da 'End' satırı."""
    zs = zaman_klasorleri(v)
    son = float(zs[-1]) if zs else 0.0
    metin = Path(log).read_text(errors="replace") if Path(log).exists() else ""
    end = re.search(r"^End\s*$", metin[-20000:], flags=re.M) is not None
    fpe = "Floating point exception" in metin[-200000:] or "FOAM FATAL" in metin[-200000:]
    return {"son_zaman": son, "endTime": bitis, "zaman_tamam": abs(son - bitis) < 1e-6 * max(1, bitis),
            "End": end, "cokme": fpe}


def test(ad, sure, cekirdek=CEKIRDEK):
    """Kurulu vakanın kopyasında kısa koşu: duvar saati / sim. saniye, Co, p_rgh, yazma boyutu."""
    kaynak = vaka_yolu(ad)
    hedef = kaynak.parent / f"test_{kaynak.name}"
    ot.guvenli_sil(hedef)
    shutil.copytree(kaynak, hedef, ignore=shutil.ignore_patterns("processor*", "postProcessing"))
    kontrol(hedef, sure, yazma=sure / 2, iki_b=ad.startswith("2b"),
            h2=json.loads((kaynak / "bilgi.json").read_text()).get("h2_mm") or 1.25)
    log = OFK / f"gaz_test_{ad}.log"
    log.unlink(missing_ok=True)
    rc, gec = kos(ad, sure, cekirdek, hedef=hedef, log=log)
    metin = log.read_text(errors="replace")
    z = re.findall(r"^Time = ([\d.e+-]+)", metin, flags=re.M)
    co = re.findall(r"Courant Number mean: [\d.e+-]+ max: ([\d.e+-]+)", metin)
    yaz = sorted({d.name for d in (hedef / "processor0").iterdir() if re.match(r"^[\d.e+-]+$", d.name)}, key=float) \
        if (hedef / "processor0").exists() else []
    son = yaz[-1] if yaz else None
    boy = sum(f.stat().st_size for f in hedef.glob(f"processor*/{son}/**/*") if f.is_file()) if son else 0
    boy_g = sum(f.stat().st_size for f in hedef.glob(f"processor*/{son}/*") if f.is_file() and f.name in GEREKLI) \
        if son else 0
    t_son = float(z[-1]) if z else 0.0
    b = bitti_mi(hedef, log, sure)
    sonuc = {"vaka": ad, "sure": sure, "rc": rc, **b, "duvar_s": gec, "t_son": t_son, "adim": len(z),
             "s_per_sim_s": gec / t_son if t_son > 0 else None, "courant_max": float(co[-1]) if co else None,
             "p_rgh_cozum": len(re.findall(r"Solving for p_rgh", metin)), "yazma_MB_tam": boy / 1e6,
             "yazma_MB_gerekli": boy_g / 1e6,
             "hata": rc != 0 or not b["zaman_tamam"] or not b["End"] or b["cokme"]}
    print(json.dumps(sonuc, ensure_ascii=False), flush=True)
    (hedef.parent / f"test_{ad}.json").write_text(json.dumps(sonuc))
    return sonuc


# ------------------------------------------------------------------ süre planı
SURE_SINIRI_SA = 9.0


def plan():
    """Kısa testlerden (test_*.json, 15 çekirdek) tam koşu süresi tahmini. 3B uzay / Mars kendi testinden,
    2B dört koşu 2b_9.81 testinden. Toplam > 9 sa ise 2B ızgara kabalaştırılır (1,25 -> 1,5 -> 2,0 mm; süre ~ h^-3)
    ve 2B vakalar yeniden kurulur. Tahmin muhafazakârdır (ilk adımlarda Δt küçük)."""
    oku = lambda ad: json.loads(((K3 if ad.startswith("3b") else K2) / f"test_{ad}.json").read_text())
    t3u, t3m, t2 = oku("3b_uzay"), oku("3b_mars"), oku("2b_9.81")
    for t in (t3u, t3m, t2):
        if t["rc"] != 0 or t["hata"] or not t["s_per_sim_s"]:
            raise SystemExit(f"test başarısız: {t}")
    sa3 = (t3u["s_per_sim_s"] + t3m["s_per_sim_s"]) * SURE / 3600
    h2, sa2 = 1.25, 4 * t2["s_per_sim_s"] * SURE / 3600
    for yeni in (1.5, 2.0):
        if sa3 + sa2 <= SURE_SINIRI_SA:
            break
        sa2 *= (h2 / yeni) ** 3
        h2 = yeni
    nyaz = int(round(SURE / YAZMA)) + 1
    disk_GB = (2 * nyaz * t3u["yazma_MB_gerekli"] + 4 * nyaz * t2["yazma_MB_gerekli"] * (1.25 / h2) ** 2
               + 2 * 2 * t3u["yazma_MB_tam"] + 4 * 2 * t2["yazma_MB_tam"]) / 1e3
    sonuc = {"tahmin_3b_sa": sa3, "tahmin_2b_sa": sa2, "toplam_sa": sa3 + sa2, "h2_mm": h2,
             "disk_tahmin_GB": disk_GB, "p_rgh_mars": t3m["p_rgh_cozum"] > 0, "sinir_sa": SURE_SINIRI_SA}
    if h2 != 1.25:
        for ad in [a for a in VAKALAR if a.startswith("2b")]:
            kur_vaka(ad, h2)
    (OFK / "gaz_plan.json").write_text(json.dumps(sonuc, ensure_ascii=False, indent=1))
    print(json.dumps(sonuc, ensure_ascii=False))
    return sonuc


def incelt(adlar):
    """Videolar / analiz bittikten sonra: görüntüleyicinin 20 karesi (of_gorsel_veri.sec) + son zaman dışındaki
    processor zamanlarını siler (postProcessing korunur). Yalnız of_kosular/ altında."""
    import of_gorsel_veri as ogv
    for ad in adlar:
        v = vaka_yolu(ad).resolve()
        if OFK.resolve() not in v.parents:
            raise SystemExit(f"silme reddedildi: {v}")
        zs = zaman_klasorleri(v)
        if not zs:
            continue
        sakla = {b for a, b in ogv.sec(ogv.zamanlar(v))} | {zs[-1]}
        n = 0
        for z in zs:
            if z not in sakla:
                for pd in v.glob(f"processor*/{z}"):
                    shutil.rmtree(pd)
                n += 1
        print(f"{ad}: {n} zaman silindi, {len(sakla)} kaldı", flush=True)


def test_temizle():
    for d in list(K3.glob("test_*")) + list(K2.glob("test_*")):
        if d.is_dir():
            ot.guvenli_sil(d)


# ------------------------------------------------------------------ video denetimi
def video_denetle(dosyalar, en_az_kare=100, en_az_sn=9.5, en_az_kB=150, en_az_parlak=0.003, panel4=False):
    """Boş video denetimi (v1'deki 40-65 kB / 0,2-0,3 s videolar gibi): kare sayısı, süre, boyut ve orta karede
    parlak piksel oranı (luminans > 60: sıcak bölge / eş-yüzey; arka plan ve 300 K siyah). Hepsi tutmalı.
    Not: görevdeki '> 1 MB' eşiği koyu arka planlı, sade kesit videolarında geçerli videoyu da reddediyor
    (51 karelik geçerli kesit videosu 0,16 MB); bu yüzden boşluk doğrudan ölçülür, boyut ayrıca raporlanır."""
    import numpy as np
    from PIL import Image
    tamam, satir = True, []
    for f in dosyalar:
        f = Path(f)
        if not f.exists():
            satir.append({"dosya": f.name, "tamam": False, "neden": "yok"})
            tamam = False
            continue
        pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                             "stream=nb_read_frames:format=duration", "-of", "json", str(f)],
                            capture_output=True, text=True)
        j = json.loads(pr.stdout or "{}")
        kare = int(j.get("streams", [{}])[0].get("nb_read_frames", 0) or 0)
        sn = float(j.get("format", {}).get("duration", 0) or 0)
        tmp = Path("/tmp") / f"gaz_vd_{f.stem}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{sn / 2:.2f}", "-i", str(f), "-frames:v", "1", str(tmp)])
        parlak, paneller = 0.0, []
        if tmp.exists():
            if panel4:     # 2 x 2: üst 96 px başlık, alt 88 px açıklama/not; her panelde etiket bandı (46 px) hariç
                b = np.asarray(Image.open(tmp).convert("L"), dtype=float)[96:-88, :-140]   # sağdaki renk çubuğu hariç
                h, w = b.shape[0] // 2, (b.shape[1] + 140) // 2
                for sy in range(2):
                    for sx in range(2):
                        q = b[sy * h + 46:(sy + 1) * h, sx * w:min((sx + 1) * w, b.shape[1])]
                        paneller.append(round(float((q > 60).mean()), 4))
                parlak = min(paneller)
            else:
                a = np.asarray(Image.open(tmp).convert("L"), dtype=float)[96:-52]     # başlık / not bantları hariç
                parlak = float((a > 60).mean())
            tmp.unlink()
        kB = f.stat().st_size / 1e3
        ok = kare >= en_az_kare and sn >= en_az_sn and kB >= en_az_kB and parlak >= en_az_parlak
        neden = [] if ok else [n for n, c in (("kare", kare < en_az_kare), ("süre", sn < en_az_sn),
                                              ("boyut", kB < en_az_kB), ("içerik", parlak < en_az_parlak)) if c]
        satir.append({"dosya": f.name, "tamam": ok, "kare": kare, "sure_s": round(sn, 2), "boyut_MB": round(kB / 1e3, 3),
                      "parlak_oran": round(parlak, 4), **({"paneller_solust_sagust_solalt_sagalt": paneller} if panel4 else {}),
                      "neden": ",".join(neden)})
        tamam &= ok
    for r in satir:
        print(json.dumps(r, ensure_ascii=False))
    return tamam


# ------------------------------------------------------------------ bekçi yardımcıları
def zaman_klasorleri(v):
    p0 = Path(v) / "processor0"
    if not p0.exists():
        return []
    return sorted((d.name for d in p0.iterdir() if re.match(r"^[\d.e+-]+$", d.name) and d.name != "0"), key=float)


def buda(v, koru=2):
    """Son `koru` zaman dışındakilerden analizde / videoda gerekmeyen alanları siler (yalnız of_kosular/ altında)."""
    v = Path(v).resolve()
    if OFK.resolve() not in v.parents:
        raise SystemExit(f"budama reddedildi: {v}")
    kayit = v / "budanan.txt"
    yapilan = set(kayit.read_text().split()) if kayit.exists() else set()
    yeni, kazanc = [], 0
    zs = zaman_klasorleri(v)
    for z in zs[:-koru] if koru else zs:
        if z in yapilan:
            continue
        for pd in v.glob(f"processor*/{z}"):
            for f in pd.iterdir():
                if f.name not in GEREKLI:
                    kazanc += f.stat().st_size if f.is_file() else sum(x.stat().st_size for x in f.rglob("*") if x.is_file())
                    shutil.rmtree(f) if f.is_dir() else f.unlink()
        yeni.append(z)
    if yeni:
        with open(kayit, "a") as k:
            k.write("\n".join(yeni) + "\n")
    return yeni, kazanc


# ------------------------------------------------------------------ analiz
def dat_oku(v, ad):
    t, y = [], []
    for f in sorted(Path(v).glob(f"postProcessing/{ad}/*/volFieldValue.dat")):
        for s in open(f, errors="replace"):
            if s.startswith("#") or not s.strip():
                continue
            p = s.split()
            try:
                t.append(float(p[0]))
                y.append(float(p[1]))
            except (ValueError, IndexError):
                pass
    import numpy as np
    t, y = np.array(t), np.array(y)
    i = np.argsort(t, kind="stable")
    return t[i], y[i]


def kesitler(v):
    """[(t, dizi[x y z T CH4 O2 Qdot])] (z = 0 düzlemine yakın kesit)."""
    import numpy as np
    out = []
    for d in Path(v).glob("postProcessing/kesit/*"):
        if not re.match(r"^[\d.e+-]+$", d.name):
            continue
        f = next(iter(sorted(d.glob("*.xy")) + sorted(d.glob("*.raw"))), None)
        if f is None:
            continue
        a = np.loadtxt(f, comments="#")
        if a.ndim == 2 and a.shape[1] >= 7:
            out.append((float(d.name), a))
    return sorted(out, key=lambda x: x[0])


T_ALEV = 1500.0
T_ALEV2 = 1200.0              # µg alevi ~1500 K'e çıkmayabiliyor (ışınım + düşük gerinim)


def alev_olcutleri(a):
    """kesit noktalarından: alev boyu (delikten T >= 1500 K bölgesinin en uzak noktası, mm), ısı salımı ağırlıklı
    alev merkezi (x, y mm), Tmax kesit."""
    import numpy as np
    x, y, T, Q = a[:, 0], a[:, 1], a[:, 3], a[:, 6]
    r = np.hypot(x - DELIK[0], y - DELIK[1])
    sic = T >= T_ALEV
    L_T = float(r[sic].max() * 1e3) if sic.any() else 0.0
    sic2 = T >= T_ALEV2
    L_T2 = float(r[sic2].max() * 1e3) if sic2.any() else 0.0
    w = np.clip(Q, 0, None)
    if w.sum() > 0:
        xc, yc = float((x * w).sum() / w.sum() * 1e3), float((y * w).sum() / w.sum() * 1e3)
        q5 = w >= 0.05 * w.max()
        L_Q = float(r[q5].max() * 1e3)
    else:
        xc = yc = L_Q = float("nan")
    return {"L_T1500_mm": L_T, "L_T1200_mm": L_T2, "L_Q5_mm": L_Q, "x_alev_mm": xc, "y_alev_mm": yc, "Tmax_kesit": float(T.max())}


def bilgi_oku(ad):
    f = vaka_yolu(ad) / "bilgi.json"
    return json.loads(f.read_text()) if f.exists() else {}


def analiz():
    import numpy as np
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import gaz_motoru as gm
    seri, satir = {}, []
    for ad in VAKALAR:
        v = vaka_yolu(ad)
        if not (v / "postProcessing").exists():
            print(f"{ad}: sonuç yok, atlandı")
            continue
        b = bilgi_oku(ad)
        iki_b = ad.startswith("2b")
        tT, Tm = dat_oku(v, "cellMax(T)")
        tq, Q = dat_oku(v, "volIntegrate(Qdot)")
        # 3B yarım alan -> tam kabin x2 (W);  2B -> birim derinlik başına (W/m) = Q / Δz
        Qc = Q * 2 if not iki_b else Q / ((b.get("h2_mm") or 1.25) * 1e-3)
        ks = kesitler(v)
        ol = [(t, alev_olcutleri(a)) for t, a in ks]
        seri[ad] = {"tT": tT, "Tm": Tm, "tq": tq, "Q": Qc, "ks": ks, "ol": ol, "g": -VAKALAR[ad][1], "iki_b": iki_b}
        son = [o for t, o in ol if 0.7 <= t <= 1.0 + 1e-9]          # yarı-durağan pencere: son 0,3 s
        ort = {k: float(np.nanmean([o[k] for o in son])) if son else float("nan") for k in
               ("L_T1500_mm", "L_T1200_mm", "L_Q5_mm", "y_alev_mm", "x_alev_mm")}
        pen = (tq >= 0.7)
        satir.append({"vaka": ad, "g_m_s2": -VAKALAR[ad][1], "boyut": "2B" if iki_b else "3B",
                      "hucre": b.get("hucre"), "t_son_s": float(tT[-1]) if len(tT) else None,
                      "Tmax_K_son03s": float(np.max(Tm[tT >= 0.7])) if (tT >= 0.7).any() else None,
                      "Q_son03s": float(np.mean(Qc[pen])) if pen.any() else None,
                      "Q_birim": "W/m" if iki_b else "W (tam kabin)", **ort})
    if not satir:
        raise SystemExit("hiç sonuç yok")
    tab = pd.DataFrame(satir)
    tab.to_csv(KOK / "of_gaz_sonuc.csv", index=False, encoding="utf-8-sig")
    # gaz_motoru karşılaştırması (3B: eksenel simetrik jet modeli ile aynı geometri)
    d_eq = 2 * DELIK_KENAR * 1e3 / math.sqrt(math.pi)
    kar = []
    for ad, g in (("3b_uzay", 1e-4), ("3b_mars", 0.38), ("3b_ay", 0.165), ("3b_dunya", 1.0)):
        if ad not in seri:
            continue
        r = gm.gaz_motoru(g, 21, 101.325, None, d_eq, "methane", "gas_jet", debi_mg_s=DEBI_TOPLAM * 1e6,
                          min_oksijen_hesapla=False)
        # düşük momentumlu sızıntı µg'de top biçimli: motorun küre (sızıntı) geometrisi de (R_f; delik çapında küre)
        rk = gm.gaz_motoru(g, 21, 101.325, None, d_eq, "methane", "leak", debi_mg_s=DEBI_TOPLAM * 1e6,
                           min_oksijen_hesapla=False)
        x = tab[tab.vaka == ad]
        al = lambda k: float(x[k].iloc[0]) if len(x) else float("nan")
        of_LQ = al("L_Q5_mm")
        kar.append({"vaka": ad, "g_g0": g, "gaz_motoru_jet_L_f_mm": r["alev_boyu"], "gaz_motoru_jet_yanma": r["yanma"],
                    "gaz_motoru_jet_T_f_K": r["sicaklik"], "gaz_motoru_kure_R_f_mm": rk["alev_yaricapi"],
                    "gaz_motoru_kure_yanma": rk["yanma"], "gaz_motoru_kure_T_f_K": rk["sicaklik"],
                    "OpenFOAM_L_Q5_mm": of_LQ, "OpenFOAM_L_T1200_mm": al("L_T1200_mm"),
                    "OpenFOAM_L_T1500_mm": al("L_T1500_mm"), "OpenFOAM_Tmax_K": al("Tmax_K_son03s"),
                    "oran_OF_LQ5_bolu_motor_jet": of_LQ / r["alev_boyu"] if r["alev_boyu"] else None,
                    "oran_OF_LQ5_bolu_motor_kure_R": of_LQ / rk["alev_yaricapi"] if rk["alev_yaricapi"] else None,
                    "not": "gaz_motoru jet ve küre modelleri bu yakıt/geometri için KALİBRE DEĞİL; OpenFOAM " + NOT_TR})
    kt = pd.DataFrame(kar)
    kt.to_csv(KOK / "of_gaz_motor_karsilastirma.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 220)
    print(tab.round(2).to_string(index=False))
    print(kt.round(3).to_string(index=False))
    # ---- grafikler (TR + EN)
    for dil in ("tr", "en"):
        M = METIN[dil]
        # 1) T haritaları: 3B uzay / Mars, 4 an
        anlar = (0.25, 0.5, 0.75, 1.0)
        for grup, adlar in (("3b", ["3b_uzay", "3b_mars", "3b_ay", "3b_dunya"]), ("2b", [f"2b_{k}" for k in G2])):
            adlar = [a for a in adlar if a in seri and seri[a]["ks"]]
            if not adlar:
                continue
            fig, axs = plt.subplots(len(adlar), len(anlar), figsize=(4.2 * len(anlar), 3.9 * len(adlar)),
                                    squeeze=False)
            for i, ad in enumerate(adlar):
                for j, ta in enumerate(anlar):
                    t, a = min(seri[ad]["ks"], key=lambda k: abs(k[0] - ta))
                    ax = axs[i, j]
                    tc = ax.tricontourf(a[:, 0] * 1e3, a[:, 1] * 1e3, a[:, 3], levels=np.linspace(300, 2300, 21),
                                        cmap="inferno", extend="max")
                    ax.plot(DELIK[0] * 1e3, 0, "c>", ms=7)
                    ax.set_aspect("equal")
                    ax.set_xlim(-100, 100)
                    ax.set_ylim(-100, 100)
                    ax.set_title(f"{M['vaka'][ad]}  t = {t:.2f} s".replace(".", M["ond"]), fontsize=10)
                    if j == 0:
                        ax.set_ylabel("y (mm)")
                    if i == len(adlar) - 1:
                        ax.set_xlabel("x (mm)")
            fig.colorbar(tc, ax=axs, label="T (K)", shrink=0.8)
            fig.suptitle(f"{M['harita_' + grup]} — {M['not']}", fontsize=12)
            f = KOK / f"of_gaz_harita_{grup}{'' if dil == 'tr' else '_en'}.png"
            fig.savefig(f, dpi=130)
            plt.close(fig)
            print("Kaydedildi:", f.name)
        # 2) karşılaştırma eğrileri
        fig, axs = plt.subplots(2, 2, figsize=(14, 9))
        renk = {"3b_uzay": "#1565C0", "3b_mars": "#C62828", "3b_ay": "#616161", "3b_dunya": "#1B5E20",
                "2b_0": "#64B5F6", "2b_1.62": "#9E9E9E",
                "2b_3.73": "#EF9A9A", "2b_9.81": "#2E7D32"}
        for ad, s in seri.items():
            st = "-" if not s["iki_b"] else "--"
            axs[0, 0].plot(s["tT"], s["Tm"], st, color=renk[ad], lw=1.2, label=M["vaka"][ad])
            axs[0, 1].plot(s["tq"], s["Q"] if not s["iki_b"] else s["Q"] / 1e3, st, color=renk[ad], lw=1.2,
                           label=M["vaka"][ad])
            to = [t for t, o in s["ol"]]
            axs[1, 0].plot(to, [o["y_alev_mm"] for t, o in s["ol"]], st + "o", ms=3, color=renk[ad], label=M["vaka"][ad])
            axs[1, 1].plot(to, [o["L_Q5_mm"] for t, o in s["ol"]], st + "o", ms=3, color=renk[ad], label=M["vaka"][ad])
        for r in kar:
            if r["gaz_motoru_jet_L_f_mm"]:
                axs[1, 1].axhline(r["gaz_motoru_jet_L_f_mm"], color=renk[r["vaka"]], ls=":", lw=1.5,
                                  label=f"gaz_motoru jet: {M['vaka'][r['vaka']]}")
        for ax in axs.ravel():
            ax.axvspan(0, ATES_SURE, color="0.6", alpha=0.25)
            ax.set_xlabel("t (s)")
            ax.grid(alpha=0.3)
        axs[0, 0].set(ylabel="Tmax (K)", title=M["tmax"])
        axs[0, 1].set(ylabel=M["q_ek"], title=M["q"])
        axs[1, 0].set(ylabel="y (mm)", title=M["merkez"])
        axs[1, 1].set(ylabel="L (mm)", title=M["boy"])
        axs[0, 0].legend(fontsize=8)
        axs[1, 1].legend(fontsize=7)
        fig.suptitle(f"{M['karsilastirma']} — {M['not']}", fontsize=12)
        fig.tight_layout()
        f = KOK / f"of_gaz_karsilastirma{'' if dil == 'tr' else '_en'}.png"
        fig.savefig(f, dpi=130)
        plt.close(fig)
        print("Kaydedildi:", f.name)
    (KOK / "of_gaz_ozet.json").write_text(json.dumps({"sonuc": satir, "gaz_motoru": kar, "not": NOT_TR,
                                                      "tarih": time.strftime("%Y-%m-%d %H:%M")},
                                                     ensure_ascii=False, indent=1, default=float))
    return tab, kt


METIN = {
    "tr": {"ond": ",", "not": NOT_TR, "harita_3b": "Metan sızıntısı, 3B kesit (z = 0): 4 yerçekimi",
           "harita_2b": "Metan sızıntısı, 2B: 4 yerçekimi",
           "vaka": {"3b_uzay": "3B uzay (g = 0)", "3b_mars": "3B Mars (3,73)", "3b_ay": "3B Ay (1,62)",
                    "3b_dunya": "3B Dünya (9,81)", "2b_0": "2B g = 0",
                    "2b_1.62": "2B Ay (1,62)", "2b_3.73": "2B Mars (3,73)", "2b_9.81": "2B Dünya (9,81)"},
           "tmax": "En yüksek sıcaklık", "q": "Isı salımı (gri: tutuşturucu açık)",
           "q_ek": "3B: W (tam kabin) · 2B: kW/m", "merkez": "Isı salımı ağırlıklı alev merkezi yüksekliği",
           "boy": "Alev boyu (delikten Qdot ≥ %5 bölgesinin ucuna)", "karsilastirma": "Metan sızıntısı: uzay / Mars / 2B 4 g"},
    "en": {"ond": ".", "not": NOT_EN, "harita_3b": "Methane leak, 3D section (z = 0): four gravity levels",
           "harita_2b": "Methane leak, 2D: four gravity levels",
           "vaka": {"3b_uzay": "3D space (g = 0)", "3b_mars": "3D Mars (3.73)", "3b_ay": "3D Moon (1.62)",
                    "3b_dunya": "3D Earth (9.81)", "2b_0": "2D g = 0",
                    "2b_1.62": "2D Moon (1.62)", "2b_3.73": "2D Mars (3.73)", "2b_9.81": "2D Earth (9.81)"},
           "tmax": "Maximum temperature", "q": "Heat release (grey: igniter on)",
           "q_ek": "3D: W (full cabin) · 2D: kW/m", "merkez": "Heat-release-weighted flame centre height",
           "boy": "Flame length (hole to tip of Qdot ≥ 5% region)", "karsilastirma": "Methane leak: space / Mars / 2D 4 g"},
}


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--kur", action="store_true")
    a.add_argument("--test", action="store_true")
    a.add_argument("--kos", action="store_true")
    a.add_argument("--analiz", action="store_true")
    a.add_argument("--plan", action="store_true")
    a.add_argument("--video-denetle", nargs="+", metavar="MP4")
    a.add_argument("--incelt", nargs="+", metavar="VAKA")
    a.add_argument("--panel4", action="store_true", help="--video-denetle: 2 x 2 videoda her panel ayrı")
    a.add_argument("--test-temizle", action="store_true")
    a.add_argument("--buda", metavar="VAKA")
    a.add_argument("--vaka", nargs="*")
    a.add_argument("--sure", type=float)
    a.add_argument("--cekirdek", type=int, default=CEKIRDEK)
    a.add_argument("--h2", type=float, default=1.25)
    k = a.parse_args()
    if k.buda:
        z, b = buda(k.buda)
        if z:
            print(f"budandı: {len(z)} zaman ({z[0]}–{z[-1]}), {b / 1e6:.0f} MB")
        return
    if k.plan:
        plan()
        return
    if k.incelt:
        incelt(k.incelt)
        return
    if k.video_denetle:
        raise SystemExit(0 if video_denetle(k.video_denetle, panel4=k.panel4) else 1)
    if k.test_temizle:
        test_temizle()
        return
    vakalar = k.vaka or list(VAKALAR)
    if k.kur:
        for v in vakalar:
            kur_vaka(v, k.h2)
    if k.test:
        for v in vakalar:
            test(v, k.sure or 0.02, k.cekirdek)
    if k.kos:
        for v in vakalar:
            bitis = k.sure or SURE
            rc, gec = kos(v, bitis, k.cekirdek)
            b = bitti_mi(vaka_yolu(v), log_yolu(v), bitis)
            tamam = rc == 0 and b["zaman_tamam"] and b["End"] and not b["cokme"]
            print(f"{v}: rc={rc} süre {gec / 3600:.2f} sa {b} -> {'TAMAM' if tamam else 'HATA'}", flush=True)
            (vaka_yolu(v) / "durum.json").write_text(json.dumps({"rc": rc, **b, "tamam": tamam}))
            if not tamam:
                raise SystemExit(f"HATA: {v} tamamlanmadı (rc={rc}, son zaman {b['son_zaman']} / {bitis}, "
                                 f"End={b['End']}, çökme={b['cokme']})")
    if k.analiz:
        analiz()


if __name__ == "__main__":
    main()
