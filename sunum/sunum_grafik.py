#!/usr/bin/env python3
"""
sunum_grafik.py — sunum grafik paketi (TR + EN, dpi 200, ortak renk ve stil). Yeni simülasyon yok:
mevcut sonuç dosyalarını ve sunum_veri.py'nin tahmin.py çıktılarını okur.

  a_sistem_semasi      : model + 3 motor + yönlendirici + güven skoru + LLM
  b_durust_auc         : dürüst AUC tablosu + çubuk grafiği (motor_dogrulama.json)
  c_ay_mars_harita     : PMMA, O2 × basınç, g = 0,165 / 0,38, birleşik ihtimal + %50 sınırı + NASA habitat kutusu
  d_damla_kismi_g      : damla motoru kısmi g (damla_kismi_g.csv)  [eski U eğrisi paneli çıkarıldı; tanı: "tani" -> deneyler/u_egrisi_tani_*.png]
  e_flex_d2_K          : FLEX d² ve K: OpenFOAM (ışınımsız) / damla_motoru / FLEX ölçümü
  f_guven_skoru        : güven skoru tek örnek vaka (PMMA, ISS, %21 O2)
  g_kevlar_celiski     : Kevlar örneği, model-motor çelişki uyarısı (ekran çıktısı)

Kullanım: python3 sunum/sunum_grafik.py [a b c ...]   (boş = hepsi)
Çıktı: sunum/<ad>_tr.png, sunum/<ad>_en.png
"""
import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

BURA = Path(__file__).resolve().parent
KOK = BURA.parent
VERI = BURA / "veri"
sys.path.insert(0, str(KOK))

# ------------------------------------------------------------------ ortak stil
YUZEY = "#fcfcfb"
METIN1, METIN2, METIN3 = "#0b0b0b", "#52514e", "#8a8984"
IZGARA = "#e4e3df"
RENK = {                 # sabit kimlik renkleri (her grafikte aynı varlık = aynı renk)
    "model": "#2a78d6",  # risk modeli
    "hafif": "#eb6834",  # katı
    "damla": "#1baf7a",  # sıvı
    "gaz": "#eda100",    # gaz
    "llm": "#6250d6",
    "ofm": "#a3a29c",  # henüz yok
    "of": "#e87ba4",     # OpenFOAM
    "olcum": "#0b0b0b",  # deney ölçümü
}
UYARI = {"kritik": "#d03b3b", "uyari": "#fab219", "iyi": "#0ca30c"}
ISI = LinearSegmentedColormap.from_list(   # ıraksak: mavi (söner) - gri (%50) - kırmızı (yanar)
    "sunum_isi", ["#184f95", "#5598e7", "#b7d3f6", "#f0efec", "#f3b3b2", "#e34948", "#9e2323"])
DPI = 200

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 11, "axes.titlesize": 13, "axes.titleweight": "bold",
    "axes.labelsize": 11, "axes.edgecolor": METIN3, "axes.labelcolor": METIN2, "axes.linewidth": 0.8,
    "xtick.color": METIN2, "ytick.color": METIN2, "text.color": METIN1, "axes.titlecolor": METIN1,
    "figure.facecolor": YUZEY, "axes.facecolor": YUZEY, "savefig.facecolor": YUZEY,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": IZGARA,
    "grid.linewidth": 0.7, "axes.axisbelow": True, "legend.frameon": False, "legend.fontsize": 9.5, "lines.linewidth": 2,
})


def sayi(dil, z, n=2):
    s = f"{z:.{n}f}"
    return s.replace(".", ",") if dil == "tr" else s


def kaydet(fig, ad, dil, kaynak):
    fig.text(0.995, 0.005, kaynak, ha="right", va="bottom", fontsize=7.5, color=METIN3)
    yol = BURA / f"{ad}_{dil}.png"
    fig.savefig(yol, dpi=DPI)
    plt.close(fig)
    print("  ->", yol.relative_to(KOK))


