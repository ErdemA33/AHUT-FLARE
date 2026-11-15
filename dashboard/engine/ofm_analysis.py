#!/usr/bin/env python3
"""
ofm_analysis.py — OpenFOAM motorunun Saffire-III S1 OpenFOAM motorunun bir koşusunu analiz eder (koşu klasörüne YAZMAZ).

    python3 ofm_analysis.py ofm_test/vaka [--cikti ofm_sonuclar] [--esik 0.10]

Okunan dosyalar (hepsi koşunun kendi functionObject çıktıları; system/functions + orkestrator.py ekleri):
  postProcessing/fluid/gazMax/<t0>/volFieldValue.dat     zaman, max(T), max(CO2), max(CH4)   -> tutuşma / sönme
  postProcessing/tel/telT/<t0>/volFieldValue.dat         zaman, tel max(T)                    -> grafik
  postProcessing/sibal/sibalYuzey/<t>/ust.xy             kumaşın gaza bakan yüzü (sibal_to_fluid), her yüz için
                                                         x, T, rhoV (bozulmamış selüloz), rhoCh (kömür) -> alev cephesi
  constant/sibal/fvModels                                rho01 (rhoV başlangıcı), rhoInert (cam elyaf)
  constant/tel/fvModels                                  ateşleyicinin kapandığı an (scale tablosu)
Birden çok <t0> klasörü (yeniden başlatılmış koşu) varsa zamanca sıralanır, çakışan zamanlarda sonraki klasör kazanır.

3B koşular (OpenFOAM motorunun kendi bilgisayarında; 2026-11-15) — 2B'den farkları ve ele alınışı:
  - postProcessing/<bölge>/<fonksiyon>/<t0>/ yapısı aynı; volFieldValue / probes dosyaları aynı biçimde.
  - sibalYuzey: yüzey artık bir şerit değil bir alan (face_x, face_y, face_z). Cephe iki türlü verilir:
      "en ileri"   : kaybın eşiği geçtiği EN BÜYÜK x (2B tanımıyla aynı; yayılma hızı bundan)
      "genişlik ortalaması": z dilimlerinde (ZDILIM adet) dilim başına en büyük x'in medyanı (alev ucunun
                     genişlik boyunca eğriliğini / kenar etkisini ayırmak için)
    Yüzey alanları tek dosyada (ust.xy) ya da alan başına ayrı dosyada (ust_T.xy, ust_rhoV.xy ...) olabilir; ikisi de
    okunur. Dosya adı "ust" değilse zaman klasöründeki ilk .xy / .raw dosyası alınır.
  - OpenFOAM yalnız postProcessing/ gönderirse constant/ olmayabilir: rho01 / rhoInert ve ateşleyici kapanışı sırayla
    <koşu>/../engine/piroliz/fvModels, MOTOR_KILIT.json (koşu klasörü, üstü, openfoam_motor/) içinden alınır;
    kaynağı "olcutler.kaynaklar" alanında yazılır.

Ölçütler:
  tutuşma : gaz max T'nin ilk kez 1500 K'yi geçtiği an (orkestrator.py tign_bul ile aynı: T > 1500, ilk satır).
  durum   : "tutuşmadı"            tutuşma yok ve koşu ateşleyici kapandıktan sonra en az 1 s daha sürdü
            "belirsiz (süre yetmedi)" tutuşma yok ve koşu o noktaya varmadan bitti
            "söndü"                tutuştu, sonra gaz max T 1200 K'nin altına indi ve koşunun son 1 s'si boyunca orada kaldı
            "yanıyor"              tutuştu ve son 1 s içinde 1200 K'nin üstünde değer var
            "belirsiz (sönme izlenemedi)"  tutuştu ama tutuşmadan sonra 1 s'lik veri yok
  cephe   : her yüzey yazımında yerel kütle kaybı = 1 - (rhoV + rhoCh + rhoInert) / (rho01 + rhoInert);
            kaybın eşiği (varsayılan %10) geçtiği en büyük x. Yayılma hızı: cephe bulunan zamanların son yarısına
            doğru uydurulan eğim (mm/s). En az 3 nokta ve x'te gerçek bir ilerleme yoksa None.
"""
import argparse
import json
import math
import re
from pathlib import Path

