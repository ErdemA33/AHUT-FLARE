#!/usr/bin/env python3
"""
scripts/flex_flame_quantify.py — NASA/TP-2015-216046 (Dietrich ve ark. 2015, "Detailed Results From the Flame
Extinguishment Experiment (FLEX) March 2009 to December 2011") Ek B grafiklerinden (Şekil 5-280, s. 29-305)
damla çapı karesi ve alev çapı geçmişlerini SAYISALLAŞTIRIR. Ham metin dosyaları psi.nasa.gov'da (kayıt gerekli),
diskte yok; grafikler PDF'de gömülü JPEG (1269x831, 220 ppi).

Yöntem (raster):
  - çerçeve: en uzun koyu sütunlar/satırlar (sol/sağ/alt eksen)
  - eksen rakamları: koyu bileşenler -> Liberation Sans ile üretilen şablonlara benzerlik (0-9, eksi) ->
    etiket değeri; etiket merkezi = ana çentik konumu -> doğrusal piksel-değer eşlemesi (3 eksen ayrı)
  - noktalar: kırmızı (damla d², sol eksen), mavi (LLUV alev çapı, sağ eksen; OH* kemilüminesans),
    yeşil (renkli kamera alev çapı, sağ eksen); içi boş halka bileşenlerinin merkezi. Gösterge (legend) kutusu
    çıkarılır.
Doğrulama (bağımsız): sayısallaştırılmış ilk d² ve d² eğimi (yanma hızı K) psi_flex_testler.csv ile karşılaştırılır.
Çıktı: data/droplet_flex_flame_points.csv (test, seri, t_s, deger), data/droplet_flex_flame_summary.csv (test başına alev/damla
oranı vb.). CSV'lere dokunmaz (yalnız yeni dosya yazar).
Kullanım: python3 scripts/flex_flame_quantify.py [--sayfa 200] [--cekirdek 8]
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

KOK = Path(__file__).resolve().parent.parent
RAPOR = Path("/mnt/ssd/nasaspaceapp/FLEX12/1/makaleler/20150023456.pdf")
FLEX_CSV = Path("/mnt/ssd/nasaspaceapp/FLEX12/psi_flex_testler.csv")
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
KARAKTER = "0123456789-"
SABLON_BOY = (24, 16)          # (y, x) normalleştirilmiş şablon


def _norm(m):
    """Glifi sınırlayıcı kutusuna kırpıp 24x16'ya gerer."""
    ys, xs = np.nonzero(m)
    m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    im = Image.fromarray((m * 255).astype(np.uint8)).resize(SABLON_BOY[::-1], Image.BILINEAR)
    return np.asarray(im, float) / 255, m.shape


_SABLON = None


def sablonlar():
    global _SABLON
    if _SABLON is None:
        f = ImageFont.truetype(FONT, 60)
        _SABLON = {}
        for c in KARAKTER:
            im = Image.new("L", (80, 90), 0)
            ImageDraw.Draw(im).text((10, 5), "–" if c == "-" else c, font=f, fill=255)
            _SABLON[c] = _norm(np.asarray(im) > 128)
    return _SABLON


def karakter_tani(m, ayrinti=False):
    """İkili glif -> karakter. Eksi: geniş ve alçak; '1': çok dar; diğerleri: gerilmiş şablonla en düşük fark."""
    h, w = m.shape
    if w > 1.6 * h:
        return "-"
    if w < 0.45 * h:
        return "1"
    a, _ = _norm(m)
    puan = {c: float(np.abs(a - s).mean()) for c, (s, shp) in sablonlar().items() if c not in "-1"}
    ad = min(puan, key=puan.get)
    return (ad, puan) if ayrinti else ad


