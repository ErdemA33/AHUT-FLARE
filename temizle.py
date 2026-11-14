#!/usr/bin/env python3
"""
veri_seti.csv'yi Gemma'yı tekrar çalıştırmadan düzeltir.

Yaptıkları:
  - Birimleri ham değerlerden (…_ham sütunları) geliştirilmiş tablolarla yeniden çevirir
    (örn. "atmosphere", "lm", "cm=s", "10^-4 g", "℃" artık tanınıyor)
  - Gemma'nın yanlışlıkla "narrow_channel" dediği platformları siler
  - 280-320 K "alev sıcaklıklarını" siler (aslında ortam sıcaklığı)
  - Yerçekimini platformdan yeniden hesaplar
  - NASA raporlarını dosya adından doğru tanır
  - Malzeme adlarını sadeleştirir (CH4, methane-air -> methane) ve yakıt türü ekler
  - Şüphe nedenlerini yeniden hesaplar

Kullanım (veri_cikar.py ile aynı klasörde):
  python temizle.py                      # ANA_KLASOR içindeki veri_seti.csv
  python temizle.py yol/veri_seti.csv    # başka bir dosya

Çıktılar (veri_seti.csv'nin yanına):
  veri_temiz.csv        -> bütün satırlar, düzeltilmiş
  kullanilabilir.csv    -> şüphesiz + alıntı olmayan + sonucu olan satırlar
"""

import re
import sys
from pathlib import Path

import pandas as pd

import veri_cikar as vc

# Ham sütun -> (çevrilmiş sütun, Gemma alan adı, çevirici)
HAM = {ham: (sutun, alan, cevir) for alan, (sutun, ham, cevir) in vc.CEVIRICILER.items()}

ESANLAMLI = {
    "ch4": "methane", "c2h4": "ethylene", "c3h8": "propane", "c2h6": "ethane",
    "h2": "hydrogen", "co": "carbon monoxide", "heptane": "n-heptane", "decane": "n-decane",
    "dodecane": "n-dodecane", "hexane": "n-hexane", "octane": "n-octane",
    "polymethylmethacrylate": "pmma", "poly methyl methacrylate": "pmma",
    "polymethyl methacrylate": "pmma", "poly(methyl methacrylate)": "pmma",
    "acrylic": "pmma", "plexiglas": "pmma", "plexiglass": "pmma",
    "polyethylene": "pe", "low density polyethylene": "ldpe", "ldpe": "ldpe",
    "polypropylene": "pp", "polystyrene": "ps", "filter paper": "paper",
    "ashless filter paper": "paper", "kimwipes": "paper", "kimwipe": "paper",
    "cellulose paper": "paper", "dimethyl ether": "dme",
}
ATILACAK_KELIMELER = r"\b(droplets?|flames?|diffusion|premixed|co-?flow|jets?|mixtures?|fuels?|" \
                     r"samples?|sheets?|films?|slabs?|rods?|cylinders?|spheres?|thin|thick)\b"

YAKIT_TURU = {"droplet": "sivi", "pool": "sivi", "gas_jet": "gaz", "particle_cloud": "toz",
              "thin_sheet": "kati", "thick_sheet": "kati", "rod": "kati", "wire": "kati",
              "fabric": "kati"}


def malzeme_sade(m):
    if not isinstance(m, str) or not m.strip():
        return None
    m = m.lower().strip()
    m = re.sub(r"\s*[-/+]\s*(air|oxygen|o2|n2|nitrogen)\b.*$", "", m)   # methane-air -> methane
    m = re.sub(r"\(.*?\)", "", m) if not m.startswith("poly(") else m
    m = re.sub(ATILACAK_KELIMELER, " ", m)
    m = re.sub(r"\s+", " ", m).strip(" -,/")
    return ESANLAMLI.get(m, m) or None


