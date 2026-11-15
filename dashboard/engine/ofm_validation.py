#!/usr/bin/env python3
"""
ofm_validation.py — OpenFOAM motoru koşusunu deneyle karşılaştıran doğrulama grafiği + JSON (koşu klasörüne YAZMAZ).

    python3 ofm_validation.py KOSU --deney saffire3 [--cikti ofm_sonuclar]     # Saffire-III S1 (2B ya da 3B)
    python3 ofm_validation.py KOSU --deney bass4                                 # BASS (PSI-26) SIBAL as-run test 4

Okuduğu (postProcessing; 2B ve 3B aynı yapı, bkz. ofm_analysis.py):
  fluid/gazMax, tel/telT, sibal/sibalYuzey (ofm_analysis.analiz ile), sibal/sibalKutle (kütle kaybı),
  fluid/sensGaz, sibal/sensYuzey (TC), fluid/sensRadMenba, fluid/sensRadAkis (radyometre vekili G/4) — Saffire.
Deney:
  saffire3 : data/saffire3_sample1.csv (PSI-100 telemetri; igniter başlangıcı 59.994 s),
             yayılma 2.3 mm/s (NTRS 20180005168 Tablo 1), alev ucu x = 32 cm @ 100-125 s, 62 cm @ 210-250 s (kamera,
             ofm_engine DEVIR_NOTU §6), gaz tutuşması 3.1-5.1 s arası belirsiz.
             Sensör eşlemesi TC7-TC12 = A-F ve radyometre vekili G/4 ÇIKARIMDIR (OpenFOAM motorunun notları).
  bass4    : BASS test matrix.xlsx 'as run' test 4: SIBAL 2.2 x 10 cm, 10 cm/s, %21.9 O2, 0.97 atm, "~40 s burn"
             -> ortalama yayılma ≈ 10 cm / 40 s = 2.5 mm/s (KABA: tutuşma ve sönme dahil, gözlemcinin tahmini süre).
Eşik zamanları (karsilastir_sensor.py ile aynı tanım): radyometre +1/+3/+10 mW/cm², TC +5/+20/+100 K, tabana göre,
en az 0.15 s üstünde kalan ilk geçiş.
"""
import argparse
import json
from pathlib import Path

import numpy as np

import ofm_analysis as ba

KOK = Path(__file__).resolve().parent
SAFFIRE_CSV = KOK / "data" / "saffire3_sample1.csv"
T_IGN_TELEMETRI = 59.994
TABAN = (40.0, 59.0)
PERS = 0.15
ES_RAD, ES_TC = (1.0, 3.0, 10.0), (5.0, 20.0, 100.0)
DENEY = {
    "saffire3": {"ad": "Saffire-III S1", "numune_x0": 0.15, "numune_x1": 1.09, "yayilma_mm_s": 2.3,
                 "cephe": [(0.32, 100, 125), (0.62, 210, 250)], "tutusma": (3.1, 5.1),
                 "kaynak": "NTRS 20180005168 Tablo 1; PSI-100 telemetri; S1C1 kamera (motor notları)"},
    "bass4": {"ad": "BASS SIBAL test 4", "numune_x0": 0.10, "numune_x1": 0.20, "yayilma_mm_s": 2.5,
              "yanma_suresi_s": 40.0, "tutusma": None,
              "kaynak": "BASS test matrix.xlsx (as run 4): '~40 s burn'; 10 cm numune (NASA 20160000593)",
              "not": "ortalama yayılma = numune boyu / yanma süresi; tutuşma ve sönme süreleri dahil, KABA"},
}
TC_ESLEME = {"TC7 A": ("sample_temp1_K", "sibal/sensYuzey", 0), "TC8 B": ("sample_temp2_K", "fluid/sensGaz", 0),
             "TC9 C": ("sample_temp3_K", "fluid/sensGaz", 1), "TC10 D": ("sample_temp4_K", "sibal/sensYuzey", 1),
             "TC11 E": ("sample_temp5_K", "fluid/sensGaz", 2), "TC12 F": ("sample_temp6_K", "fluid/sensGaz", 3)}