def jread(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ a) sistem şeması
def a_sistem_semasi():
    M = {
        "tr": dict(
            baslik="Sistem: risk modeli + 3 fizik motoru + güven skoru",
            girdi="Kullanıcı girdisi\nmalzeme · O₂ · basınç · g\nakış · kalınlık · seyreltici",
            llm="LLM (EVREN)\nlistede olmayan malzemeyi\nbenzer malzemeye eşler",
            yon="Yönlendirici (motor.py)\nyakıt türü + numune tipi",
            model="Risk modeli\n(makine öğrenmesi; literatür + NASA PSI)\nyanma ihtimali · sönme sınırı",
            hafif="Hafif motor\nKATI\nalev yayılması\n(levha, kumaş)",
            damla="Damla motoru\nSIVI\nyarı-durağan damla\n(FLEX kalibre)",
            gaz="Gaz motoru\nGAZ\nküre / düz / jet\nalev",
            ofm="OpenFOAM motoru\n(henüz yok)",
            bir="Birleştirme\nağırlık = max(0, 2(AUC − 0,5))\ndürüst test AUC'leri",
            guven="Güven skoru 0–100\n0,4 veri + 0,3 uyum + 0,3 motor",
            cikti="Çıktı\nbirleşik yanma ihtimali · risk seviyesi\nsönme sınırı · güven · uyarılar",
            yorum="isteğe bağlı: LLM yorumu",
            not_="Her motor yalnız kendi yakıt grubunda dürüst testle ağırlık alır; kalibre değilse ağırlık 0."),
        "en": dict(
            baslik="System: risk model + 3 physics engines + confidence score",
            girdi="User input\nmaterial · O₂ · pressure · g\nflow · thickness · diluent",
            llm="LLM (EVREN)\nmaps an unlisted material\nto a similar known one",
            yon="Router (motor.py)\nfuel type + sample type",
            model="Risk model\n(machine learning; literature + NASA PSI)\nignition probability · extinction limit",
            hafif="Light engine\nSOLID\nflame spread\n(sheet, fabric)",
            damla="Droplet engine\nLIQUID\nquasi-steady droplet\n(FLEX calibrated)",
            gaz="Gas engine\nGAS\nsphere / flat / jet\nflame",
            ofm="OpenFOAM engine\n(not yet)",
            bir="Combination\nweight = max(0, 2(AUC − 0.5))\nfrom honest-test AUCs",
            guven="Confidence score 0–100\n0.4 data + 0.3 agreement + 0.3 engine",
            cikti="Output\ncombined ignition probability · risk level\nextinction limit · confidence · warnings",
            yorum="optional: LLM commentary",
            not_="Each engine is weighted only by its honest test on its own fuel group; uncalibrated -> weight 0."),
    }
    for dil, m in M.items():
        fig = plt.figure(figsize=(14, 8.2))
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, 14)
        ax.set_ylim(0, 8.2)
        ax.axis("off")
        ax.text(0.4, 7.75, m["baslik"], fontsize=17, fontweight="bold", va="center")

        def kutu(x, y, w, h, metin, renk, dolu=0.14, kesik=False, kalin=False, fs=10.5):
            r = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                               fc=matplotlib.colors.to_rgba(renk, dolu), ec=renk, lw=2.2 if kalin else 1.6,
                               ls=(0, (4, 3)) if kesik else "-")
            ax.add_patch(r)
            ax.text(x + w / 2, y + h / 2, metin, ha="center", va="center", fontsize=fs,
                    color=METIN3 if kesik else METIN1, linespacing=1.35)
            return (x, y, w, h)

        def ok(a, b, renk=METIN2, kesik=False, rad=0.0):
            ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=16, color=renk, lw=1.5,
                                         ls=(0, (4, 3)) if kesik else "-", connectionstyle=f"arc3,rad={rad}",
                                         shrinkA=2, shrinkB=2))

        kutu(0.3, 5.2, 3.0, 1.4, m["girdi"], METIN2, dolu=0.06)
        kutu(0.3, 2.7, 3.0, 1.4, m["llm"], RENK["llm"])
        ok((1.8, 5.2), (1.8, 4.1), RENK["llm"], kesik=True)
        kutu(3.9, 5.25, 3.0, 1.3, m["model"], RENK["model"], kalin=True, fs=9.5)
        kutu(3.9, 3.0, 3.0, 1.0, m["yon"], METIN2, dolu=0.06, fs=10)
        ok((3.3, 5.9), (3.9, 5.9))
        ok((3.3, 5.4), (3.9, 3.9))
        ok((3.3, 3.4), (3.9, 3.4), RENK["llm"], kesik=True)
        # motorlar (dikey yığın)
        ys = [4.75, 3.5, 2.25]
        for y0, k in zip(ys, ("hafif", "damla", "gaz")):
            kutu(7.5, y0, 2.2, 1.05, m[k].replace("\n", " ", 1), RENK[k], fs=9)
            ok((6.9, 3.5), (7.5, y0 + 0.52))
            ok((9.7, y0 + 0.52), (10.3, 5.4), METIN3)
        kutu(7.5, 1.0, 2.2, 0.9, m["ofm"], RENK["ofm"], dolu=0.03, kesik=True, fs=9)
        ok((6.9, 3.5), (7.5, 1.45), RENK["ofm"], kesik=True)
        # birleştirme / güven / çıktı
        kutu(10.3, 5.0, 3.4, 1.55, m["bir"], METIN2, dolu=0.06, fs=10)
        ok((6.9, 6.2), (10.3, 6.2), RENK["model"])
        kutu(10.3, 3.35, 3.4, 1.15, m["guven"], UYARI["iyi"], dolu=0.10, fs=10)
        ok((12.0, 5.0), (12.0, 4.5))
        kutu(10.3, 1.55, 3.4, 1.3, m["cikti"].replace(" · risk", "\nrisk", 1), METIN1, dolu=0.04, kalin=True, fs=9.5)
        ok((12.0, 3.35), (12.0, 2.85))
        kutu(10.3, 0.45, 3.4, 0.6, m["yorum"], RENK["llm"], dolu=0.05, kesik=True, fs=9)
        ok((12.0, 1.55), (12.0, 1.05), RENK["llm"], kesik=True)
        ax.text(0.3, 0.3, m["not_"], fontsize=9.5, color=METIN2)
        kaydet(fig, "a_sistem_semasi", dil, "tahmin.py · motor.py · motor_kontrol.py · llm_analiz.py")