def etiketler(dark, bolge, yon):
    """bolge: (y0, y1, x0, x1); yon 'yatay' (alt eksen: glifler x'te dizilir) ya da 'dikey' (sol/sağ: satırlar).
    -> [(değer, merkez_px)]"""
    y0, y1, x0, x1 = bolge
    y0, x0 = max(0, int(y0)), max(0, int(x0))
    y1, x1 = min(dark.shape[0], int(y1)), min(dark.shape[1], int(x1))
    sub = dark[y0:y1, x0:x1]
    if sub.size == 0:
        return []
    lab, n = ndimage.label(sub)
    sl = ndimage.find_objects(lab)
    glif = []
    for k, s in enumerate(sl):
        hh, ww = s[0].stop - s[0].start, s[1].stop - s[1].start
        if hh < 6 and ww < 6:
            continue
        m = lab[s] == k + 1
        glif.append({"y0": s[0].start + y0, "y1": s[0].stop + y0, "x0": s[1].start + x0, "x1": s[1].stop + x0,
                     "c": karakter_tani(m), "h": hh, "w": ww})
    if not glif:
        return []
    # rakam yüksekliği: medyan (eksi işareti hariç)
    hmed = np.median([g["h"] for g in glif if g["c"] != "-"] or [10])
    glif = [g for g in glif if g["c"] == "-" or abs(g["h"] - hmed) < 0.35 * hmed]
    # gruplama: aynı satır (dikey eksen) ya da aynı satırda yakın x (yatay eksen)
    glif.sort(key=lambda g: ((g["y0"] + g["y1"]) / 2, g["x0"]) if yon == "dikey" else (g["x0"],))
    gruplar = []
    for g in glif:
        yc = (g["y0"] + g["y1"]) / 2
        if gruplar:
            s = gruplar[-1]
            syc = np.mean([(q["y0"] + q["y1"]) / 2 for q in s])
            if abs(yc - syc) < 0.6 * hmed and g["x0"] - max(q["x1"] for q in s) < 0.9 * hmed:
                s.append(g)
                continue
        gruplar.append([g])
    out = []
    for s in gruplar:
        s.sort(key=lambda q: q["x0"])
        metin = "".join(q["c"] for q in s)
        if not re.fullmatch(r"-?\d+", metin):
            continue
        rak = [q for q in s if q["c"] != "-"]
        if yon == "dikey":
            mer = np.mean([(q["y0"] + q["y1"]) / 2 for q in rak])
        else:
            mer = (min(q["x0"] for q in rak) + max(q["x1"] for q in rak)) / 2
        out.append((float(metin), mer))
    return out


def eksen_esle(et):
    """[(değer, px)] -> (a, b) değer = a px + b; aykırı etiket (yanlış okuma) sağlam uydurmayla atılır."""
    if len(et) < 3:
        return None
    v = np.array([e[0] for e in et])
    p = np.array([e[1] for e in et])
    en = None
    for i in range(len(v)):
        for j in range(i + 1, len(v)):
            if p[i] == p[j] or v[i] == v[j]:
                continue
            a = (v[j] - v[i]) / (p[j] - p[i])
            b = v[i] - a * p[i]
            r = np.abs(a * p + b - v)
            tol = 0.15 * np.median(np.abs(np.diff(np.sort(v)))) if len(v) > 1 else 0.1
            ic = r < max(tol, 1e-6)
            if en is None or ic.sum() > en[0]:
                en = (ic.sum(), ic)
    if en is None or en[0] < 3:
        return None
    ic = en[1]
    A = np.c_[p[ic], np.ones(ic.sum())]
    a, b = np.linalg.lstsq(A, v[ic], rcond=None)[0]
    return float(a), float(b), int(ic.sum())


def renkli(a, ad):
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    if ad == "kirmizi":
        return (R > 170) & (G < 110) & (B < 110)
    if ad == "mavi":
        return (B > 170) & (R < 110) & (G < 130)
    return (G > 170) & (R < 140) & (B < 140)


