#!/usr/bin/env python3
"""
scripts/gas_test.py — scripts/gas_engine.py regresyon testi (sistem python3'ü ile, venv'siz).

  python3 scripts/gas_test.py              # denetimleri çalıştır + gas_test_record/last.json ile karşılaştır, last.json'u güncelle
  python3 scripts/gas_test.py --kaydet v1  # ayrıca gas_test_record/v1.json olarak sakla
  python3 scripts/gas_test.py --once v1    # karşılaştırmayı v1 ile yap

Denetimler (BAŞARISIZ varsa çıkış kodu 1):
  1. çalışma ortamı: Cantera / scipy / pandas / sklearn gas_engine() çağrısında içe aktarılmıyor
  2. taşınım tabloları literatürle (300 K; Incropera 7. baskı Tablo A.4, Marrero & Mason 1972) <= %6
  3. termokimya: PSI-10 Flame Design T_ad (medyan <= 30 K) ve Z_st (<= 1e-3); Irace 2021 Tablo 2 R_f <= %8
  4. BRE (kayıtlı parametrelerle, içeride): AUC >= 0.93, X_r (FT) medyan hata <= 0.06, q'' (FT) <= %20
  5. fizik yönleri: O2 artınca yanma artmaz değil; büyük BRE alevinde basınç düşünce yanma artar (ışınım ∝ p);
     küçük debide kaynak kaybıyla "kimyasal", büyük debide "isinim" sönme; kalibre_degil bayrakları
  6. örnek çıktılar (ORNEKLER) önceki kayıtla karşılaştırılır (değişen her alan önce -> sonra)
"""
import argparse
import json
import math
import sys
import time
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "scripts"))          # python3 -I ile de (betik klasörü yolda olmasa da) gas_engine bulunsun
KAYIT = KOK / "gas_test_record"

ORNEKLER = [
    ("BRE C2H4 %34 O2 0.57 bar 1.78 g/m2s (87B1, FT)", dict(g=1e-4, oksijen=34, basinc=57, akis=None, kalinlik=25,
                                                         malzeme="ethylene", numune_tipi="flat_burner",
                                                         kutle_akisi_g_m2s=1.78)),
    ("BRE C2H4 %30 O2 0.57 bar 6.95 g/m2s (94K1, SE)", dict(g=1e-4, oksijen=30, basinc=57, akis=None, kalinlik=25,
                                                         malzeme="ethylene", numune_tipi="flat_burner",
                                                         kutle_akisi_g_m2s=6.95)),
    ("BRE %50 C2H4 %21 O2 1 bar", dict(g=1e-4, oksijen=21, basinc=101.3, akis=None, kalinlik=25, malzeme="50% C2H4",
                                      numune_tipi="flat_burner", kutle_akisi_g_m2s=2.0)),
    ("küre Irace alev 3 (SE)", dict(g=1e-4, oksijen=28.4, basinc=100, akis=None, kalinlik=6.4,
                                   malzeme="13.2% ethylene", numune_tipi="porous_sphere", debi_mg_s=4.49)),
    ("küre Irace alev 1 (FT)", dict(g=1e-4, oksijen=19.0, basinc=100, akis=None, kalinlik=6.4, malzeme="ethylene",
                                   numune_tipi="porous_sphere", debi_mg_s=0.33)),
    ("küre H2/He s-Flame", dict(g=1e-4, oksijen=21, basinc=101.3, akis=None, kalinlik=6.4,
                               malzeme="45% H2 with He", numune_tipi="porous_sphere", seyreltici="he", debi_mg_s=1.0)),
    ("sızıntı CH4 hava 1 g", dict(g=1.0, oksijen=21, basinc=101.3, akis=None, kalinlik=6.4, malzeme="methane",
                                 numune_tipi="leak", debi_mg_s=2.0)),
    ("jet CH4 hava 1 g", dict(g=1.0, oksijen=21, basinc=101.3, akis=30, kalinlik=3.2, malzeme="methane",
                             numune_tipi="gas_jet")),
    ("jet CH4 hava ISS", dict(g=1e-4, oksijen=21, basinc=101.3, akis=30, kalinlik=3.2, malzeme="methane",
                             numune_tipi="gas_jet")),
    ("jet propan CO2'li ortam", dict(g=1.0, oksijen=18, basinc=101.3, akis=20, kalinlik=4, malzeme="propane",
                                    numune_tipi="gas_jet", seyreltici="co2")),
]


