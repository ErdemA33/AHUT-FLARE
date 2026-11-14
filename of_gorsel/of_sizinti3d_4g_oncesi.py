#!/usr/bin/env python3
"""
of_sizinti3d.py — kabin sızıntısının AYRINTILI 3B koşusu (GÖSTERİM; deney verisiyle doğrulanmadı).

of_sizinti.py vakasından türetilir (kabin, enjektör, tutuşturucu, kimya, bulut, tavandaki havalandırma çıkışı aynı):
  - YARIM ALAN: z >= 0, z = 0 yüzü symmetryPlane ("simetri"). Enjektör (-80, 0, 0) mm ve tutuşturucu (0, 20, 0) mm
    zaten z = 0 düzlemindedir (taşınmadı). Yarım alanda püskürmenin ve ateşleyicinin YARISI vardır:
    debi 0,5 g/s (toplam 0,1 g), ateşleyici 150 W (parsel/s aynı; diskin z<0 yarısı atılır). Hacim integralleri (ısı salımı) analizde ×2.
  - Izgara: 5 mm taban (40 x 40 x 20), püskürme + alev kutusunda refineMesh ile 3 yönde bölme -> 2,5 mm.
  - Mars: g = (0, -3,73, 0), p_rgh + hidrostatik başlatma (of_sizinti.sifir ile aynı).
  - Yazma: alanlar YAZMA aralığıyla; analizde gerekmeyen alanlar (phi, k, epsilon, ...) kuyruk bekçisi tarafından
    eski zaman klasörlerinden silinir (son iki zaman klasörü yeniden başlatma için tam kalır).

Kullanım:
  python3 of_sizinti3d.py --kur [--kutu genis|dar] [--h 2.5|3]
  python3 of_sizinti3d.py --test --sure 0.02 --varyant uzay
  python3 of_sizinti3d.py --kos --varyant uzay
"""
import argparse
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import of_sizinti as osz
import of_tek_damla as ot

VAKA_KOK = ot.OF_KOK / "sizinti3d_ince"
AYAR = VAKA_KOK / "ayar.json"
VARYANTLAR = osz.VARYANTLAR
L = osz.L
N_TABAN = 40                                   # 5 mm
SURE = 1.0
YAZMA = 0.01
CEKIRDEK = 15
KUTULAR = {                                    # inceltilen bölge (m): püskürme konisi + alev
    "genis": ((-0.095, -0.075, 0.0), (0.100, 0.075, 0.050)),
    "dar":   ((-0.090, -0.050, 0.0), (0.100, 0.060, 0.035)),
}
GEREKLI = {"T", "O2", "C7H16", "U", "rho", "Qdot", "PaSR:kappa", "uniform", "lagrangian"}   # analizde kullanılanlar


LAG_GEREKLI = {"positions", "d", "T", "nParticle", "U", "origId", "origProcId"}   # damla_vtk / foamToVTK için


def zaman_klasorleri(v):
    p0 = v / "processor0"
    if not p0.exists():
        return []
    return sorted((d.name for d in p0.iterdir() if re.match(r"^[\d.e+-]+$", d.name) and d.name != "0"), key=float)


def buda(v, koru=2):
    """Son `koru` zaman klasörü dışındakilerden analizde gerekmeyen alanları siler (yeniden başlatma son zamandan).
    Budanan zamanlar v/budanan.txt'de tutulur. Silme yalnız of_kosular/ altında."""
    v = Path(v).resolve()
    if ot.OF_KOK.resolve() not in v.parents:
        raise SystemExit(f"budama reddedildi: {v}")
    kayit = v / "budanan.txt"
    yapilan = set(kayit.read_text().split()) if kayit.exists() else set()
    zs = zaman_klasorleri(v)
    yeni, kazanc = [], 0
    for z in zs[:-koru] if koru else zs:
        if z in yapilan:
            continue
        for pd in v.glob(f"processor*/{z}"):
            for f in pd.iterdir():
                if f.name not in GEREKLI:
                    kazanc += f.stat().st_size if f.is_file() else 0
                    shutil.rmtree(f) if f.is_dir() else f.unlink()
            bulut = pd / "lagrangian/cloud"
            if bulut.exists():
                for f in bulut.iterdir():
                    if f.name not in LAG_GEREKLI and f.is_file():
                        kazanc += f.stat().st_size
                        f.unlink()
        yeni.append(z)
    if yeni:
        with open(kayit, "a") as k:
            k.write("\n".join(yeni) + "\n")
    return yeni, kazanc