def probe(case, yol, alan):
    """postProcessing/<yol>/<t0>/<alan> (yeniden başlatmalar birleştirilir) -> (t, değerler[n, k]) ya da None."""
    kok = Path(case) / "postProcessing" / yol
    if not kok.is_dir():
        return None
    parca = []
    for d in sorted((d for d in kok.iterdir() if d.is_dir() and ba._sayi(d.name) is not None),
                    key=lambda d: float(d.name)):
        f = d / alan
        if f.exists():
            a = np.loadtxt(f, comments="#", ndmin=2)
            if a.size:
                parca.append(a)
    if not parca:
        return None
    a = np.vstack(parca)
    _, i = np.unique(a[:, 0][::-1], return_index=True)       # çakışan zamanda sonraki klasör
    a = a[::-1][i]
    return a[:, 0], a[:, 1:]


def esik_zamani(t, y, esik):
    if len(t) < 2:
        return None
    k = max(1, int(round(PERS / np.median(np.diff(t)))))
    ust = y > esik
    for i in range(len(y) - k + 1):
        if ust[i:i + k].all():
            return float(t[i])
    return None


def deney_yukle():
    satir = [s for s in SAFFIRE_CSV.read_text().splitlines() if not s.startswith("#")]
    ad = satir[0].split(",")
    v = np.array([[float(x) for x in s.split(",")[:len(ad)]] for s in satir[1:]])
    return {a: v[:, i] for i, a in enumerate(ad)}


def saffire_sensorler(case):
    if not SAFFIRE_CSV.exists():
        return {"hata": f"deney dosyası yok: {SAFFIRE_CSV}"}, {}
    d = deney_yukle()
    t_tel = d["elapsed_time_s"]
    te = t_tel - T_IGN_TELEMETRI
    taban = (t_tel >= TABAN[0]) & (t_tel <= TABAN[1])
    m = te >= 0
    tablo, egriler = {}, {}
    for ad, (kol, yol, i) in TC_ESLEME.items():
        y = d[kol]
        dz = {f"+{e:g} K": esik_zamani(te[m], (y - y[taban].mean())[m], e) for e in ES_TC}
        mp = probe(case, yol, "T")
        md = None
        if mp is not None and mp[1].shape[1] > i:
            ym = mp[1][:, i]
            md = {f"+{e:g} K": esik_zamani(mp[0], ym - ym[0], e) for e in ES_TC}
            egriler[ad] = {"model": (mp[0], ym), "deney": (te[m], y[m])}
        tablo[ad] = {"deney": dz, "model": md,
                     "fark_s": None if md is None else {k: (None if md[k] is None or dz[k] is None
                                                            else round(md[k] - dz[k], 2)) for k in dz}}
    for yol, ad_, kanallar in (("fluid/sensRadMenba", "radyometre ilk yarı (R1, R3)", (1, 3)),
                               ("fluid/sensRadAkis", "radyometre ikinci yarı (R2, R4)", (2, 4))):
        y = np.mean([d[f"radiometer{k}_mW_cm2"] for k in kanallar], axis=0)
        dz = {f"+{e:g} mW/cm²": esik_zamani(te[m], (y - y[taban].mean())[m], e) for e in ES_RAD}
        mp = probe(case, yol, "G")
        md = None
        if mp is not None and len(mp[0]) > 2:
            g = mp[1].mean(axis=1) / 4 * 0.1          # G/4 W/m² -> mW/cm²
            md = {k: esik_zamani(mp[0], g - g[1], e) for k, e in zip(dz, ES_RAD)}
            egriler[ad_] = {"model": (mp[0], g - g[1]), "deney": (te[m], (y - y[taban].mean())[m])}
        tablo[ad_] = {"deney": dz, "model": md,
                      "fark_s": None if md is None else {k: (None if md[k] is None or dz[k] is None
                                                             else round(md[k] - dz[k], 2)) for k in dz}}
    return tablo, egriler


def kutle_kaybi(case):
    s = ba.zaman_serisi(case, "sibal/sibalKutle")
    if not s:
        return None
    t = np.array(list(s))
    m = np.array([sum(v[:2]) for v in s.values()])     # volIntegrate(rhoV) + volIntegrate(rhoCh)
    return t, 1 - m / m[0] if m[0] else m * 0