def ham_ayir(ham):
    """'2.5 cm/s' -> (2.5, 'cm/s')"""
    if not isinstance(ham, str) or not ham.strip():
        return None, None
    parca = ham.strip().split(" ", 1)
    try:
        return float(parca[0]), (parca[1] if len(parca) > 1 else "")
    except ValueError:
        return None, None


def metinde_narrow_channel(makale_id, kanit):
    txt = vc.METIN_KLASORU / f"{makale_id}.txt"
    if txt.exists():
        try:
            return "narrow channel" in vc.sadelestir(txt.read_text(encoding="utf-8"))
        except Exception:
            pass
    return "narrow" in str(kanit).lower()


def temizle(df):
    df = df.copy()
    # NASA tespiti: NTRS dosya adları sadece rakam
    df["kaynak"] = df.makale_id.astype(str).str.fullmatch(r"\d+").map({True: "nasa", False: "diger"})

    yeni_neden = []
    for i, r in df.iterrows():
        nedenler = [n for n in str(r.supheli_nedenleri).split("; ")
                    if n and n != "nan"] if isinstance(r.supheli_nedenleri, str) else []

        # 1) birimleri ham değerlerden yeniden çevir
        for ham, (sutun, alan, cevir) in HAM.items():
            v, u = ham_ayir(r.get(ham))
            if v is None:
                continue
            c = cevir(v, u)
            df.at[i, sutun] = None if c is None else round(c, 6)
            if c is not None:   # artık tanınıyorsa "birim tanınmadı" nedenini sil
                nedenler = [n for n in nedenler if not n.startswith(f"{alan}: birim tanınmadı")]

        # 2) narrow_channel düzeltmesi
        if r.platform == "narrow_channel" and not metinde_narrow_channel(r.makale_id, r.kanit):
            df.at[i, "platform"] = None

        # 3) ortam sıcaklığı alev sıcaklığı değildir
        t = df.at[i, "alev_sicakligi_k"]
        if pd.notna(t) and 280 <= t <= 320:
            df.at[i, "alev_sicakligi_k"] = None

        # 4) yerçekimi: metindeki sayı çevrilebildiyse o, yoksa platformdan
        gv, gu = ham_ayir(r.get("g_ham"))
        g_metin = vc.g_cevir(gv, gu) if gv is not None else None
        if g_metin is not None:
            df.at[i, "g_seviyesi"], df.at[i, "g_kaynagi"] = round(g_metin, 8), "metin"
        else:
            p = df.at[i, "platform"]
            g_p = vc.PLATFORM_G.get(p) if isinstance(p, str) else None
            df.at[i, "g_seviyesi"] = g_p
            df.at[i, "g_kaynagi"] = "platformdan" if g_p is not None else None

        # 5) mantık kontrolünü yeni değerlerle baştan yap
        nedenler = [n for n in nedenler if "mantıksız" not in n and " ama g=" not in n
                    and "sönme sınırı" not in n]
        s = {k: (None if pd.isna(df.at[i, k]) else df.at[i, k]) for k in
             ["oksijen_yuzde", "min_oksijen_yuzde", "basinc_kpa", "g_seviyesi", "kalinlik_mm",
              "alev_yayilma_hizi_mm_s", "alev_sicakligi_k", "akis_hizi_cm_s", "platform",
              "sondu_mu"]}
        nedenler += vc.mantik_kontrol(s)

        # mikro-g platformunda küçük bir g sayısının metinde birebir geçmemesi sorun değil
        g = s["g_seviyesi"]
        if g is not None and g < 0.01 and s["platform"] in vc.MIKRO_G_PLATFORMLAR:
            nedenler = [n for n in nedenler if not n.startswith("g_level=")]
        yeni_neden.append(nedenler)

    # 6) platformu boş satırlar: aynı makalede tek bir platform kullanılmışsa onu al
    tek = (df.dropna(subset=["platform"]).groupby("makale_id").platform
           .agg(lambda x: x.iloc[0] if x.nunique() == 1 else None).dropna())
    bos = df.platform.isna() & df.makale_id.isin(tek.index)
    df.loc[bos, "platform"] = df.loc[bos, "makale_id"].map(tek)
    g_bos = bos & df.g_seviyesi.isna()
    df.loc[g_bos, "g_seviyesi"] = df.loc[g_bos, "platform"].map(vc.PLATFORM_G)
    df.loc[g_bos & df.g_seviyesi.notna(), "g_kaynagi"] = "makaleden"

    df["supheli_nedenleri"] = ["; ".join(n) for n in yeni_neden]
    df["supheli"] = ["evet" if n else "hayir" for n in yeni_neden]
    sonuc_sutun = ["alev_yayilma_hizi_mm_s", "min_oksijen_yuzde", "alev_sicakligi_k"]
    df["sonuc_var"] = ((df[sonuc_sutun].notna().any(axis=1)) | df.sondu_mu.notna()).map(
        {True: "evet", False: "hayir"})
    df["malzeme_sade"] = df.malzeme.map(malzeme_sade)
    df["yakit_turu"] = df.numune_tipi.map(YAKIT_TURU)
    return df