# ------------------------------------------------------------------ b) dürüst AUC
def b_durust_auc():
    d = jread(KOK / "motor_dogrulama.json")
    mo, md = d["model"], d["motorlar"]
    gz = md["gaz"]["geometri"]
    sat = [  # (anahtar, renk, auc, n, test TR, test EN, kalibre)
        ("model", "model", mo["nasa_auc"], None,
         f"makaleye göre ayrılmış test, NASA verisi (tüm test {sayi('tr', mo['tum_test_auc'])})", f"held-out papers, NASA data (all test {mo['tum_test_auc']:.2f})", True),
        ("hafif", "hafif", md["hafif"]["kati"]["auc"], md["hafif"]["kati"]["n"],
         "deney ailesi 5'li GroupKFold", "5-fold GroupKFold by test family", True),
        ("damla", "damla", md["damla"]["sivi"]["auc"], md["damla"]["sivi"]["n"],
         "FLEX: N₂ ile kalibre → CO₂/He testleri", "FLEX: calibrate on N₂ → test CO₂/He", True),
        ("gaz_duz", "gaz", gz["duz"]["auc"], gz["duz"]["n"],
         "düz brülör, BRE gün dışarıda", "flat burner, BRE day held out", True),
        ("gaz_jet", "gaz", gz["jet"]["auc"], gz["jet"]["n"],
         "jet: literatür kontrolü, sabitler kalibre değil", "jet: literature check, constants uncalibrated",
         False),
        ("ofm", "ofm", None, None, "henüz yok", "not yet", False),
    ]
    ad = {"tr": {"model": "Risk modeli", "hafif": "Hafif motor (katı)", "damla": "Damla motoru (sıvı)",
                 "gaz_duz": "Gaz motoru — düz", "gaz_jet": "Gaz motoru — jet", "ofm": "OpenFOAM motoru"},
          "en": {"model": "Risk model", "hafif": "Light engine (solid)", "damla": "Droplet engine (liquid)",
                 "gaz_duz": "Gas engine — flat", "gaz_jet": "Gas engine — jet", "ofm": "OpenFOAM engine"}}
    T = {"tr": dict(baslik="Dürüst test AUC'si: her bileşen, görmediği veride",
                    x="AUC (0,5 = yazı tura, 1 = kusursuz)", rast="rastgele", agir="ağırlık 0",
                    yok="henüz yok", sut=["bileşen", "AUC", "n", "test yöntemi", "ağırlık gücü"],
                    not_="Ağırlık gücü = max(0, 2(AUC − 0,5)); jet kalibre değil → tahmin.py'de ağırlık 0."),
         "en": dict(baslik="Honest-test AUC: every component on data it never saw",
                    x="AUC (0.5 = coin flip, 1 = perfect)", rast="random", agir="weight 0",
                    yok="not yet", sut=["component", "AUC", "n", "test method", "weight power"],
                    not_="Weight power = max(0, 2(AUC − 0.5)); jet is uncalibrated → weight 0 in tahmin.py.")}
    for dil, t in T.items():
        fig = plt.figure(figsize=(14, 7.6))
        ax = fig.add_axes([0.17, 0.42, 0.78, 0.48])
        y = np.arange(len(sat))[::-1]
        for yi, (k, r, auc, n, ttr, ten, kal) in zip(y, sat):
            if auc is None:
                ax.text(0.505, yi, t["yok"], va="center", fontsize=10, color=METIN3, style="italic")
                continue
            ax.barh(yi, auc - 0.5, left=0.5, height=0.58, color=RENK[r] if kal else YUZEY,
                    ec=RENK[r], lw=1.6, hatch=None if kal else "///")
            ax.text(auc + 0.006, yi, sayi(dil, auc, 3) + ("" if kal else f"  ({t['agir']})"), va="center",
                    fontsize=10.5, color=METIN1, fontweight="bold")
        ax.set_yticks(y, [ad[dil][s[0]] for s in sat])
        ax.set_xlim(0.5, 1.0)
        ax.set_ylim(-0.6, len(sat) - 0.4)
        ax.set_xlabel(t["x"])
        ax.grid(axis="y", visible=False)
        ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: sayi(dil, v, 1)))
        ax.set_title(t["baslik"], loc="left", x=-0.2, pad=14)
        # tablo
        hucre = []
        for k, r, auc, n, ttr, ten, kal in sat:
            guc = "–" if auc is None else (sayi(dil, max(0, 2 * (auc - 0.5)), 2) if kal else "0")
            hucre.append([ad[dil][k], "–" if auc is None else sayi(dil, auc, 3), "–" if n is None else str(n),
                          ttr if dil == "tr" else ten, guc])
        tx = fig.add_axes([0.03, 0.06, 0.94, 0.27])
        tx.axis("off")
        tb = tx.table(cellText=hucre, colLabels=t["sut"], loc="center", cellLoc="left",
                      colWidths=[0.2, 0.07, 0.06, 0.5, 0.12])
        tb.auto_set_font_size(False)
        tb.set_fontsize(9.5)
        for (i, j), c in tb.get_celld().items():
            c.set_edgecolor(IZGARA)
            c.set_facecolor(YUZEY)
            if i == 0:
                c.set_text_props(fontweight="bold", color=METIN2)
            c.set_height(0.14)
        fig.text(0.03, 0.02, t["not_"], fontsize=8.5, color=METIN2)
        kaydet(fig, "b_durust_auc", dil, "motor_dogrulama.json")


# ------------------------------------------------------------------ c) Ay / Mars haritası
def c_ay_mars_harita():
    f = VERI / "harita.csv"
    if not f.exists():
        print("  harita.csv yok: önce python3 sunum/sunum_veri.py harita")
        return
    h = pd.read_csv(f)
    T = {"tr": dict(baslik="PMMA ince levha: Ay ve Mars habitatında yanabilirlik",
                    ay="Ay (g = 0,165)", mars="Mars (g = 0,38)", x="oksijen (%)", y="toplam basınç (kPa)",
                    renk="birleşik yanma ihtimali (model + motor)", sinir="%50 sınırı", model_sinir="yalnız risk modeli",
                    nasa="NASA önerilen habitat\natmosferi (%30–34 O₂, 55–70 kPa)", deniz="Dünya havası",
                    not_="tahmin.py, PMMA 0,2 mm, akış bilinmiyor (en kötü durum). Kutu: keşif atmosferi önerisi.\nSiyah sınır hafif motor yüzünden "
                         "düşük olabilir (U eğrisi tanısı); mavi kesik çizgi yalnız risk modeli."),
         "en": dict(baslik="Thin PMMA sheet: flammability in Moon and Mars habitats",
                    ay="Moon (g = 0.165)", mars="Mars (g = 0.38)", x="oxygen (%)", y="total pressure (kPa)",
                    renk="combined ignition probability (model + engine)", sinir="50% boundary", model_sinir="risk model only",
                    nasa="NASA recommended habitat\natmosphere (30–34% O₂, 55–70 kPa)", deniz="Earth air",
                    not_="tahmin.py, PMMA 0.2 mm, flow unknown (worst case). Box: exploration atmosphere proposal.\nThe black boundary may be low "
                         "because of the light engine (U-curve diagnosis); dashed blue: risk model only.")}
    for dil, t in T.items():
        fig, axs = plt.subplots(1, 2, figsize=(14, 6.4), sharey=True)
        fig.subplots_adjust(left=0.07, right=0.88, top=0.86, bottom=0.14, wspace=0.06)
        for ax, g, ad in zip(axs, (0.165, 0.38), (t["ay"], t["mars"])):
            x = h[h.g == g].pivot(index="basinc_kpa", columns="oksijen", values="yanma_birlesik")
            O, B = np.meshgrid(x.columns.values, x.index.values)
            pc = ax.pcolormesh(O, B, x.values, cmap=ISI, vmin=0, vmax=1, shading="nearest")
            cs = ax.contour(O, B, x.values, levels=[0.5], colors=METIN1, linewidths=2)
            ax.clabel(cs, fmt={0.5: t["sinir"]}, fontsize=9, inline_spacing=6)
            xm = h[h.g == g].pivot(index="basinc_kpa", columns="oksijen", values="yanma_ihtimali")
            cm = ax.contour(O, B, xm.values, levels=[0.5], colors=RENK["model"], linewidths=1.8, linestyles=[(0, (5, 3))])
            ax.clabel(cm, fmt={0.5: t["model_sinir"]}, fontsize=8.5, inline_spacing=4)
            ax.add_patch(Rectangle((30, 55), 4, 15, fill=False, ec=METIN1, lw=2, ls=(0, (5, 3))))
            ax.annotate(t["nasa"], (34, 62.5), xytext=(21.5, 38), fontsize=9.5, color=METIN1,
                        arrowprops=dict(arrowstyle="-", color=METIN1, lw=1),
                        bbox=dict(boxstyle="round,pad=0.3", fc=YUZEY, ec=IZGARA))
            ax.plot(20.9, 101.3, "o", ms=8, mfc=YUZEY, mec=METIN1, mew=1.8)
            ax.annotate(t["deniz"], (20.9, 101.3), xytext=(21.5, 96), fontsize=9)
            ax.set_title(ad, loc="left")
            ax.set_xlabel(t["x"])
            ax.grid(False)
            # habitat kutusundaki ihtimal aralığı
            k = h[(h.g == g) & h.oksijen.between(30, 34) & h.basinc_kpa.between(55, 70)].yanma_birlesik
            ax.text(0.02, 0.03, f"{'habitat kutusunda' if dil == 'tr' else 'in habitat box'}: " +
                    (sayi(dil, k.min(), 2) if round(k.min(), 2) == round(k.max(), 2)
                     else f"{sayi(dil, k.min(), 2)}–{sayi(dil, k.max(), 2)}"), transform=ax.transAxes, fontsize=9.5,
                    bbox=dict(boxstyle="round,pad=0.3", fc=YUZEY, ec=IZGARA))
        axs[0].set_ylabel(t["y"])
        cax = fig.add_axes([0.9, 0.14, 0.017, 0.72])
        cb = fig.colorbar(pc, cax=cax)
        cb.set_label(t["renk"])
        cb.outline.set_visible(False)
        fig.suptitle(t["baslik"], x=0.07, ha="left", fontsize=15, fontweight="bold")
        fig.text(0.07, 0.02, t["not_"], fontsize=8.5, color=METIN2)
        kaydet(fig, "c_ay_mars_harita", dil, "sunum_veri.py → tahmin.py (yanma_birlesik)")