import numpy as np

T_ISIK = 1500.0          # orkestrator.py T_ISIK
ZDILIM = 8               # 3B yüzeyde cephe için z dilim sayısı
KOK = Path(__file__).resolve().parent
T_SONME = 1200.0
SONME_PENCERE = 1.0      # s
DENEY = {"kaynak": "Saffire-III Sample 1 (NTRS 20180005168, Tablo 1)", "yayilma_hizi_mm_s": 2.3,
         "not": "pamuk/cam elyaf (SIBAL), 25 cm/s eşakışlı, O2 %21"}


# ------------------------------------------------------------------ okuma
def _sayi(s):
    try:
        return float(s)
    except ValueError:
        return None


def zaman_serisi(case, yol):
    """postProcessing/<yol>/<t0>/volFieldValue.dat dosyalarını birleştirir: {zaman: [değerler]}."""
    kok = Path(case) / "postProcessing" / yol
    if not kok.is_dir():
        return {}
    klasorler = sorted((d for d in kok.iterdir() if d.is_dir() and _sayi(d.name) is not None),
                       key=lambda d: float(d.name))
    satirlar = {}
    for d in klasorler:
        f = d / "volFieldValue.dat"
        if not f.exists():
            continue
        for l in f.read_text(errors="ignore").splitlines():
            if l.startswith("#") or not l.strip():
                continue
            p = [_sayi(x) for x in l.split()]
            if len(p) >= 2 and None not in p:
                satirlar[p[0]] = p[1:]
    return dict(sorted(satirlar.items()))


def tign_bul(rows):
    """orkestrator.py tign_bul'un aynısı: rows = [(t, Tmax, ...), ...]."""
    for t, T, *_ in rows:
        if T > T_ISIK:
            return t
    return None


def sozluk_degeri(metin, anahtar):
    m = re.search(rf"\b{anahtar}\s+([0-9.eE+-]+)\s*;", metin)
    return float(m.group(1)) if m else None


def ates_kapanis(case):
    """constant/tel/fvModels scale tablosunda değerin 1 olduğu son zaman."""
    f = Path(case) / "constant/tel/fvModels"
    if not f.exists():
        return None
    m = re.search(r"scale\s+table\s*\((.*?)\)\s*;", f.read_text(), flags=re.S)
    if not m:
        return None
    ciftler = [(float(a), float(b)) for a, b in re.findall(r"\(\s*([0-9.eE+-]+)\s+([0-9.eE+-]+)\s*\)", m.group(1))]
    acik = [t for t, s in ciftler if s > 0]
    return max(acik) if acik else None


def _xy_oku(f):
    satir = f.read_text(errors="ignore").splitlines()
    if not satir or not satir[0].startswith("#"):
        return None
    adlar = satir[0].lstrip("#").split()
    try:
        veri = np.loadtxt(satir[1:], ndmin=2)
    except ValueError:
        return None
    if veri.size == 0 or veri.shape[1] != len(adlar):
        return None
    return {a: veri[:, i] for i, a in enumerate(adlar)}


def yuzey_oku(case):
    """sibalYuzey/<t>/ust.xy (ya da alan başına ust_<alan>.xy; 2B ve 3B) -> [(t, {sütun: dizi})]."""
    kok = Path(case) / "postProcessing/sibal/sibalYuzey"
    if not kok.is_dir():
        return []
    sonuc = []
    for d in sorted((d for d in kok.iterdir() if d.is_dir() and _sayi(d.name) is not None), key=lambda d: float(d.name)):
        dosyalar = sorted(d.glob("*.xy")) + sorted(d.glob("*.raw"))
        if not dosyalar:
            continue
        tek = [f for f in dosyalar if f.stem == "ust"] or ([dosyalar[0]] if len(dosyalar) == 1 else [])
        if tek:
            s = _xy_oku(tek[0])
        else:                      # alan başına ayrı dosya: koordinatlar ortak, alanları birleştir
            s = {}
            for f in dosyalar:
                x = _xy_oku(f)
                if x is None:
                    continue
                if s and len(next(iter(x.values()))) != len(next(iter(s.values()))):
                    continue
                for a, v in x.items():
                    s.setdefault(a, v)
                alan = f.stem.split("_")[-1]
                kalan = [a for a in x if not a.startswith(("face_", "x", "y", "z"))]
                if len(kalan) == 1 and kalan[0] != alan:
                    s[alan] = x[kalan[0]]
            s = s or None
        if s:
            sonuc.append((float(d.name), s))
    return sonuc


