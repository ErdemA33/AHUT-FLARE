#!/usr/bin/env python3
"""
scripts/of_single_droplet.py — OpenFOAM 14'te tek n-heptan damlası (NASA FLEX doğrulaması).

Temel örnek: $FOAM_TUTORIALS/multicomponentFluid/aachenBomb (lagrangian sprayCloud, C7H16 sıvı özellikleri,
liquidEvaporationBoil buharlaşma, Ranz-Marshall ısı transferi, tek adım heptan kimyası). Sprey enjeksiyonu
yerine manualInjection ile TEK damla; laminer; g = 0; açık sınırlar.

Vaka (of_kosular/tek_damla/<varyant>):
  - 3B kutu 80 mm, KENAR_HUCRE hücre/kenar (33 -> 2.42 mm; damla tam ortadaki hücrenin merkezinde)
  - 2 mm n-heptan damlası, hız 0, 300 K;  ortam %21 O2 + N2 (kütle 0.233 / 0.767), 1 atm, 300 K
  - Tutuşturma: setFields ile t=0'da damla çevresinde r = 4 mm küre: 1500 K + %5 heptan buharı (FLEX'teki sıcak
    tel ateşleyicinin taklidi: küre hemen yanar, damlayı ısıtır, sonra damla kendi difüzyon alevini sürdürür)
  - Kimya: tek adım C7H16 + 11 O2 -> 7 CO2 + 8 H2O (aachenBomb'daki mekanizma), reactionModel laminar
  - Işınım: "isinimsiz" varyantta kapalı; "p1" varyantında P1 + greyMeanReaction (CO2, H2O Planck ortalama
    eğrileri, TNF/RADCAL), sınırlar MarshakRadiation
  - Sınırlar: totalPressure (1 atm), pressureInletOutletVelocity, T / türler inletOutlet (ortam)

Kullanım:
  python3 scripts/of_single_droplet.py --kur                       # of_kosular/tek_damla/{isinimsiz,p1} hazırla
  python3 scripts/of_single_droplet.py --olc --sure 0.1            # isinimsiz kopyada 0.1 s koşup hızı ölç, tahmini süreyi yaz
  nohup python3 scripts/of_single_droplet.py --kos > of_kosular/tek_damla_surucu.log 2>&1 &
                                                      # önce isinimsiz sonra p1, sırayla (internetsiz çalışır)
  python3 scripts/of_single_droplet.py --analiz                    # d²-t, K, en yüksek T, alev yarıçapı; FLEX + droplet_engine
                                                      # karşılaştırması -> figures/of_single_droplet.png, data/of_single_droplet_result.csv
Loglar: of_kosular/tek_damla_<varyant>.log (OpenFOAM), of_kosular/tek_damla_ilerleme.log (ara özet).
Silme yalnızca of_kosular/ altında yapılır.
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
OF_KOK = KOK / "of_kosular"
VAKA_KOK = OF_KOK / "tek_damla"
ILERLEME = OF_KOK / "tek_damla_ilerleme.log"
BASHRC = os.environ.get("OF_BASHRC", "/opt/openfoam14/etc/bashrc")
VARYANTLAR = ["isinimsiz", "p1"]

L = 0.080            # kutu kenarı (m)
KENAR_HUCRE = 33
D0 = 2.0e-3          # damla çapı (m)
T_ATES, R_ATES = 1500.0, 4.0e-3
Y_ATES = 0.05        # ateşleme küresine konan yakıt buharı kütle kesri (O2/N2 aynı oranda azaltılır)
SURE = 12.0          # tam koşu üst sınırı (s); damla bitince stopAtEmptyClouds durdurur
YAZMA = 0.05         # alan/ lagrangian yazma aralığı (s)
CEKIRDEK = 15        # nproc - 1
BOLME = "(5 3 1)"    # 15 alt bölge
MAKS_DT = 2e-3


def kabuk(cmd, cwd, log=None, zaman_asimi=None):
    """OpenFOAM ortamı yüklenmiş bash'te komut."""
    tam = f"source {BASHRC} >/dev/null 2>&1; {cmd}"
    if log:
        with open(log, "a") as f:
            return subprocess.run(["bash", "-c", tam], cwd=cwd, stdout=f, stderr=subprocess.STDOUT,
                                  timeout=zaman_asimi).returncode
    r = subprocess.run(["bash", "-c", tam], cwd=cwd, capture_output=True, text=True, timeout=zaman_asimi)
    return r


def foam_tut():
    r = kabuk("echo $FOAM_TUTORIALS", KOK)
    return Path(r.stdout.strip())


def baslik(sinif, nesne, konum):
    return (f'FoamFile\n{{\n    format      ascii;\n    class       {sinif};\n    location    "{konum}";\n'
            f'    object      {nesne};\n}}\n\n')