def sayisallastir(jpg):
    a = np.asarray(Image.open(jpg).convert("RGB")).astype(int)
    H, W, _ = a.shape
    dark = a.max(2) < 100
    cols, rows = dark.sum(0), dark.sum(1)
    # sol / sağ eksen: en uzun iki koyu sütun (birbirinden uzak)
    c = np.argsort(cols)[::-1]
    xl = int(c[0])
    xr = int(next(x for x in c[1:] if abs(x - xl) > W / 3))
    xl, xr = min(xl, xr), max(xl, xr)
    r = np.argsort(rows)[::-1]
    yb = int(next(y for y in r if y > H / 2))
    # üst kenar: çerçevenin üstü (sol eksen sütununun en üst koyu pikseli)
    ys = np.nonzero(dark[:, xl])[0]
    yt = int(ys.min())
    et_sol = etiketler(dark, (yt - 12, yb + 14, xl - 48, xl - 3), "dikey")
    et_sag = etiketler(dark, (yt - 12, yb + 14, xr + 3, xr + 48), "dikey")
    et_alt = etiketler(dark, (yb + 6, min(H, yb + 40), max(0, xl - 30), min(W, xr + 30)), "yatay")
    es = {"sol": eksen_esle(et_sol), "sag": eksen_esle(et_sag), "alt": eksen_esle(et_alt)}
    if any(v is None for v in es.values()):
        return None, {"hata": "eksen okunamadı", **{k: v for k, v in es.items()}}
    # gösterge kutusu: çerçeve içindeki koyu METİN bileşenleri (çentikler hariç: kenardan 28 px içeride,
    # yükseklik 8-30 px); en kalabalık kümenin sınırlayıcı kutusu + soldaki işaretler için pay
    ic = dark.copy()
    ic[:, :xl + 28] = False
    ic[:, xr - 28:] = False
    ic[:yt + 28] = False
    ic[yb - 28:] = False
    lab, n = ndimage.label(ic)
    kutu = None
    if n:
        bx = [s_ for s_ in ndimage.find_objects(lab) if 8 <= s_[0].stop - s_[0].start <= 30]
        if bx:
            c = np.array([[(q[0].start + q[0].stop) / 2, (q[1].start + q[1].stop) / 2] for q in bx])
            med = np.median(c, 0)
            bx = [q for q, cc in zip(bx, c) if abs(cc[0] - med[0]) < 120 and abs(cc[1] - med[1]) < 350]
            y0 = min(q[0].start for q in bx); y1 = max(q[0].stop for q in bx)
            x0 = min(q[1].start for q in bx); x1 = max(q[1].stop for q in bx)
            kutu = (y0 - 10, y1 + 10, x0 - 45, x1 + 5)
    seri = {}
    for ad, eksen, kod in (("kirmizi", "sol", "d2"), ("mavi", "sag", "alev_lluv"), ("yesil", "sag", "alev_renk")):
        m = renkli(a, ad)
        m[:, :xl + 2] = False
        m[:, xr - 1:] = False
        m[:yt + 1] = False
        m[yb - 1:] = False
        if kutu:
            m[max(0, kutu[0]):kutu[1], max(0, kutu[2]):kutu[3]] = False
        # sütun taraması (halkalar üst üste biniyor): 3 px'lik sütun dilimlerinde rengin ortanca satırı.
        # Aynı dilimde birbirinden uzak iki küme varsa (aykırı nokta) ikisi de ayrı nokta olarak alınır.
        mer = []
        for x0_ in range(xl + 2, xr - 1, 3):
            yy = np.nonzero(m[:, x0_:x0_ + 3].any(1))[0]
            if len(yy) < 2:
                continue
            kume = np.split(yy, np.nonzero(np.diff(yy) > 12)[0] + 1)
            for k_ in kume:
                if len(k_) >= 2:
                    mer.append((float(np.median(k_)), x0_ + 1.0))
        mer = np.array(mer).reshape(-1, 2)
        if not len(mer):
            seri[kod] = np.zeros((0, 2))
            continue
        ax, bx = es["alt"][:2]
        ay, by = es[eksen][:2]
        seri[kod] = np.c_[ax * mer[:, 1] + bx, ay * mer[:, 0] + by]
        seri[kod] = seri[kod][np.argsort(seri[kod][:, 0])]
    return seri, {"cerceve": (xl, xr, yt, yb), "eksen": es, "gosterge": kutu}


def sayfa_testleri(pdf):
    """Ek B: sayfa -> test no (altyazı 'Figure N.—Test FLEX–NNN')."""
    out = {}
    n = int(re.search(r"Pages:\s+(\d+)", subprocess.run(["pdfinfo", str(pdf)], capture_output=True,
                                                         text=True).stdout).group(1))
    for p in range(28, n + 1):
        t = subprocess.run(["pdftotext", "-f", str(p), "-l", str(p), str(pdf), "-"], capture_output=True,
                           text=True).stdout
        m = re.search(r"Figure (\d+)\.\s*[—-]\s*Test FLEX\s*[−–-]\s*(\d+)\.(.{0,300})", t, re.S)
        if m and 5 <= int(m.group(1)) <= 280:
            out[p] = (int(m.group(2)), altyazi_kosulu(m.group(3)))
    return out


