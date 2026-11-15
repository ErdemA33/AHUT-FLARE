#!/usr/bin/env python3
"""
scripts/of_visual.py — OpenFOAM koşularının etkileşimli, TEK DOSYA ve tamamen çevrimdışı HTML görüntüleyicisi.

  python3 scripts/of_visual.py            -> of_gorsel.html  (+ of_visual/*.gif, of_visual/*.png sunum yedekleri)
  xdg-open of_gorsel.html

Yeni simülasyon koşmaz. of_kosular/ altındaki sonuçları yalnızca OKUR (bkz. scripts/of_visual_data.py);
çıkarılan kesitler of_visual/onbellek_*.npz olarak saklanır, ikinci çalıştırmada OpenFOAM çağrılmaz.
Seçenekler:  --gif-yok (GIF/PNG üretme)
"""
import argparse
import base64
import json
import math
import re
import sys
import time
from pathlib import Path

import numpy as np

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))
import of_visual_data as gv          # noqa: E402

CIK = gv.CIK
HTML = KOK / "of_gorsel.html"

KOSU_BILGI = {
    "tek_damla": {"tr": "Tek damla: ışınımsız", "en": "Single droplet: no radiation", "tur": "damla",
                  "g": "0", "kimya_tr": "tek adım heptan (Arrhenius), laminer",
                  "kimya_en": "single-step heptane (Arrhenius), laminar"},
    "sizinti_uzay": {"tr": "Sızıntı: uzay (g = 0)", "en": "Leak: space (g = 0)", "tur": "sizinti", "g": "0",
                     "kimya_tr": "tek adım heptan + PaSR, k-ε (RAS)", "kimya_en": "single-step heptane + PaSR, k-ε (RAS)"},
    "sizinti_mars": {"tr": "Sızıntı: Mars (g = 3,73)", "en": "Leak: Mars (g = 3.73)", "tur": "sizinti", "g": "3.73",
                     "kimya_tr": "tek adım heptan + PaSR, k-ε (RAS), gaz kaldırması açık (p_rgh)",
                     "kimya_en": "single-step heptane + PaSR, k-ε (RAS), gas buoyancy on (p_rgh)"},
    "ince_uzay": {"tr": "İnce sızıntı: uzay (g = 0)", "en": "Fine leak: space (g = 0)", "tur": "sizinti", "g": "0",
                  "kimya_tr": "tek adım heptan + PaSR, k-ε (RAS); 3B yarım alan (z = 0 simetri), 2,5 mm inceltme",
                  "kimya_en": "single-step heptane + PaSR, k-ε (RAS); 3D half domain (z = 0 symmetry), 2.5 mm refinement"},
    "ince_mars": {"tr": "İnce sızıntı: Mars (g = 3,73)", "en": "Fine leak: Mars (g = 3.73)", "tur": "sizinti", "g": "3.73",
                  "kimya_tr": "tek adım heptan + PaSR, k-ε (RAS), p_rgh; 3B yarım alan (z = 0 simetri), 2,5 mm inceltme",
                  "kimya_en": "single-step heptane + PaSR, k-ε (RAS), p_rgh; 3D half domain (z = 0 symmetry), 2.5 mm refinement"},
}
GRUP = {"tek_damla": {"tr": "Tek damla", "en": "Single droplet"},
        "sizinti_uzay": {"tr": "Sızıntı — kaba ızgara (5 mm, tam alan)", "en": "Leak — coarse grid (5 mm, full domain)"},
        "ince_uzay": {"tr": "Sızıntı — ince ızgara (2,5 mm, 3B yarım alan)", "en": "Leak — fine grid (2.5 mm, 3D half domain)"}}
GRUP["sizinti_mars"], GRUP["ince_mars"] = GRUP["sizinti_uzay"], GRUP["ince_uzay"]
for _a, _b in KOSU_BILGI.items():
    _b["grup_tr"], _b["grup_en"] = GRUP[_a]["tr"], GRUP[_a]["en"]
ALANLAR = {   # anahtar: (birim, renk haritası, ölçek çarpanı)
    "T": ("K", "inferno", 1.0),
    "O2": ("–", "viridis", 1.0),
    "C7H16": ("–", "cividis", 1.0),
    "Qdot": ("MW/m³", "magma", 1e-6),
    "U": ("m/s", "plasma", 1.0),
}


# ------------------------------------------------------------------ yardımcılar
def b64(a, dtype):
    return base64.b64encode(np.ascontiguousarray(a, dtype=dtype).tobytes()).decode()