def guvenli_sil(p):
    p = Path(p).resolve()
    if OF_KOK.resolve() not in p.parents:
        raise SystemExit(f"Silme reddedildi (of_kosular dışında): {p}")
    if p.exists():
        shutil.rmtree(p)


# ------------------------------------------------------------------ vaka dosyaları
def alan(ad, boyut, ic, sinir, sinif="volScalarField"):
    return baslik(sinif, ad, "0") + f"dimensions      {boyut};\n\ninternalField   {ic};\n\nboundaryField\n{{\n" \
        f"    disari\n    {{\n{sinir}    }}\n}}\n"


def sifir_klasoru(v, isinim):
    s = {
        "p": alan("p", "[pressure]", "uniform 101325",
                  "        type            totalPressure;\n        p0              uniform 101325;\n"
                  "        value           uniform 101325;\n"),
        "U": alan("U", "[velocity]", "uniform (0 0 0)",
                  "        type            pressureInletOutletVelocity;\n        value           uniform (0 0 0);\n",
                  "volVectorField"),
        "T": alan("T", "[temperature]", "uniform 300",
                  "        type            inletOutlet;\n        inletValue      uniform 300;\n"
                  "        value           uniform 300;\n"),
        "O2": alan("O2", "[]", "uniform 0.233",
                   "        type            inletOutlet;\n        inletValue      uniform 0.233;\n"
                   "        value           uniform 0.233;\n"),
        "N2": alan("N2", "[]", "uniform 0.767",
                   "        type            inletOutlet;\n        inletValue      uniform 0.767;\n"
                   "        value           uniform 0.767;\n"),
        "Ydefault": alan("Ydefault", "[]", "uniform 0",
                         "        type            inletOutlet;\n        inletValue      uniform 0;\n"
                         "        value           uniform 0;\n"),
        "C7H16": alan("C7H16", "[]", "uniform 0",
                      "        type            inletOutlet;\n        inletValue      uniform 0;\n"
                      "        value           uniform 0;\n"),
    }
    if isinim:
        s["G"] = alan("G", "[heatFluxDensity]", "uniform 0",
                      "        type            MarshakRadiation;\n        T               T;\n"
                      "        emissivityMode  lookup;\n        emissivity      uniform 1.0;\n"
                      "        value           uniform 0;\n")
    z = v / "0"
    if z.exists():
        shutil.rmtree(z)
    z.mkdir()
    for ad, icerik in s.items():
        (z / ad).write_text(icerik)


def blockmesh(v):
    h = L / 2 * 1000
    n = KENAR_HUCRE
    (v / "system/blockMeshDict").write_text(
        baslik("dictionary", "blockMeshDict", "system") +
        f"units [mm];\n\nvertices\n(\n    ({-h} {-h} {-h})\n    ({h} {-h} {-h})\n    ({h} {h} {-h})\n"
        f"    ({-h} {h} {-h})\n    ({-h} {-h} {h})\n    ({h} {-h} {h})\n    ({h} {h} {h})\n    ({-h} {h} {h})\n);\n\n"
        f"blocks\n(\n    hex (0 1 2 3 4 5 6 7) ({n} {n} {n}) simpleGrading (1 1 1)\n);\n\n"
        "boundary\n(\n    disari\n    {\n        type patch;\n        faces\n        (\n"
        "            (0 3 2 1)\n            (4 5 6 7)\n            (0 1 5 4)\n            (2 3 7 6)\n"
        "            (0 4 7 3)\n            (1 2 6 5)\n        );\n    }\n);\n")


def bulut(v, isinim):
    p = v / "constant/cloudProperties"
    s = p.read_text()
    a = s.index("    injectionModels")
    b = s.index("    dispersionModel")
    enj = ("    injectionModels\n    {\n        tekDamla\n        {\n            type            manualInjection;\n"
           "            nParticle       1;\n            SOI             0;\n"
           '            positionsFile   "cloudPositions";\n            U0              (0 0 0);\n'
           "            sizeDistribution\n            {\n                type            fixedValue;\n"
           f"                value           {D0};\n            }}\n        }}\n    }}\n\n")
    s = s[:a] + enj + s[b:]
    s = re.sub(r"T0\s+[\d.e+-]+;", "T0              300;", s)
    s = re.sub(r"rho0\s+[\d.e+-]+;", "rho0            684;", s)
    s = re.sub(r"Cp0\s+[\d.e+-]+;", "Cp0             2240;", s)
    s = re.sub(r"breakupModel\s+\w+;[^\n]*", "breakupModel    none;", s)
    s = re.sub(r"radiation\s+off;", "radiation       off;", s)
    p.write_text(s)
    (v / "constant/cloudPositions").write_text(baslik("vectorField", "cloudPositions", "constant") +
                                               "(\n    (0 0 0)\n)\n")


