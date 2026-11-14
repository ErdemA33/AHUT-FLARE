#!/usr/bin/env python3
"""Otomatik aralik bulma (A carpani) + 3x3 kalibrasyon izgarasi. Kurallar baştan sayısal, tek koşu, termal bekçi.

Kullanim: setsid nohup python3 orkestrator.py > orkestrator.out 2>&1 &
Cikti: sonuclar.json (atomik), olay.log. Durdurma: dosya DUR olusturulursa yeni kosu baslatilmaz,
calisan kosu bitirilir. Acil: kill $(cat orkestrator.pid).
"""
import glob, json, math, os, re, shutil, signal, subprocess, sys, time
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent   # y/vakalar (tasinabilir)
BASE = KOK / "test_uzun_Nl7_Co05"          # mesh + ayar kaynagi (Nl 7, Nt 5, 26 um, maxCo 0.5)
OUT = KOK / "_kalibrasyon"
RUNS = OUT / "kosular"
SONUC = OUT / "sonuclar.json"
OLAY = OUT / "olay.log"
IZLE = KOK.parent / "optimizasyon_matched" / "kapasite" / "izle.py"
BASHRC = os.environ.get("OF_BASHRC", "/opt/openfoam14/etc/bashrc")

A0, TA0, TREF = 4.0e12, 24358.0, 1350.0
T_ISIK = 1500.0          # model tutusma olcutu: gaz maks T
HEDEF_LO, HEDEF_HI, HEDEF = 3.0, 4.5, 3.7
ALT_M = 30.0             # bilinen: x30 kucuk dt ile 4.7 s'ye kadar tutusmadi (dogrulanacak)
MAX_BRACKET = 4
M_CAP = 1000.0
UFUK_BRACKET, UFUK_GRID = 5.0, 6.0
GRID_SONRA = 2.5         # tutusmadan sonra ek simulasyon suresi [s]
KOSU_DUVAR_MAX = 4.5 * 3600   # 08.11: 3 saat sinirinda sensorlu_hedef02 7.535 s'de kesildi (olay.log 01:51:48)
TOPLAM_MAX = 30 * 3600
ACPI_MAX = 60.0
DISK_MIN = 5e9
T0 = time.time()


def olay(msg):
    with open(OLAY, "a") as f:
        f.write(time.strftime("%m-%d %H:%M:%S ") + msg + "\n")


def atomik_yaz(path, obj):
    tmp = str(path) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


SONUCLAR = json.load(open(SONUC)) if SONUC.exists() else []


def kaydet(r):
    SONUCLAR.append(r)
    atomik_yaz(SONUC, SONUCLAR)


def acpitz():
    for z in glob.glob("/sys/class/thermal/thermal_zone*"):
        if open(f"{z}/type").read().strip() == "acpitz":
            return int(open(f"{z}/temp").read()) / 1000.0
    return float("nan")


def sogumayi_bekle():
    for _ in range(60):          # 10 dk
        if acpitz() <= ACPI_MAX:
            return True
        time.sleep(10)
    return False


def solver_sayisi():
    return int(subprocess.run("pgrep -x foamMultiRun | wc -l", shell=True, capture_output=True, text=True).stdout)


def gazmax_oku(case):
    dirs = sorted(glob.glob(f"{case}/postProcessing/fluid/gazMax/*"), key=lambda p: float(os.path.basename(p)))
    rows = []
    for d in dirs:
        f = Path(d) / "volFieldValue.dat"
        if not f.exists():
            continue
        for l in open(f):
            if l.startswith("#") or not l.strip():
                continue
            p = l.split()
            try:
                rows.append((float(p[0]), float(p[1]), float(p[2]), float(p[3])))
            except Exception:
                pass
    return rows


def tign_bul(rows):
    for t, T, *_ in rows:
        if T > T_ISIK:
            return t
    return None


R2 = None   # (A2, Ta2) verilirse CO->CO2 reaksiyonu degistirilir


def a_hesapla(theta1, Ta):
    return math.exp(theta1 + Ta / TREF)


def theta1_of(A, Ta):
    return math.log(A) - Ta / TREF


def _tek_degistir(metin, desen, yeni, aciklama):
    """desen tam bir kez eslesmeli, yoksa hata (sessiz yama yok)."""
    sonuc, n = re.subn(desen, yeni, metin, count=0, flags=re.S)
    if n != 1:
        raise RuntimeError(f"yama '{aciklama}': {n} eslesme (1 beklenir)")
    return sonuc


