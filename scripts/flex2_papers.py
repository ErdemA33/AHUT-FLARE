#!/usr/bin/env python3
"""
FLEX-2 yayın listesindeki makalelerden elle çıkarılan yanma/sönme noktaları.
Çıktı: data/psi_labeled_flex2.csv  (scripts/risk_model.py otomatik okur)

Kaynaklar (tablolar elle okundu):
  A) Shaw & Wei 2007, Combust. Sci. Tech. 10.1080/00102200601057394  (1-propanol, 0.1 MPa)
  B) Shaw & Wei 2010, Combust. Sci. Tech. 10.1080/00102202.2010.498798 Tablo 2 (n-heptane + 1-propanol, 0.1/0.3 MPa)
  C) Shaw & Wei 2012, J. Combustion 10.1155/2012/587987 Tablo 1 (metanol, 0.1 MPa)
  D) Wei & Shaw 2009, Combust. Sci. Tech. 10.1080/00102200903190851 Tablo 1 (1-propanol, O2 %21, 5 farklı inert gaz)
  E) Dzik, Nayagam & Williams 2010, ICHMT 10.1016/j.icheatmasstransfer.2009.10.006 Tablo 1 + Şekil 2 metni (n-heptane, 1 g)
  H) Takahashi ve ark. 2015, Proc. Comb. Inst. 10.1016/j.proci.2014.07.017 Tablo 3
     (0.125 mm PMMA, 101 kPa: 1 g aşağı yanma LOI ve parabolik uçuşta en düşük oksijen MLOC)
  G) Niehaus ve ark. 2015, ICES-2015-293, NTRS 20150022123 (Saffire öncesi silikon, 1 g, hava, 1 atm)
  F) Dietrich ve ark. 2014, Microgravity Sci. Tech. 10.1007/s12217-014-9372-2 (ISS FLEX, LOI = alt oksijen sınırı)

A–C: Havaya Xd oranında seyreltici gaz eklenmiş -> oksijen = 20.95 * (1 - Xd)
  Case 3 = alev kendi kendine sürdü  -> yanar
  Case 2 = sadece ateşleyici açıkken yandı, sonra söndü -> söner
  Case 1 = hiç ateşlenmedi -> söner
  µg = NASA Glenn 2.2 s düşme kulesi (g ~1e-4), damla çapı ~1 mm
"""
import pandas as pd

O2_HAVA = 20.95
MUG = 1e-4

# yakıt, seyreltici, basınç MPa, (µg: case1, case2, case3), (1g: case1, case2, case3)   None = ölçülmemiş
SHAW = [
    ("10.1080/00102202.2010.498798", "n-heptane", "he", 0.1, (.40, .30, .20), (.30, None, .20)),
    ("10.1080/00102202.2010.498798", "n-heptane", "co2", 0.1, (.40, .30, .20), (.30, .20, .10)),
    ("10.1080/00102202.2010.498798", "n-heptane", "xe", 0.1, (.85, .80, .60), (.70, .60, .30)),
    ("10.1080/00102202.2010.498798", "n-heptane", "he", 0.3, (.90, .80, .50), (.70, .50, .40)),
    # Xe 0.3 MPa 1g: case2=0.50 < case3=0.60 çelişkili -> case2 atlandı
    ("10.1080/00102202.2010.498798", "n-heptane", "xe", 0.3, (.90, .85, .70), (.70, None, .60)),
    ("10.1080/00102200601057394", "1-propanol", "he", 0.1, (.40, .30, .20), (.30, None, .20)),
    ("10.1080/00102200601057394", "1-propanol", "co2", 0.1, (.50, .40, .20), (.40, .30, .10)),
    ("10.1080/00102202.2010.498798", "1-propanol", "xe", 0.1, (.90, .80, .50), (.60, .50, .20)),
    ("10.1080/00102202.2010.498798", "1-propanol", "he", 0.3, (None, None, .50), (.50, .40, .30)),
    ("10.1080/00102202.2010.498798", "1-propanol", "co2", 0.3, (.70, .60, .50), (.60, .40, .30)),
    ("10.1155/2012/587987", "methanol", "he", 0.1, (.50, .40, .20), (.40, .30, .20)),
    ("10.1155/2012/587987", "methanol", "co2", 0.1, (.50, .40, .20), (.30, None, .20)),
    ("10.1155/2012/587987", "methanol", "xe", 0.1, (.85, .80, .50), (.80, .70, .40)),
]