def isinim_dosyalari(v):
    katsayi = {
        "CO2": "18.741 -121.31e3 273.5e6 -194.05e9 56.31e12 -5.8169e15",
        "H2O": "-0.23093 -1.12390e3 9.41530e6 -2.99880e9 0.51382e12 -1.86840e10",
    }
    blok = ""
    for tur in ("CO2", "H2O", "O2", "N2", "C7H16"):
        k = katsayi.get(tur, "0 0 0 0 0 0")
        blok += (f"    {tur}\n    {{\n        Tcommon 200;\n        invTemp true;\n        Tlow 200;\n"
                 f"        Thigh 2500;\n        loTcoeffs (0 0 0 0 0 0);\n        hiTcoeffs ({k});\n    }}\n")
    (v / "constant/radiationProperties").write_text(
        baslik("dictionary", "radiationProperties", "constant") +
        "radiation on;\nradiationModel  P1;\nsolverFreq 1;\nabsorptionEmissionModel greyMeanReaction;\n"
        "greyMeanReaction\n{\n    lookUpTableFileName none;\n    EhrrCoeff 0.0;\n" + blok + "}\n"
        "scatterModel    none;\nsootModel       none;\n")


def kur_varyant(ad):
    tut = foam_tut() / "multicomponentFluid/aachenBomb"
    v = VAKA_KOK / ad
    guvenli_sil(v)
    shutil.copytree(tut, v)
    for f in ("Allrun", "Allrun-parallel", "Allclean", "constant/dynamicMeshDict"):   # yük dengeleme gereksiz
        (v / f).unlink(missing_ok=True)
    isinim = ad == "p1"
    blockmesh(v)
    sifir_klasoru(v, isinim)
    bulut(v, isinim)
    (v / "constant/g").write_text(baslik("uniformDimensionedVectorField", "g", "constant") +
                                  "dimensions      [acceleration];\nvalue           (0 0 0);\n")
    (v / "constant/momentumTransport").write_text(baslik("dictionary", "momentumTransport", "constant") +
                                                  "simulationType  laminar;\n")
    rp = v / "constant/reactionProperties"
    rp.write_text(baslik("dictionary", "reactionProperties", "constant") + "reactionModel  laminar;\n")
    fvm = baslik("dictionary", "fvModels", "constant") + \
        'clouds\n{\n    type    clouds;\n    libs    ("liblagrangianParcel.so");\n}\n'
    if isinim:
        fvm += 'radiation\n{\n    type    radiation;\n    libs    ("libradiationModels.so");\n}\n'
        isinim_dosyalari(v)
    (v / "constant/fvModels").write_text(fvm)
    (v / "system/setFieldsDict").write_text(
        baslik("dictionary", "setFieldsDict", "system") +
        "zones\n{\n    sicakBolge\n    {\n        type        sphere;\n        centre      (0 0 0);\n"
        f"        radius      {R_ATES};\n        values\n        {{\n            T {T_ATES};\n"
        f"            C7H16 {Y_ATES};\n            O2 {0.233 * (1 - Y_ATES):.5f};\n"
        f"            N2 {0.767 * (1 - Y_ATES):.5f};\n        }}\n"
        "    }\n}\n")
    (v / "system/decomposeParDict").write_text(
        baslik("dictionary", "decomposeParDict", "system") +
        f"numberOfSubdomains {CEKIRDEK};\n\ndecomposer      simple;\n\nsimple\n{{\n    n           {BOLME};\n}}\n")
    kontrol(v, SURE)
    fs = v / "system/fvSchemes"
    s = fs.read_text()
    if isinim and "laplacian(gammaRad,G)" not in s:
        pass                                    # laplacianSchemes default kapsıyor
    fsol = v / "system/fvSolution"
    s = fsol.read_text()
    if isinim and '"G.*"' not in s:
        s = s.replace("solvers\n{", 'solvers\n{\n    "G.*"\n    {\n        solver          PCG;\n'
                      "        preconditioner  DIC;\n        tolerance       1e-5;\n        relTol          0.1;\n    }\n", 1)
        fsol.write_text(s)
    return v


def kontrol(v, bitis, yazma=YAZMA, maxco=0.5, maksdt=MAKS_DT):
    h = L / 2
    (v / "system/controlDict").write_text(
        baslik("dictionary", "controlDict", "system") +
        f"solver          multicomponentFluid;\n\nstartFrom       latestTime;\nstartTime       0;\n"
        f"stopAt          endTime;\nendTime         {bitis};\ndeltaT          1e-05;\n"
        f"writeControl    adjustableRunTime;\nwriteInterval   {yazma};\npurgeWrite      0;\n"
        "writeFormat     binary;\nwritePrecision  6;\nwriteCompression off;\ntimeFormat      general;\n"
        f"timePrecision   6;\nadjustTimeStep  yes;\nmaxCo           {maxco};\nmaxDeltaT       {maksdt};\n"
        "runTimeModifiable yes;\n")
    (v / "system/functions").write_text(
        baslik("dictionary", "functions", "system") +
        "#includeFunc cellMax(T)\n"
        f"#includeFunc graphCell(start=({-h + 1e-6} 0 0), end=({h - 1e-6} 0 0), fields=(T C7H16 O2 CO2), "
        "name=hat)\n"
        "#includeFunc stopAtEmptyClouds\n")