# ------------------------------------------------------------------ d) damla kısmi g
# Not (2026-11-12): eski d grafiğinin sol paneli (hafif motorla U eğrisi) paketten çıkarıldı; literatürle
# uyuşmuyor (en düşük %6,8 / Dünya %14,2'ye karşı MLOC %14,7 / LOI %17). Tanı grafiği: u_tani() ->
# deneyler/u_egrisi_tani_{tr,en}.png. Ayrıntı: sunum_ozet.md.
def d_damla_kismi_g():
    kg = pd.read_csv(KOK / "damla_kismi_g.csv")
    T = {"tr": dict(baslik="Kısmi yerçekiminde damla daha hızlı yanar",
                    s2="Sıvı: damla yanma hızı, kısmi g (damla motoru)", y2="K(g) / K(mikro-g)",
                    x="yerçekimi (g, Dünya = 1)", lit="literatür, 1 g: 1,2–1,5",
                    not_="Kısmi g için deney verisi yok; Ranz–Marshall/Faeth düzeltmesi 1 g verisinde (96 nokta, 5 makale) AUC 0,60."),
         "en": dict(baslik="Droplets burn faster in partial gravity",
                    s2="Liquid: droplet burning rate, partial g (droplet engine)", y2="K(g) / K(micro-g)",
                    x="gravity (g, Earth = 1)", lit="literature, 1 g: 1.2–1.5",
                    not_="No partial-g experiment data; Ranz–Marshall/Faeth correction scored AUC 0.60 on 1 g data (96 points, 5 papers).")}
    for dil, t in T.items():
        fig, a2 = plt.subplots(figsize=(8.5, 6.2))
        fig.subplots_adjust(left=0.11, right=0.97, top=0.84, bottom=0.15)
        for j, (yak, x) in enumerate(kg.groupby("yakit", sort=False)):
            for d0, xx in x.groupby("d0_mm"):
                xx = xx.sort_values("g")
                ls = "-" if j == 0 else (0, (5, 2))
                a2.plot(xx.g, xx.K_oran_ug, ls=ls, marker="o", ms=7, mec=YUZEY, mew=1.5,
                        color=RENK["damla"] if j == 0 else "#0d6e4c",
                        label=f"{yak}, d₀ = {sayi(dil, d0, 1)} mm" if dil == "tr" else
                        f"{yak.replace('n-heptan', 'n-heptane').replace('metanol', 'methanol')}, d₀ = {d0:.1f} mm")
                break
        a2.plot([1.0, 1.0], [1.2, 1.5], color=METIN3, lw=9, alpha=0.45, solid_capstyle="butt", zorder=1)
        a2.annotate(t["lit"], (1.0, 1.5), xytext=(-8, 4), textcoords="offset points", fontsize=9, color=METIN2,
                    ha="right")
        a2.axhline(1.0, color=METIN3, lw=1)
        a2.set(xlabel=t["x"], ylabel=t["y2"])
        a2.set_xscale("log")
        a2.legend(loc="upper left")
        a2.set_title(t["s2"], loc="left", fontsize=12)
        fig.suptitle(t["baslik"], x=0.11, ha="left", fontsize=15, fontweight="bold")
        fig.text(0.11, 0.02, t["not_"], fontsize=8.5, color=METIN2)
        kaydet(fig, "d_damla_kismi_g", dil, "damla_kismi_g.csv · damla_dogrulama_ek.json")


# ------------------------------------------------------------------ U eğrisi tanısı (paket dışı)
# literatür / NASA noktaları: (konum, O2, etiket_tr, etiket_en, tür) tür: "sinir" = ölçülen sınır,
# "alt" = bu O2'de bile sönüyor (sınır daha yüksek)
LIT_U = [
    ("ug", 14.7, "Takahashi, µg MLOC %14,7\n(0,125 mm, 6 cm/s akışla)", "Takahashi, µg MLOC 14.7%\n(0.125 mm, with 6 cm/s flow)", "sinir"),
    ("ug", 15.0, "BASS-II (Olson, NASA PSI-25)\n%15'te 3–5 cm/s'de yanar, 2 cm/s'de söner",
     "BASS-II (Olson, NASA PSI-25)\nat 15%: burns at 3–5 cm/s, out at 2 cm/s", "sinir"),
    ("ug", 21.7, "BASS (Olson, NASA PSI-26), durgun:\n%21,7'de bile söner", "BASS (Olson, NASA PSI-26), quiescent:\nout even at 21.7%", "alt"),
    (1.0, 17.0, "Takahashi, 1 g LOI %17,0", "Takahashi, 1 g LOI 17.0%", "sinir"),
    (1.0, 17.5, "LOI %17,5 (0,2 mm; Fire Technol. 2021)", "LOI 17.5% (0.2 mm; Fire Technol. 2021)", "sinir"),
]