# Wei & Shaw 2009: µg, O2 %21, hepsi yandı (He'de sonradan söndü ama önce yanmaya devam etti)
# basınç MPa: {gaz: (K mm2/s, ilk çap mm)}
WEI = {
    0.03: {"he": 1.32, "ar": 1.19, "xe": 1.17, "n2": 1.13, "co2": 1.20},
    0.1: {"he": 1.25, "ar": 1.18, "xe": 1.18, "n2": 1.10, "co2": 1.20},
    0.3: {"he": 1.19, "ar": 1.18, "xe": 1.20, "n2": 1.15, "co2": 1.30},
}

# Dzik 2010 Tablo 1: 1 g, O2 %21, N2 yerine CO2. (ilk çap mm, CO2 %, basınç kPa) -> hepsi yandı
DZIK = [
    (1.039, 0.0, 29), (1.174, 0.0, 100), (0.953, 0.0, 101), (0.929, 10.43, 36), (0.911, 10.67, 29),
    (1.237, 10.67, 105), (1.041, 10.91, 33), (0.937, 20.54, 36), (0.953, 20.54, 104), (1.067, 20.74, 30),
    (0.976, 20.74, 33), (0.989, 30.24, 32), (1.054, 30.24, 33), (1.139, 30.24, 105), (1.252, 39.61, 70),
    (1.054, 40.41, 68), (1.072, 44.18, 94), (0.989, 44.42, 80), (1.098, 44.42, 88), (1.067, 44.42, 102),
    (1.093, 44.54, 83), (1.131, 44.54, 91), (1.086, 45.61, 79), (1.076, 45.61, 100), (0.963, 46.14, 105),
    (1.001, 46.78, 103),
]
# Metin: "CO2 %30'a kadar ateşlenme alt sınırı ~28 kPa" -> 25 kPa'da söner
# (%46 üstü CO2 sınırı eklenmedi: modelde seyreltici ORANI özelliği yok, çelişki yaratır)
DZIK_SONER = [(1.0, 0.0, 25), (1.0, 10.0, 25), (1.0, 20.0, 25), (1.0, 30.0, 25)]


# Dietrich 2014: ISS'te 1 atm'de sürekli yanmanın olduğu en düşük oksijen (LOI), % olarak
DIETRICH_LOI = [("methanol", "n2", 12.0), ("methanol", "co2", 14.0), ("methanol", "he", 14.0),
                ("n-heptane", "n2", 15.0), ("n-heptane", "co2", 17.0), ("n-heptane", "he", 15.0)]
SINIR_PAYLARI = (1.0, 3.0)   # sınırın bu kadar üstü yanar, altı söner (risk_model ile aynı)


# Niehaus 2015: silikon levha (5x30 cm), 1 g, laboratuvar havası.
# (kalınlık mm, yayılma yönü, yanar)  — yukarı yönde kısmi yanmalar belirsiz olduğu için eklenmedi
NIEHAUS = [(1.00, "yukari", 0),                                  # ateşlenemedi
           (0.25, "asagi", 1), (0.36, "asagi", 1),               # tamamı yandı
           (0.61, "asagi", 0), (1.00, "asagi", 0),               # ateşlenemedi
           (0.25, "yatay", 1), (0.36, "yatay", 1)]               # tamamı yandı


# Takahashi 2015 ölçülen sınırlar: (seyreltici, g, sınır O2 %, karşı akış cm/s)
TAKAHASHI = [("n2", 1.0, 17.0, 0.0), ("ar", 1.0, 12.9, 0.0), ("co2", 1.0, 24.3, 0.0),   # 1 g, aşağı yanma
             ("n2", 0.01, 14.7, 10.0), ("co2", 0.01, 19.2, 2.0)]                         # parabolik uçuş