def kur():
    VAKA_KOK.mkdir(parents=True, exist_ok=True)
    for ad in VARYANTLAR:
        v = kur_varyant(ad)
        log = OF_KOK / f"tek_damla_{ad}_hazirlik.log"
        log.unlink(missing_ok=True)
        for cmd in ("chemkinToFoam chemkin/chem.inp chemkin/therm.dat chemkin/transportProperties "
                    "constant/reactions constant/speciesThermo", "blockMesh", "setFields"):
            rc = kabuk(cmd, v, log=log)
            if rc != 0:
                raise SystemExit(f"{ad}: '{cmd.split()[0]}' başarısız (rc={rc}), bkz. {log}")
        print(f"Kuruldu: {v}  (hazırlık logu {log.name})")


# ------------------------------------------------------------------ koşu
def ilerleme_yaz(mesaj):
    with open(ILERLEME, "a") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + mesaj + "\n")


def log_ozet(log):
    """OpenFOAM logundan son zaman, son Dmax/kütle ve en yüksek T."""
    if not Path(log).exists():
        return {}
    metin = Path(log).read_text(errors="replace")[-200000:]
    z = re.findall(r"^Time = ([\d.e+-]+)", metin, flags=re.M)
    dm = re.findall(r"Dmax \(mu\)\s*=\s*[\d.e+-]+,\s*[\d.e+-]+,\s*([\d.e+-]+)", metin)
    ms = re.findall(r"Current mass in system\s*=\s*([\d.e+-]+)", metin)
    tm = []
    v = Path(log).name.replace("tek_damla_", "").replace(".log", "")
    for f in (VAKA_KOK / v).glob("postProcessing/cellMax(T)/*/volFieldValue.dat"):
        satirlar = [x for x in open(f).read().splitlines() if x and not x.startswith("#")]
        if satirlar:
            tm.append(satirlar[-1].split()[1])
    return {"t": float(z[-1]) if z else None, "Dmax_mm": float(dm[-1]) / 1e3 if dm else None,
            "kutle": float(ms[-1]) if ms else None, "Tmax": float(tm[-1]) if tm else None}


def kos_varyant(ad, bitis=SURE, cekirdek=CEKIRDEK, hedef=None, maxco=0.5, maksdt=MAKS_DT):
    v = hedef or VAKA_KOK / ad
    log = OF_KOK / f"tek_damla_{ad}.log"
    kontrol(v, bitis, maxco=maxco, maksdt=maksdt)
    if not any(v.glob("processor*")):
        rc = kabuk("decomposePar -force", v, log=OF_KOK / f"tek_damla_{ad}_hazirlik.log")
        if rc != 0:
            raise SystemExit(f"{ad}: decomposePar başarısız")
    ilerleme_yaz(f"{ad}: başladı (bitiş {bitis} s, {cekirdek} çekirdek), log {log.name}")
    bas = time.time()
    p = subprocess.Popen(["bash", "-c", f"source {BASHRC} >/dev/null 2>&1; "
                                        f"exec mpirun --oversubscribe -np {cekirdek} foamRun -parallel"],
                         cwd=v, stdout=open(log, "a"), stderr=subprocess.STDOUT)
    (OF_KOK / f"tek_damla_{ad}.pid").write_text(str(p.pid))
    while p.poll() is None:
        time.sleep(60)
        o = log_ozet(log)
        if o.get("t"):
            gec = time.time() - bas
            kalan = gec / o["t"] * (bitis - o["t"]) if o["t"] > 0 else float("nan")
            ilerleme_yaz(f"{ad}: t = {o['t']:.4f} s | Dmax {o.get('Dmax_mm')} mm | max T {o.get('Tmax')} K | "
                         f"geçen {gec / 60:.1f} dk | kalan ~{kalan / 3600:.2f} sa")
    ilerleme_yaz(f"{ad}: bitti, rc={p.returncode}, süre {(time.time() - bas) / 3600:.2f} sa")
    return p.returncode, time.time() - bas