def piroliz_yamala(fvmodels_yolu, piroliz):
    """piroliz: {'A1': 1/s, 'E1': J/mol, 'XL0': J/kg} (herhangi biri verilmeyebilir). Yalniz verilenler degisir."""
    s = Path(fvmodels_yolu).read_text()
    if piroliz.get("A1") is not None:
        s = _tek_degistir(s, r"(\bA1\s+)[0-9.eE+-]+;", lambda m: f"{m.group(1)}{piroliz['A1']:.6e};", "A1")
    if piroliz.get("E1") is not None:
        s = _tek_degistir(s, r"(\bE1\s+)[0-9.eE+-]+;", lambda m: f"{m.group(1)}{piroliz['E1']:.6e};", "E1")
    if piroliz.get("XL0") is not None:
        s = _tek_degistir(s, r"(\bXL0\s+)[0-9.eE+-]+;", lambda m: f"{m.group(1)}{piroliz['XL0']:.6e};", "XL0")
    Path(fvmodels_yolu).write_text(s)


def eps_sibal_yamala(g_yolu, eps):
    """0/fluid/G: fluid_to_sibal yamasinin emissivity degeri."""
    s = Path(g_yolu).read_text()
    s = _tek_degistir(s, r"(fluid_to_sibal\s*\{[^}]*?emissivity\s+uniform\s+)[0-9.eE+-]+;",
                      lambda m: f"{m.group(1)}{eps:.6f};", "eps_sibal")
    Path(g_yolu).write_text(s)