def takahashi_noktalari():
    r = []
    for gaz, g, sinir, akis in TAKAHASHI:
        for pay in SINIR_PAYLARI:
            for yon, yanar in ((+1, 1), (-1, 0)):
                r.append({"makale_id": "10.1016_j.proci.2014.07.017", "kaynak": "makale_elle",
                          "link": "https://doi.org/10.1016/j.proci.2014.07.017", "veri_turu": "deney",
                          "platform": "lab" if g == 1 else "parabolic", "g_seviyesi": g,
                          "malzeme_sade": "pmma", "numune_tipi": "thin_sheet", "yakit_turu": "kati",
                          "kalinlik_mm": 0.125, "oksijen_yuzde": sinir + yon * pay, "seyreltici": gaz,
                          "basinc_kpa": 101.0, "akis_hizi_cm_s": akis, "akis_yonu": "ters",
                          "yanar": yanar, "etiket_kaynagi": "makale_elle"})
    return r


def kati_nokta(kalinlik, yon, yanar):
    return {"makale_id": "NTRS_20150022123", "kaynak": "makale_elle",
            "link": "https://ntrs.nasa.gov/citations/20150022123", "veri_turu": "deney",
            "platform": "lab", "g_seviyesi": 1.0, "malzeme_sade": "silicone",
            "numune_tipi": "thin_sheet" if kalinlik < 0.5 else "thick_sheet", "yakit_turu": "kati",
            "kalinlik_mm": kalinlik, "oksijen_yuzde": 20.95, "seyreltici": "n2", "basinc_kpa": 101.3,
            "akis_hizi_cm_s": 0.0, "akis_yonu": {"yukari": "ayni", "asagi": "ters"}.get(yon),
            "yanar": yanar, "etiket_kaynagi": "makale_elle"}


def nokta(kaynak, yakit, seyreltici, o2, p_kpa, g, cap, yanar):
    return {"makale_id": kaynak.replace("/", "_"), "kaynak": "makale_elle", "link": "https://doi.org/" + kaynak,
            "veri_turu": "deney", "platform": "drop_tower" if g < 0.01 else "lab", "g_seviyesi": g,
            "malzeme_sade": yakit, "numune_tipi": "droplet", "yakit_turu": "sivi", "kalinlik_mm": cap,
            "oksijen_yuzde": round(o2, 2), "seyreltici": seyreltici, "basinc_kpa": p_kpa,
            "akis_hizi_cm_s": 0.0, "akis_yonu": "yok", "yanar": yanar, "etiket_kaynagi": "makale_elle"}


def main():
    r = []
    for kaynak, yakit, gaz, p, mug, bir_g in SHAW:
        for g, uclu in ((MUG, mug), (1.0, bir_g)):
            for xd, yanar in zip(uclu, (0, 0, 1)):        # case1 söner, case2 söner, case3 yanar
                if xd is not None:
                    r.append(nokta(kaynak, yakit, gaz, O2_HAVA * (1 - xd), p * 1000, g, 1.0, yanar))
    for p, gazlar in WEI.items():
        for gaz, cap in gazlar.items():
            r.append(nokta("10.1080/00102200903190851", "1-propanol", gaz, 21.0, p * 1000, MUG, cap, 1))
    for liste, yanar in ((DZIK, 1), (DZIK_SONER, 0)):
        for cap, co2, p in liste:
            r.append(nokta("10.1016/j.icheatmasstransfer.2009.10.006", "n-heptane",
                           "co2" if co2 > 0 else "n2", 21.0, p, 1.0, cap, yanar))
    for yakit, gaz, loi in DIETRICH_LOI:
        for pay in SINIR_PAYLARI:
            for yon, yanar in ((+1, 1), (-1, 0)):
                r.append(nokta("10.1007/s12217-014-9372-2", yakit, gaz, loi + yon * pay, 101.3, MUG, 3.0, yanar))
    r += [kati_nokta(*x) for x in NIEHAUS]
    r += takahashi_noktalari()
    df = pd.DataFrame(r)
    df.to_csv("data/psi_labeled_flex2.csv", index=False, encoding="utf-8-sig")
    print(f"{len(df)} nokta yazıldı: yanar {int(df.yanar.sum())}, söner {int((1 - df.yanar).sum())}")
    print(df.groupby(["malzeme_sade", "g_seviyesi"]).yanar.agg(["count", "sum"]))


if __name__ == "__main__":
    main()