def olc(sure, cekirdek):
    hedef = VAKA_KOK / "olcum"
    guvenli_sil(hedef)
    shutil.copytree(VAKA_KOK / "isinimsiz", hedef)
    for d in hedef.glob("processor*"):
        shutil.rmtree(d)
    log = OF_KOK / "tek_damla_olcum.log"
    log.unlink(missing_ok=True)
    rc, gec = kos_varyant("olcum", bitis=sure, cekirdek=cekirdek, hedef=hedef)
    o = log_ozet(log)
    t = o.get("t") or 0
    print(f"Ölçüm: {sure} s fiziksel süre, rc={rc}, duvar süresi {gec:.0f} s, ulaşılan t={t}")
    print(f"  son Dmax {o.get('Dmax_mm')} mm, max T {o.get('Tmax')} K")
    if t > 0:
        print(f"  -> {SURE} s için tahmini {gec / t * SURE / 3600:.1f} saat (varyant başına)")


def kos(cekirdek, bitis):
    for ad in VARYANTLAR:
        kos_varyant(ad, bitis=bitis, cekirdek=cekirdek)


# ------------------------------------------------------------------ P1: ışınımsız koşudan devam
DEVAM_T = "0.5"                      # tutuşma sonrası an (ışınımsız koşu bu anda yazılmış)
DEVAM_MAXCO, DEVAM_MAKS_DT = 0.2, 5e-4


def p1_devam_kur():
    """P1'i sıfırdan değil, ışınımsız koşunun t=0.5 s anından başlatır; ışınım orada açılır."""
    kaynak, v = VAKA_KOK / "isinimsiz", VAKA_KOK / "p1"
    if v.exists():                                   # ıraksayan ilk P1 koşusu saklanır
        eski = VAKA_KOK / "p1_iraksak"
        if eski.exists():
            guvenli_sil(v)
        else:
            v.rename(eski)
    log = OF_KOK / "tek_damla_p1_hazirlik.log"
    if not (kaynak / DEVAM_T).exists():
        rc = kabuk(f"reconstructPar -time {DEVAM_T}", kaynak, log=log)
        if rc != 0 or not (kaynak / DEVAM_T).exists():
            raise SystemExit(f"p1 devam: reconstructPar başarısız (rc={rc}), bkz. {log}")
    v.mkdir(parents=True)
    for d in ("constant", "system", "chemkin"):
        shutil.copytree(kaynak / d, v / d)
    shutil.copytree(kaynak / DEVAM_T, v / DEVAM_T)
    (v / "constant/fvModels").write_text(
        (v / "constant/fvModels").read_text() +
        'radiation\n{\n    type    radiation;\n    libs    ("libradiationModels.so");\n}\n')
    isinim_dosyalari(v)
    (v / DEVAM_T / "G").write_text(alan("G", "[heatFluxDensity]", "uniform 0",
                                        "        type            MarshakRadiation;\n        T               T;\n"
                                        "        emissivityMode  lookup;\n        emissivity      uniform 1.0;\n"
                                        "        value           uniform 0;\n"))
    fsol = v / "system/fvSolution"
    s = fsol.read_text()
    if '"G.*"' not in s:
        s = s.replace("solvers\n{", 'solvers\n{\n    "G.*"\n    {\n        solver          PCG;\n'
                      "        preconditioner  DIC;\n        tolerance       1e-5;\n        relTol          0.1;\n    }\n", 1)
        fsol.write_text(s)
    kontrol(v, SURE, maxco=DEVAM_MAXCO, maksdt=DEVAM_MAKS_DT)
    rc = kabuk("decomposePar -force", v, log=log)
    if rc != 0:
        raise SystemExit(f"p1 devam: decomposePar başarısız, bkz. {log}")
    print(f"P1 devam vakası hazır: {v} (başlangıç t={DEVAM_T} s, maxCo {DEVAM_MAXCO}, maxDeltaT {DEVAM_MAKS_DT})")
    return v


def p1_devam_kos(cekirdek=CEKIRDEK):
    v = VAKA_KOK / "p1"
    if not any(v.glob("processor*")):
        p1_devam_kur()
    log = OF_KOK / "tek_damla_p1.log"
    if log.exists():                                 # ıraksayan koşunun logu ayrı kalsın
        log.rename(OF_KOK / "tek_damla_p1_iraksak.log")
    return kos_varyant("p1", bitis=SURE, cekirdek=cekirdek, maxco=DEVAM_MAXCO, maksdt=DEVAM_MAKS_DT)


# ------------------------------------------------------------------ analiz
FLEX_ADAYLAR = [KOK / "psi_flex_testler.csv", Path("/mnt/ssd/nasaspaceapp/FLEX12/psi_flex_testler.csv")]


def log_serileri(log):
    """Her zaman adımı: t, Dmax (cloud), parsel kütlesi. max(T) cellMax'tan."""
    t, d, m = [], [], []
    cur = None
    for satir in open(log, errors="replace"):
        a = re.match(r"^Time = ([\d.e+-]+)", satir)
        if a:
            cur = float(a.group(1))
            continue
        b = re.search(r"Dmax \(mu\)\s*=\s*[\d.e+-]+,\s*[\d.e+-]+,\s*([\d.e+-]+)", satir)
        if b and cur is not None:
            t.append(cur)
            d.append(float(b.group(1)) / 1e3)            # mikron -> mm
        c = re.search(r"Current mass in system\s*=\s*([\d.e+-]+)", satir)
        if c and cur is not None:
            m.append((cur, float(c.group(1))))
    return t, d, m


