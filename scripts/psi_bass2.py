#!/usr/bin/env python3
"""
NASA PSI BASS-II deney tablosunu (PSI-25 Experimental table) okur ve risk modeli için
"yandı / söndü" etiketli noktalara çevirir.

Tablodaki "Air display" sütunu hava akış hızlarıdır (cm/s). Testlerde akış adım adım
değiştirilmiş, alev sönünce "ext", akış çok artınca kopunca "blowoff" yazılmış.
  - alev bir akışta sürdüyse          -> yandı noktası
  - "ext" ile biten akış              -> söndü noktası (o akışta)
  - "blowoff"                         -> söndü noktası (en yüksek akışta)
  - "no ign" (hiç tutuşmadı)          -> söndü noktası

Kullanım:
  python scripts/psi_bass2.py PSI-25_Experimental_table_BASS-II.csv
Çıktılar:
  psi_bass2_testler.csv   -> her test, okunan değerlerle (elle kontrol için)
  data/psi_labeled.csv        -> scripts/risk_model.py'nin kullanacağı etiketli noktalar
"""

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

KAYNAK = "PSI-25 BASS-II"
DOI_NOTU = "NASA PSI-25 (BASS-II) – Experimental table"


def sayi(x):
    try:
        return float(str(x).strip())
    except ValueError:
        return np.nan


def oksijen(bas, son):
    """Başlangıç ve bitiş O2'si; bozuk değerleri (0.6, 39.1, 'none') at."""
    b, s = sayi(bas), sayi(son)
    b = b if 10 <= b <= 30 else np.nan
    s = s if 10 <= s <= 30 else np.nan
    if pd.notna(b) and pd.notna(s) and abs(b - s) <= 1.5:
        return round((b + s) / 2, 2)
    return b if pd.notna(b) else s


def malzeme_oku(m):
    t = str(m).lower().replace("blac ", "black ")
    kalinlik, numune = np.nan, "other"
    if "sibal" in t:
        return "cotton-fiberglass (sibal)", "fabric", np.nan
    if "nomex" in t:
        return "nomex", "fabric", np.nan
    if "candle" in t or "wax" in t:
        return "wax", "other", np.nan
    if "rod" in t:
        inc = {"1/4": 6.35, "3/8": 9.525, "1/2": 12.7, "0.5": 12.7}
        for k, v in inc.items():
            if k in t:
                kalinlik = v
        ad = "pmma (black)" if "black" in t else "pmma"
        return ad, "rod", kalinlik
    m = re.search(r"(\d+(?:\.\d+)?)\s*micron", t)
    if m:
        kalinlik = float(m.group(1)) / 1000
    else:
        m = re.search(r"(\d+(?:\.\d+)?)\s*mm", t)
        if m:
            kalinlik = float(m.group(1))
    numune = "thin_sheet" if pd.notna(kalinlik) and kalinlik <= 0.5 else "thick_sheet"
    return "pmma", numune, kalinlik


def akis_oku(hava, fan):
    """'5 3 2 ext' -> ([5, 3, 2], 'ext').  Parantez içleri (fan potansiyometresi) atılır."""
    t = f"{hava}".lower()
    hepsi = f"{hava} {fan}".lower()
    son = ("noign" if "no ign" in hepsi or "would not stay lit" in hepsi else
           "blowoff" if "blowoff" in hepsi else
           "ext" if re.search(r"\bext|extinguish|\bout\b", hepsi) else "")
    t = re.sub(r"\(.*?\)", " ", t)                       # parantez içi fan değerleri
    t = re.sub(r"pots?\s*\d*\.?\d+", " ", t)              # 'pot 0.4' fan ayarıdır, akış değil
    akislar = [float(x) for x in re.findall(r"(?<![\d.])(\d+(?:\.\d+)?)", t)]
    akislar = [a for a in akislar if a <= 50]             # 50 cm/s üstü fan sayısıdır
    m = re.search(r"(\d+(?:\.\d+)?)\s*ext", t)          # söndüğü akış açıkça yazılmış mı?
    ext_akis = float(m.group(1)) if m else None
    return akislar, son, ext_akis


