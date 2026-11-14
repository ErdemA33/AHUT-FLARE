#!/usr/bin/env python3
"""
of_gorsel_veri.py — of_gorsel.py'nin veri katmanı: OpenFOAM koşularından kesit, damla ve eğri verisi çıkarır.

of_kosular/ altına HİÇBİR ŞEY YAZILMAZ. Her koşu için of_gorsel/_is/<koşu>/ altında geçici bir çalışma
kopyası kurulur (constant/system kopya, processor* klasörleri salt-okunur sembolik bağ), reconstructPar
ve foamPostProcess orada çalışır; çıkarılan kesitler of_gorsel/onbellek_<koşu>.npz'ye yazılır ve geçici
kopya silinir. Önbellek varsa OpenFOAM hiç çağrılmaz.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np

KOK = Path(__file__).resolve().parent
OFK = KOK / "of_kosular"
CIK = KOK / "of_gorsel"
BASHRC = os.environ.get("OF_BASHRC", "/opt/openfoam14/etc/bashrc")
KARE = 20                       # koşu başına en fazla kare

KOSULAR = {
    "tek_damla": {"vaka": OFK / "tek_damla/isinimsiz", "log": OFK / "tek_damla_isinimsiz.log"},
    "sizinti_uzay": {"vaka": OFK / "sizinti/uzay", "log": OFK / "sizinti_uzay.log"},
    "sizinti_mars": {"vaka": OFK / "sizinti/mars", "log": OFK / "sizinti_mars.log"},
    # ayrıntılı 3B yarım alan (of_sizinti3d.py): kesit simetri düzleminin ilk hücre katmanı, karışık 2,5 / 5 mm
    "ince_uzay": {"vaka": OFK / "sizinti3d_ince/uzay", "log": OFK / "sizinti3d_uzay.log"},
    "ince_mars": {"vaka": OFK / "sizinti3d_ince/mars", "log": OFK / "sizinti3d_mars.log"},
    "ince_ay": {"vaka": OFK / "sizinti3d_ince/ay", "log": OFK / "sizinti3d_ay.log"},          # 4 yerçekimi
    "ince_dunya": {"vaka": OFK / "sizinti3d_ince/dunya", "log": OFK / "sizinti3d_dunya.log"},
    # metan (gaz) sızıntısı (of_gaz.py): yakıt alanı CH4 (görüntüleyicide "C7H16" yuvasında, etiketi koşuya özel)
    "gaz3d_uzay": {"vaka": OFK / "gaz3d_ince/uzay", "log": OFK / "gaz_3b_uzay.log", "yakit": "CH4"},
    "gaz3d_mars": {"vaka": OFK / "gaz3d_ince/mars", "log": OFK / "gaz_3b_mars.log", "yakit": "CH4"},
    "gaz2d_0": {"vaka": OFK / "gaz2d/0", "log": OFK / "gaz_2b_0.log", "yakit": "CH4"},
    "gaz2d_1.62": {"vaka": OFK / "gaz2d/1.62", "log": OFK / "gaz_2b_1.62.log", "yakit": "CH4"},
    "gaz2d_3.73": {"vaka": OFK / "gaz2d/3.73", "log": OFK / "gaz_2b_3.73.log", "yakit": "CH4"},
    "gaz2d_9.81": {"vaka": OFK / "gaz2d/9.81", "log": OFK / "gaz_2b_9.81.log", "yakit": "CH4"},
}


def mevcut(ad):
    """Koşunun 0 dışında en az iki yazılmış zamanı var mı (ince koşular kuyruk bitmeden yoksa atlanır)."""
    p0 = KOSULAR[ad]["vaka"] / "processor0"
    return p0.exists() and len([d for d in p0.iterdir() if re.match(r"^[\d.e+-]+$", d.name) and d.name != "0"]) >= 2

# tek adım heptan kimyası (constant/reactions ile aynı): C7H16^0.25 + 11 O2^1.5 -> 7 CO2 + 8 H2O
KIM_A, KIM_TA = 2811706.626, 7940.357749            # kmol/m3 tabanlı SI, Ta (K)
M_YAKIT, M_O2 = 100.2, 32.0
DH_YANMA = 4.5011e9                                  # J/kmol yakıt (hf: C7H16 -187.8, CO2 -393.5, H2O -241.8 kJ/mol)


def kabuk(cmd, cwd):
    r = subprocess.run(["bash", "-c", f"source {BASHRC} >/dev/null 2>&1; {cmd}"], cwd=cwd,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"'{cmd}' başarısız ({cwd}):\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    return r.stdout


def zamanlar(vaka):
    z = []
    for d in (vaka / "processor0").iterdir():
        try:
            z.append((float(d.name), d.name))
        except ValueError:
            pass
    return sorted(z)


def sec(z, n=KARE):
    if len(z) <= n:
        return z
    i = np.unique(np.round(np.linspace(0, len(z) - 1, n)).astype(int))
    return [z[k] for k in i]


def alan_oku(f):
    """ascii OpenFOAM alanının internalField'ı -> (N,) ya da (N,3); uniform ise (değer, None)."""
    s = Path(f).read_text(errors="replace")
    m = re.search(r"internalField\s+uniform\s+([^;]+);", s)
    if m:
        v = m.group(1).strip().strip("()").split()
        return np.array([float(x) for x in v]), "uniform"
    m = re.search(r"internalField\s+nonuniform\s+List<(\w+)>\s*\n?(\d+)\s*\n?\(", s)
    if not m:
        raise ValueError(f"internalField okunamadı: {f}")
    n = int(m.group(2))
    govde = s[m.end():]
    if m.group(1) == "vector":
        govde = govde[:govde.index("\n)\n") if "\n)\n" in govde else None]
        a = np.array(re.sub(r"[()]", " ", govde).split()[:3 * n], dtype=float).reshape(n, 3)
    else:
        a = np.array(govde.split(maxsplit=n)[:n], dtype=float)
    return a, None