def denetim(sonuclar, ad, kosul, ayrinti=""):
    sonuclar.append((ad, bool(kosul), ayrinti))


def calistir():
    import numpy as np
    t0 = time.time()
    once = set(sys.modules)
    import gas_engine as gm
    r = gm.gas_engine(1e-4, 34, 57, None, 25, "ethylene", "flat_burner", kutle_akisi_g_m2s=1.78)
    yeni = set(sys.modules) - once
    d = []
    yasak = [m for m in ("cantera", "scipy", "pandas", "sklearn") if any(x == m or x.startswith(m + ".") for x in yeni)]
    denetim(d, "1. çalışma anında yalnız numpy (cantera/scipy/pandas/sklearn yok)", not yasak, f"yüklenen: {yasak}")
    denetim(d, "1. python yorumlayıcısı", True, f"{sys.executable} {sys.version.split()[0]}, numpy {np.__version__}")
    O = gm.oz()
    T = np.array([300.0])
    lit = {("mu", "N2"): 1.78e-5, ("mu", "O2"): 2.07e-5, ("mu", "HE"): 1.99e-5, ("lam", "N2"): 0.0259,
           ("lam", "O2"): 0.0263, ("lam", "HE"): 0.152, ("lam", "CO2"): 0.0166}
    en = 0.0
    for (k, s), v in lit.items():
        en = max(en, abs(O.tab(getattr(O, k), T)[O.i[s], 0] / v - 1))
    io = O.i["O2"]
    Dn2 = O.tab(O.D[io], T)[O.i["N2"], 0]
    en = max(en, abs(Dn2 / 2.0e-5 - 1))
    denetim(d, "2. taşınım tabloları literatürle <= %6", en <= 0.06, f"en büyük sapma %{en * 100:.1f}")
    # 3. termokimya
    import csv
    satir = [x for x in csv.DictReader(open(KOK / "PSI_SFLAME" / "PSI-10_Experimental table_Flame Design_Normal Flame.csv"))
             if x["Xfuel"] not in ("RAMP", "RAMPED")]
    XF, XO, p, Tad, Z = [], [], [], [], []
    for x in satir:
        xf = float(x["Xfuel"])
        XF.append(gm.vektor({x["Fuel"]: xf, "N2": 1 - xf} if xf < 1 else {x["Fuel"]: 1.0}))
        xo = (float(x["XO2 (init)"]) + float(x["XO2 (final)"] or x["XO2 (init)"])) / 2
        XO.append(gm.vektor({"O2": xo, "N2": 1 - xo}))
        p.append(float(x["pmean (atm)"] or x["pinit (atm)"]) * gm.P0)
        Tad.append(float(x["Tad (K)"]))
        Z.append(float(x["mean Zst"]))
    tk = gm.termokimya(np.array(XF).T, np.array(XO).T, np.array(p))
    eT = float(np.median(np.abs(tk["T_ad"] - np.array(Tad))))
    eZ = float(np.max(np.abs(tk["Zst"] - np.array(Z))))
    denetim(d, "3. PSI-10 T_ad medyan hata <= 30 K", eT <= 30, f"{eT:.1f} K ({len(satir)} test)")
    denetim(d, "3. PSI-10 Z_st en büyük hata <= 1e-3", eZ <= 1e-3, f"{eZ:.5f}")
    par = gm.varsayilan_parametreler()
    ir = list(csv.DictReader(open(gm.VERI / "flame_design_irace2021.csv")))
    XFi, XOi, mdi = [], [], []
    for x in ir:
        mC, mN = float(x["m_C2H4_mg_s"]), float(x["m_N2_mg_s"])
        nC, nN = mC / 28.054, mN / 28.014
        XFi.append(gm.vektor({"C2H4": nC / (nC + nN), "N2": nN / (nC + nN)} if nN > 0 else {"C2H4": 1.0}))
        XOi.append(gm.vektor({"O2": float(x["X_O2"]), "N2": 1 - float(x["X_O2"])}))
        mdi.append((mC + mN) * 1e-6)
    gi = gm.kure_girdi(XFi, XOi, np.full(len(ir), 1.0e5), mdi)
    rr = gm.hesapla(par, **gi)
    eR = float(np.max(np.abs(rr["R0"] * 1e3 / np.array([float(x["R_f_kuram_mm"]) for x in ir]) - 1)))
    denetim(d, "3. Irace 2021 Tablo 2 R_f (kuram) <= %8", eR <= 0.08, f"en büyük sapma %{eR * 100:.1f}")
    # 4. BRE
    b = list(csv.DictReader(open(gm.VERI / "bre_dehghani2021_table2.csv")))
    N = len(b)
    XFb = np.zeros((O.ns, N))
    XOb = np.zeros((O.ns, N))
    for k, x in enumerate(b):
        XFb[O.i["C2H4"], k] = float(x["X_f"])
        XFb[O.i["N2"], k] = 1 - float(x["X_f"])
        XOb[O.i["O2"], k] = float(x["X_O2"])
        XOb[O.i["N2"], k] = 1 - float(x["X_O2"])
    Rb = 0.0125
    rb = gm.hesapla(par, np.ones(N, int), XFb, XOb, np.array([float(x["p_bar"]) for x in b]) * 1e5,
                    np.full(N, 1e-4), np.array([float(x["m_akisi_g_m2s"]) for x in b]) * 1e-3 * math.pi * Rb ** 2,
                    np.full(N, Rb), np.zeros(N), np.full(N, 300.0))
    y = np.array([x["sonuc"] == "FT" for x in b], int)
    auc = _auc(y, rb["yanma"])
    ft = y == 1
    xr = np.array([float(x["isinim_orani_X_r"]) if x["isinim_orani_X_r"] else np.nan for x in b])
    m = ft & np.isfinite(xr)
    eX = float(np.median(np.abs(rb["chi_r"][m] - xr[m])))
    qc = np.array([float(x["q_merkez_kW_m2"]) for x in b])
    eq = float(np.median(np.abs(rb["q_flux"][ft] / qc[ft] - 1)))
    denetim(d, "4. BRE içeride AUC >= 0.93", auc >= 0.93, f"{auc:.3f}")
    denetim(d, "4. BRE X_r (FT) medyan hata <= 0.06", eX <= 0.06, f"{eX:.3f}")
    denetim(d, "4. BRE q'' (FT) medyan hata <= %20", eq <= 0.20, f"%{eq * 100:.1f}")
    # 5. fizik yönleri
    ys = [gm.gas_engine(1e-4, o, 57, None, 25, "ethylene", "flat_burner", kutle_akisi_g_m2s=3.0,
                        min_oksijen_hesapla=False)["yanma"] for o in (22, 26, 30, 34, 38)]
    denetim(d, "5. BRE: O2 arttıkça yanma azalmıyor", all(b2 >= a2 - 1e-6 for a2, b2 in zip(ys, ys[1:])),
            str([round(v, 3) for v in ys]))
    yp = [gm.gas_engine(1e-4, 30, pk, None, 25, "ethylene", "flat_burner", kutle_akisi_g_m2s=4.0,
                        min_oksijen_hesapla=False)["yanma"] for pk in (101, 80, 57)]
    denetim(d, "5. BRE büyük alev: basınç düştükçe yanma artıyor (ışınım ∝ p)", yp[0] <= yp[1] <= yp[2],
            str([round(v, 3) for v in yp]))
    kucuk = gm.gas_engine(1e-4, 21, 101.3, None, 6.4, "13.2% ethylene", "porous_sphere", debi_mg_s=0.3,
                          min_oksijen_hesapla=False)
    buyuk = gm.gas_engine(1e-4, 21, 101.3, None, 6.4, "ethylene", "porous_sphere", debi_mg_s=3.0,
                          min_oksijen_hesapla=False)
    denetim(d, "5. küçük debi -> kimyasal, büyük debi -> ışınım sönmesi",
            kucuk["sonme_turu"] == "kimyasal" and buyuk["sonme_turu"] == "isinim",
            f"küçük: {kucuk['sonme_turu']} (χ_s {kucuk['kaynak_kaybi_orani']}), büyük: {buyuk['sonme_turu']} "
            f"(χ_r {buyuk['isinim_orani']})")
    jet = gm.gas_engine(1.0, 21, 101.3, 30, 3.2, "methane", "gas_jet")
    denetim(d, "5. kalibre_degil: jet True, BRE C2H4/N2 µg False", jet["kalibre_degil"] and not r["kalibre_degil"])
    denetim(d, "5. çıktı alanları", all(k in r for k in ("yanma", "min_oksijen", "sicaklik", "alev_yaricapi",
                                                          "alev_boyu", "sonme_turu", "mesafe", "kalibre_degil")))
    cikti = {}
    for ad, kw in ORNEKLER:
        o = gm.gas_engine(**kw)
        o = {k: v for k, v in o.items() if k != "uyarilar"}
        o["uyari_sayisi"] = len(gm.gas_engine(**kw)["uyarilar"])
        cikti[ad] = o
    return d, cikti, time.time() - t0