def temizle(v, sakla):
    """Analiz bittikten sonra: `sakla` (zaman adları) + son zaman dışındaki processor zamanlarını siler."""
    v = Path(v).resolve()
    if ot.OF_KOK.resolve() not in v.parents:
        raise SystemExit(f"silme reddedildi: {v}")
    zs = zaman_klasorleri(v)
    tut = set(sakla) | ({zs[-1]} if zs else set())
    silinen = 0
    for z in zs:
        if z in tut:
            continue
        for pd in v.glob(f"processor*/{z}"):
            shutil.rmtree(pd)
        silinen += 1
    return silinen, len(tut)


def ayar_oku():
    return json.loads(AYAR.read_text()) if AYAR.exists() else {"kutu": "genis", "bolme": 2}


def blockmesh_yarim(v):
    h = L / 2 * 1000
    n = N_TABAN
    yuz = {"disari": ["(3 7 6 2)"], "simetri": ["(0 3 2 1)"],
           "duvar": ["(0 4 7 3)", "(1 2 6 5)", "(0 1 5 4)", "(4 5 6 7)"]}
    tip = {"disari": "patch", "simetri": "symmetryPlane", "duvar": "wall"}
    b = "".join(f"    {ad}\n    {{\n        type {tip[ad]};\n        faces\n        (\n"
                + "".join(f"            {f}\n" for f in fl) + "        );\n    }\n" for ad, fl in yuz.items())
    (v / "system/blockMeshDict").write_text(
        ot.baslik("dictionary", "blockMeshDict", "system") +
        f"units [mm];\n\nvertices\n(\n    ({-h} {-h} 0)\n    ({h} {-h} 0)\n    ({h} {h} 0)\n"
        f"    ({-h} {h} 0)\n    ({-h} {-h} {h})\n    ({h} {-h} {h})\n    ({h} {h} {h})\n    ({-h} {h} {h})\n);\n\n"
        f"blocks\n(\n    hex (0 1 2 3 4 5 6 7) ({n} {n} {n // 2}) simpleGrading (1 1 1)\n);\n\nboundary\n(\n{b});\n")


def refine_dict(v, kutu):
    a, b = KUTULAR[kutu]
    (v / "system/refineMeshDict").write_text(
        ot.baslik("dictionary", "refineMeshDict", "system") +
        "coordinates\n{\n    type            global;\n    e1              (1 0 0);\n    e2              (0 1 0);\n"
        "    directions      (e1 e2 e3);\n}\n\n"
        f"zone\n{{\n    type            box;\n    box             ({a[0]} {a[1]} {a[2] - 0.001}) ({b[0]} {b[1]} {b[2]});\n}}\n")


def simetri_ekle(v):
    for f in (v / "0").iterdir():
        s = f.read_text()
        if "simetri" not in s:
            s = s.replace("boundaryField\n{\n", "boundaryField\n{\n    simetri\n    {\n        type            symmetryPlane;\n"
                                                "    }\n", 1)
            f.write_text(s)


def kontrol(v, bitis, yazma=YAZMA):
    (v / "system/controlDict").write_text(
        ot.baslik("dictionary", "controlDict", "system") +
        f"solver          multicomponentFluid;\n\nstartFrom       latestTime;\nstartTime       0;\n"
        f"stopAt          endTime;\nendTime         {bitis};\ndeltaT          1e-06;\n"
        f"writeControl    adjustableRunTime;\nwriteInterval   {min(yazma, bitis / 2)};\npurgeWrite      0;\n"
        "writeFormat     binary;\nwritePrecision  6;\nwriteCompression off;\ntimeFormat      general;\n"
        "timePrecision   6;\nadjustTimeStep  yes;\nmaxCo           0.3;\nmaxDeltaT       1e-3;\n"
        "runTimeModifiable yes;\n")
    # kesit: z = 0 simetri düzleminin hemen üstü (ince hücre merkezleri z = 1,25 mm; düzlemin kendisi sınır)
    (v / "system/functions").write_text(
        ot.baslik("dictionary", "functions", "system") +
        "#includeFunc Qdot(executeControl=timeStep)\n#includeFunc cellMax(T)\n#includeFunc volIntegrate(Qdot)\n"
        "#includeFunc cutPlaneSurface(point=(0 0 0.001), normal=(0 0 1), fields=(T C7H16), surfaceFormat=raw, "
        "name=kesit)\n")