def altyazi_kosulu(metin):
    """'... methanol droplet burning in a 0.14/0.50/0.36 O2/N2/CO2, 1.0-atm ...' -> {yakit, X{tür: kesir}, p_atm}"""
    t = " ".join(metin.split())
    y = re.search(r"(heptane|methanol)", t.lower())
    k = {"yakit": y.group(1) if y else None, "X": None, "p_atm": None}
    m = re.search(r"(\d?\.\d+(?:\s*/\s*\d?\.\d+)+)\s*((?:O|N|CO|He)\s*2?(?:\s*/\s*(?:O|N|CO|He)\s*2?)+)", t)
    if m:
        v = [float(x) for x in re.split(r"\s*/\s*", m.group(1))]
        ad = [re.sub(r"\s", "", x) for x in re.split(r"\s*/\s*", m.group(2))]
        ad = [{"O": "O2", "N": "N2", "CO": "CO2", "O2": "O2", "N2": "N2", "CO2": "CO2", "He": "He"}.get(a, a) for a in ad]
        if len(v) == len(ad):
            k["X"] = dict(zip(ad, v))
    elif "air" in t.lower():
        k["X"] = {"O2": 0.21, "N2": 0.79}
    m = re.search(r"(\d+(?:\.\d+)?)\s*-?\s*atm", t)
    if m:
        k["p_atm"] = float(m.group(1))
    return k


def eslestir(oz, flex, atla=1.5):
    """Rapordaki 'FLEX–NNN' numaraları CSV test numaralarıyla aynı değil (rapor tabloda olmayan denemeleri de
    numaralandırıyor; ör. FLEX–167 grafiği CSV 166). Sırayı koruyan hizalama (dinamik programlama):
    maliyet = koşul farkı (yakıt, gaz kesirleri, basınç; altyazıdan) + ölçüm farkı (ilk çap, K); her iki
    taraftan atlama serbest ama 'atla' maliyetli. -> oz'a 'test' (CSV) ve 'eslesme_hatasi'."""
    oz = oz.sort_values("rapor_no").reset_index(drop=True)
    fl = flex.sort_values("test").reset_index(drop=True)
    n, m = len(oz), len(fl)
    C = np.full((n, m), 9.0)
    for i, r in oz.iterrows():
        k = r.kosul if isinstance(r.kosul, dict) else {}
        for j, f in fl.iterrows():
            c = 0.0
            if k.get("yakit") and k["yakit"] != f.yakit:
                c += 5
            if k.get("X"):
                X = k["X"]
                c += 10 * (abs(X.get("O2", 0) - f.oksijen_yuzde / 100) + abs(X.get("CO2", 0) - f.co2_yuzde / 100)
                           + abs(X.get("He", 0) - f.he_yuzde / 100))
            if k.get("p_atm"):
                c += 2 * abs(k["p_atm"] - f.basinc_kpa / 101.325)
            if np.isfinite(r.get("d2_ilk_mm2", np.nan)) and f.ilk_cap_mm == f.ilk_cap_mm:
                c += min(abs(np.sqrt(r.d2_ilk_mm2) / f.ilk_cap_mm - 1), 0.5) * 2
            C[i, j] = c
    D = np.full((n + 1, m + 1), np.inf)
    D[0, :] = np.arange(m + 1) * atla
    D[:, 0] = np.arange(n + 1) * atla
    B = np.zeros((n + 1, m + 1), int)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sec = (D[i - 1, j - 1] + C[i - 1, j - 1], D[i - 1, j] + atla, D[i, j - 1] + atla)
            B[i, j] = int(np.argmin(sec))
            D[i, j] = sec[B[i, j]]
    test, hata = [np.nan] * n, [np.nan] * n
    i, j = n, m
    while i > 0 and j > 0:
        if B[i, j] == 0:
            test[i - 1], hata[i - 1] = int(fl.test[j - 1]), float(C[i - 1, j - 1])
            i, j = i - 1, j - 1
        elif B[i, j] == 1:
            i -= 1
        else:
            j -= 1
    oz["test"] = test
    oz["eslesme_hatasi"] = hata
    # kötü eşleşme (koşul tutmuyor) -> eşleştirme yok
    oz.loc[oz.eslesme_hatasi > 1.5, "test"] = np.nan
    return oz


def _is(arg):
    pdf, p, (test, yakit) = arg
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["pdfimages", "-j", "-f", str(p), "-l", str(p), str(pdf), f"{d}/g"], check=True)
        j = sorted(Path(d).glob("g-*"))
        if not j:
            return test, p, None, {"hata": "görüntü yok"}
        j = max(j, key=lambda f: f.stat().st_size)
        try:
            s, bilgi = sayisallastir(j)
        except Exception as e:     # bozuk / farklı düzen
            return test, p, None, {"hata": f"{type(e).__name__}: {e}"}
    return test, p, s, bilgi