def _auc(y, s):
    import numpy as np
    y = np.asarray(y)
    s = np.asarray(s)
    pos, neg = s[y == 1], s[y == 0]
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum())
                 / (len(pos) * len(neg)))


def karsilastir(eski, yeni):
    satir = []
    for ad, o in yeni.items():
        e = eski.get(ad, {})
        for k, v in o.items():
            if k not in e:
                satir.append(f"  [yeni] {ad} :: {k} = {v}")
            elif e[k] != v and not (isinstance(v, float) and isinstance(e[k], float)
                                    and abs(v - e[k]) <= 1e-9 * max(1, abs(v))):
                satir.append(f"  {ad} :: {k}: {e[k]} -> {v}")
    return satir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kaydet")
    ap.add_argument("--once", default="son")
    a = ap.parse_args()
    d, cikti, sure = calistir()
    hata = 0
    for ad, ok, ay in d:
        print(f"{'TAMAM ' if ok else 'BAŞARISIZ'}  {ad}  {ay}")
        hata += 0 if ok else 1
    KAYIT.mkdir(exist_ok=True)
    f_once = KAYIT / f"{a.once}.json"
    if f_once.exists():
        fark = karsilastir(json.loads(f_once.read_text(encoding="utf-8"))["ornekler"], cikti)
        print(f"\nÖrnek çıktılar, {f_once.name} ile karşılaştırma: " + ("değişiklik yok" if not fark else
                                                                  f"{len(fark)} değişiklik"))
        for s in fark:
            print(s)
    else:
        print(f"\nÖnceki kayıt yok ({f_once.name}): ilk kayıt yazılıyor")
    kayit = {"tarih": time.strftime("%Y-%m-%d %H:%M"), "denetimler": [list(x) for x in d], "ornekler": cikti}
    (KAYIT / "last.json").write_text(json.dumps(kayit, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.kaydet:
        (KAYIT / f"{a.kaydet}.json").write_text(json.dumps(kayit, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(d) - hata}/{len(d)} denetim tamam, {sure:.1f} s")
    sys.exit(1 if hata else 0)


if __name__ == "__main__":
    main()