def _kesisim(x, c):
    x = x.sort_values("oksijen")
    y, o = x[c].to_numpy(float), x.oksijen.to_numpy(float)
    i = np.nonzero(y >= 0.5)[0]
    if len(i) == 0:
        return np.nan
    i = i[0]
    return o[0] if i == 0 else o[i - 1] + (0.5 - y[i - 1]) / (y[i] - y[i - 1]) * (o[i] - o[i - 1])


def u_tani():
    f = VERI / "u_bilesenler.csv"
    if not f.exists():
        print("  u_bilesenler.csv yok: önce python3 sunum/sunum_veri.py u3")
        return
    d = pd.read_csv(f)
    gs = np.array(sorted(d.g.unique()))
    egri = {c: np.array([_kesisim(d[d.g == g], c) for g in gs]) for c in ("model", "motor", "birlesik")}
    T = {"tr": dict(baslik="U eğrisi tanısı: sistemin bileşenleri literatürle karşılaştırılıyor",
                    alt="PMMA ince levha (0,2 mm), durgun, 101,3 kPa · her eğri: yanma ihtimalinin %50'yi geçtiği O₂",
                    y="sönme sınırı: en az oksijen (%)", x="yerçekimi (g, Dünya = 1)",
                    model="risk modeli", motor="hafif motor", birlesik="birleşik ihtimal",
                    ug="µg / ISS\n(≤10⁻⁴ g)", yer={0.165: "Ay", 0.38: "Mars", 1.0: "Dünya"},
                    not_="tahmin.py, ≤10⁻⁴ g girdileri 10⁻⁶ g olarak hesaplanır. µg ölçümleri zorlanmış akışlı (Takahashi, "
                         "BASS-II) ya da durgun (BASS);\neğriler durgun ortam içindir. Paket dışı: hafif motor literatürle uyuşmuyor."),
         "en": dict(baslik="U-curve diagnosis: system components against the literature",
                    alt="Thin PMMA sheet (0.2 mm), quiescent, 101.3 kPa · each curve: O₂ where burn probability crosses 50%",
                    y="extinction limit: minimum oxygen (%)", x="gravity (g, Earth = 1)",
                    model="risk model", motor="light engine", birlesik="combined probability",
                    ug="µg / ISS\n(≤10⁻⁴ g)", yer={0.165: "Moon", 0.38: "Mars", 1.0: "Earth"},
                    not_="tahmin.py; inputs ≤1e-4 g are computed at 1e-6 g. µg measurements are with forced flow (Takahashi, "
                         "BASS-II) or quiescent (BASS);\ncurves are quiescent. Not in the deck: light engine disagrees with the literature.")}
    for dil, t in T.items():
        fig, ax = plt.subplots(figsize=(12, 6.8))
        fig.subplots_adjust(left=0.07, right=0.7, top=0.85, bottom=0.17)
        for c, ls in (("model", "-"), ("motor", "-"), ("birlesik", (0, (6, 3)))):
            renk = {"model": RENK["model"], "motor": RENK["hafif"], "birlesik": METIN1}[c]
            ax.plot(gs, egri[c], ls=ls, color=renk, lw=2.4, marker="o", ms=6, mec=YUZEY, mew=1.5, label=t[c])
            ax.annotate(f"{sayi(dil, egri[c][-1], 1)}", (gs[-1], egri[c][-1]), xytext=(8, {"model": 5, "birlesik": -6}.get(c, 0)),
                        textcoords="offset points", va="center", fontsize=9, color=METIN2)
        sx = {"ug": 1e-4}
        dy = {14.7: -1.6, 15.0: 1.2, 21.7: 0.8, 17.0: -1.6, 17.5: 1.0}
        for k, (yer, o, etr, een, tur) in enumerate(LIT_U):
            gx = sx.get(yer, yer)
            gx = gx * (1.25 if tur != "alt" and yer == "ug" and o == 15.0 else 1.0)
            if tur == "alt":
                ax.annotate("", (gx, o + 2.2), xytext=(gx, o), arrowprops=dict(arrowstyle="-|>", color=RENK["olcum"], lw=1.6))
                ax.plot(gx, o, "_", ms=16, mew=2.4, color=RENK["olcum"])
            else:
                ax.plot(gx, o, "D", ms=8, color=RENK["olcum"], mec=YUZEY, mew=1.5, zorder=6)
        # etiketler sağ kenarda, numaralı
        for k, (yer, o, etr, een, tur) in enumerate(LIT_U):
            gx = sx.get(yer, yer) * (1.25 if yer == "ug" and o == 15.0 else 1.0)
            ax.annotate(str(k + 1), (gx, o), xytext=(-12 if yer != "ug" else 9, 0), textcoords="offset points",
                        fontsize=9, fontweight="bold", va="center", ha="center")
            fig.text(0.72, 0.78 - k * 0.085, f"{k + 1}  " + (etr if dil == "tr" else een), fontsize=9, va="top",
                     color=METIN1)
        fig.text(0.72, 0.83, "♦ NASA / literatür ölçümleri" if dil == "tr" else "♦ NASA / literature measurements",
                 fontsize=10, fontweight="bold")
        for g, ad in t["yer"].items():
            ax.axvline(g, color=IZGARA, lw=1, zorder=0)
            ax.text(g, 5.4, ad, ha="center", fontsize=9.5, color=METIN2)
        ax.text(1e-4, 5.4, t["ug"], ha="center", fontsize=9, color=METIN2, va="bottom")
        ax.axhline(20.9, color=METIN3, lw=1, ls=(0, (4, 3)))
        ax.text(1.8e-4, 20.9 + 0.3, "%20,9 O₂" if dil == "tr" else "20.9% O₂", fontsize=8.5, color=METIN3)
        ax.set_xscale("log")
        ax.set_xlim(6e-5, 1.6)
        ax.set_ylim(5, 25)
        ax.set(xlabel=t["x"], ylabel=t["y"])
        ax.set_title(t["alt"], loc="left", fontsize=10.5, fontweight="normal", color=METIN2)
        ax.legend(loc="upper center", ncol=3, bbox_to_anchor=(0.5, -0.1))
        fig.suptitle(t["baslik"], x=0.07, ha="left", fontsize=15, fontweight="bold")
        fig.text(0.07, 0.015, t["not_"], fontsize=8, color=METIN2, wrap=True)
        fig.text(0.995, 0.005, "sunum/veri/u_bilesenler.csv ← tahmin.py", ha="right", va="bottom", fontsize=7.5, color=METIN3)
        yol = KOK / "deneyler" / f"u_egrisi_tani_{dil}.png"
        fig.savefig(yol, dpi=DPI)
        plt.close(fig)
        print("  ->", yol.relative_to(KOK))