def ozet(test, s, flex):
    """Test başına: ilk d² (t in [0.3, 1] s), d² eğimi (K), alev/damla oranı (yanmanın %20-60 zaman aralığı)."""
    import pandas as pd
    r = {"test": test}
    d2 = s["d2"]
    d2 = d2[d2[:, 0] > 0.3] if len(d2) else d2
    if len(d2) >= 8:
        bas = d2[d2[:, 0] < d2[0, 0] + 0.7]
        r["d2_ilk_mm2"] = float(np.median(bas[:, 1])) if len(bas) else np.nan
        # alev varken (LLUV ya da renk noktası olan zaman aralığı) d² eğimi
        alev = np.r_[s["alev_lluv"][:, 0], s["alev_renk"][:, 0]] if (len(s["alev_lluv"]) + len(s["alev_renk"])) else []
        t_son = np.percentile(alev, 95) if len(alev) else d2[-1, 0]
        x = d2[(d2[:, 0] > 0.5) & (d2[:, 0] < t_son)]
        if len(x) >= 6:
            k = np.polyfit(x[:, 0], x[:, 1], 1)[0]
            r["K_say_mm2_s"] = float(-k)
            r["t_alev_son_s"] = float(t_son)
            for kod in ("alev_lluv", "alev_renk"):
                f = s[kod]
                if len(f) < 5:
                    continue
                t0, t1 = 0.5, t_son
                f = f[(f[:, 0] > t0 + 0.2 * (t1 - t0)) & (f[:, 0] < t0 + 0.6 * (t1 - t0))]
                if len(f) < 3:
                    continue
                dd = np.sqrt(np.clip(np.interp(f[:, 0], d2[:, 0], d2[:, 1]), 1e-3, None))
                r[f"{kod}_mm"] = float(np.median(f[:, 1]))
                r[f"oran_{kod}"] = float(np.median(f[:, 1] / dd))
                r[f"d_ayni_an_{kod}_mm"] = float(np.median(dd))
    return r


def hedef_tablosu(nk, oz, dilim=4):
    """Kalibrasyon hedefi: test başına alev ömrünün %15-70'i arasında 'dilim' eşit zaman diliminde
    ortanca d/d0 ve alev/damla çap oranı (LLUV ve renkli kamera ayrı). d0 = CSV ilk çapı."""
    sat = []
    for r in oz.dropna(subset=["test", "ilk_cap_mm"]).itertuples():
        x = nk[nk.rapor_no == r.rapor_no]
        d2 = x[x.seri == "d2"].sort_values("t_s")
        if len(d2) < 8:
            continue
        for kod in ("alev_lluv", "alev_renk"):
            f = x[x.seri == kod].sort_values("t_s")
            if len(f) < 8:
                continue
            t0, t1 = max(0.3, f.t_s.min()), f.t_s.quantile(0.95)
            if t1 <= t0:
                continue
            for k in range(dilim):
                a = t0 + (t1 - t0) * (0.15 + 0.55 * k / dilim)
                b = t0 + (t1 - t0) * (0.15 + 0.55 * (k + 1) / dilim)
                ff = f[(f.t_s >= a) & (f.t_s < b)]
                if len(ff) < 3:
                    continue
                dd = np.sqrt(np.clip(np.interp(ff.t_s, d2.t_s, d2.deger), 1e-3, None))
                sat.append({"test": int(r.test), "seri": kod, "t_s": float(ff.t_s.median()),
                            "d_oran": float(np.median(dd) / r.ilk_cap_mm), "oran": float(np.median(ff.deger / dd)),
                            "n_nokta": int(len(ff))})
    return pd.DataFrame(sat)