def kur_varyant(ad, g, kutu, bolme):
    tut = ot.foam_tut() / "multicomponentFluid/aachenBomb"
    v = VAKA_KOK / ad
    ot.guvenli_sil(v)
    shutil.copytree(tut, v)
    for f in ("Allrun", "Allrun-parallel", "Allclean", "constant/dynamicMeshDict"):
        (v / f).unlink(missing_ok=True)
    blockmesh_yarim(v)
    osz.sifir(v, g)
    simetri_ekle(v)
    osz.bulut(v)
    p = v / "constant/cloudProperties"
    s = p.read_text()
    s = re.sub(r"massTotal\s+[\d.e+-]+;", f"massTotal       {osz.DEBI * osz.ENJ_SURE / 2:.3e};", s)
    # parcelsPerSecond tam alandaki gibi 100 000 bırakılır: enjektör diski z = 0'da olduğundan diskin z < 0 yarısına
    # düşen parseller atılıyor (kütle kalanlara dağıtılıyor) -> yarım alanda etkin ~50 000/s
    p.write_text(s)
    fvm = (v / "constant/fvModels").read_text()
    a = osz.ATES_POZ
    fvm += ("\natesleyici\n{\n    type            heatSource;\n    cellZone\n    {\n        type    sphere;\n"
            f"        centre  ({a[0]} {a[1]} {a[2]});\n        radius  {osz.ATES_R};\n    }}\n"
            f"    Q               table ((0 {osz.ATES_GUC / 2}) ({osz.ATES_SURE} {osz.ATES_GUC / 2}) "
            f"({osz.ATES_SURE + 1e-4} 0) (1000 0));\n}}\n")
    (v / "constant/fvModels").write_text(fvm)
    (v / "constant/g").write_text(ot.baslik("uniformDimensionedVectorField", "g", "constant") +
                                  f"dimensions      [acceleration];\nvalue           ({g[0]} {g[1]} {g[2]});\n")
    (v / "system/setFieldsDict").write_text(
        ot.baslik("dictionary", "setFieldsDict", "system") +
        "zones\n{\n    ateslemeKaynagi\n    {\n        type        sphere;\n"
        f"        centre      ({a[0]} {a[1]} {a[2]});\n        radius      {osz.ATES_R};\n"
        f"        values\n        {{\n            T {osz.ATES_T};\n        }}\n    }}\n}}\n")
    (v / "system/decomposeParDict").write_text(
        ot.baslik("dictionary", "decomposeParDict", "system") +
        f"numberOfSubdomains {CEKIRDEK};\n\ndecomposer      scotch;\n")
    refine_dict(v, kutu)
    kontrol(v, SURE)
    log = ot.OF_KOK / f"sizinti3d_{ad}_hazirlik.log"
    log.unlink(missing_ok=True)
    adimlar = ["chemkinToFoam chemkin/chem.inp chemkin/therm.dat chemkin/transportProperties "
               "constant/reactions constant/speciesThermo", "blockMesh"]
    adimlar += ["refineMesh -dict system/refineMeshDict"] * bolme
    adimlar += ["setFields", "checkMesh -constant"]
    for cmd in adimlar:
        if ot.kabuk(cmd, v, log=log) != 0:
            raise SystemExit(f"{ad}: '{cmd.split()[0]}' başarısız, bkz. {log}")
        if cmd.startswith("refineMesh") and bolme > 1:
            pass
    (v / f"{ad}.foam").touch()
    m = re.findall(r"^\s*cells:\s+(\d+)", log.read_text(), flags=re.M)
    print(f"Kuruldu: {v}  hücre {m[-1] if m else '?'}")
    return int(m[-1]) if m else None


def kur(sadece=None, kutu="genis", bolme=1):
    VAKA_KOK.mkdir(parents=True, exist_ok=True)
    AYAR.write_text(json.dumps({"kutu": kutu, "bolme": bolme, "kutu_m": KUTULAR[kutu]}))
    for ad, g in VARYANTLAR.items():
        if sadece and ad not in sadece:
            continue
        kur_varyant(ad, g, kutu, bolme)


def kos_varyant(ad, bitis, cekirdek=CEKIRDEK, hedef=None, log=None):
    v = hedef or VAKA_KOK / ad
    log = log or ot.OF_KOK / f"sizinti3d_{ad}.log"
    s = (v / "system/controlDict").read_text()
    (v / "system/controlDict").write_text(re.sub(r"endTime\s+[\d.e+-]+;", f"endTime         {bitis};", s))
    if not any(v.glob("processor*")):
        if ot.kabuk("decomposePar -force", v, log=ot.OF_KOK / f"sizinti3d_{ad}_hazirlik.log") != 0:
            raise SystemExit(f"{ad}: decomposePar başarısız")
    bas = time.time()
    p = subprocess.Popen(["bash", "-c", f"source {ot.BASHRC} >/dev/null 2>&1; "
                                        f"exec mpirun --oversubscribe -np {cekirdek} foamRun -parallel"],
                         cwd=v, stdout=open(log, "a"), stderr=subprocess.STDOUT)
    (ot.OF_KOK / f"sizinti3d_{ad}.pid").write_text(str(p.pid))
    p.wait()
    return p.returncode, time.time() - bas