def ozet(eski, yeni):
    def kul(d):
        return d[(d.supheli == "hayir") & (d.veri_turu != "alinti") & (d.sonuc_var == "evet")]
    print(f"{'':28}{'önce':>8}{'sonra':>8}")
    for ad, f in [("şüpheli", lambda d: (d.supheli == "evet").sum()),
                  ("sonucu olan", lambda d: (d.sonuc_var == "evet").sum()),
                  ("KULLANILABİLİR", lambda d: len(kul(d))),
                  ("narrow_channel", lambda d: (d.platform == "narrow_channel").sum()),
                  ("NASA satırı", lambda d: (d.kaynak == "nasa").sum())]:
        print(f"  {ad:26}{f(eski):8}{f(yeni):8}")
    k = kul(yeni)
    print(f"\nKullanılabilir satırlar: {len(k)} ({k.makale_id.nunique()} makale)")
    g = pd.cut(k.g_seviyesi, [-1, 1e-3, 0.05, 0.12, 0.25, 0.3, 0.45, 0.9, 1.1, 100],
               labels=["mikro (<0.001)", "0.001-0.05", "0.05-0.12", "Ay (0.12-0.25)", "0.25-0.3",
                       "Mars (0.3-0.45)", "0.45-0.9", "1 g", "1 g üstü"])
    print("  yerçekimi:", g.value_counts(dropna=False).to_dict())
    print("  yakıt türü:", k.yakit_turu.value_counts(dropna=False).to_dict())
    print("  sonuç türü:", {c: int(k[c].notna().sum()) for c in
                           ["alev_yayilma_hizi_mm_s", "min_oksijen_yuzde", "alev_sicakligi_k",
                            "sondu_mu"]})
    print("  en sık malzemeler:", k.malzeme_sade.value_counts().head(12).to_dict())


def main():
    girdi = Path(sys.argv[1]) if len(sys.argv) > 1 else vc.ANA_KLASOR / "veri_seti.csv"
    eski = pd.read_csv(girdi, low_memory=False)
    print(f"{girdi}: {len(eski)} satır okunuyor, temizleniyor...\n")
    yeni = temizle(eski)
    yeni.to_csv(girdi.with_name("veri_temiz.csv"), index=False, encoding="utf-8-sig")
    kul = yeni[(yeni.supheli == "hayir") & (yeni.veri_turu != "alinti") & (yeni.sonuc_var == "evet")]
    kul.to_csv(girdi.with_name("kullanilabilir.csv"), index=False, encoding="utf-8-sig")
    ozet(eski, yeni)
    print(f"\nYazıldı: {girdi.with_name('veri_temiz.csv')}  ve  {girdi.with_name('kullanilabilir.csv')}")


if __name__ == "__main__":
    main()
