#!/usr/bin/env python3
"""
NASA PSI FLEX (PSI-69) deney tablosunu okur ve risk modeli için etiketli noktalara çevirir.

FLEX: ISS'te serbest yüzen yakıt damlaları (metanol, heptan) farklı oksijen, basınç ve
seyreltici gazlarda (N2, CO2, He) yakılmış. Test sonu:
  Completion  -> damla tamamen yandı
  Disruption  -> damla parçalandı (alev o ana kadar yandı)
  Extinction  -> alev damla bitmeden söndü

Etiket kuralı:
  - Alev damlanın büyük kısmını yaktıysa                          -> yandı
  - Alev neredeyse hemen söndüyse (sönme çapı / ilk çap >= 0.85)  -> söndü
    (ortam alevi sürdüremedi; söndürme gazının etkisi)

Kullanım:
  python scripts/psi_flex.py "PSI-69_Experimental table_FLEX.csv"
Çıktılar:
  psi_flex_testler.csv     -> her test (dashboard ve kontrol için)
  data/psi_labeled_flex.csv    -> scripts/risk_model.py'nin kullanacağı noktalar
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

KAYNAK_NOTU = "NASA PSI-69 (FLEX) – Experimental table"
HEMEN_SONDU_ORANI = 0.85


def sutun(df, *kelimeler):
    for c in df.columns:
        if all(k in c.lower() for k in kelimeler):
            return c
    raise SystemExit(f"Sütun bulunamadı: {kelimeler}")


def sayi(x):
    return pd.to_numeric(x, errors="coerce")


def main():
    girdi = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("PSI-69_Experimental table_FLEX.csv")
    df = pd.read_csv(girdi, encoding="cp1252")
    c_p = sutun(df, "pressure")
    c_o2, c_n2 = sutun(df, "o initial"), sutun(df, "n initial")
    c_co2, c_he = sutun(df, "co initial"), sutun(df, "he initial")
    c_d0, c_dx = sutun(df, "initial diameter"), sutun(df, "extinction diameter")
    c_k, c_t = sutun(df, "burning rate"), sutun(df, "burn time")

    t = pd.DataFrame({
        "test": df[sutun(df, "test #")], "kimlik": df[sutun(df, "identifier")],
        "yakit": df["Fuel"].str.lower().str.strip(),
        "basinc_kpa": (sayi(df[c_p]) * 0.133322).round(1),
        "oksijen_yuzde": (sayi(df[c_o2]) * 100).round(1),
        "n2_yuzde": (sayi(df[c_n2]) * 100).round(1),
        "co2_yuzde": (sayi(df[c_co2]) * 100).round(1),
        "he_yuzde": (sayi(df[c_he]) * 100).round(1),
        "ilk_cap_mm": sayi(df[c_d0]), "sonme_capi_mm": sayi(df[c_dx]),
        "yanma_hizi_mm2_s": sayi(df[c_k]), "yanma_suresi_s": sayi(df[c_t]),
        "test_sonu": df["Test end"].str.strip(),
    })
    t["seyreltici"] = np.select([t.he_yuzde > 0, t.co2_yuzde > 0], ["he", "co2"], "n2")
    t["sonme_orani"] = (t.sonme_capi_mm / t.ilk_cap_mm).round(2)
    t["hemen_sondu"] = (t.test_sonu == "Extinction") & (t.sonme_orani >= HEMEN_SONDU_ORANI)
    t.to_csv("psi_flex_testler.csv", index=False, encoding="utf-8-sig")

    k = t.dropna(subset=["oksijen_yuzde", "basinc_kpa"])
    k = k[k.basinc_kpa > 5]          # basıncı 0 yazılmış bozuk satırlar
    e = pd.DataFrame({
        "makale_id": "PSI-69_" + k.test.astype(str), "kaynak": "nasa_psi", "link": KAYNAK_NOTU,
        "veri_turu": "deney", "platform": "ISS", "g_seviyesi": 1e-4,
        "malzeme_sade": k.yakit, "numune_tipi": "droplet", "yakit_turu": "sivi",
        "kalinlik_mm": k.ilk_cap_mm, "oksijen_yuzde": k.oksijen_yuzde,
        "seyreltici": k.seyreltici, "basinc_kpa": k.basinc_kpa, "akis_hizi_cm_s": 0.0,
        "akis_yonu": "yok", "yanar": (~k.hemen_sondu).astype(int), "etiket_kaynagi": "psi"})
    e.to_csv("data/psi_labeled_flex.csv", index=False, encoding="utf-8-sig")

    print(f"{len(t)} test okundu | test sonu: {t.test_sonu.value_counts().to_dict()}")
    print(f"seyreltici: {t.seyreltici.value_counts().to_dict()}")
    print(f"oksijen aralığı: %{t.oksijen_yuzde.min()}–{t.oksijen_yuzde.max()} | "
          f"basınç: {t.basinc_kpa.min()}–{t.basinc_kpa.max()} kPa")
    print(f"{len(e)} etiketli nokta: yandı {int(e.yanar.sum())}, hemen söndü {int((1 - e.yanar).sum())}")
    print("Yazıldı: psi_flex_testler.csv, data/psi_labeled_flex.csv")


if __name__ == "__main__":
    main()