def noktalar(test):
    """Bir testten (akış, yanar) noktaları üretir."""
    akis, son = test["akislar"], test["son"]
    p = []
    # 0 cm/s (durgun hava) sadece açıkça "ext" yazıyorsa kullanılır; yoksa belirsiz
    if son != "ext":
        akis = [a for a in akis if a > 0]
    if son == "noign":
        for a in (akis or [np.nan]):
            p.append((a, 0))
        return p
    if son == "ext" and akis:
        if test.get("ext_akis") is not None:          # "3 2 1 ext": 1'de söndü
            p += [(a, 1) for a in akis if a > test["ext_akis"]]
            p.append((test["ext_akis"], 0))
        else:                                         # "5 down to ext": söndüğü akış belli değil
            p += [(a, 1) for a in akis if a > 0]
    elif son == "blowoff" and akis:
        en_yuksek = max(akis)
        p += [(a, 1) for a in akis if a < en_yuksek]
        p.append((en_yuksek, 0))         # en yüksek akışta koptu
    else:
        p += [(a, 1) for a in akis]      # sönme yazılmamış: alev bu akışlarda sürdü
    return p


def main():
    girdi = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("PSI-25_Experimental_table_BASS-II.csv")
    df = pd.read_csv(girdi, dtype=str).dropna(subset=["Test #"])
    o2_bas = [c for c in df.columns if "initial" in c.lower() and "o2" in c.lower()][0]
    o2_son = [c for c in df.columns if "final" in c.lower() and "o2" in c.lower()][0]

    testler, etiketli = [], []
    for _, r in df.iterrows():
        malzeme, numune, kalinlik = malzeme_oku(r["Fuel Sample Material"])
        akislar, son, ext_akis = akis_oku(r["Air display"], r["Fan display"])
        o2 = oksijen(r[o2_bas], r[o2_son])
        t = {"test": r["Test #"], "arastirmaci": r["PI"], "malzeme_ham": r["Fuel Sample Material"],
             "malzeme_sade": malzeme, "numune_tipi": numune, "kalinlik_mm": kalinlik,
             "oksijen_yuzde": o2, "hava_ham": r["Air display"], "akislar": akislar, "son": son,
             "ext_akis": ext_akis}
        testler.append(t)
        if pd.isna(o2) or malzeme == "wax":
            continue
        for a, yanar in noktalar(t):
            etiketli.append({
                "makale_id": f"PSI-25_{r['Test #']}", "kaynak": "nasa_psi", "link": DOI_NOTU,
                "veri_turu": "deney", "platform": "ISS", "g_seviyesi": 1e-4,
                "malzeme_sade": malzeme, "numune_tipi": numune,
                "yakit_turu": "kati", "kalinlik_mm": kalinlik, "oksijen_yuzde": o2,
                "seyreltici": "n2", "basinc_kpa": 101.3, "akis_hizi_cm_s": a,
                "akis_yonu": None,          # tabloda yazmıyor
                "yanar": yanar, "etiket_kaynagi": "psi"})

    pd.DataFrame(testler).to_csv("psi_bass2_testler.csv", index=False, encoding="utf-8-sig")
    e = pd.DataFrame(etiketli)
    e.to_csv("data/psi_labeled.csv", index=False, encoding="utf-8-sig")
    t = pd.DataFrame(testler)
    print(f"{len(t)} test okundu | sonlar: {t.son.replace('', 'yazılmamış').value_counts().to_dict()}")
    print(f"{len(e)} etiketli nokta: yandı {int(e.yanar.sum())}, söndü {int((1 - e.yanar).sum())}")
    print("Yazıldı: psi_bass2_testler.csv (kontrol için), data/psi_labeled.csv (model için)")


if __name__ == "__main__":
    main()