# ------------------------------------------------------------------ e) FLEX d² ve K
def e_flex_d2_K():
    import damla_motoru as dm
    import of_tek_damla as of
    t_of, d_of, _ = of.log_serileri(of.OF_KOK / "tek_damla_isinimsiz.log")
    t_of, d_of = np.array(t_of), np.array(d_of)
    tab = pd.read_csv(KOK / "of_tek_damla_sonuc.csv")
    K_of = float(tab[tab.kaynak.str.startswith("OpenFOAM")].K_mm2_s.iloc[0])
    flex = tab[tab.kaynak.str.startswith("FLEX")]
    r = dm.damla_motoru(1e-4, 21, 101.3, 0, 2.0, "n-heptane", "droplet", mod="hizli")
    K_dm, ds_dm = r["yanma_hizi_K"], r["sonme_capi"]
    nk = pd.read_csv(KOK / "damla_flex_alev_noktalar.csv")
    K_fx = flex.K_mm2_s.astype(float).values
    T = {"tr": dict(baslik="Tek n-heptan damlası (2 mm, %21 O₂, 1 atm, mikro-g): d² yasası",
                    s1="damla çapının karesi (d₀² ile ölçekli; eğim = K)", s2="yanma hızı K = −d(d²)/dt",
                    of="OpenFOAM (ışınımsız)", dm="damla_motoru", fx="FLEX ölçümü (ISS)",
                    y1="d² / d₀²", y2="K (mm²/s)", x="t / d₀² (s/mm²)",
                    kutu="OpenFOAM, FLEX'in ~{o}×'i: nokta damla buharlaşması + tek adım kimya\n"
                         "damla_motoru FLEX ortalamasından {f} farklı",
                    sonme="sönme çapı"),
         "en": dict(baslik="Single n-heptane droplet (2 mm, 21% O₂, 1 atm, micro-g): d² law",
                    s1="droplet diameter squared (scaled by d₀²; slope = K)", s2="burning rate K = −d(d²)/dt",
                    of="OpenFOAM (no radiation)", dm="droplet engine", fx="FLEX measurement (ISS)",
                    y1="d² / d₀²", y2="K (mm²/s)", x="t / d₀² (s/mm²)",
                    kutu="OpenFOAM is ~{o}× FLEX: point-droplet evaporation + one-step chemistry\n"
                         "droplet engine differs from the FLEX mean by {f}",
                    sonme="extinction diameter")}
    for dil, t in T.items():
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 6.2), gridspec_kw=dict(width_ratios=[1.6, 1]))
        fig.subplots_adjust(left=0.07, right=0.98, top=0.84, bottom=0.2, wspace=0.22)
        d0_fx = {int(k.split()[2]): float(v) for k, v in zip(flex.kaynak, flex.d0_mm)}
        for j, test in enumerate((7, 51, 229)):
            x = nk[(nk.test == test) & (nk.seri == "d2") & (nk.t_s >= 0)].sort_values("t_s")
            q = d0_fx[test] ** 2
            x = x[x.deger / q <= 1.05]          # sayısallaştırmadaki birkaç taşan nokta (başka seri) dışarıda
            a1.plot(x.t_s / q, x.deger / q, "o", ms=3, color=RENK["olcum"], alpha=0.45,
                    label=t["fx"] + f" ({len(d0_fx)} {'test' if dil == 'tr' else 'tests'})" if j == 0 else None)
        q0 = 4.0
        a1.plot(t_of / q0, d_of ** 2 / q0, color=RENK["of"], lw=2.6, label=f"{t['of']}  K = {sayi(dil, K_of, 2)}")
        tt = np.linspace(0, (q0 - (ds_dm or 0) ** 2) / K_dm, 50)
        a1.plot(tt / q0, (q0 - K_dm * tt) / q0, color=RENK["damla"], lw=2.6,
                label=f"{t['dm']}  K = {sayi(dil, K_dm, 2)}")
        if ds_dm:
            a1.plot(tt[-1] / q0, ds_dm ** 2 / q0, "X", ms=11, color=RENK["damla"], mec=YUZEY, zorder=5)
            a1.annotate(f"{t['sonme']} {sayi(dil, ds_dm, 2)} mm", (tt[-1] / q0, ds_dm ** 2 / q0), xytext=(10, -4),
                        textcoords="offset points", fontsize=9, va="top")
        a1.set(xlabel=t["x"], ylabel=t["y1"], ylim=(0, 1.1), xlim=(0, None))
        a1.legend(loc="upper right")
        a1.set_title(t["s1"], loc="left", fontsize=12)
        # K çubukları
        ad = [t["fx"].replace(" (ISS)", ""), t["dm"], t["of"]]
        deg = [float(np.mean(K_fx)), K_dm, K_of]
        renk = [RENK["olcum"], RENK["damla"], RENK["of"]]
        xs = np.arange(3)
        a2.bar(xs, deg, width=0.6, color=renk)
        a2.errorbar(0, np.mean(K_fx), yerr=[[np.mean(K_fx) - K_fx.min()], [K_fx.max() - np.mean(K_fx)]],
                    color=METIN3, capsize=6, lw=1.5)
        for xi, v in zip(xs, deg):
            ust = (K_fx.max() if xi == 0 else v) + 0.03
            a2.text(xi, ust, sayi(dil, v, 2), ha="center", va="bottom", fontsize=11, fontweight="bold")
        a2.set_xticks(xs, ad, fontsize=9.5)
        a2.set(ylabel=t["y2"], ylim=(0, max(deg) * 1.2))
        a2.grid(axis="x", visible=False)
        a2.set_title(t["s2"], loc="left", fontsize=12)
        fig.text(0.07, 0.04, t["kutu"].format(o=sayi(dil, K_of / np.mean(K_fx), 1),
                                              f=(f"%{100 * (K_dm / np.mean(K_fx) - 1):+.0f}" if dil == "tr"
                                                 else f"{100 * (K_dm / np.mean(K_fx) - 1):+.0f}%").replace("-", "−")),
                 fontsize=10, color=METIN1, bbox=dict(boxstyle="round,pad=0.5", fc="#fff6de", ec=UYARI["uyari"]))
        fig.suptitle(t["baslik"], x=0.07, ha="left", fontsize=15, fontweight="bold")
        kaydet(fig, "e_flex_d2_K", dil, "of_tek_damla_sonuc.csv · of_kosular/tek_damla_isinimsiz.log · "
                                        "damla_flex_alev_noktalar.csv (NASA/TP-2015-216046) · damla_motoru.py")