def main():
    a = argparse.ArgumentParser(description="OpenFOAM motoru doğrulama grafiği")
    a.add_argument("kosu")
    a.add_argument("--deney", choices=sorted(DENEY), required=True)
    a.add_argument("--cikti", default="ofm_sonuclar")
    a.add_argument("--esik", type=float, default=0.10)
    a.add_argument("--x0", type=float, help="numune ön kenarı x [m] (BILGI.json'u ezer)")
    a.add_argument("--x1", type=float, help="numune arka kenarı x [m]")
    k = a.parse_args()
    case = Path(k.kosu).resolve()
    dz = dict(DENEY[k.deney])
    # OpenFOAM motorunun geometrisi bizimkinden farklı olabilir: koşu klasöründeki (ya da üstündeki) BILGI.json'dan
    for f in (case / "BILGI.json", case.parent / "BILGI.json"):
        if f.exists():
            b = json.loads(f.read_text(encoding="utf-8"))
            dz["numune_x0"] = b.get("numune_x0_m", dz["numune_x0"])
            dz["numune_x1"] = b.get("numune_x1_m", dz["numune_x1"])
            dz["bilgi"] = b
            break
    dz["numune_x0"] = dz["numune_x0"] if k.x0 is None else k.x0
    dz["numune_x1"] = dz["numune_x1"] if k.x1 is None else k.x1
    sonuc, gaz, tel, x_t = ba.analiz(case, k.esik)
    ozet = {"kosu": str(case), "deney": dz, "boyut": sonuc["boyut"], "tutusma_zamani_s": sonuc["tutusma_zamani_s"],
            "durum": sonuc["durum"], "simulasyon_suresi_s": sonuc["simulasyon_suresi_s"],
            "yayilma_hizi_mm_s": sonuc["yayilma_hizi_mm_s"],
            "yayilma_hizi_genislik_mm_s": sonuc.get("yayilma_hizi_genislik_mm_s"),
            "yayilma_farki_mm_s": None if sonuc["yayilma_hizi_mm_s"] is None
            else round(sonuc["yayilma_hizi_mm_s"] - dz["yayilma_mm_s"], 3)}
    if dz.get("tutusma") and sonuc["tutusma_zamani_s"] is not None:
        lo, hi = dz["tutusma"]
        ti = sonuc["tutusma_zamani_s"]
        ozet["tutusma_deney_araliginda"] = lo <= ti <= hi
    cephe = [(t, x) for t, x in x_t if x is not None]
    if k.deney == "bass4":
        uc = [t for t, x in cephe if x >= dz["numune_x1"] - 0.002]
        ozet["model_yanma_suresi_s"] = uc[0] if uc else None
        ozet["yanma_suresi_farki_s"] = None if not uc else round(uc[0] - dz["yanma_suresi_s"], 2)
    tablo, egriler = saffire_sensorler(case) if k.deney == "saffire3" else ({}, {})
    ozet["sensor_esikleri"] = tablo
    kk = kutle_kaybi(case)
    ozet["kutle_kaybi_son"] = None if kk is None else round(float(kk[1][-1]), 4)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n = 5 if k.deney == "saffire3" else 3
    fig, ax = plt.subplots(n, 1, figsize=(9, 2.8 * n))
    # 1) tutuşma
    if gaz:
        ax[0].plot(list(gaz), [v[0] for v in gaz.values()], lw=1.1, label="model gaz T maks")
    ax[0].axhline(ba.T_ISIK, color="r", ls="--", lw=0.8, label="tutuşma ölçütü 1500 K")
    if dz.get("tutusma"):
        ax[0].axvspan(*dz["tutusma"], color="gray", alpha=0.25, label="deney: tutuşma aralığı (belirsiz)")
    ax[0].set_ylabel("T [K]"); ax[0].legend(fontsize=7); ax[0].set_title("Tutuşma", fontsize=10, loc="left")
    # 2) alev ucu
    if cephe:
        ax[1].plot([t for t, _ in cephe], [100 * (x - dz["numune_x0"]) for _, x in cephe], "o-", ms=3,
                   label="model alev ucu (en ileri)")
    xg = [(p["t"], p["x_m"]) for p in (sonuc.get("alev_cephesi_genislik_ortalamasi") or []) if p["x_m"] is not None]
    if xg:
        ax[1].plot([t for t, _ in xg], [100 * (x - dz["numune_x0"]) for _, x in xg], "s--", ms=3,
                   label="model alev ucu (genişlik medyanı, 3B)")
    for x_cm, t0, t1 in dz.get("cephe", []):
        ax[1].plot([t0, t1], [100 * x_cm] * 2, color="k", lw=4, alpha=0.6)
    if dz.get("cephe"):
        x_cm, t0, t1 = dz["cephe"][0]
        tt = np.array([0.5 * (t0 + t1) - 60, 0.5 * (t0 + t1) + 160])
        ax[1].plot(tt, 100 * x_cm + 0.1 * dz["yayilma_mm_s"] * (tt - 0.5 * (t0 + t1)), "k:", lw=1,
                   label=f"deney {dz['yayilma_mm_s']} mm/s (kalın çizgi: kamera)")
    if dz.get("yanma_suresi_s"):
        L = 100 * (dz["numune_x1"] - dz["numune_x0"])
        ax[1].plot([0, dz["yanma_suresi_s"]], [0, L], "k:", lw=1, label=f"deney ortalaması ~{dz['yayilma_mm_s']} mm/s")
        ax[1].plot(dz["yanma_suresi_s"], L, "k*", ms=10, label="deney: numune sonu (~40 s, kaba)")
    ax[1].set_ylabel("ön kenardan [cm]"); ax[1].legend(fontsize=7)
    ax[1].set_title(f"Alev ucu – model {sonuc['yayilma_hizi_mm_s']} mm/s, deney {dz['yayilma_mm_s']} mm/s",
                    fontsize=10, loc="left")
    # 3) sensörler (Saffire)
    if k.deney == "saffire3":
        renk = plt.rcParams["axes.prop_cycle"].by_key()["color"]
        for j, (ad, e) in enumerate(egriler.items()):
            if ad.startswith("TC"):
                ax[2].plot(*e["deney"], color=renk[j % 10], lw=0.8, alpha=0.6)
                ax[2].plot(*e["model"], color=renk[j % 10], lw=1.4, ls="--", label=ad)
        ax[2].set_xlim(0, max(10, sonuc["simulasyon_suresi_s"] or 10))
        ax[2].set_ylabel("T [K]"); ax[2].legend(fontsize=7, ncol=3)
        ax[2].set_title("TC: deney (ince) / model (kesik); eşleme çıkarım", fontsize=10, loc="left")
        for j, (ad, e) in enumerate((a_, e_) for a_, e_ in egriler.items() if not a_.startswith("TC")):
            ax[3].plot(*e["deney"], lw=0.8, alpha=0.6, label=f"deney {ad}")
            ax[3].plot(*e["model"], lw=1.4, ls="--", label=f"model vekil G/4 {ad}")
        ax[3].set_xlim(0, max(10, sonuc["simulasyon_suresi_s"] or 10))
        ax[3].set_ylabel("Δ mW/cm²"); ax[3].legend(fontsize=7)
        ax[3].set_title("Radyometre (vekil: G/4; mutlak değer güvenilmez)", fontsize=10, loc="left")
    # son) kütle kaybı
    a_k = ax[-1]
    if kk is not None:
        a_k.plot(kk[0], 100 * kk[1], color="tab:brown", lw=1, label="model kütle kaybı (yanabilir)")
        a_k.set_ylabel("kütle kaybı [%]")
        a_k.legend(fontsize=7, loc="lower right")
        a_k.set_title("Kütle kaybı (deneyde ölçüm yok)", fontsize=10, loc="left")
    else:
        a_k.text(0.5, 0.5, "sibalKutle çıktısı yok", transform=a_k.transAxes, ha="center")
    for x in ax:
        x.set_xlabel("ateşleyici başlangıcından [s]", fontsize=8)
    fig.suptitle(f"OpenFOAM motoru ({sonuc['boyut']}) – {dz['ad']} doğrulaması", fontsize=12)
    fig.tight_layout()
    cikti = Path(k.cikti)
    if cikti.resolve() == case or case in cikti.resolve().parents:
        raise SystemExit("çıktı klasörü koşu klasörünün içinde olamaz")
    cikti.mkdir(parents=True, exist_ok=True)
    ad = case.name if case.name != "vaka" else f"{case.parent.name}_{case.name}"
    png, js = cikti / f"ofm_validation_{ad}_{k.deney}.png", cikti / f"ofm_validation_{ad}_{k.deney}.json"
    fig.savefig(png, dpi=120)
    plt.close(fig)
    ozet["grafik"] = str(png)
    js.write_text(json.dumps(ozet, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(json.dumps({x: ozet[x] for x in ("boyut", "tutusma_zamani_s", "durum", "yayilma_hizi_mm_s",
                                         "yayilma_farki_mm_s")}, ensure_ascii=False))
    print("->", js, "\n->", png)


if __name__ == "__main__":
    main()