def kilit_bul(case):
    """MOTOR_KILIT.json: koşu klasörü, üstü ya da openfoam_motor/ içinde."""
    case = Path(case)
    for f in (case / "MOTOR_KILIT.json", case.parent / "MOTOR_KILIT.json", KOK / "openfoam_motor" / "MOTOR_KILIT.json"):
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8")), str(f)
            except ValueError:
                pass
    return None, None


# ------------------------------------------------------------------ hesap
def durum_bul(gaz, t_ign, t_kapanis):
    t = np.array(list(gaz)) if gaz else np.array([])
    if len(t) == 0:
        return "belirsiz (gaz verisi yok)", None
    T = np.array([v[0] for v in gaz.values()])
    t_son = float(t[-1])
    if t_ign is None:
        sinir = (t_kapanis if t_kapanis is not None else 0.0) + SONME_PENCERE
        if t_son >= sinir:
            return "tutuşmadı", None
        return "belirsiz (süre yetmedi)", None
    if t_son - t_ign < SONME_PENCERE:
        return "belirsiz (sönme izlenemedi)", None
    son = t >= t_son - SONME_PENCERE
    if np.all(T[son] < T_SONME):
        sonra = (t > t_ign) & (T < T_SONME)
        return "söndü", float(t[sonra][0])
    return "yanıyor", None


def _koordinat(s, eksen):
    for a in (f"face_{eksen}", eksen):
        if a in s:
            return s[a]
    return None


def boyut_bul(yuzeyler):
    """Yüzey z yönünde 1 mm'den genişse 3B."""
    for _, s in yuzeyler:
        z = _koordinat(s, "z")
        if z is not None and len(z):
            return "3B" if np.ptp(z) > 1e-3 else "2B"
    return "2B"