# ------------------------------------------------------------------ f) güven skoru
def f_guven_skoru():
    r = jread(VERI / "ornek_guven.json")
    gv = r["guven"]
    w = gv["agirliklar"]
    T = {"tr": dict(baslik="Güven skoru nasıl hesaplanıyor? Örnek: PMMA levha, ISS, %21 O₂, 1 atm",
                    veri="veri", uyum="uyum", motor="motor",
                    averi="yakın deney sayısı / 15 (en çok 1)\n{n} yakın deney → {v}",
                    auyum="1 − |yakın deney yanma oranı − model|\n|{o} − {p}| → {v}",
                    amotor="max(0, 2(AUC − 0,5)), yakın deneylerde\nmotor AUC {a} → {v}",
                    top="skor = 100 × (0,4·{v} + 0,3·{u} + 0,3·{m}) = {s}",
                    birl="Birleşik ihtimal: model {p} (ağırlık {wm}) + motor {mt} (ağırlık {wt}) = {b}",
                    xl="skora katkı (puan)", not_="Yakın deney yoksa uyum hesaplanmaz: 100 × (0,7 veri + 0,3 motor)."),
         "en": dict(baslik="How is the confidence score computed? Example: PMMA sheet, ISS, 21% O₂, 1 atm",
                    veri="data", uyum="agreement", motor="engine",
                    averi="nearby tests / 15 (max 1)\n{n} nearby tests → {v}",
                    auyum="1 − |nearby burn fraction − model|\n|{o} − {p}| → {v}",
                    amotor="max(0, 2(AUC − 0.5)) on nearby tests\nengine AUC {a} → {v}",
                    top="score = 100 × (0.4·{v} + 0.3·{u} + 0.3·{m}) = {s}",
                    birl="Combined probability: model {p} (weight {wm}) + engine {mt} (weight {wt}) = {b}",
                    xl="contribution to score (points)",
                    not_="With no nearby tests agreement is skipped: 100 × (0.7 data + 0.3 engine).")}
    import re
    auc = re.search(r"AUC ([\d.]+)", gv["motor_yontemi"])
    auc = float(auc.group(1)) if auc else float("nan")
    for dil, t in T.items():
        s = lambda z, n=2: sayi(dil, z, n)  # noqa: E731
        bil = [("veri", w["veri"], gv["veri_bileseni"], t["averi"].format(n=gv["yakin_deney"], v=s(gv["veri_bileseni"]))),
               ("uyum", w["uyum"], gv["uyum_bileseni"], t["auyum"].format(o=s(gv["yakin_deney_yanma_orani"]),
                                                                        p=s(r["yanma_ihtimali"]),
                                                                        v=s(gv["uyum_bileseni"]))),
               ("motor", w["motor"], gv["motor_bileseni"], t["amotor"].format(a=s(auc), v=s(gv["motor_bileseni"])))]
        renk = {"veri": RENK["model"], "uyum": RENK["llm"], "motor": RENK["hafif"]}
        fig = plt.figure(figsize=(14, 7))
        ax = fig.add_axes([0.06, 0.5, 0.9, 0.2])
        sol = 0
        for k, wk, v, _ in bil:
            katki = 100 * wk * v
            ax.barh(0, katki, left=sol, height=0.6, color=renk[k], ec=YUZEY, lw=2)
            ax.barh(0, 100 * wk - katki, left=sol + katki, height=0.6, color=renk[k], alpha=0.15, ec=YUZEY, lw=2)
            ax.text(sol + katki / 2, 0, f"{t[k]}\n{s(katki, 1)}", ha="center", va="center", color="white",
                    fontsize=11, fontweight="bold")
            sol += 100 * wk
        ax.set_xlim(0, 100)
        ax.set_yticks([])
        ax.set_xlabel(t["xl"])
        ax.grid(False)
        ax.spines["left"].set_visible(False)
        ax.axvline(gv["skor"], color=METIN1, lw=0)
        fig.text(0.06, 0.8, t["top"].format(v=s(gv["veri_bileseni"]), u=s(gv["uyum_bileseni"]),
                                            m=s(gv["motor_bileseni"]), s=gv["skor"]),
                 fontsize=15, fontweight="bold")
        for i, (k, wk, v, aciklama) in enumerate(bil):
            x = 0.06 + i * 0.31
            fig.text(x, 0.36, f"{t[k]}  (× {s(wk, 1)})", fontsize=12, fontweight="bold", color=renk[k])
            fig.text(x, 0.33, aciklama, fontsize=10, color=METIN1, va="top", linespacing=1.4)
        m = r["motor"]
        fig.text(0.06, 0.14, t["birl"].format(p=s(r["yanma_ihtimali"], 3), wm=s(r["agirliklar"]["model"], 3),
                                              mt=s(m["yanma"], 3), wt=s(r["agirliklar"]["motor"], 3),
                                              b=s(r["yanma_birlesik"], 3)), fontsize=11, color=METIN1,
                 bbox=dict(boxstyle="round,pad=0.5", fc=YUZEY, ec=IZGARA))
        fig.text(0.06, 0.06, t["not_"], fontsize=9, color=METIN2)
        fig.suptitle(t["baslik"], x=0.06, ha="left", fontsize=15, fontweight="bold", y=0.95)
        kaydet(fig, "f_guven_skoru", dil, "sunum/veri/ornek_guven.json ← tahmin.py · motor_kontrol.guven_skoru")


