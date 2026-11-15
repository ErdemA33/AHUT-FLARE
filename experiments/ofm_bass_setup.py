#!/usr/bin/env python3
"""
ofm_bass_setup.py — OpenFOAM motorunun KİLİTLİ motorunu (MOTOR_KILIT 1, parametreler değişmez) NASA BASS (PSI-26) SIBAL
testine uygular: motorun Saffire dışındaki bir deneyde dürüst testi ("BASS planı", experiments/ofm_bass_plan.md).

    python3 experiments/ofm_bass_setup.py [--test 4] [--hedef ofm_kosular/bass_sibal_t4]

openfoam_motor/ SALT OKUNUR: kopyası hedef klasöre alınır, yalnız kopyada değişiklik yapılır.
Değişen yalnız deney koşulları ve geometri (motor: kinetik, piroliz, ışınım, sayısal ayarlar AYNEN):
  - numune 10 cm uzun (BASS SIBAL 2.2 cm x 10 cm; NASA 20160000593), x = 0.10-0.20 m; alan 0-0.40 m (5 cm ön bölge blockMesh büyüme dizisine sığmadı)
  - kanal yarı yüksekliği H = 0.038 m  [VARSAYIM: SPICE kanal kesiti belgelerde yok]
  - tel numune ön kenarından 6.25 mm (Saffire ile aynı yer)  [VARSAYIM: BASS "saw tooth hotwire", konumu yok]
  - ateşleyici gücü (birim genişlik) ve 7.986 s kapanma Saffire ile aynı  [VARSAYIM: BASS ateşleyici gücü yok]
  - tutucu (kaymasız taban) numune önü/arkası 0.01 m  [VARSAYIM: BASS numune kartı çerçevesi]
  - ortam: test matrisinden (BASS test matrix.xlsx, 'as run'): akış, O2 %hacim, basınç (atm), CO2 (mm Hg);
    H2O mol kesri Saffire ile aynı (0.0116) [VARSAYIM], T 294.32 K (Saffire) [VARSAYIM]
  - Saffire sensör probları kaldırıldı (konumları bu alanda yok); gazMax, telT, sibalKutle, sibalYuzey, yakitAkisi kalır
  - endTime 40 s, writeInterval 1 s (disk)
  - ağ: üst satır hücre tavanı 16 mm -> 2 mm (kanal 0.30 m -> 0.038 m); duvar yanı çözünürlük aynı
Sonra blockMesh + splitMeshRegions; decomposePar ve koşu experiments/ofm_bass_start.sh ile.
"""
import argparse
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
KAYNAK = KOK / "openfoam_motor"
LIB = KOK / "ofm_kosular" / "v2_10s" / "lib"       # kilitli kaynaktan derlenmiş kütüphane (md5 kilitle aynı)
TESTLER = {   # BASS test matrix.xlsx 'as run matrix' (as run test no.): akış cm/s, O2 %hacim, p atm, CO2 mmHg, gözlem
    4: dict(akis=10.0, o2=21.9, p_atm=0.97, co2_mmhg=3.12, numune="SIBAL 2 cm", gozlem="~40 s burn"),
    5: dict(akis=5.0, o2=21.9, p_atm=0.97, co2_mmhg=3.12, numune="SIBAL 2 cm", gozlem="~60 s burn"),
    12: dict(akis=22.0, o2=21.63, p_atm=0.983684, co2_mmhg=1.51, numune="SIBAL 2 cm", gozlem="26 s burn"),
}
GEO = {"X0": 0.0, "X1": 0.10, "X4": 0.20, "X5": 0.40, "H": 0.038}
TUTUCU_M = 0.01
X_H2O = 0.0116
T0 = 294.32
SAFFIRE = {"O2": 0.235494, "N2": 0.751269, "H2O": 0.0072, "CO2": 0.006037, "U": 0.2453, "p": 99451}
M = {"O2": 31.998, "N2": 28.014, "H2O": 18.015, "CO2": 44.009}


def kutle_kesirleri(o2, co2_mmhg, p_atm):
    X = {"O2": o2 / 100, "CO2": co2_mmhg / (760.0 * p_atm), "H2O": X_H2O}
    X["N2"] = 1 - sum(X.values())
    m = {k: X[k] * M[k] for k in X}
    s = sum(m.values())
    return {k: round(v / s, 6) for k, v in m.items()}, X


