#!/usr/bin/env python3
"""
OpenFOAM motorunun'da çalıştıracağı koşulların listesini hazırlar -> data/openfoam_runs.csv

İki tür koşu:
  dogrulama : NASA'nın uzayda gerçekten yaptığı deneyler (BASS, BASS-II, Saffire).
              Motorun sonucu NASA'nın gerçek sonucuyla karşılaştırılır -> güven skoru.
              Sonucu yandı/söndü sınırına yakın olanlar ve her deneyden örnekler seçilir.
  ay_mars   : Ay ve Mars yaşam alanı koşulları (asıl soru; deney verisi neredeyse yok).

Öncelik: 1 = mutlaka, 2 = vakit olursa. OpenFOAM sonuçları openfoam_sonuclar.csv'ye yazar
(aynı girdi sütunları + yandi, yayilma_hizi, min_oksijen, sicaklik).

Kullanım:  python scripts/openfoam_runs.py [--dogrulama 40]
"""
import argparse
import glob

import numpy as np
import pandas as pd

GIRDI = ["g", "oksijen", "basinc", "akis", "kalinlik", "malzeme"]
AY_MARS_MALZEMELER = {"pmma": 0.2, "cotton-fiberglass (sibal)": 0.33, "nomex": 0.37, "silicone": 0.36}


def dogrulama_kosulari(n):
    d = pd.concat([pd.read_csv(f) for f in glob.glob("data/psi_labeled*.csv")], ignore_index=True)
    d = d[d.yakit_turu.astype(str).eq("kati") & d.oksijen_yuzde.notna()].copy()
    def aile_adi(m):
        m = str(m)
        if m.startswith("PSI-25"): return "BASS-II"
        if m.startswith("PSI-26"): return "BASS"
        if m.startswith(("PSI-98", "PSI-99", "PSI-100", "Saffire")): return "Saffire"
        return "makale"
    d["deney"] = d.makale_id.map(aile_adi)
    d = d.rename(columns={"g_seviyesi": "g", "oksijen_yuzde": "oksijen", "basinc_kpa": "basinc",
                          "akis_hizi_cm_s": "akis", "kalinlik_mm": "kalinlik", "malzeme_sade": "malzeme"})
    d = d.drop_duplicates(GIRDI)
    # aynı ailede (deney, malzeme, kalınlık) hem yanan hem sönen varsa koşul sınıra yakındır: önce onlar
    aile = d.groupby(["deney", "malzeme", "kalinlik"]).yanar.transform(lambda s: s.nunique() > 1)
    d["oncelik"] = np.where(aile, 1, 2)
    d["_r"] = np.random.default_rng(0).random(len(d))
    pay = {"BASS-II": 0.35, "BASS": 0.3, "Saffire": 0.2, "makale": 0.15}
    parcalar = []
    for deney, oran in pay.items():
        g = d[d.deney == deney].sort_values(["oncelik", "_r"])
        k = max(2, round(n * oran))
        # yarısı söndü, yarısı yandı olsun (motorun iki yönde de sınanması için)
        parcalar += [g[g.yanar == 0].head(k // 2), g[g.yanar == 1].head(k - min(k // 2, (g.yanar == 0).sum()))]
    secilen = pd.concat(parcalar).head(n)
    return secilen.assign(tur="dogrulama", nasa_sonucu=secilen.yanar.map({1: "yandı", 0: "söndü"}),
                          kaynak=secilen.makale_id)[["tur", "oncelik", *GIRDI, "nasa_sonucu", "kaynak"]]


def ay_mars_kosulari():
    r = []
    for yer, g in (("Ay", 0.165), ("Mars", 0.38)):
        for malzeme, kalinlik in AY_MARS_MALZEMELER.items():
            for o2 in (21, 26, 30, 34):
                for basinc in (55, 70, 101.3):
                    for akis in (0, 10):
                        # NASA'nın önerdiği yaşam alanı atmosferi: %30-34 O2, ~55-70 kPa
                        oncelik = 1 if (o2 >= 30 and basinc <= 70 and malzeme == "pmma") else 2
                        r.append({"tur": f"ay_mars ({yer})", "oncelik": oncelik, "g": g, "oksijen": o2,
                                  "basinc": basinc, "akis": akis, "kalinlik": kalinlik, "malzeme": malzeme})
    return pd.DataFrame(r)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dogrulama", type=int, default=40, help="kaç NASA deneyi koşulu")
    a = p.parse_args()
    k = pd.concat([dogrulama_kosulari(a.dogrulama), ay_mars_kosulari()], ignore_index=True)
    k.insert(0, "kosu_no", range(1, len(k) + 1))
    for c in ("yandi", "yayilma_hizi", "min_oksijen", "sicaklik"):
        k[c] = np.nan                                          # OpenFOAM dolduracak
    k.to_csv("data/openfoam_runs.csv", index=False, encoding="utf-8-sig")
    print(f"data/openfoam_runs.csv: {len(k)} koşu")
    print(k.groupby(["tur", "oncelik"]).size().to_string())
    print("\nOfm: dolu sütunları OpenFOAM'da çalıştırıp yandi / yayilma_hizi / min_oksijen / sicaklik "
          "sütunlarını doldursun, dosyayı openfoam_sonuclar.csv olarak kaydetsin.")


if __name__ == "__main__":
    main()
