#!/usr/bin/env python3
"""
NASA PSI BASS (PSI-26) test kaydını (BASS_test_matrix.xlsx) okur ve risk modeli için
"yandı / söndü" etiketli noktalara çevirir.

Kullanılan sütunlar: material, Air display (akış, cm/s), O2 % by volume, pressure (atm),
Test Observations (ne olduğu, serbest yazı).

Etiket kuralları (notlardan):
  - listelenen her akışta alev yandıysa                 -> yandı
  - "fan/akış kapatılınca söndü"                        -> akış 0'da söndü (durgun hava)
  - "ateşleyici kapanınca alev öldü" (kendi kendine yanamadı) -> söndü
  - hiç tutuşmama kullanılmaz: notlara göre çoğu ateşleyici arızası
  - N2 ile söndürme testleri: N2 ortamı değiştirdiği için söndü noktası eklenmez

Kullanım:
  python psi_bass1.py BASS_test_matrix.xlsx
Çıktılar:
  psi_bass1_testler.csv      -> her test, okunan değerlerle (elle kontrol için)
  psi_etiketli_bass1.csv     -> risk_modeli.py'nin kullanacağı noktalar
"""

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

KAYNAK_NOTU = "NASA PSI-26 (BASS) – BASS_test_matrix.xlsx"


def baslik_bul(ham):
    for i in range(min(15, len(ham))):
        satir = " ".join(str(x).lower() for x in ham.iloc[i].tolist())
        if "material" in satir and "air display" in satir:
            return i
    raise SystemExit("Başlık satırı bulunamadı (material / Air display).")


def sutun(df, *kelimeler):
    for c in df.columns:
        if all(k in str(c).lower() for k in kelimeler):
            return c
    return None


def malzeme_oku(m):
    t = str(m).lower()
    if any(k in t for k in ("candle", "wax", "paraffin", "parrafin")):
        return None, None, np.nan                  # mum: kapsam dışı
    cap = re.search(r"(\d+(?:\.\d+)?)\s*cm", t)
    boy = float(cap.group(1)) * 10 if cap else np.nan
    if "sibal" in t:
        return "cotton-fiberglass (sibal)", "fabric", np.nan
    if "nomex" in t:
        return "nomex", "fabric", np.nan
    if "ultem" in t:
        return "ultem", "thin_sheet", np.nan
    if "sphere" in t:
        return "pmma", "sphere", boy
    if "slab" in t:
        return "pmma", "thick_sheet", np.nan
    if "pmma" in t:
        return "pmma", "thin_sheet", np.nan
    return t.strip() or None, "other", np.nan


def akislar(hava):
    """'10, 5'  '6, 3-2, 1-0'  '10,2-3'  -> sayılar; aralıklar ortalanır, '?' olanlar atılır."""
    t = str(hava).lower()
    if t in ("nan", ""):
        return []
    sonuc = []
    for parca in re.split(r"[,;>]", t):
        if "?" in parca:
            continue
        sayilar = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", parca)]
        if sayilar:
            sonuc.append(round(sum(sayilar) / len(sayilar), 2))
    return [a for a in sonuc if a <= 50]


def sonuc_oku(not_):
    t = str(not_).lower()
    n2 = bool(re.search(r"n2[^.]*(extinguish|out)|(extinguish|out)[^.]*n2", t))
    # Sadece "tutuştu ama kendi kendine söndü" sayılır. Hiç tutuşmama çoğu zaman ateşleyici
    # arızasıdır (notlarda "broke igniter", "igniter failed" geçiyor), malzemeyle ilgisi yok.
    tutusmadi = bool(re.search(r"died when igniter|burned for only|would not stay lit|"
                               r"re-ignition attempts failed", t))
    durgun_sondu = bool(re.search(
        r"(extinguish|went out|goes out|go out|\bout\b)[^.]*(fan off|flow off|air off|flow stops|"
        r"turned off|fan goes|fan to)|(fan off|flow off|air off|turned off the flow|"
        r"turned off flow|all flow stops)[^.]*(extinguish|out)", t))
    return {"n2": n2, "tutusmadi": tutusmadi, "durgun_sondu": durgun_sondu}


def main():
    girdi = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("BASS_test_matrix.xlsx")
    ham = pd.read_excel(girdi, header=None)
    b = baslik_bul(ham)
    df = ham.iloc[b + 1:].copy()
    df.columns = [str(c).strip() for c in ham.iloc[b].tolist()]
    df = df.dropna(how="all")

    c_mal, c_hava = sutun(df, "material"), sutun(df, "air display")
    c_o2, c_p = sutun(df, "o2", "volume"), sutun(df, "pressure")
    c_not, c_test = sutun(df, "observation"), sutun(df, "as run")

    testler, etiketli = [], []
    for _, r in df.iterrows():
        malzeme, numune, boy = malzeme_oku(r[c_mal])
        if malzeme is None:
            continue
        o2 = pd.to_numeric(r[c_o2], errors="coerce")
        o2 = o2 * 100 if pd.notna(o2) and o2 <= 1 else o2
        p = pd.to_numeric(r[c_p], errors="coerce")
        p = p * 101.325 if pd.notna(p) and p < 5 else np.nan
        ak = akislar(r[c_hava])
        s = sonuc_oku(r[c_not])
        test_id = f"PSI-26_{r[c_test]}"
        testler.append({"test": r[c_test], "malzeme_ham": r[c_mal], "malzeme_sade": malzeme,
                        "numune_tipi": numune, "boyut_mm": boy, "oksijen_yuzde": o2,
                        "basinc_kpa": p, "hava_ham": r[c_hava], "akislar": ak, **s,
                        "not": str(r[c_not])[:200]})
        if pd.isna(o2) or not (10 <= o2 <= 30):
            continue

        noktalar = []
        if s["tutusmadi"]:
            noktalar += [(a, 0) for a in (ak[:1] or [np.nan])]
        else:
            noktalar += [(a, 1) for a in ak if a > 0]
            if s["durgun_sondu"] and not s["n2"]:
                noktalar.append((0.0, 0))
        for a, yanar in noktalar:
            etiketli.append({
                "makale_id": test_id, "kaynak": "nasa_psi", "link": KAYNAK_NOTU,
                "veri_turu": "deney", "platform": "ISS", "g_seviyesi": 1e-4,
                "malzeme_sade": malzeme, "numune_tipi": numune, "yakit_turu": "kati",
                "kalinlik_mm": boy, "oksijen_yuzde": round(o2, 2), "seyreltici": "n2",
                "basinc_kpa": round(p, 1) if pd.notna(p) else 101.3, "akis_hizi_cm_s": a,
                "akis_yonu": None, "yanar": yanar, "etiket_kaynagi": "psi"})

    t, e = pd.DataFrame(testler), pd.DataFrame(etiketli)
    t.to_csv("psi_bass1_testler.csv", index=False, encoding="utf-8-sig")
    e.to_csv("psi_etiketli_bass1.csv", index=False, encoding="utf-8-sig")
    print(f"{len(t)} test okundu (mumlar hariç) | tutuşmadı: {int(t.tutusmadi.sum())} | "
          f"akış kesilince söndü: {int(t.durgun_sondu.sum())} | N2 ile söndürme: {int(t.n2.sum())}")
    print(f"{len(e)} etiketli nokta: yandı {int(e.yanar.sum())}, söndü {int((1 - e.yanar).sum())}")
    print("Yazıldı: psi_bass1_testler.csv (kontrol için), psi_etiketli_bass1.csv (model için)")


if __name__ == "__main__":
    main()