def main():
    import pandas as pd
    from multiprocessing import Pool
    a = argparse.ArgumentParser()
    a.add_argument("--sayfa", type=int)
    a.add_argument("--cekirdek", type=int, default=8)
    k = a.parse_args()
    st = sayfa_testleri(RAPOR)
    if k.sayfa:
        st = {k.sayfa: st.get(k.sayfa, (-1, None))}
    print(f"{len(st)} grafik sayfası", flush=True)
    with Pool(k.cekirdek) as h:
        son = h.map(_is, [(RAPOR, p, t) for p, t in sorted(st.items())])
    flex = pd.read_csv(FLEX_CSV)
    nok, oz, hata = [], [], []
    flex["yakit"] = flex.yakit.astype(str)
    for c in ("co2_yuzde", "he_yuzde", "oksijen_yuzde"):
        flex[c] = flex[c].fillna(0)
    yak = {p: y for p, (t, y) in st.items()}
    for test, p, s, bilgi in son:
        if s is None:
            hata.append({"rapor_no": test, "sayfa": p, **{kk: str(v) for kk, v in bilgi.items()}})
            oz.append({"rapor_no": test, "sayfa": p, "kosul": yak.get(p)})     # eşleme için (koşul altyazıdan)
            continue
        for kod, v in s.items():
            for t_, y_ in v:
                nok.append({"rapor_no": test, "seri": kod, "t_s": round(float(t_), 4), "deger": round(float(y_), 4)})
        r = ozet(test, s, flex)
        r["rapor_no"] = r.pop("test")
        r["sayfa"] = p
        r["kosul"] = yak.get(p)
        oz.append(r)
    nk = pd.DataFrame(nok)
    oz = eslestir(pd.DataFrame(oz), flex)
    oz[["rapor_no", "sayfa", "test", "eslesme_hatasi"]].to_csv(KOK / "data/droplet_flex_report_matching.csv", index=False,
                                                                 encoding="utf-8-sig")
    oz["kosul"] = oz.kosul.astype(str)
    nk = nk.merge(oz[["rapor_no", "test"]], on="rapor_no", how="left")
    oz = oz.merge(flex[["test", "kimlik", "yakit", "seyreltici", "basinc_kpa", "oksijen_yuzde", "he_yuzde",
                        "co2_yuzde", "ilk_cap_mm", "yanma_hizi_mm2_s", "sonme_capi_mm", "test_sonu"]],
                  on="test", how="left")
    print(f"rapor no -> CSV test kayması: {(oz.test - oz.rapor_no).value_counts().to_dict()}")
    if k.sayfa:
        pd.set_option("display.width", 250)
        print(oz.T)
        for kod in ("d2", "alev_lluv", "alev_renk"):
            x = nk[nk.seri == kod]
            print(kod, len(x), x.head(3).values.tolist(), x.tail(2).values.tolist())
        return
    nk.to_csv(KOK / "data/droplet_flex_flame_points.csv", index=False, encoding="utf-8-sig")
    hd = hedef_tablosu(nk, oz)
    hd = hd[(hd.d_oran > 0.05) & (hd.d_oran < 1.1) & (hd.oran > 1) & (hd.oran < 40)]
    hd.to_csv(KOK / "data/droplet_flex_flame_target.csv", index=False, encoding="utf-8-sig")
    print(f"hedef: {hd.test.nunique()} test, {len(hd)} dilim -> data/droplet_flex_flame_target.csv")
    oz.to_csv(KOK / "data/droplet_flex_flame_summary.csv", index=False, encoding="utf-8-sig")
    print(f"sayısallaştırılan: {len(oz)} test, okunamayan {len(hata)}: {[h['rapor_no'] for h in hata][:20]}")
    # bağımsız doğrulama
    v = oz.dropna(subset=["d2_ilk_mm2", "ilk_cap_mm"])
    e1 = np.abs(np.sqrt(v.d2_ilk_mm2) / v.ilk_cap_mm - 1)
    print(f"ilk çap: sayısal vs CSV medyan |hata| %{100 * np.median(e1):.1f} (n={len(v)}); %90'ı < %"
          f"{100 * np.percentile(e1, 90):.1f}")
    v = oz.dropna(subset=["K_say_mm2_s", "yanma_hizi_mm2_s"])
    v = v[v.yanma_hizi_mm2_s > 0.05]
    e2 = np.abs(v.K_say_mm2_s / v.yanma_hizi_mm2_s - 1)
    print(f"K: sayısal eğim vs CSV medyan |hata| %{100 * np.median(e2):.1f} (n={len(v)})")
    for kod in ("lluv", "renk"):
        c = f"oran_alev_{kod}"
        if c in oz:
            print(f"alev/damla çap oranı ({kod}):")
            print(oz.dropna(subset=[c]).groupby(["yakit", "seyreltici"])[c].agg(["count", "median"]).round(2))
    print("Kaydedildi: data/droplet_flex_flame_points.csv, data/droplet_flex_flame_summary.csv")


if __name__ == "__main__":
    main()