def cellmax_oku(v):
    f = sorted(v.glob("postProcessing/cellMax*/*/*.dat")) or sorted(v.glob("postProcessing/cellMax*/*/*"))
    t, T = [], []
    for x in f:
        for satir in open(x, errors="replace"):
            if satir.startswith("#") or not satir.strip():
                continue
            p = satir.replace("(", " ").replace(")", " ").split()
            try:
                t.append(float(p[0]))
                T.append(float(p[1]))
            except (ValueError, IndexError):
                pass
    return t, T


def alev_yaricapi(v):
    """graphCell (x ekseni boyunca) profillerinden: en yüksek T noktasının merkeze uzaklığı (mm)."""
    sonuc = []
    for d in sorted(v.glob("postProcessing/hat/*"), key=lambda p: float(p.name) if re.match(r"^[\d.e+-]+$", p.name)
                    else -1):
        try:
            zt = float(d.name)
        except ValueError:
            continue
        f = next(iter(sorted(d.glob("*.xy")) + sorted(d.glob("*.csv")) + sorted(d.glob("*"))), None)
        if f is None:
            continue
        xs, Ts = [], []
        for satir in open(f, errors="replace"):
            if satir.startswith("#") or not satir.strip():
                continue
            p = satir.split()
            try:
                xs.append(float(p[0]))
                Ts.append(float(p[1]))
            except (ValueError, IndexError):
                pass
        if not xs:
            continue
        i = max(range(len(Ts)), key=lambda k: Ts[k])
        merkez = L / 2
        sonuc.append((zt, abs(xs[i] - merkez) * 1e3, Ts[i]))
    return sonuc


def K_hesapla(t, d, d0_mm=D0 * 1e3, t_bas=0.1, t_son=3.0):
    """d²-t doğrusal kısmının eğimi (mm²/s): ilk ~3 s'de, d² 0.9..0.2 d0² aralığında."""
    import numpy as np
    t, d = np.asarray(t), np.asarray(d)
    d2 = d ** 2
    mk = (t >= t_bas) & (t <= t_son) & (d2 <= 0.95 * d0_mm ** 2) & (d2 >= 0.1 * d0_mm ** 2)
    if mk.sum() < 5:
        mk = (t >= t_bas) & (d > 0)
    if mk.sum() < 5:
        return None
    return float(-np.polyfit(t[mk], d2[mk], 1)[0])


ANALIZ_VARYANTLARI = ["isinimsiz"]     # P1 iki denemede de ıraksadı (bkz. of_kosular/canli.log) -> analize girmez

METIN = {
    "tr": {"baslik": "Tek n-heptan damlası, 2 mm, %21 O2, 1 atm, g = 0 — OpenFOAM / FLEX / droplet_engine",
           "of": "OpenFOAM (ışınımsız)", "dm": "droplet_engine", "flex": "FLEX benzer testler: d0² − K t",
           "d2": "damla çapının karesi", "d2y": "d² (mm²)", "T": "en yüksek gaz sıcaklığı",
           "Ty": "en yüksek T (K)", "rf": "alev yarıçapı (x ekseninde en yüksek T'nin merkeze uzaklığı)",
           "rfy": "alev yarıçapı (mm)", "rfnot": "basamaklar: ızgara 2,5 mm",
           "sutun": ["kaynak", "K (mm²/s)", "sönme çapı (mm)", "T maks (K)", "r_alev (mm)"],
           "kutu": "K (mm²/s): FLEX {f1}–{f2} | droplet_engine {dm} | OpenFOAM {of} (×{oran})",
           "kutu2": "OpenFOAM nokta damla: buharlaşma sıcak hücre ortalamasıyla -> K fazla.\n"
                    "Tek adım kimya: ayrışma yok -> T yüksek. P1 ıraksadı, gösterilmiyor.",
           "dosya": "figures/of_single_droplet.png"},
    "en": {"baslik": "Single n-heptane droplet, 2 mm, 21% O2, 1 atm, g = 0 — OpenFOAM / FLEX / droplet engine",
           "of": "OpenFOAM (no radiation)", "dm": "droplet engine (droplet_engine)",
           "flex": "similar FLEX tests: d0² − K t",
           "d2": "droplet diameter squared", "d2y": "d² (mm²)", "T": "maximum gas temperature",
           "Ty": "max T (K)", "rf": "flame radius (distance of max T from centre along x)",
           "rfy": "flame radius (mm)", "rfnot": "steps: grid 2.5 mm",
           "sutun": ["source", "K (mm²/s)", "extinction d (mm)", "T max (K)", "r_flame (mm)"],
           "kutu": "K (mm²/s): FLEX {f1}–{f2} | droplet engine {dm} | OpenFOAM {of} (×{oran})",
           "kutu2": "OpenFOAM point droplet: evaporation uses hot cell average -> K too high.\n"
                    "Single-step chemistry: no dissociation -> T too high. P1 diverged, not shown.",
           "dosya": "figures/of_single_droplet_en.png"},
}