def of(komut, cwd):
    r = subprocess.run(["bash", "-c", f"source /opt/openfoam14/etc/bashrc >/dev/null 2>&1; {komut}"], cwd=cwd,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"{komut} başarısız:\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    return r.stdout


def govde(f):
    """OpenFOAM ascii dosyasının FoamFile başlığından sonraki kısmı."""
    t = Path(f).read_text()
    return t[t.index("}", t.index("FoamFile")) + 1:] if "FoamFile" in t else t


def taban_yuz_merkezleri(poly):
    b = (poly / "boundary").read_text()
    m = re.search(r"\bbase\s*\{[^}]*?nFaces\s+(\d+);[^}]*?startFace\s+(\d+);", b, re.S)
    if not m:
        m2 = re.search(r"\bbase\s*\{[^}]*?startFace\s+(\d+);[^}]*?nFaces\s+(\d+);", b, re.S)
        n, s = int(m2.group(2)), int(m2.group(1))
    else:
        n, s = int(m.group(1)), int(m.group(2))
    P = [tuple(map(float, x)) for x in
         re.findall(r"\(\s*([-0-9.eE+]+)\s+([-0-9.eE+]+)\s+([-0-9.eE+]+)\s*\)", govde(poly / "points"))]
    F = re.findall(r"\d+\(([\d\s]+)\)", govde(poly / "faces"))
    xs = []
    for k in range(s, s + n):
        ids = list(map(int, F[k].split()))
        xs.append(sum(P[i][0] for i in ids) / len(ids))
    return xs


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--test", type=int, default=4, choices=sorted(TESTLER))
    a.add_argument("--hedef")
    k = a.parse_args()
    t = TESTLER[k.test]
    hedef = Path(k.hedef) if k.hedef else KOK / "ofm_kosular" / f"bass_sibal_t{k.test}"
    if hedef.exists():
        raise SystemExit(f"{hedef} zaten var (üzerine yazılmaz)")
    shutil.copytree(KAYNAK, hedef)
    v = hedef / "vaka"
    # 1) geometri
    mo = v / "mesh_olustur.py"
    s = mo.read_text()
    s = re.sub(r"^X0, X1, X4, X5 = .*$", f"X0, X1, X4, X5 = {GEO['X0']}, {GEO['X1']}, {GEO['X4']}, {GEO['X5']}"
               "   # BASS (ofm_bass_setup.py)", s, count=1, flags=re.M)
    s = re.sub(r"^H = .*$", f"H = {GEO['H']}   # BASS, VARSAYIM", s, count=1, flags=re.M)
    s = re.sub(r"^xw = .*$", f"xw = {GEO['X1']} + 0.00625   # BASS: ön kenardan 6.25 mm (Saffire gibi)", s, count=1,
               flags=re.M)
    # üst satır hücre tavanı: Saffire'de 16 mm (H = 0.30 m); BASS'in 3.8 cm kanalına sığmıyor -> 2 mm
    # (duvar yanı ilk hücre dy0 ve büyüme oranı 1.15 aynı; yalnız ağ, motor değil)
    s = re.sub(r"^dyU_max = 16e-3", "dyU_max = 2e-3   # BASS (ofm_bass_setup.py)", s, count=1, flags=re.M)
    mo.write_text(s)
    print(of("python3 mesh_olustur.py && blockMesh > log.blockMesh 2>&1 && "
             "splitMeshRegions -cellZones '(fluid sibal tel)' > log.splitMeshRegions 2>&1 && "
             "checkMesh -region fluid > log.checkMesh_fluid 2>&1; tail -3 log.checkMesh_fluid", v))
    # 2) ortam
    Y, X = kutle_kesirleri(t["o2"], t["co2_mmhg"], t["p_atm"])
    p_pa = round(101325 * t["p_atm"])
    U = t["akis"] / 100
    for f in (v / "0").rglob("*"):
        if not f.is_file():
            continue
        s = f.read_text()
        for tur in ("O2", "N2", "H2O", "CO2"):
            s = re.sub(rf"(?<![0-9.]){SAFFIRE[tur]}(?![0-9])", f"{Y[tur]}", s)
        s = s.replace(f"({SAFFIRE['U']} 0 0)", f"({U} 0 0)").replace(str(SAFFIRE["p"]), str(p_pa))
        f.write_text(s)
    # 3) tutucu: tabanda numune önü/arkası TUTUCU_M kaymasız
    xs = taban_yuz_merkezleri(v / "constant" / "fluid" / "polyMesh")
    vf = [1 if (GEO["X1"] - TUTUCU_M <= x <= GEO["X1"] or GEO["X4"] <= x <= GEO["X4"] + TUTUCU_M) else 0 for x in xs]
    uf = v / "0" / "fluid" / "U"
    s = uf.read_text()
    s = re.sub(r"valueFraction nonuniform List<scalar> \d+\([^)]*\)",
               f"valueFraction nonuniform List<scalar> {len(vf)}({' '.join(map(str, vf))})", s)
    uf.write_text(s)
    # 4) fonksiyonlar: Saffire probları çıkar
    fn = v / "system" / "functions"
    s = fn.read_text()
    for blok in ("gazProb", "sensGaz", "sensGazYukseklik", "sensYuzey", "sensRadMenba", "sensRadAkis"):
        s = re.sub(rf"\n{blok}\n\{{.*?\n\}}\n", "\n", s, flags=re.S)
    fn.write_text(s)
    # 5) süre
    cd = v / "system" / "controlDict"
    s = cd.read_text()
    s = re.sub(r"^endTime\s+[^;]+;", "endTime         40.0;", s, flags=re.M)
    s = re.sub(r"^writeInterval\s+[^;]+;", "writeInterval   1.0;", s, flags=re.M)
    cd.write_text(s)
    (hedef / "lib").mkdir(exist_ok=True)
    shutil.copy2(LIB / "libFlameInFreefallSolid.so", hedef / "lib")
    bilgi = {"test": k.test, "bass": t, "ortam_Y": Y, "ortam_X": {kk: round(vv, 5) for kk, vv in X.items()},
             "p_Pa": p_pa, "U_m_s": U, "geometri_m": GEO, "tutucu_m": TUTUCU_M, "taban_yuz": len(vf),
             "kaymasiz_yuz": sum(vf), "motor": "MOTOR_KILIT 1 (openfoam_motor), parametreler değişmedi",
             "varsayimlar": ["kanal yarı yüksekliği 0.038 m", "tel konumu ön kenardan 6.25 mm",
                             "ateşleyici gücü/genişlik ve 7.986 s kapanma Saffire ile aynı",
                             "tutucu 0.01 m", "H2O mol kesri 0.0116", "T 294.32 K", "2B simetrik (iki yüzlü) numune"]}
    (hedef / "BASS_VAKA.json").write_text(json.dumps(bilgi, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(bilgi, ensure_ascii=False))


if __name__ == "__main__":
    main()