def vtk_noktalar(f):
    """foamToVTK lagrangian (legacy ascii): POINTS + d."""
    t = Path(f).read_text(errors="replace").split()
    if "POINTS" not in t:
        return np.zeros((0, 3)), np.zeros(0)
    i = t.index("POINTS")
    n = int(t[i + 1])
    p = np.array(t[i + 3:i + 3 + 3 * n], dtype=float).reshape(n, 3)
    d = np.full(n, np.nan)
    for k in range(i, len(t) - 3):
        if t[k] == "d" and t[k + 1] == "1" and t[k + 2] == str(n):
            d = np.array(t[k + 4:k + 4 + n], dtype=float)
            break
    return p, d


def hesapla_qdot(T, rho, Yf, Yo, kappa=None):
    cf = np.clip(rho * Yf / M_YAKIT, 0, None)
    co = np.clip(rho * Yo / M_O2, 0, None)
    w = KIM_A * np.exp(-KIM_TA / np.maximum(T, 200.0)) * cf ** 0.25 * co ** 1.5
    if kappa is not None:
        w = w * kappa
    return w * DH_YANMA


def cikar(ad, yaz=print):
    """Kesit + damla verisini çıkarır (önbellekli). Dönen sözlük numpy dizileri içerir."""
    onb = CIK / f"onbellek_{ad}.npz"
    k = KOSULAR[ad]
    vaka = k["vaka"]
    if onb.exists() and onb.stat().st_mtime > max(p.stat().st_mtime for p in (vaka / "processor0").iterdir()):
        z = np.load(onb, allow_pickle=True)
        return {a: z[a] for a in z.files}
    yakit = k.get("yakit", "C7H16")
    tum = zamanlar(vaka)
    secim = sec(tum)
    adlar = [b for a, b in secim]
    is_ = CIK / "_is" / ad
    if is_.exists():
        shutil.rmtree(is_)
    is_.mkdir(parents=True)
    shutil.copytree(vaka / "constant", is_ / "constant", symlinks=True)
    shutil.copytree(vaka / "system", is_ / "system", symlinks=True)
    cd = is_ / "system/controlDict"
    s = cd.read_text()
    s = re.sub(r"writeFormat\s+\w+;", "writeFormat     ascii;", s)
    s = re.sub(r"writeCompression\s+\w+;", "writeCompression off;", s)
    cd.write_text(s)
    (is_ / "system/functions").write_text("FoamFile { format ascii; class dictionary; object functions; }\n")
    for p in sorted(vaka.glob("processor*")):
        (is_ / p.name).symlink_to(p.resolve(), target_is_directory=True)
    try:
        yaz(f"  {ad}: reconstructPar ({len(adlar)} zaman / {len(tum)} yazılmış)")
        alanlar = f"(T O2 {yakit} U rho Qdot PaSR:kappa)"
        kabuk(f"reconstructPar -time '{','.join(adlar)}' -fields '{alanlar}' -lagrangianFields '(d nParticle)' -withZero",
              is_)
        kabuk(f"foamPostProcess -func writeCellCentres -time '{adlar[1]}'", is_)
        kabuk(f"foamPostProcess -func writeCellVolumes -time '{adlar[1]}'", is_)
        if yakit == "C7H16":                             # gaz koşularında damla bulutu yok
            yaz(f"  {ad}: foamToVTK (lagrangian)")
            kabuk(f"foamToVTK -ascii -noInternal -excludePatches '(\".*\")' -noFaceZones -useTimeName "
                  f"-time '{','.join(adlar)}' -fields '(d)'", is_)
        C, _ = alan_oku(is_ / adlar[1] / "C")
        V, _ = alan_oku(is_ / adlar[1] / "Vc")
        x, y, zc = C[:, 0], C[:, 1], C[:, 2]
        hc = np.cbrt(V)                                  # hücre kenarı (küp hücreler)
        zk = zc[np.argmin(np.abs(zc))]                  # z=0'a en yakın hücre merkezi (ince koşuda ince katman)
        kat = np.abs(zc - zk) < 0.5 * hc - 1e-9          # z = zk düzlemini kesen hücreler (karışık boyutlu olabilir)
        h = float(hc[kat].min())                         # piksel = en küçük hücre; büyük hücreler birkaç piksel kaplar
        xmin, ymin = float((x[kat] - hc[kat] / 2).min()), float((y[kat] - hc[kat] / 2).min())
        xmax, ymax = float((x[kat] + hc[kat] / 2).max()), float((y[kat] + hc[kat] / 2).max())
        nx, ny = int(round((xmax - xmin) / h)), int(round((ymax - ymin) / h))
        xs, ys = xmin + h * (np.arange(nx) + 0.5), ymin + h * (np.arange(ny) + 0.5)
        hucre = np.full((ny, nx), -1, dtype=np.int32)
        for c in np.nonzero(kat)[0]:
            k_ = int(round(hc[c] / h))
            i0 = int(round((x[c] - hc[c] / 2 - xmin) / h))
            j0 = int(round((y[c] - hc[c] / 2 - ymin) / h))
            hucre[j0:j0 + k_, i0:i0 + k_] = c
        assert (hucre >= 0).all(), "kesit ızgarası kapanmadı"
        hboy = (hc[hucre] * 1e3).astype(np.float32)     # piksel başına gerçek hücre boyutu (mm)
        veri = {k_: np.zeros((len(adlar), ny, nx), dtype=np.float32) for k_ in ("T", "O2", "C7H16", "Qdot", "U")}
        parx, pary, pard, parn = [], [], [], []
        qkaynak = "alan"
        for j, tn in enumerate(adlar):
            d = is_ / tn
            def oku(f, varsay=None):
                if not (d / f).exists():
                    return varsay
                a, u = alan_oku(d / f)
                return np.full(len(C), a[0]) if u else a
            T = oku("T")
            rho = oku("rho")
            if rho is None:                              # t=0: rho yazılmamış -> ideal gaz, 1 atm, hava
                rho = 101325.0 * 28.9 / (8314.0 * T)
            Yf = oku(yakit, np.zeros(len(C)))
            Yo = oku("O2")
            U = oku("U")
            Umag = np.linalg.norm(U.reshape(len(C), -1), axis=1) if U is not None and U.ndim == 2 \
                else np.full(len(C), float(np.linalg.norm(U)) if U is not None else 0.0)
            Q = oku("Qdot")
            if Q is None:
                if j > 0:
                    qkaynak = "hesap"
                Q = hesapla_qdot(T, rho, Yf, Yo, oku("PaSR:kappa"))
            for k_, a in (("T", T), ("O2", Yo), ("C7H16", Yf), ("Qdot", Q), ("U", Umag)):
                veri[k_][j] = a[hucre]
            f = sorted((is_ / "VTK" / "lagrangian").glob(f"*/*_{tn}.vtk")) if (is_ / "VTK/lagrangian").exists() \
                else []
            if f:
                p, dd = vtk_noktalar(f[0])
            else:
                p, dd = np.zeros((0, 3)), np.zeros(0)
            parx.append((p[:, 0] * 1e3).astype(np.float32))
            pary.append((p[:, 1] * 1e3).astype(np.float32))
            pard.append((dd * 1e6).astype(np.float32))
            parn.append(len(p))
        # doğrulama: Qdot alanı olan koşuda hesapla_qdot ile karşılaştır
        qkontrol = np.nan
        if qkaynak == "alan" and (is_ / adlar[len(adlar) // 2] / "PaSR:kappa").exists():
            d = is_ / adlar[len(adlar) // 2]
            q1, _ = alan_oku(d / "Qdot")
            q2 = hesapla_qdot(alan_oku(d / "T")[0], alan_oku(d / "rho")[0], alan_oku(d / "C7H16")[0],
                              alan_oku(d / "O2")[0], alan_oku(d / "PaSR:kappa")[0])
            qkontrol = float(q2.sum() / q1.sum()) if q1.sum() > 0 else np.nan
        sonuc = {"zaman": np.array([a for a, b in secim]), "tum_zaman_sayisi": np.array(len(tum)),
                 "x": (xs * 1e3).astype(np.float32), "y": (ys * 1e3).astype(np.float32),
                 "h_mm": np.array(h * 1e3), "z_kesit_mm": np.array(zk * 1e3), "hucre_no": hucre,
                 "hucre_sayisi": np.array(len(C)), "qkaynak": np.array(qkaynak), "qkontrol": np.array(qkontrol),
                 "hboy_mm": hboy, "h_maks_mm": np.array(float(hboy.max())),
                 "par_n": np.array(parn)}
        for k_, a in veri.items():
            sonuc["f_" + k_] = a
        sonuc["par_x"] = np.array(parx, dtype=object)
        sonuc["par_y"] = np.array(pary, dtype=object)
        sonuc["par_d"] = np.array(pard, dtype=object)
        CIK.mkdir(exist_ok=True)
        np.savez_compressed(onb, **sonuc)
        return sonuc
    finally:
        if not os.environ.get("OF_GORSEL_TUT"):
            shutil.rmtree(is_, ignore_errors=True)


if __name__ == "__main__":
    import sys
    for a in sys.argv[1:] or list(KOSULAR):
        r = cikar(a)
        print(a, {k: (v.shape if hasattr(v, "shape") and v.ndim else v) for k, v in r.items()
                  if not k.startswith("par_")}, "parsel/kare:", list(r["par_n"]))