def test(sure, varyant="uzay"):
    """Kurulu vakanın kopyasında kısa koşu: hız, Courant, p_rgh, disk/yazma ölçümü."""
    kaynak = VAKA_KOK / varyant
    hedef = VAKA_KOK / f"test_{varyant}"
    ot.guvenli_sil(hedef)
    shutil.copytree(kaynak, hedef, ignore=shutil.ignore_patterns("processor*", "postProcessing"))
    kontrol(hedef, sure, yazma=sure / 2)
    log = ot.OF_KOK / f"sizinti3d_test_{varyant}.log"
    log.unlink(missing_ok=True)
    rc, gec = kos_varyant(f"test_{varyant}", sure, hedef=hedef, log=log)
    metin = log.read_text(errors="replace")
    z = re.findall(r"^Time = ([\d.e+-]+)", metin, flags=re.M)
    co = re.findall(r"Courant Number mean: [\d.e+-]+ max: ([\d.e+-]+)", metin)
    prgh = len(re.findall(r"Solving for p_rgh", metin))
    par = re.findall(r"Current number of parcels\s*=\s*(\d+)", metin)
    yaz = sorted({d.name for d in (hedef / "processor0").iterdir() if re.match(r"^[\d.e+-]+$", d.name)}, key=float)
    son = yaz[-1] if yaz else None
    boy = sum(f.stat().st_size for f in hedef.glob(f"processor*/{son}/**/*") if f.is_file()) if son else 0
    boy_g = sum(f.stat().st_size for f in hedef.glob(f"processor*/{son}/**/*")
                if f.is_file() and (f.relative_to(hedef).parts[2] in GEREKLI)) if son else 0
    sonuc = {"varyant": varyant, "sure": sure, "rc": rc, "duvar_s": gec, "t_son": float(z[-1]) if z else 0.0,
             "adim": len(z), "courant_max": float(co[-1]) if co else None, "p_rgh_cozum": prgh,
             "parsel": int(par[-1]) if par else None, "yazma_MB_tam": boy / 1e6, "yazma_MB_gerekli": boy_g / 1e6,
             "son_yazma": son}
    print(json.dumps(sonuc, ensure_ascii=False))
    (VAKA_KOK / f"test_{varyant}.json").write_text(json.dumps(sonuc))
    return sonuc


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--kur", action="store_true")
    a.add_argument("--kutu", default="genis", choices=list(KUTULAR))
    a.add_argument("--bolme", type=int, default=1)
    a.add_argument("--test", action="store_true")
    a.add_argument("--kos", action="store_true")
    a.add_argument("--sure", type=float)
    a.add_argument("--varyant", nargs="*")
    a.add_argument("--buda", metavar="VAKA", help="bekçi için: eski zamanlardan gereksiz alanları sil")
    a.add_argument("--temizle", action="store_true", help="analizden sonra kullanılmayan zamanları sil")
    k = a.parse_args()
    if k.buda:
        z, b = buda(k.buda)
        if z:
            print(f"budandı: {len(z)} zaman ({z[0]}–{z[-1]}), {b / 1e6:.0f} MB")
        return
    if k.temizle:
        import of_gorsel_veri as ogv
        for v in k.varyant or list(VARYANTLAR):
            vaka = VAKA_KOK / v
            sakla = [b for a_, b in ogv.sec(ogv.zamanlar(vaka))]
            n, t = temizle(vaka, sakla)
            print(f"{v}: {n} zaman silindi, {t} zaman kaldı (görüntüleyicinin 20 karesi + son)")
        return
    if k.kur:
        kur(k.varyant, k.kutu, k.bolme)
    if k.test:
        for v in k.varyant or ["uzay"]:
            test(k.sure or 0.02, v)
    if k.kos:
        for v in k.varyant or list(VARYANTLAR):
            rc, gec = kos_varyant(v, k.sure or SURE)
            print(f"{v}: rc={rc} süre {gec / 3600:.2f} sa", flush=True)
            if rc != 0:
                raise SystemExit(rc)


if __name__ == "__main__":
    main()