def analiz():
    import numpy as np
    import pandas as pd
    satir, seri = [], {}
    for ad in ANALIZ_VARYANTLARI:
        v = VAKA_KOK / ad
        log = OF_KOK / f"tek_damla_{ad}.log"
        if not log.exists():
            print(f"{ad}: log yok, atlandı")
            continue
        t, d, _m = log_serileri(log)
        tc, Tc = cellmax_oku(v)
        rf = alev_yaricapi(v)
        K = K_hesapla(t, d) if len(t) > 5 else None
        Tort = float(np.median([T for tt, T in zip(tc, Tc) if tt > 0.2])) if any(tt > 0.2 for tt in tc) else None
        rf_ort = float(np.median([r for zt, r, T in rf if zt > 0.2 and T > 1200])) if rf else None
        satir.append({"kaynak": f"OpenFOAM {ad}", "K_mm2_s": K, "T_maks_medyan_K": Tort,
                      "alev_yaricapi_mm": rf_ort, "son_t_s": t[-1] if t else None, "son_d_mm": d[-1] if d else None,
                      "sondu_mu": None})
        seri[ad] = (t, d, tc, Tc, rf, K)
    flex = []
    f = next((x for x in FLEX_ADAYLAR if x.exists()), None)
    if f is not None:
        x = pd.read_csv(f)
        x = x[(x.yakit == "heptane") & x.oksijen_yuzde.between(19, 23) & x.basinc_kpa.between(90, 110)
              & x.ilk_cap_mm.between(1.5, 2.5) & (x.co2_yuzde.fillna(0) == 0) & (x.he_yuzde.fillna(0) == 0)]
        for r in x.itertuples():
            satir.append({"kaynak": f"FLEX test {int(r.test)} ({r.kimlik})", "d0_mm": r.ilk_cap_mm,
                          "K_mm2_s": r.yanma_hizi_mm2_s, "sonme_capi_mm": r.sonme_capi_mm,
                          "yanma_suresi_s": r.yanma_suresi_s, "test_sonu": r.test_sonu})
            if r.yanma_hizi_mm2_s == r.yanma_hizi_mm2_s:
                flex.append((r.ilk_cap_mm, r.yanma_hizi_mm2_s,
                             r.yanma_suresi_s if r.yanma_suresi_s == r.yanma_suresi_s else 6))
        print(f"FLEX benzer test: {len(x)} (heptan, %19-23 O2, 90-110 kPa, 1.5-2.5 mm, N2)")
    else:
        print("psi_flex_testler.csv bulunamadı; FLEX karşılaştırması atlandı")
    dmK = None
    try:
        sys.path.insert(0, str(KOK / "scripts"))
        import droplet_engine as dm
        r = dm.droplet_engine(1e-4, 21, 101.3, 0, D0 * 1e3, "n-heptane", "droplet", mod="hizli")
        dmK = r["yanma_hizi_K"]
        satir.append({"kaynak": "droplet_engine (hızlı)", "d0_mm": D0 * 1e3, "K_mm2_s": dmK,
                      "sonme_capi_mm": r["sonme_capi"], "T_maks_medyan_K": r["sicaklik"]})
    except Exception as e:
        print("droplet_engine çalıştırılamadı:", e)
    tab = pd.DataFrame(satir)
    for dil in ("tr", "en"):
        _ciz(dil, tab, seri, flex, dmK)
    tab.to_csv(KOK / "data/of_single_droplet_result.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 200)
    print(tab.to_string(index=False))
    print("Kaydedildi: figures/of_single_droplet.png, figures/of_single_droplet_en.png, data/of_single_droplet_result.csv")


def _ciz(dil, tab, seri, flex, dmK):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    M = METIN[dil]
    sayi = (lambda z, n=2: f"{z:.{n}f}".replace(".", ",")) if dil == "tr" else (lambda z, n=2: f"{z:.{n}f}")
    renk = "#1565C0"
    fig, ax = plt.subplots(2, 2, figsize=(13, 9.5))
    ofK = None
    for ad, (t, d, tc, Tc, rf, K) in seri.items():
        ofK = K
        if t:
            ax[0, 0].plot(t, np.asarray(d) ** 2, color=renk, label=M["of"] + (f" (K={sayi(K, 3)})" if K else ""))
        if tc:
            ax[0, 1].plot(tc, Tc, color=renk, lw=.9, label=M["of"])
        if rf:
            ax[1, 0].plot([a for a, b, c in rf], [b for a, b, c in rf], "o-", ms=3, color=renk, label=M["of"])
    for d0, K, ts in flex:
        tt = np.linspace(0, ts, 20)
        ax[0, 0].plot(tt, d0 ** 2 - K * tt, ":", color="gray", lw=.9)
    if dmK:
        tt = np.linspace(0, (D0 * 1e3) ** 2 / dmK, 20)
        ax[0, 0].plot(tt, (D0 * 1e3) ** 2 - dmK * tt, "--", color="k", label=f"{M['dm']} (K={sayi(dmK, 3)})")
    ax[0, 0].plot([], [], ":", color="gray", label=M["flex"])
    ax[0, 0].set(xlabel="t (s)", ylabel=M["d2y"], title=M["d2"])
    ax[0, 0].set_ylim(bottom=0)
    ax[0, 0].legend(fontsize=8)
    ax[0, 1].set(xlabel="t (s)", ylabel=M["Ty"], title=M["T"], ylim=(1000, 3000))
    ax[0, 1].legend(fontsize=8)
    ax[1, 0].set(xlabel="t (s)", ylabel=M["rfy"], title=M["rf"])
    ax[1, 0].text(0.98, 0.04, M["rfnot"], transform=ax[1, 0].transAxes, ha="right", va="bottom", fontsize=9,
                  color="#444", bbox=dict(boxstyle="round", fc="#F5F5F5", ec="#BBB"))
    ax[1, 0].legend(fontsize=8, loc="upper left")
    # sağ alt: sonuç kutusu + tablo
    a = ax[1, 1]
    a.axis("off")
    if flex and dmK and ofK:
        fk = [k for _, k, _ in flex]
        kutu = M["kutu"].format(f1=sayi(min(fk)), f2=sayi(max(fk)), dm=sayi(dmK), of=sayi(ofK),
                                oran=sayi(ofK / float(np.mean(fk)), 1))
        a.text(0.5, 0.97, kutu, transform=a.transAxes, ha="center", va="top", fontsize=10.5, fontweight="bold",
               bbox=dict(boxstyle="round,pad=0.5", fc="#FFF8E1", ec="#F9A825"))
        a.text(0.5, 0.80, M["kutu2"], transform=a.transAxes, ha="center", va="top", fontsize=8.5, color="#444")
    g = tab[["kaynak", "K_mm2_s", "sonme_capi_mm", "T_maks_medyan_K", "alev_yaricapi_mm"]].copy()
    if dil == "en":
        g["kaynak"] = g["kaynak"].str.replace("droplet_engine (hızlı)", "droplet engine (fast)", regex=False) \
            .str.replace("OpenFOAM isinimsiz", "OpenFOAM no radiation", regex=False)
    else:
        g["kaynak"] = g["kaynak"].str.replace("OpenFOAM isinimsiz", "OpenFOAM ışınımsız", regex=False)
    for c in g.columns[1:]:
        g[c] = g[c].map(lambda z: "" if z is None or (isinstance(z, float) and math.isnan(z))
                        else (f"{z:.0f}" if c == "T_maks_medyan_K" else
                              (f"{z:.3g}".replace(".", ",") if dil == "tr" else f"{z:.3g}")))
    tb = a.table(cellText=g.values, colLabels=M["sutun"], bbox=[0.0, 0.0, 1.0, 0.62],
                 colWidths=[0.31, 0.13, 0.22, 0.16, 0.18])
    tb.auto_set_font_size(False)
    tb.set_fontsize(8)
    fig.suptitle(M["baslik"])
    fig.tight_layout()
    fig.savefig(KOK / M["dosya"], dpi=200)
    plt.close(fig)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--kur", action="store_true")
    a.add_argument("--olc", action="store_true")
    a.add_argument("--kos", action="store_true")
    a.add_argument("--analiz", action="store_true")
    a.add_argument("--p1-devam-kur", action="store_true", help="P1 vakasını ışınımsız t=0.5 s anından kur")
    a.add_argument("--p1-devam", action="store_true", help="P1 devam vakasını (gerekirse kurup) koş")
    a.add_argument("--sure", type=float, default=None, help="--olc: ölçüm süresi; --kos: bitiş süresi (s)")
    a.add_argument("--cekirdek", type=int, default=CEKIRDEK)
    k = a.parse_args()
    if k.kur:
        kur()
    if k.olc:
        olc(k.sure or 0.1, k.cekirdek)
    if k.kos:
        kos(k.cekirdek, k.sure or SURE)
    if k.p1_devam_kur:
        p1_devam_kur()
    if k.p1_devam:
        p1_devam_kos(k.cekirdek)
    if k.analiz:
        analiz()


if __name__ == "__main__":
    main()