# ------------------------------------------------------------------ g) Kevlar çelişki
def g_kevlar_celiski():
    r = jread(VERI / "kevlar.json")
    gv, m, ll = r["guven"], r["motor"], r["llm_siniflandirma"]
    cev = {"'kevlar' listede yok, LLM bunu 'nomex' malzemesine benzetti (kati, fabric) — kontrol edin.":
           "'kevlar' is not in the list; the LLM matched it to 'nomex' (solid, fabric) — please check.",
           "Hava akışı bilinmiyor; en kötü durum (akış var) varsayıldı.":
           "Air flow unknown; worst case (flow present) assumed.",
           "Model ve motor çelişiyor: model 'söner', motor 'yanar' diyor.":
           "Model and engine disagree: model says 'extinguishes', engine says 'burns'."}
    T = {"tr": dict(baslik="Kevlar örneği: model ile fizik motoru çeliştiğinde",
                    alt="tahmin('kevlar', oksijen=21, basinc=101.3, g=1e-4) — ekran çıktısı",
                    model="Risk modeli", motor="Hafif motor (fizik)", bir="Birleşik", guv="Güven",
                    yan="yanma ihtimali", sny="söner", ynr="yanar", uy="Uyarılar",
                    llm="Öneri — 'kevlar' listede yok. Yapay zeka nomex (katı, kumaş) malzemesine benzetti:\n"
                        "\"{g}\"   [Onayla] [Değiştir]",
                    ac="Neden: bu koşula yakın deney az ({n}, nomex eşlemesiyle); motorun bu bölgedeki AUC'si 0,50 → motor bileşeni 0."),
         "en": dict(baslik="Kevlar example: when the model and the physics engine disagree",
                    alt="tahmin('kevlar', oksijen=21, basinc=101.3, g=1e-4) — screen output",
                    model="Risk model", motor="Light engine (physics)", bir="Combined", guv="Confidence",
                    yan="ignition probability", sny="extinguishes", ynr="burns", uy="Warnings",
                    llm="Suggestion — 'kevlar' is not in the list. The AI matched it to nomex (solid, fabric):\n"
                        "\"Kevlar and Nomex are both heat-resistant aromatic polyamide fabrics.\"   [Accept] [Change]",
                    ac="Why: few nearby tests ({n}, via the nomex match); engine AUC here is 0.50 → engine component 0.")}
    for dil, t in T.items():
        fig = plt.figure(figsize=(14, 7.6))
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, 14)
        ax.set_ylim(0, 7.6)
        ax.axis("off")
        ax.text(0.5, 7.1, t["baslik"], fontsize=16, fontweight="bold")
        ax.text(0.5, 6.7, t["alt"], fontsize=10, color=METIN2, family="DejaVu Sans Mono")
        ax.add_patch(FancyBboxPatch((0.5, 5.55), 13, 0.9, boxstyle="round,pad=0.02,rounding_size=0.1",
                                    fc=matplotlib.colors.to_rgba(RENK["llm"], 0.08), ec=RENK["llm"], lw=1.4))
        ax.text(0.7, 6.0, t["llm"].format(g=ll["gerekce"]), fontsize=9.8, va="center", linespacing=1.5)
        kart = [(t["model"], r["yanma_ihtimali"], RENK["model"]), (t["motor"], m["yanma"], RENK["hafif"]),
                (t["bir"], r["yanma_birlesik"], METIN1)]
        for i, (ad, p, rk) in enumerate(kart):
            x = 0.5 + i * 3.35
            ax.add_patch(FancyBboxPatch((x, 3.0), 3.1, 2.25, boxstyle="round,pad=0.02,rounding_size=0.1",
                                        fc=YUZEY, ec=rk, lw=2))
            ax.text(x + 0.2, 4.95, ad, fontsize=11.5, fontweight="bold", color=rk if rk != METIN1 else METIN1)
            ax.text(x + 0.2, 4.1, sayi(dil, p, 2), fontsize=30, fontweight="bold")
            ax.text(x + 0.2, 3.55, t["yan"], fontsize=9.5, color=METIN2)
            if i < 2:
                karar = t["ynr"] if p >= 0.5 else t["sny"]
                ax.text(x + 2.9, 4.2, karar, fontsize=11, ha="right", fontweight="bold",
                        color=UYARI["kritik"] if p >= 0.5 else RENK["model"])
            ax.add_patch(Rectangle((x + 0.2, 3.25), 2.7, 0.12, fc=IZGARA, ec="none"))
            ax.add_patch(Rectangle((x + 0.2, 3.25), 2.7 * p, 0.12, fc=rk, ec="none"))
        x = 0.5 + 3 * 3.35
        ax.add_patch(FancyBboxPatch((x, 3.0), 2.5, 2.25, boxstyle="round,pad=0.02,rounding_size=0.1",
                                    fc=YUZEY, ec=UYARI["uyari"], lw=2))
        ax.text(x + 0.2, 4.95, t["guv"], fontsize=11.5, fontweight="bold")
        ax.text(x + 0.2, 4.1, f"{gv['skor']}/100", fontsize=26, fontweight="bold")
        ax.text(x + 0.2, 3.55, f"{'veri' if dil == 'tr' else 'data'} {sayi(dil, gv['veri_bileseni'])} · "
                f"{'uyum' if dil == 'tr' else 'agr.'} {sayi(dil, gv['uyum_bileseni'])} · "
                f"{'motor' if dil == 'tr' else 'engine'} {sayi(dil, gv['motor_bileseni'])}", fontsize=8.5, color=METIN2)
        # uyarılar
        ax.add_patch(FancyBboxPatch((0.5, 0.75), 13, 1.95, boxstyle="round,pad=0.02,rounding_size=0.1",
                                    fc="#fff6de", ec=UYARI["uyari"], lw=1.4))
        ax.text(0.75, 2.38, "⚠  " + t["uy"], fontsize=12, fontweight="bold")
        for i, u in enumerate(r["uyarilar"]):
            metin = u if dil == "tr" else cev.get(u, u)
            vurgu = "çeliş" in u
            ax.text(0.95, 1.95 - i * 0.38, "• " + metin, fontsize=10.5,
                    fontweight="bold" if vurgu else "normal", color=UYARI["kritik"] if vurgu else METIN1)
        ax.text(0.5, 0.35, t["ac"].format(n=gv["yakin_deney"]), fontsize=9.5, color=METIN2)
        kaydet(fig, "g_kevlar_celiski", dil, "sunum/veri/kevlar.json ← tahmin.py (LLM sınıflandırması önbellekten)")


HEPSI = {"a": a_sistem_semasi, "b": b_durust_auc, "c": c_ay_mars_harita, "d": d_damla_kismi_g,
         "e": e_flex_d2_K, "f": f_guven_skoru, "g": g_kevlar_celiski}

if __name__ == "__main__":
    for k in sys.argv[1:] or list(HEPSI):
        f = HEPSI.get(k) or {"tani": u_tani}[k]       # "tani": U eğrisi tanısı (paket dışı, deneyler/)
        print(k, f.__name__)
        f()