def cephe_bul(yuzeyler, rho01, rho_inert, esik, genislik=False):
    """-> ([(t, x)], hata). genislik=True (3B): z dilimlerindeki en ileri x'lerin medyanı."""
    if rho01 is None:
        return [], "rho01 bulunamadı (constant/sibal/fvModels, engine/piroliz/fvModels, MOTOR_KILIT.json)"
    ri = rho_inert or 0.0
    x_t = []
    for t, s in yuzeyler:
        x = _koordinat(s, "x")
        if x is None or "rhoV" not in s:
            return [], "yüzey dosyasında x / rhoV sütunu yok"
        kalan = s["rhoV"] + s.get("rhoCh", 0.0) + ri
        kayip = 1.0 - kalan / (rho01 + ri)
        yanan = kayip >= esik
        z = _koordinat(s, "z")
        if not genislik or z is None or np.ptp(z) <= 1e-3:
            x_t.append((t, float(x[yanan].max()) if yanan.any() else None))
            continue
        kenar = np.linspace(z.min(), z.max(), ZDILIM + 1)
        dil = np.clip(np.digitize(z, kenar) - 1, 0, ZDILIM - 1)
        ileri = [float(x[yanan & (dil == k)].max()) for k in range(ZDILIM) if (yanan & (dil == k)).any()]
        x_t.append((t, float(np.median(ileri)) if len(ileri) >= ZDILIM // 2 else None))
    return x_t, None


def yayilma_hizi(x_t):
    noktalar = [(t, x) for t, x in x_t if x is not None]
    if len(noktalar) < 3:
        return None, f"cephe bulunan zaman sayısı {len(noktalar)} (< 3)"
    son = noktalar[len(noktalar) // 2:]
    if len(son) < 3:
        son = noktalar[-3:]
    t = np.array([p[0] for p in son]); x = np.array([p[1] for p in son])
    if np.ptp(x) <= 0:
        return None, "son yarıda cephe ilerlemiyor"
    egim = np.polyfit(t, x, 1)[0]
    return float(egim * 1000.0), f"son yarı doğru uydurma, {len(son)} nokta, t = {t[0]:g}-{t[-1]:g} s"


# ------------------------------------------------------------------ çıktı
def grafik(png, gaz, tel, x_t, t_ign, ad):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(3, 1, figsize=(8, 9), sharex=True)
    if gaz:
        ax[0].plot(list(gaz), [v[0] for v in gaz.values()], lw=1.2)
    ax[0].axhline(T_ISIK, color="r", ls="--", lw=0.8, label="tutuşma 1500 K")
    ax[0].axhline(T_SONME, color="gray", ls=":", lw=0.8, label="sönme 1200 K")
    ax[0].set_ylabel("gaz T maks [K]"); ax[0].legend(fontsize=8)
    if tel:
        ax[1].plot(list(tel), [v[0] for v in tel.values()], color="tab:orange", lw=1.2)
    ax[1].set_ylabel("tel T maks [K]")
    xs = [(t, x) for t, x in x_t if x is not None]
    if xs:
        ax[2].plot([p[0] for p in xs], [p[1] * 100 for p in xs], "o-", ms=3)
    else:
        ax[2].text(0.5, 0.5, "alev cephesi yok", transform=ax[2].transAxes, ha="center", va="center")
    ax[2].set_ylabel("alev cephesi x [cm]"); ax[2].set_xlabel("zaman [s]")
    if t_ign is not None:
        for a in ax:
            a.axvline(t_ign, color="r", lw=0.6)
    fig.suptitle(f"OpenFOAM motoru: {ad}")
    fig.tight_layout()
    fig.savefig(png, dpi=120)
    plt.close(fig)


def analiz(case, esik=0.10):
    case = Path(case)
    if not (case / "postProcessing").is_dir():
        raise SystemExit(f"{case}: postProcessing klasörü yok")
    gaz = zaman_serisi(case, "fluid/gazMax")
    tel = zaman_serisi(case, "tel/telT")
    rows = [(t, *v) for t, v in gaz.items()]
    t_ign = tign_bul(rows)
    kilit, kilit_yolu = kilit_bul(case)
    kaynaklar = {}
    t_kapanis = ates_kapanis(case)
    kaynaklar["ateslayici_kapanis"] = "constant/tel/fvModels"
    if t_kapanis is None and kilit:
        t_kapanis = kilit.get("atesleyici", {}).get("kapanma_s")
        kaynaklar["ateslayici_kapanis"] = f"{kilit_yolu} (atesleyici.kapanma_s)"
    durum, t_sonme = durum_bul(gaz, t_ign, t_kapanis)

    rho01 = rho_inert = None
    for fv in (case / "constant/sibal/fvModels", case.parent / "engine/piroliz/fvModels"):
        if fv.exists():
            metin = fv.read_text()
            rho01, rho_inert = sozluk_degeri(metin, "rho01"), sozluk_degeri(metin, "rhoInert")
            if rho01 is not None:
                kaynaklar["rho01"] = str(fv.relative_to(case.parent) if case.parent in fv.parents else fv)
                break
    if rho01 is None and kilit:
        rho01, rho_inert = kilit.get("piroliz", {}).get("rho01"), kilit.get("piroliz", {}).get("rhoInert")
        kaynaklar["rho01"] = f"{kilit_yolu} (piroliz)"
    yuzeyler = yuzey_oku(case)
    boyut = boyut_bul(yuzeyler)
    x_t, hata = cephe_bul(yuzeyler, rho01, rho_inert, esik) if yuzeyler else ([], "sibalYuzey çıktısı yok")
    hiz, hiz_not = (None, hata) if hata else yayilma_hizi(x_t)
    x_t_g, hiz_g, hiz_g_not = [], None, None
    if boyut == "3B" and not hata:
        x_t_g, _ = cephe_bul(yuzeyler, rho01, rho_inert, esik, genislik=True)
        hiz_g, hiz_g_not = yayilma_hizi(x_t_g)

    sonuc = {
        "kosu": str(case),
        "simulasyon_suresi_s": round(max(gaz), 6) if gaz else None,
        "tutusma_zamani_s": t_ign,
        "durum": durum,
        "sonme_zamani_s": t_sonme,
        "gaz_T_maks_K": round(max(v[0] for v in gaz.values()), 1) if gaz else None,
        "tel_T_maks_K": round(max(v[0] for v in tel.values()), 1) if tel else None,
        "ateslayici_kapanis_s": t_kapanis,
        "yayilma_hizi_mm_s": None if hiz is None else round(hiz, 3),
        "yayilma_hizi_aciklama": hiz_not,
        "boyut": boyut,
        "alev_cephesi": [{"t": t, "x_m": x} for t, x in x_t],
        "alev_cephesi_genislik_ortalamasi": [{"t": t, "x_m": x} for t, x in x_t_g] if boyut == "3B" else None,
        "yayilma_hizi_genislik_mm_s": None if hiz_g is None else round(hiz_g, 3),
        "yayilma_hizi_genislik_aciklama": hiz_g_not,
        "deney": DENEY,
        "deney_farki_mm_s": None if hiz is None else round(hiz - DENEY["yayilma_hizi_mm_s"], 3),
        "olcutler": {
            "tutusma": f"gaz max T > {T_ISIK:g} K ilk an (orkestrator.py tign_bul)",
            "sonme": f"tutuşma sonrası gaz max T < {T_SONME:g} K ve son {SONME_PENCERE:g} s boyunca altında",
            "tutusmadi": f"tutuşma yok ve koşu ateşleyici kapanışından en az {SONME_PENCERE:g} s sonra bitti",
            "cephe": (f"sibalYuzey/ust.xy (kumaşın gaza bakan yüz hücreleri): kayıp = 1 - (rhoV + rhoCh + rhoInert)"
                      f" / (rho01 + rhoInert) >= {esik:g} olan en büyük x"),
            "rho01": rho01, "rhoInert": rho_inert, "kaynaklar": kaynaklar,
            "cephe_3B": f"en ileri x (yayılma hızı bundan) + {ZDILIM} z diliminin medyanı" if boyut == "3B" else None,
        },
        "veri_sayisi": {"gazMax": len(gaz), "telT": len(tel), "sibalYuzey": len(yuzeyler)},
    }
    return sonuc, gaz, tel, x_t



# ================================================================== sıvı / gaz koşuları (yakıt türüne göre analiz)
# Beklenen postProcessing çıktıları. Eksik olan çıktı için ne eksik olduğu "eksik" listesine yazılır;
# hiçbir değer uydurulmaz.
OFM_ESIK_ALEV = T_ISIK


def bilgi_oku(case):
    f = Path(case) / "BILGI.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def dat_serisi(case, yollar):
    """postProcessing/<yol>/<t0>/*.dat dosyalarının ilk iki sayısal sütunu: [(t, değer, ...)] (zamanca birleştirilmiş).
    yollar: aday yol listesi (ilk bulunan). Sütun adları '# Time ...' başlığından; yoksa None."""
    for yol in yollar:
        kok = Path(case) / "postProcessing" / yol
        if not kok.is_dir():
            continue
        klasorler = sorted((d for d in kok.iterdir() if d.is_dir() and _sayi(d.name) is not None), key=lambda d: float(d.name))
        satirlar, adlar = {}, None
        for d in klasorler:
            for f in sorted(d.glob("*.dat")):
                for l in f.read_text(errors="ignore").splitlines():
                    if l.startswith("#"):
                        if "Time" in l:
                            adlar = l.lstrip("#").split()
                        continue
                    p = [_sayi(x) for x in l.split()]
                    if len(p) >= 2 and None not in p:
                        satirlar[p[0]] = p[1:]
        if satirlar:
            return {"yol": yol, "adlar": adlar, "veri": dict(sorted(satirlar.items()))}
    return None


def _gaz_tmax(case):
    """fluid/gazMax (max T, ...) ya da cellMax(T) -> {t: [T, ...]}."""
    r = dat_serisi(case, ["fluid/gazMax", "gazMax", "fluid/cellMax(T)", "cellMax(T)"])
    return (r["veri"], r["yol"]) if r else ({}, None)


def _dogrusal_egim(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3 or np.ptp(x) <= 0:
        return None
    return float(np.polyfit(x, y, 1)[0])


def analiz_sivi(case, bilgi=None):
    """Sıvı (damla) koşusu: d²–t, K, sönme çapı, Tmax, alev yarıçapı.
    Okunan: fluid/gazMax (max T) · damla/damlaCap (t, d [m]) · fluid/alevYaricap (t, r_f [m], isteğe bağlı)."""
    bilgi = bilgi or bilgi_oku(case)
    eksik, sonuc = [], {"yakit_turu": "sivi"}
    gaz, gaz_yol = _gaz_tmax(case)
    if not gaz:
        eksik.append("fluid/gazMax (zaman, max T): tutuşma, söndü/yandı ve Tmax için gerekli")
    t_ign = tign_bul([(t, *v) for t, v in gaz.items()]) if gaz else None
    durum, t_sonme = durum_bul(gaz, t_ign, None)
    cap = dat_serisi(case, ["damla/damlaCap", "damlaCap", "fluid/damlaCap"])
    if not cap:
        # damlaBuharlasma günlüğü: postProcessing/damla/<t0>/damla.dat, sütunlar t dt rs d2d02 ...; çap d = 2 rs [m]
        dd = dat_serisi(case, ["damla"])
        if dd:
            cap = {"yol": dd["yol"], "veri": {t: [2.0 * v[1]] for t, v in dd["veri"].items() if len(v) > 1}}
            bilgi = {**bilgi, "cap_birim": "m"}
    birim = (bilgi.get("cap_birim") or "m").lower()
    k_say, d2, d0, d_sonme = None, None, None, None
    if not cap:
        eksik.append("damla/damlaCap (zaman, damla çapı [m]): d²–t eğrisi, K ve sönme çapı için gerekli")
    else:
        t = np.array(list(cap["veri"]), float)
        d = np.array([v[0] for v in cap["veri"].values()], float) * (1.0 if birim == "mm" else 1e3)   # mm
        d0 = float(d[0]) if d[0] > 0 else float(np.nanmax(d))
        d2 = [{"t": float(a), "d2_mm2": float(b * b)} for a, b in zip(t, d)]
        sec = (d / d0 <= 0.85) & (d / d0 >= 0.20) & (d > 0)          # ısınma evresi (d/d0 > 0,85) hariç, DSM'nin K aralığı
        if sec.sum() >= 4:
            egim = _dogrusal_egim(t[sec], d[sec] ** 2)
            k_say = None if egim is None else round(-egim, 4)           # mm²/s
        else:
            eksik.append("K: d/d0 = 0,85–0,20 aralığında en az 4 nokta yok")
        if durum == "söndü" and t_sonme is not None and len(t) > 1:
            d_sonme = round(float(np.interp(t_sonme, t, d)), 4)
    rf = dat_serisi(case, ["fluid/alevYaricap", "alevYaricap"])
    r_f_maks = None
    if rf:
        r_f_maks = round(max(v[0] for v in rf["veri"].values()) * 1e3, 4)    # mm
    else:
        eksik.append("fluid/alevYaricap (zaman, alev yarıçapı [m]): alev yarıçapı için gerekli (isteğe bağlı)")
    sonuc.update({
        "kosu": str(case), "simulasyon_suresi_s": round(max(gaz), 6) if gaz else None,
        "tutusma_zamani_s": t_ign, "durum": durum, "sonme_zamani_s": t_sonme,
        "gaz_T_maks_K": round(max(v[0] for v in gaz.values()), 1) if gaz else None,
        "ilk_cap_mm": None if d0 is None else round(d0, 4), "K_mm2_s": k_say, "sonme_capi_mm": d_sonme,
        "alev_yaricapi_maks_mm": r_f_maks, "d2_t": d2, "boyut": bilgi.get("boyut"),
        "olcutler": {"tutusma": f"gaz max T > {T_ISIK:g} K ilk an", "sonme": f"T < {T_SONME:g} K ve son {SONME_PENCERE:g} s altında",
                     "K": "-d(d²)/dt, d/d0 = 0,85–0,20 aralığına doğrusal uydurma (mm²/s)",
                     "sonme_capi": "sönme anındaki damla çapı (mm; yalnız söndüyse)"},
        "eksik": eksik, "veri_sayisi": {"gazMax": len(gaz), "damlaCap": len(cap["veri"]) if cap else 0}})
    return sonuc


def _kesit_alev(case):
    """postProcessing/<kesit>/<son t>/*.xy|.raw: sütunlar (x y z T) varsayılır; T > 1500 K noktalarından alev boyu (x aralığı) ve
    yarıçapı (en büyük |y|)."""
    for kok in sorted((Path(case) / "postProcessing").glob("*")):
        if not kok.is_dir():
            continue
        zamanlar = sorted((d for d in kok.iterdir() if d.is_dir() and _sayi(d.name) is not None), key=lambda d: float(d.name))
        for d in reversed(zamanlar):
            for f in sorted(list(d.glob("*.xy")) + list(d.glob("*.raw"))):
                try:
                    v = np.loadtxt([l for l in f.read_text(errors="ignore").splitlines() if l.strip() and not l.startswith("#")], ndmin=2)
                except ValueError:
                    continue
                if v.shape[1] >= 4:
                    sicak = v[v[:, -1] > OFM_ESIK_ALEV]
                    if len(sicak):
                        return {"t": float(d.name), "boy_m": float(np.ptp(sicak[:, 0])), "yaricap_m": float(np.max(np.abs(sicak[:, 1])))}
                    return {"t": float(d.name), "boy_m": 0.0, "yaricap_m": 0.0}
    return None


def _kuresel_alev(case):
    """1B küresel gaz vakası (ofm_gas_case.py): son yazılan T alanında en sıcak hücrenin merkezden uzaklığı = alev yarıçapı [m].
    Hücre yarıçapları vakadaki hucre_r.json'dan. -> {"yaricap_m", "T_maks_K", "t"} ya da None."""
    case = Path(case)
    try:
        rc = json.loads((case / "hucre_r.json").read_text(encoding="utf-8"))["rc_m"]
    except (OSError, ValueError, KeyError):
        return None
    zamanlar = sorted((d for d in case.iterdir() if d.is_dir() and _sayi(d.name) is not None and (d / "fluid" / "T").is_file()),
                      key=lambda d: float(d.name))
    if not zamanlar:
        return None
    m = re.search(r"internalField\s+nonuniform\s+List<scalar>\s*\d+\s*\(([^)]*)\)", (zamanlar[-1] / "fluid" / "T").read_text(errors="ignore"))
    if not m:
        return None
    T = np.array([float(x) for x in m.group(1).split()])
    if len(T) != len(rc):
        return None
    k = int(np.argmax(T))
    return {"yaricap_m": float(rc[k]), "T_maks_K": float(T[k]), "t": float(zamanlar[-1].name)}


def analiz_gaz(case, bilgi=None):
    """Gaz koşusu: Tmax, alev boyu / yarıçapı, sönme. Okunan: fluid/gazMax (ya da cellMax(T)) ·
    fluid/alevBoyutu (t, L [m], R [m]) ya da kesit (cutPlane .xy/.raw: x y z T)."""
    bilgi = bilgi or bilgi_oku(case)
    eksik = []
    gaz, gaz_yol = _gaz_tmax(case)
    if not gaz:
        eksik.append("fluid/gazMax ya da cellMax(T) (zaman, max T): tutuşma, sönme ve Tmax için gerekli")
    t_ign = tign_bul([(t, *v) for t, v in gaz.items()]) if gaz else None
    durum, t_sonme = durum_bul(gaz, t_ign, None)
    boy = yar = None
    ab = dat_serisi(case, ["fluid/alevBoyutu", "alevBoyutu"])
    if ab:
        son = list(ab["veri"].values())[-1]
        boy, yar = son[0], (son[1] if len(son) > 1 else None)
    else:
        k = _kesit_alev(case)
        ks = None if k else _kuresel_alev(case)
        if k:
            boy, yar = k["boy_m"], k["yaricap_m"]
        elif ks:
            yar = ks["yaricap_m"]       # küresel simetri: alev boyu tanımsız, yalnız yarıçap
        else:
            eksik.append("fluid/alevBoyutu (zaman, alev boyu [m], yarıçap [m]) ya da kesit/*.xy (x y z T): alev boyu ve yarıçapı için gerekli")
    return {"yakit_turu": "gaz", "kosu": str(case), "simulasyon_suresi_s": round(max(gaz), 6) if gaz else None,
            "tutusma_zamani_s": t_ign, "durum": durum, "sonme_zamani_s": t_sonme,
            "gaz_T_maks_K": round(max(v[0] for v in gaz.values()), 1) if gaz else None,
            "alev_boyu_mm": None if boy is None else round(boy * 1e3, 3), "alev_yaricapi_mm": None if yar is None else round(yar * 1e3, 3),
            "boyut": bilgi.get("boyut"),
            "olcutler": {"tutusma": f"gaz max T > {T_ISIK:g} K ilk an", "sonme": f"T < {T_SONME:g} K ve son {SONME_PENCERE:g} s altında",
                         "alev": f"T > {OFM_ESIK_ALEV:g} K bölgesi: boy = x aralığı, yarıçap = en büyük |y|"},
            "eksik": eksik, "veri_sayisi": {"gazMax": len(gaz)}}


def analiz_tur(case, esik=0.10):
    """BILGI.json'daki yakıt türüne göre analiz. Katı: mevcut analiz() (tutuşma, alev ucu–zaman, yayılma hızı, sensörler,
    kütle kaybı) — eksik çıktılar 'eksik' listesine yazılır. Dönüş: sonuç sözlüğü (yakit_turu, durum, ... eksik)."""
    case = Path(case)
    bilgi = bilgi_oku(case)
    tur = (bilgi.get("yakit_turu") or "kati").lower()
    tur = {"katı": "kati", "sıvı": "sivi"}.get(tur, tur)
    if tur == "sivi":
        return analiz_sivi(case, bilgi)
    if tur == "gaz":
        return analiz_gaz(case, bilgi)
    if not (case / "postProcessing").is_dir():
        return {"yakit_turu": "kati", "kosu": str(case), "eksik": ["postProcessing/ klasörü yok"], "durum": "belirsiz (çıktı yok)"}
    s, gaz, tel, x_t = analiz(case, esik)
    eksik = []
    if not gaz:
        eksik.append("fluid/gazMax")
    if not s["alev_cephesi"]:
        eksik.append("sibal/sibalYuzey (alev ucu–zaman, yayılma hızı için)")
    if not (case / "postProcessing" / "sibal" / "sibalKutle").is_dir():
        eksik.append("sibal/sibalKutle (kütle kaybı)")
    if (bilgi.get("deney") == "saffire3") and not (case / "postProcessing" / "fluid" / "sensGaz").is_dir():
        eksik.append("fluid/sensGaz (TC eğrileri; Saffire'da gerekli)")
    s["yakit_turu"], s["eksik"] = "kati", eksik
    return s

def main():
    a = argparse.ArgumentParser(description="OpenFOAM motoru koşu analizi (koşu klasörüne yazmaz)")
    a.add_argument("kosu")
    a.add_argument("--cikti", default="ofm_sonuclar", help="JSON ve PNG'nin yazılacağı klasör")
    a.add_argument("--esik", type=float, default=0.10, help="alev cephesi için yerel kütle kaybı eşiği")
    k = a.parse_args()
    kosu = Path(k.kosu).resolve()
    sonuc, gaz, tel, x_t = analiz(kosu, k.esik)
    ad = kosu.name if kosu.name != "vaka" else f"{kosu.parent.name}_{kosu.name}"
    cikti = Path(k.cikti)
    if cikti.resolve() == kosu or kosu in cikti.resolve().parents:
        raise SystemExit("çıktı klasörü koşu klasörünün içinde olamaz")
    cikti.mkdir(parents=True, exist_ok=True)
    js, png = cikti / f"{ad}.json", cikti / f"{ad}.png"
    sonuc["grafik"] = str(png)
    js.write_text(json.dumps(sonuc, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    grafik(png, gaz, tel, x_t, sonuc["tutusma_zamani_s"], ad)
    ozet = {k2: sonuc[k2] for k2 in ("simulasyon_suresi_s", "tutusma_zamani_s", "durum", "gaz_T_maks_K",
                                      "tel_T_maks_K", "yayilma_hizi_mm_s", "yayilma_hizi_aciklama")}
    print(json.dumps(ozet, ensure_ascii=False, indent=1))
    print(f"-> {js}\n-> {png}")


if __name__ == "__main__":
    main()
