#!/usr/bin/env python3
"""Model sensorleri ile deney sensorlerinin esik zamanlarini karsilastirir.

Kullanim:  python3 -I karsilastir_sensor.py kosular/sensorlu_hedef02
Yalnizca okur. Esikler: radyometre +1/+3/+10 mW/cm2, TC +5/+20/+100 K (tabana gore).
Esik zamani = sinyalin esigi gecip en az PERS saniye ustunde kaldigi ilk an.
Zaman: igniter baslangicina gore (deney 59.994 s).
"""
import sys
from pathlib import Path
import numpy as np

KOK = Path(__file__).resolve().parent
CSV = KOK.parent.parent / "veri" / "islenmis" / "saffire3_sample1.csv"
T_IGN = 59.994          # igniter baslangici (telemetri zamani, s)
TABAN_PENCERE = (40.0, 59.0)   # deney taban penceresi (telemetri zamani)
PERS = 0.15             # esigin ustunde kalma suresi (s)
ES_RAD = (1.0, 3.0, 10.0)      # mW/cm2
ES_TC = (5.0, 20.0, 100.0)     # K


def deney_yukle():
    with open(CSV) as f:
        satirlar = [s for s in f if not s.startswith("#")]
    ad = satirlar[0].strip().split(",")
    veri = np.array([[float(x) for x in s.strip().split(",")] for s in satirlar[1:]])
    return ad, veri


def esik_zamani(t, y, esik, pers=PERS):
    """Ilk kalici gecis zamani; yoksa None."""
    dt = np.median(np.diff(t))
    k = max(1, int(round(pers / dt)))
    ust = y > esik
    for i in range(len(y) - k + 1):
        if ust[i:i + k].all():
            return t[i]
    return None


def probe_yukle(yol):
    """OpenFOAM probes dosyasi: '#' satirlari atilir, ilk sutun zaman."""
    if not yol.exists():
        return None
    a = np.loadtxt(yol, comments="#")
    return a if a.ndim == 2 else a.reshape(1, -1)


def f(x):
    return "   -  " if x is None else f"{x:6.2f}"


def satir(ad, t, y, esikler, baz):
    return f"{ad:<22}" + "".join(f(esik_zamani(t, y - baz, e)) for e in esikler)


def main():
    kosu = Path(sys.argv[1]) if len(sys.argv) > 1 else KOK / "kosular" / "sensorlu_hedef02"
    if not kosu.is_absolute():
        kosu = KOK / kosu if not kosu.exists() else kosu.resolve()
    pp = kosu / "postProcessing"

    ad, v = deney_yukle()
    te = v[:, 0] - T_IGN
    taban = (v[:, 0] >= TABAN_PENCERE[0]) & (v[:, 0] <= TABAN_PENCERE[1])
    sut = {a: i for i, a in enumerate(ad)}
    m = te >= 0

    print(f"Kosu: {kosu.name}   (zaman = igniter baslangicina gore, s)")
    print(f"Esik gecis = ilk kalici gecis (>= {PERS} s); '-' = gecmedi")

    # --- Radyometreler ---
    print("\nRADYOMETRE (mW/cm2)          " + "".join(f"  +{e:g}  " for e in ES_RAD))
    for k in range(1, 5):
        c = f"radiometer{k}_mW_cm2"
        y = v[:, sut[c]][m]
        b = v[:, sut[c]][taban].mean()
        print(satir(f"deney R{k}", te[m], y, ES_RAD, b))
    mb = probe_yukle(pp / "fluid" / "sensRadMenba" / "0" / "G")
    if mb is not None:
        g = mb[:, 1:].mean(axis=1) / 4 * 0.1   # G/4 (W/m2) -> mW/cm2, 5 sensor ortalamasi
        # ilk satir G = 0 (baslangic kosulu); taban = ikinci satir (t = 0.02 s, ~42.55 mW/cm2)
        print(satir("model vekil (Menba ort)", mb[:, 0], g, ES_RAD, g[1]))
        print(f"   model son zaman: {mb[-1, 0]:.2f} s")

    # --- TC'ler ---
    print("\nTC (K)                       " + "".join(f"  +{e:g}  " for e in ES_TC))
    esleme = {   # ad: (deney kolonu, model dosyasi, model sutun indeksi)
        "TC7  A": ("sample_temp1_K", "sibal/sensYuzey", 1),
        "TC8  B": ("sample_temp2_K", "fluid/sensGaz", 1),
        "TC9  C": ("sample_temp3_K", "fluid/sensGaz", 2),
        "TC10 D": ("sample_temp4_K", "sibal/sensYuzey", 2),
        "TC11 E": ("sample_temp5_K", "fluid/sensGaz", 3),
        "TC12 F": ("sample_temp6_K", "fluid/sensGaz", 4),
    }
    for ad_, (kol, mdosya, mi) in esleme.items():
        y = v[:, sut[kol]]
        print(satir(f"deney {ad_}", te[m], y[m], ES_TC, y[taban].mean()))
        mp = probe_yukle(pp / mdosya / "0" / "T")
        if mp is not None:
            print(satir(f"model  {ad_}", mp[:, 0], mp[:, mi], ES_TC, mp[0, mi]))
    for k in range(1, 7):   # plume: modelde sensor yok
        c = f"plume_temp{k}_K"
        y = v[:, sut[c]]
        print(satir(f"deney plume TC{k}", te[m], y[m], ES_TC, y[taban].mean()))
    print("\nNot: plume TC'lerin ve anemometrenin konumu bilinmiyor, modelde karsiligi yok.")
    print("Not: TC7-TC12 = A-F eslemesi ve radyometre vekili (G/4, 2B P1) cikarimdir.")


if __name__ == "__main__":
    main()