def nicemle(a, ust=None):
    """float dizisi -> (uint16 base64, min, max). ust verilirse üst sınır kırpılır (renk ölçeği için)."""
    a = np.asarray(a, dtype=np.float64)
    lo = float(np.nanmin(a))
    hi = float(ust if ust is not None else np.nanmax(a))
    if hi <= lo:
        hi = lo + 1e-12
    q = np.round((np.clip(a, lo, hi) - lo) / (hi - lo) * 65535)
    return b64(q, "<u2"), lo, hi


def lut(ad, n=256):
    import matplotlib
    cm = matplotlib.colormaps[ad]
    return "".join("%02x%02x%02x" % tuple(int(255 * c) for c in cm(i / (n - 1))[:3]) for i in range(n))


def seyrelt(x, y, n=1500):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) <= n:
        return x.tolist(), y.tolist()
    i = np.unique(np.round(np.linspace(0, len(x) - 1, n)).astype(int))
    return x[i].tolist(), y[i].tolist()


def yuvarla(a, n=5):
    return [None if (v is None or (isinstance(v, float) and not math.isfinite(v))) else float(f"{v:.{n}g}")
            for v in a]


def saat_oku(log):
    """Log sonundaki ClockTime (s) ve son Time."""
    with open(log, "rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 400000))
        s = f.read().decode(errors="replace")
    c = re.findall(r"ClockTime = ([\d.]+) s", s)
    t = re.findall(r"^Time = ([\d.e+-]+)s?", s, flags=re.M)
    return (float(c[-1]) if c else None), (float(t[-1]) if t else None)


# ------------------------------------------------------------------ veri paketi
def kosu_paketi(ad, d):
    nf, ny, nx = d["f_T"].shape
    alan = {}
    for k, (birim, cmap, carp) in ALANLAR.items():
        a = d["f_" + k] * carp
        ust = float(np.percentile(a, 99.7)) if k == "Qdot" else None
        s, lo, hi = nicemle(a, ust)
        alan[k] = {"v": s, "min": lo, "max": hi, "birim": birim, "cmap": cmap}
    parsel = []
    for j in range(nf):
        x, y, dd = d["par_x"][j], d["par_y"][j], d["par_d"][j]
        parsel.append({"n": int(len(x)), "x": b64(np.round(np.asarray(x) * 10), "<i2"),
                       "y": b64(np.round(np.asarray(y) * 10), "<i2"),
                       "d": b64(np.round(np.clip(np.nan_to_num(np.asarray(dd)), 0, 6553.5) * 10), "<u2")})
    return {"ad": ad, "nx": nx, "ny": ny, "x": yuvarla(d["x"]), "y": yuvarla(d["y"]), "h": float(d["h_mm"]),
            "z": float(d["z_kesit_mm"]), "hucre": b64(d["hucre_no"], "<i4"), "hucre_sayisi": int(d["hucre_sayisi"]),
            "zaman": yuvarla(d["zaman"]), "tum": int(d["tum_zaman_sayisi"]), "alan": alan, "parsel": parsel,
            "qkaynak": str(d["qkaynak"]), "qkontrol": None if not np.isfinite(d["qkontrol"]) else float(d["qkontrol"]),
            # karışık hücre boyutu (ince koşu): piksel başına gerçek hücre boyutu, 0,01 mm
            "hb": b64(np.round(d["hboy_mm"] * 100), "<u2") if "hboy_mm" in d and float(d["h_maks_mm"]) > float(d["h_mm"]) * 1.01
            else None, "h_maks": float(d["h_maks_mm"]) if "h_maks_mm" in d else float(d["h_mm"])}


def egri_paketi():
    import of_leak as osz
    import of_single_droplet as otd
    e = {}
    for ad in ("uzay", "mars"):
        v = osz.VAKA_KOK / ad
        t, T = osz.dat_oku(v, "cellMax(T)")
        tq, Q = osz.dat_oku(v, "volIntegrate(Qdot)")
        h = osz.alev_yuksekligi(v)
        e[ad] = {"Tmax": seyrelt(t, T), "Q": seyrelt(tq, np.asarray(Q) / 1e3),
                 "h": ([a for a, b in h], [b for a, b in h])}
    v = otd.VAKA_KOK / "isinimsiz"
    t, dd, _ = otd.log_serileri(gv.KOSULAR["tek_damla"]["log"])
    tc, Tc = otd.cellmax_oku(v)
    rf = otd.alev_yaricapi(v)
    K = otd.K_hesapla(t, dd)
    e["damla"] = {"d2": seyrelt(t, np.asarray(dd) ** 2), "Tmax": seyrelt(tc, Tc),
                  "rf": ([a for a, b, c in rf], [b for a, b, c in rf]), "K": K}
    # FLEX benzer testler (psi_flex_testler.csv; of_single_droplet ile aynı seçim)
    import pandas as pd
    flex = []
    f = next((x for x in otd.FLEX_ADAYLAR if x.exists()), None)
    if f is not None:
        x = pd.read_csv(f)
        x = x[(x.yakit == "heptane") & x.oksijen_yuzde.between(19, 23) & x.basinc_kpa.between(90, 110)
              & x.ilk_cap_mm.between(1.5, 2.5) & (x.co2_yuzde.fillna(0) == 0) & (x.he_yuzde.fillna(0) == 0)]
        for r in x.itertuples():
            flex.append({"ad": f"FLEX {int(r.test)} ({r.kimlik})", "d0": float(r.ilk_cap_mm),
                         "K": float(r.yanma_hizi_mm2_s), "O2": float(r.oksijen_yuzde), "p": float(r.basinc_kpa),
                         "sure": None if r.yanma_suresi_s != r.yanma_suresi_s else float(r.yanma_suresi_s),
                         "son": str(r.test_sonu)})
    e["flex"] = flex
    e["flex_kaynak"] = str(f) if f else None
    try:
        import droplet_engine as dm
        r = dm.droplet_engine(1e-4, 21, 101.3, 0, 2.0, "n-heptane", "droplet", mod="hizli")
        e["droplet_engine"] = {"K": float(r["yanma_hizi_K"]), "T": float(r["sicaklik"]),
                             "sonme": float(r["sonme_capi"])}
    except Exception as ex:                                            # pragma: no cover
        print("droplet_engine çalıştırılamadı:", ex)
        e["droplet_engine"] = None
    return e


def kosu_tablosu(veriler):
    satir = []
    for ad, d in veriler.items():
        saat, son_t = saat_oku(gv.KOSULAR[ad]["log"])
        b = KOSU_BILGI[ad]
        vaka = gv.KOSULAR[ad]["vaka"]
        durum = "damla_bitti" if ad == "tek_damla" else "tamam"
        if (vaka / "IRAKSADI").exists() or (vaka / "KALDIRMA_YOK").exists() or (vaka / "DISK_DOLU").exists():
            durum = "durdu"
        hmax = float(d["h_maks_mm"]) if "h_maks_mm" in d else float(d["h_mm"])
        satir.append({"ad": ad, "tr": b["tr"], "en": b["en"], "hucre": int(d["hucre_sayisi"]),
                      "h": float(d["h_mm"]), "h2": hmax if hmax > float(d["h_mm"]) * 1.01 else None,
                      "son_t": son_t, "saat_s": saat, "cekirdek": 15,
                      "kimya_tr": b["kimya_tr"], "kimya_en": b["kimya_en"], "isinim": False,
                      "durum": durum,
                      "gosterim": b["tur"] == "sizinti", "g": b["g"]})
    return satir


def p1_notu():
    """P1 denemelerini canlı loglardan oku (yalnız not olarak)."""
    notlar = []
    il = gv.OFK / "tek_damla_ilerleme.log"
    if il.exists():
        s = il.read_text(errors="replace")
        if re.search(r"p1: t = 0\.7840 s .*max T 6000", s):
            notlar.append({"tr": "P1 (1. deneme, t = 0'dan): t = 0,784 s'de Tmax 6000 K sınırına dayandı, "
                                 "Δt 6·10⁻⁴⁸ s'ye düştü; 3,5 saat ilerlemedi, elle durduruldu.",
                           "en": "P1 (attempt 1, from t = 0): at t = 0.784 s Tmax hit the 6000 K limit, "
                                 "Δt fell to 6·10⁻⁴⁸ s; no progress for 3.5 h, stopped manually."})
        m = re.search(r"IRAKSADI: tek_damla/p1 durduruldu \(zaman adımı ([\d.e+-]+) s.*t = ([\d.]+)", s)
        if m:
            t = float(m.group(2))
            notlar.append({"tr": f"P1 (2. deneme, ışınımsız koşunun t = 0,5 s anından): t = {t:.3f} s'de "
                                 f"Δt {float(m.group(1)):.1e} s'ye düştü; bekçi durdurdu.".replace(".", ",", 1),
                           "en": f"P1 (attempt 2, restarted from the no-radiation run at t = 0.5 s): "
                                 f"Δt fell to {float(m.group(1)):.1e} s at t = {t:.3f} s; stopped by the watchdog."})
    if (gv.OFK / "sizinti/mars_kaldirmasiz").exists():
        notlar.append({"tr": "İlk Mars sızıntı koşusu (0–0,4 s) gösterilmiyor: 0/p_rgh olmadığı için OpenFOAM gaz fazı "
                             "kaldırmasını açmamış, yerçekimi yalnız damlalara etki etmişti. Mars, p_rgh ile t = 0'dan "
                             "yeniden koşuldu; uzay 0,4 s'den 1,0 s'ye devam ettirildi.",
                       "en": "The first Mars leak run (0–0.4 s) is not shown: without 0/p_rgh OpenFOAM did not enable "
                             "gas-phase buoyancy, so gravity acted only on the droplets. Mars was rerun from t = 0 with "
                             "p_rgh; space was continued from 0.4 s to 1.0 s."})
    return notlar


# ------------------------------------------------------------------ sunum yedekleri (GIF, PNG)
def yedekler(veriler, egri):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation, PillowWriter
    from matplotlib.colors import TwoSlopeNorm
    ciktilar = []
    ad_dosya = {"tek_damla": "of_single_droplet", "sizinti_uzay": "of_leak_uzay", "sizinti_mars": "of_leak_mars",
                "ince_uzay": "of_leak_thin_uzay", "ince_mars": "of_leak_thin_mars"}
    for ad, d in veriler.items():
        x, y, h = d["x"], d["y"], float(d["h_mm"])
        kx = np.r_[x - h / 2, x[-1] + h / 2]
        ky = np.r_[y - h / 2, y[-1] + h / 2]
        T = d["f_T"]
        b = KOSU_BILGI[ad]
        fig, ax = plt.subplots(figsize=(6.4, 5.6))
        pc = ax.pcolormesh(kx, ky, T[0], cmap="inferno", vmin=300, vmax=max(2600, float(T.max())))
        fig.colorbar(pc, ax=ax, label="T (K)")
        sc = ax.scatter([], [], s=4, c="#4FC3F7", edgecolors="none")
        ax.set_aspect("equal")
        ax.set_xlabel("x (mm)")
        ax.set_ylabel("y (mm)")
        bas = ax.set_title("")

        def kare(j):
            pc.set_array(T[j].ravel())
            px, py, pd_ = d["par_x"][j], d["par_y"][j], d["par_d"][j]
            if len(px):
                if b["tur"] == "damla":
                    s = 60.0 * (np.asarray(pd_) / 2000.0) ** 2          # 2 mm damla ~60 pt²
                else:
                    s = 1 + 30 * (np.asarray(pd_) / 100.0) ** 2
                sc.set_offsets(np.c_[px, py])
                sc.set_sizes(s)
            else:
                sc.set_offsets(np.zeros((0, 2)))
            bas.set_text(f"{b['tr']} — z = {float(d['z_kesit_mm']):.1f} mm kesiti, t = {d['zaman'][j]:.3f} s")
            return pc, sc, bas

        an = FuncAnimation(fig, kare, frames=len(d["zaman"]), blit=False)
        f = CIK / f"{ad_dosya[ad]}.gif"
        an.save(f, writer=PillowWriter(fps=3), dpi=90)
        plt.close(fig)
        ciktilar.append(f)
        # harita PNG: 5 alan, temsilî an
        hedef = 0.1 if b["tur"] == "sizinti" else 1.05
        j = int(np.argmin(np.abs(np.asarray(d["zaman"]) - hedef)))
        fig, axs = plt.subplots(1, 5, figsize=(22, 4.6))
        for a, (k, (birim, cmap, carp)) in zip(axs, ALANLAR.items()):
            v = d["f_" + k][j] * carp
            ust = float(np.percentile(d["f_" + k] * carp, 99.7)) if k == "Qdot" else None
            p = a.pcolormesh(kx, ky, v, cmap=cmap, vmax=ust)
            fig.colorbar(p, ax=a, label=f"{k} ({birim})", fraction=0.046)
            a.set_aspect("equal")
            a.set_title(k + (" (hesap)" if k == "Qdot" and str(d["qkaynak"]) == "hesap" else ""))
            a.set_xlabel("x (mm)")
            if b["tur"] == "sizinti":
                a.scatter(d["par_x"][j], d["par_y"][j], s=1, c="#4FC3F7", edgecolors="none")
        axs[0].set_ylabel("y (mm)")
        ek = "  ·  GÖSTERİM — deney verisiyle doğrulanmadı" if b["tur"] == "sizinti" else ""
        fig.suptitle(f"{b['tr']}: z = {float(d['z_kesit_mm']):.1f} mm kesiti, t = {d['zaman'][j]:.3f} s, "
                     f"ızgara {h:.2f} mm{ek}")
        fig.tight_layout()
        f = CIK / f"{ad_dosya[ad]}_harita.png"
        fig.savefig(f, dpi=200)
        plt.close(fig)
        ciktilar.append(f)
    # uzay / Mars / fark PNG (son an)
    u, m = veriler["sizinti_uzay"], veriler["sizinti_mars"]
    x, y, h = u["x"], u["y"], float(u["h_mm"])
    kx, ky = np.r_[x - h / 2, x[-1] + h / 2], np.r_[y - h / 2, y[-1] + h / 2]
    j = len(u["zaman"]) - 1
    fig, axs = plt.subplots(1, 4, figsize=(22, 5), gridspec_kw={"width_ratios": [1, 1, 1, 1.15]})
    for a, (dd, ba) in zip(axs[:2], ((u, "uzay (g = 0)"), (m, "Mars (g = 3,73 m/s²)"))):
        p = a.pcolormesh(kx, ky, dd["f_T"][j], cmap="inferno", vmin=300, vmax=2900)
        fig.colorbar(p, ax=a, label="T (K)", fraction=0.046)
        a.set_title(f"{ba}, t = {dd['zaman'][j]:.2f} s")
        a.set_aspect("equal")
        a.set_xlabel("x (mm)")
    fark = m["f_T"][j] - u["f_T"][j]
    lim = float(np.abs(fark).max()) or 1.0
    p = axs[2].pcolormesh(kx, ky, fark, cmap="RdBu_r", norm=TwoSlopeNorm(0, -lim, lim))
    fig.colorbar(p, ax=axs[2], label="ΔT = Mars − uzay (K)", fraction=0.046)
    axs[2].set_title("fark: Mars − uzay")
    axs[2].set_aspect("equal")
    axs[0].set_ylabel("y (mm)")
    for ad, r in (("uzay", "#4FC3F7"), ("mars", "#EF5350")):
        axs[3].plot(*egri[ad]["h"], "o-", ms=3, color=r, label=ad)
    axs[3].axvspan(0, 0.03, color="0.6", alpha=0.35, label="tutuşturucu darbesi")
    axs[3].set(xlabel="t (s)", ylabel="y_alev (mm)", title="alev merkezinin yüksekliği")
    axs[3].legend()
    fig.suptitle("Sızıntı: uzay ve Mars — GÖSTERİM, deney verisiyle doğrulanmadı")
    fig.tight_layout()
    f = CIK / "of_leak_space_mars_diff.png"
    fig.savefig(f, dpi=200)
    plt.close(fig)
    ciktilar.append(f)
    return ciktilar


# ------------------------------------------------------------------ ana
def main():
    a = argparse.ArgumentParser()
    a.add_argument("--gif-yok", action="store_true")
    k = a.parse_args()
    bas = time.time()
    CIK.mkdir(exist_ok=True)
    veriler = {}
    for ad in gv.KOSULAR:
        if ad.startswith("ince_") and not gv.mevcut(ad):
            print(f"{ad}: henüz sonuç yok, atlandı")
            continue
        print(f"{ad}: kesit verisi")
        veriler[ad] = gv.cikar(ad)
    print("eğriler, FLEX, droplet_engine")
    egri = egri_paketi()
    paket = {"kosu": {ad: kosu_paketi(ad, d) for ad, d in veriler.items()},
             "bilgi": KOSU_BILGI, "egri": egri, "tablo": kosu_tablosu(veriler), "p1": p1_notu(),
             "lut": {c: lut(c) for c in ("inferno", "viridis", "cividis", "magma", "plasma", "RdBu_r")},
             "uretim": time.strftime("%Y-%m-%d %H:%M")}
    js = json.dumps(paket, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    sablon = (KOK / "scripts/of_visual_template.html").read_text(encoding="utf-8")
    HTML.write_text(sablon.replace("/*__VERI__*/null", js), encoding="utf-8")
    print(f"Kaydedildi: {HTML.name}  ({HTML.stat().st_size / 1e6:.2f} MB)")
    if not k.gif_yok:
        print("GIF / PNG yedekleri")
        for f in yedekler(veriler, egri):
            print(f"  {f.relative_to(KOK)}  ({f.stat().st_size / 1e6:.2f} MB)")
    print(f"Süre {time.time() - bas:.0f} s.  Açmak için: xdg-open {HTML.name}")


if __name__ == "__main__":
    main()