def vaka_kur(ad, A, Ta, baslangic, ufuk, maxdt=2e-5, piroliz=None, eps_sibal=None, decompose=True):
    """baslangic: 'restart1.5' veya 'sifir'.
    piroliz: {'A1','E1','XL0'} yamalari (constant/sibal/fvModels); eps_sibal: 0/fluid/G fluid_to_sibal emissivity.
    decompose=False: decomposePar calistirilmaz (testler icin; CFD baslatmaz)."""
    case = RUNS / ad
    if case.exists():
        shutil.rmtree(case)
    case.mkdir(parents=True)
    shutil.copytree(BASE / "system", case / "system")
    shutil.copytree(BASE / "constant", case / "constant")
    shutil.copy(BASE / "izle_T.sh", case / "izle_T.sh")
    # reactions: yalniz CH4 reaksiyonunun A ve Ta'si
    rp = case / "constant/fluid/reactions"
    s = rp.read_text()
    s = re.sub(r"(CH4oxReaction\s*\{[^}]*?\bA\s+)[0-9.eE+-]+;", lambda m: f"{m.group(1)}{A:.6e};", s, count=1, flags=re.S)
    s = re.sub(r"(CH4oxReaction\s*\{[^}]*?\bTa\s+)[0-9.eE+-]+;", lambda m: f"{m.group(1)}{Ta:.2f};", s, count=1, flags=re.S)
    if R2 is not None:
        s = re.sub(r"(COoxReaction\s*\{[^}]*?\bA\s+)[0-9.eE+-]+;", lambda m: f"{m.group(1)}{R2[0]:.6e};", s, count=1, flags=re.S)
        s = re.sub(r"(COoxReaction\s*\{[^}]*?\bTa\s+)[0-9.eE+-]+;", lambda m: f"{m.group(1)}{R2[1]:.2f};", s, count=1, flags=re.S)
    rp.write_text(s)
    if piroliz:
        piroliz_yamala(case / "constant/sibal/fvModels", piroliz)
    # ODE toleransi
    cp = case / "constant/fluid/chemistryProperties"
    s = cp.read_text()
    s = re.sub(r"absTol\s+[0-9.eE+-]+;", "absTol          1e-12;", s)
    s = re.sub(r"relTol\s+[0-9.eE+-]+;", "relTol          1e-5;", s)
    cp.write_text(s)
    # controlDict
    cd = case / "system/controlDict"
    s = cd.read_text()
    s = re.sub(r"^startFrom .*$", "startFrom       " + ("latestTime;" if baslangic == "restart1.5" else "startTime;"), s, flags=re.M)
    s = re.sub(r"^endTime .*$", f"endTime         {ufuk};", s, flags=re.M)
    s = re.sub(r"^writeInterval .*$", "writeInterval   0.2;", s, flags=re.M)
    s = re.sub(r"^maxDeltaT .*$", f"maxDeltaT       {maxdt:g};", s, flags=re.M)
    s = re.sub(r"^maxCo .*$", "maxCo            0.5;", s, flags=re.M)
    cd.write_text(s)
    # G radyasyon vekil cikislari (radyometre vekili sonra hesaplanacak)
    fn = case / "system/functions"
    s = fn.read_text()
    s += """
gIntegral
{
    type            volFieldValue;
    libs            ("libfieldFunctionObjects.so");
    region          fluid;
    writeControl    timeStep;
    writeInterval   10;
    writeFields     no;
    cellZone        all;
    operation       volIntegrate;
    fields          (G);
}
gMax
{
    $gIntegral;
    operation       max;
}
// --- Saffire-III deney sensorleri (konumlar: x = ornek on kenari 0.15 m + deney mesafesi) ---
// TC7-TC12 = A-F eslemesi (Saffire-I semasindan CIKARIM): A 30cm yuzey, B 32cm 3mm, C 34cm 10mm, D 60cm yuzey, E 62cm 8mm, F 64cm 15mm
sensGaz
{
    type            probes;
    libs            ("libsampling.so");
    region          fluid;
    writeControl    adjustableRunTime;
    writeInterval   0.02;
    fields          (T);
    probeLocations
    (
        (0.47 0.003 0)    // B  (TC8)  32 cm, 3 mm
        (0.49 0.010 0)    // C  (TC9)  34 cm, 10 mm
        (0.77 0.008 0)    // E  (TC11) 62 cm, 8 mm
        (0.79 0.015 0)    // F  (TC12) 64 cm, 15 mm
    );
}
sensYuzey
{
    $sensGaz;
    region          sibal;
    probeLocations
    (
        (0.45 -0.00003 0)  // A (TC7)  30 cm yuzey
        (0.75 -0.00003 0)  // D (TC10) 60 cm yuzey
    );
}
sensRadMenba
{
    $sensGaz;
    fields          (G);
    probeLocations
    (
        (0.20 0.29 0) (0.30 0.29 0) (0.40 0.29 0) (0.50 0.29 0) (0.60 0.29 0)   // menba yarisi (R1,R3)
    );
}
sensRadAkis
{
    $sensRadMenba;
    probeLocations
    (
        (0.70 0.29 0) (0.80 0.29 0) (0.90 0.29 0) (1.00 0.29 0) (1.05 0.29 0)   // akis asagisi yarisi (R2,R4)
    );
}
"""
    fn.write_text(s)
    if baslangic == "restart1.5":
        for i in range(4):
            (case / f"processor{i}").mkdir()
            shutil.copytree(BASE / f"processor{i}/constant", case / f"processor{i}/constant")
            shutil.copytree(BASE / f"processor{i}/1.5", case / f"processor{i}/1.5")
    else:
        shutil.copytree(BASE / "0", case / "0")
        if eps_sibal is not None:
            eps_sibal_yamala(case / "0/fluid/G", eps_sibal)
        if decompose:
            r = subprocess.run(f"source {BASHRC} >/dev/null 2>&1; cd {case} && decomposePar -allRegions > log.decomposePar 2>&1",
                               shell=True, executable="/bin/bash")
            if r.returncode != 0:
                raise RuntimeError("decomposePar basarisiz")
    return case


def kos(ad, m, Ta, baslangic, ufuk, asama, grid_sonra=None, retry_dt=None, piroliz=None, eps_sibal=None):
    """Bir koşu: baslat, izle, sonuc dondur. (CFD BASLATIR: ml/ icinden yalniz ml/kos_et.py cagirir.)"""
    A = m * A0 if asama == "aralik" else m  # grid asamasinda m = A dogrudan
    th1 = theta1_of(A, Ta)
    if os.path.exists(OUT / "DUR"):
        olay("DUR dosyasi var, yeni kosu baslatilmiyor"); return None
    if time.time() - T0 > TOPLAM_MAX:
        olay("toplam sure siniri asildi"); return None
    if shutil.disk_usage("/home").free < DISK_MIN:
        olay("disk alani < 5 GB, durduruluyor"); return None
    if not sogumayi_bekle():
        olay(f"acpitz {acpitz():.0f} C > {ACPI_MAX} C, 10 dk beklendi, durduruluyor"); return None
    maxdt = retry_dt or 2e-5
    case = vaka_kur(ad, A, Ta, baslangic, ufuk, maxdt, piroliz=piroliz, eps_sibal=eps_sibal)
    cmd =f"source {BASHRC} >/dev/null 2>&1; cd {case}; exec mpirun -np 4 foamMultiRun -parallel > log.run 2>&1"
    p = subprocess.Popen(["bash", "-c", cmd], preexec_fn=os.setsid)
    sid = p.pid
    csv = str(OUT / "termal.csv")
    subprocess.Popen([sys.executable, str(IZLE), str(sid), "4", csv, str(OLAY)], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    olay(f"BASLADI {ad}: A={A:.4e} Ta={Ta:.1f} theta1={th1:.3f} baslangic={baslangic} ufuk={ufuk} maxDeltaT={maxdt:g} SID={sid}")
    t_basla = time.time()
    t_ign = None
    durum = "ufuk"
    while p.poll() is None:
        time.sleep(20)
        rows = gazmax_oku(case)
        if rows:
            t_son = rows[-1][0]
            if t_ign is None:
                t_ign = tign_bul(rows)
                if t_ign is not None:
                    olay(f"{ad}: tutusma t_ign={t_ign:.4f} s (gaz maks T>{T_ISIK:.0f} K)")
            if t_ign is not None:
                hedef_t = t_ign if grid_sonra is None else t_ign + grid_sonra
                if t_son >= hedef_t:
                    durum = "tutustu"
                    os.killpg(sid, signal.SIGTERM); break
        if os.path.exists(str(csv) + ".iptal"):
            durum = "termal_iptal"; break
        if time.time() - t_basla > KOSU_DUVAR_MAX:
            durum = "zaman_asimi"
            os.killpg(sid, signal.SIGTERM); break
    time.sleep(5)
    try:
        os.killpg(sid, signal.SIGKILL)
    except Exception:
        pass
    p.wait()
    log = (case / "log.run").read_text(errors="ignore") if (case / "log.run").exists() else ""
    cokme = ("Floating point exception" in log) or ("FOAM FATAL" in log)
    rows = gazmax_oku(case)
    if t_ign is None and rows:
        t_ign = tign_bul(rows)
    if durum == "ufuk":
        if t_ign is not None:
            durum = "tutustu"          # tutusma kaydedildiyse sonraki cokme onemsiz (cokme alani ayrica kayitli)
        elif cokme:
            durum = "cokme"
        else:
            durum = "tutusma_yok"
    elif durum == "tutustu" and cokme and t_ign is None:
        durum = "cokme"
    r = dict(ad=ad, asama=asama, A=A, Ta=Ta, theta1=th1, m=(A / A0), baslangic=baslangic, ufuk=ufuk, maxDeltaT=maxdt,
             t_ign=t_ign, durum=durum, cokme=cokme, t_son=(rows[-1][0] if rows else None), T_maks=(max(x[1] for x in rows) if rows else None),
             duvar_s=round(time.time() - t_basla), komut=cmd, piroliz=piroliz, eps_sibal=eps_sibal)
    kaydet(r)
    olay(f"BITTI {ad}: durum={durum} t_ign={t_ign} t_son={r['t_son']} T_maks={r['T_maks']} duvar={r['duvar_s']} s")
    return r


def siniflandir(r):
    if r["durum"] == "tutustu":
        t = r["t_ign"]
        if t < HEDEF_LO:
            return "erken"
        if t <= HEDEF_HI:
            return "hedef"
        return "gec"
    if r["durum"] == "tutusma_yok":
        return "gec"
    return "guvenilmez"   # cokme, termal, zaman asimi


def asama1():
    # bilinen alt sinir: crash-fix kosusu (x30, kucuk dt) sonucu
    lo, hi = ALT_M, None            # lo: tutusmayan/gec; hi: erken/guvenilmez
    ters = {}
    hedef_m = None
    m = 100.0
    for it in range(MAX_BRACKET):
        if m > M_CAP:
            olay(f"aralik bulma: m={m:.0f} > {M_CAP:.0f}, tutusma bulunamadi -> DUR")
            return None
        ad = f"aralik_m{m:.0f}"
        r = kos(ad, m, TA0, "restart1.5", UFUK_BRACKET, "aralik")
        if r is None:
            return None
        if r["durum"] in ("termal_iptal", "zaman_asimi"):
            olay(f"{ad}: {r['durum']} -> sweep DUR"); return None
        sn = siniflandir(r)
        if sn == "guvenilmez" and r["durum"] == "cokme" and r["maxDeltaT"] == 2e-5:
            olay(f"{ad}: cokme, maxDeltaT=1e-5 ile bir kez tekrar")
            r = kos(ad + "_tekrar", m, TA0, "restart1.5", UFUK_BRACKET, "aralik", retry_dt=1e-5)
            if r is None:
                return None
            sn = siniflandir(r)
        ters[m] = (sn, r.get("t_ign"))
        olay(f"aralik bulma {it+1}/{MAX_BRACKET}: m={m:.0f} -> {sn} t_ign={r.get('t_ign')}")
        if sn == "hedef":
            hedef_m = m
            break
        if sn in ("erken", "guvenilmez"):
            hi = m if hi is None else min(hi, m)
        else:
            lo = m if lo is None else max(lo, m)
        if hi is None:
            m = lo * 3.0
        else:
            m = math.sqrt(lo * hi)
            if abs(math.log(hi / lo)) < 0.15:
                olay("aralik cok dar, duruyor"); break
    if hedef_m is not None:
        mstar = hedef_m
    elif hi is not None and lo is not None:
        mstar = math.sqrt(lo * hi)
    else:
        olay("aralik bulunamadi -> DUR"); return None
    alt = max([k for k, v in ters.items() if v[0] == "gec" and k < mstar] + [ALT_M])
    ust = min([k for k, v in ters.items() if v[0] in ("erken", "guvenilmez") and k > mstar] + [mstar * math.e ** 1.1])
    dth = min(1.5, max(0.5, math.log(ust / alt) / 2.0))
    olay(f"aralik sonucu: m*={mstar:.1f} alt={alt:.1f} ust={ust:.1f} dtheta={dth:.2f}")
    return mstar, dth


def asama2(mstar, dth):
    A_c = mstar * A0
    th_c = theta1_of(A_c, TA0)
    noktalar = []
    for dth_i in (0.0, -dth, dth):
        for fta in (1.0, 0.85, 1.15):
            noktalar.append((dth_i, fta))
    noktalar.sort(key=lambda x: (abs(x[0]) / dth + abs(x[1] - 1.0) / 0.15, x[0], x[1]))
    for k, (dt_i, fta) in enumerate(noktalar):
        Ta = TA0 * fta
        A = a_hesapla(th_c + dt_i, Ta)
        ad = f"izgara_{k+1:02d}_th{dt_i:+.2f}_Ta{Ta:.0f}"
        r = kos(ad, A, Ta, "sifir", UFUK_GRID, "izgara", grid_sonra=GRID_SONRA)
        if r is None:
            olay("izgara durduruldu"); return
        if r["durum"] == "termal_iptal":
            olay("termal iptal: sweep durduruluyor"); return
    olay("izgara bitti (9/9)")


def main():
    OUT.mkdir(exist_ok=True); RUNS.mkdir(exist_ok=True)
    open(OUT / "orkestrator.pid", "w").write(str(os.getpid()))
    olay("ORKESTRATOR basladi")
    while solver_sayisi() > 0:     # onceki kosunun (crash-fix) bitmesini bekle
        time.sleep(15)
    # crash-fix kosusunun sonucunu kayda gec
    cf = KOK / "test_A30_cokme_duzelt"
    rows = gazmax_oku(cf)
    if rows:
        t = tign_bul(rows)
        olay(f"x30 crash-fix kosusu: t_son={rows[-1][0]:.3f} s, T_maks={max(x[1] for x in rows):.0f} K, t_ign={t}")
        kaydet(dict(ad="x30_cokme_duzelt", asama="onceki", m=30.0, A=30 * A0, Ta=TA0, t_ign=t,
                    durum=("tutustu" if t else "tutusma_yok"), t_son=rows[-1][0], T_maks=max(x[1] for x in rows)))
    sonuc = asama1()
    if sonuc is None:
        olay("ORKESTRATOR: aşama 1 sonuçsuz, izgara kurulmadı. BITTI"); return
    mstar, dth = sonuc
    atomik_yaz(OUT / "izgara_plani.json", dict(mstar=mstar, dtheta=dth, A0=A0, Ta0=TA0, Tref=TREF))
    asama2(mstar, dth)
    olay("ORKESTRATOR BITTI")


if __name__ == "__main__":
    main()
