#!/usr/bin/env python3
"""
Fizik motorunu (engine.py) NASA deneyleri ve literatürle karşılaştırır, güven skoru verir.

1) Kontrol : motor her etiketli deneyde çalıştırılır. "Yandı/söndü" dediği gerçekle tutuyor mu?
             Uzay (µg), kısmi g ve 1 g için ayrı ayrı; NASA ve diğer kaynaklar ayrı ayrı.
2) Güven   : yeni bir koşul için: o bölgede kaç gerçek deney var + motor orada ne kadar tutmuş.

Kullanım:
  python engine_check.py                     # kontrol raporu + engine_check.png
  python engine_check.py --guven --g 0.38 --oksijen 30 --basinc 70 --malzeme pmma
"""
import argparse
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import engine as motor_modulu
from engine import motor

KOK = Path(__file__).resolve().parent   # yollar çalışma klasörüne değil bu dosyanın klasörüne bağlı
# YANGIN_VERI_KLASORU: yazılabilir klasör (dashboard/kurulu sürüm). Verilmişse yeniden üretilen önbellek oraya yazılır;
# paketle gelen geçerli önbellek varsa o okunur. Verilmemişse davranış eskisi gibi (bu klasör).
YAZ = Path(os.environ["YANGIN_VERI_KLASORU"]) if os.environ.get("YANGIN_VERI_KLASORU") else KOK
VERI = KOK / "data_clean.csv"
CIKTI_CSV = KOK / "engine_comparison.csv"
HAFIF_CV = KOK / "light_engine_validation_points.csv"   # hafif motorun çapraz doğrulama tahminleri
DAMLA_CV = KOK / "droplet_validation.csv"                  # damla motorunun kalibrasyon dışı tahminleri (FLEX)
CIKTI_PNG = YAZ / "engine_check.png"
PENCERE = {"oksijen": 3.0, "log_basinc": 0.3}   # "yakın deney" sınırları (aynı malzeme + aynı g bandı)
YAKIN_DENEY_TAVAN = 15     # bu kadar yakın deney varsa veri bileşeni tam puan
TEK_SINIF_CEZASI = 0.6     # yakın deneylerde hem yanan hem sönen yoksa doğruluk bununla çarpılır
EN_AZ_SINIF = 3            # AUC için her sınıftan en az bu kadar nokta


def tablo_imzasi():
    """Önbelleğin hangi motorla hesaplandığını ayırt eden (motor türü, tablo değiştirilme zamanı)."""
    if motor_modulu.MOTOR_TURU == "tablo" and motor_modulu.TABLO.exists():
        return motor_modulu.MOTOR_TURU, str(motor_modulu.TABLO.stat().st_mtime_ns)
    if motor_modulu.MOTOR_TURU in ("hafif", "yonlendirici", "damla"):
        import light_engine as light_engine
        import droplet_engine as droplet_engine
        import hashlib     # içerik özeti: dosyalar kopyalanınca / zip'ten açılınca da önbellek geçerli kalır
        dosyalar = [light_engine.PARAM_DOSYASI, HAFIF_CV]
        if motor_modulu.MOTOR_TURU != "hafif":
            dosyalar += [droplet_engine.PARAM_DOSYASI, DAMLA_CV, motor_modulu.TABLO]
        return motor_modulu.MOTOR_TURU, "|".join(hashlib.md5(x.read_bytes()).hexdigest()[:12] if x.exists()
                                                  else "yok" for x in dosyalar)
    return motor_modulu.MOTOR_TURU, "yok"


def _gecerli_mi(dosya):
    if not dosya.exists():
        return False
    try:
        b = pd.read_csv(dosya, usecols=["motor_turu", "tablo_mtime"], dtype=str, nrows=1)
    except ValueError:            # eski biçim: sütunlar yok
        return False
    return len(b) == 1 and (b.motor_turu.iloc[0], b.tablo_mtime.iloc[0]) == tablo_imzasi()


def onbellek_gecerli():
    """Paketle gelen (KOK) ya da yazılabilir klasördeki (YAZ) önbellekten geçerli olanı CIKTI_CSV yapar."""
    global CIKTI_CSV
    for aday in dict.fromkeys([KOK / "engine_comparison.csv", YAZ / "engine_comparison.csv"]):
        if _gecerli_mi(aday):
            CIKTI_CSV = aday
            return True
    return False


def etiketli():
    sys.argv, eski = [sys.argv[0]], sys.argv
    import risk_model as r
    sys.argv = eski
    df = r.etiketli_veri(pd.read_csv(VERI, low_memory=False) if VERI.exists() else pd.DataFrame())
    return df.reset_index(drop=True)


def hafif_cv_ekle(df):
    """Hafif motor NASA/elle noktalarıyla kalibre edildi; bu noktalarda güven skoru için motorun kendi
    tahmini değil, light_engine.py --dogrula'nın çapraz doğrulama (deney ailesi dışarıda) tahmini kullanılır.
    Eşleştirme: (makale_id, makale içindeki sıra) + oksijen/yanar kontrolü. Diğer satırlarda NaN."""
    df["motor_yanma_cv"] = np.nan
    if motor_modulu.MOTOR_TURU not in ("hafif", "yonlendirici") or not HAFIF_CV.exists():
        return df
    cv = pd.read_csv(HAFIF_CV)
    nasa = df[df.etiket_kaynagi.isin(["psi", "makale_elle"])].copy()
    if "motor_kaynagi" in df:              # yönlendirici: sadece hafif motora giden satırlar
        nasa = nasa[nasa.motor_kaynagi.eq("hafif")]
    nasa["_sira"] = nasa.groupby("makale_id").cumcount()
    cv["_sira"] = cv.groupby("makale_id").cumcount()
    b = nasa.reset_index().merge(cv[["makale_id", "_sira", "oksijen_yuzde", "yanar", "hafif"]],
                                 on=["makale_id", "_sira"], suffixes=("", "_cv"))
    b = b[np.isclose(b.oksijen_yuzde, b.oksijen_yuzde_cv, equal_nan=True) & (b.yanar == b.yanar_cv)]
    df.loc[b["index"], "motor_yanma_cv"] = b.hafif.to_numpy()
    if motor_modulu.MOTOR_TURU == "yonlendirici" and DAMLA_CV.exists() and "motor_kaynagi" in df:
        # damla motoru FLEX ile kalibre edildi: FLEX satırlarında kalibrasyonda görmediği modelin tahmini
        # (CO2/He testleri: N2 ile kalibre model; N2 testleri: o yakıt dışarıda bırakılarak kalibre model)
        dv = pd.read_csv(DAMLA_CV)
        dv["tahmin"] = np.where(dv.seyreltici.eq("n2"), dv.hizli_yakitdisarida_yanma, dv.hizli_n2kal_yanma)
        es = dict(zip("PSI-69_" + dv.test.astype(int).astype(str), dv.tahmin))
        mk = df.motor_kaynagi.eq("damla") & df.makale_id.astype(str).isin(es)
        df.loc[mk, "motor_yanma_cv"] = df.loc[mk, "makale_id"].astype(str).map(es)
    return df


def motoru_calistir(df):
    sayi = lambda v: None if pd.isna(v) else float(v)
    satirlar = []
    for _, x in df.iterrows():
        try:
            m = motor(sayi(x.get("g_seviyesi")), sayi(x.get("oksijen_yuzde")), sayi(x.get("basinc_kpa")),
                      sayi(x.get("akis_hizi_cm_s")), sayi(x.get("kalinlik_mm")),
                      None if pd.isna(x.get("malzeme_sade")) else str(x.get("malzeme_sade")),
                      None if pd.isna(x.get("numune_tipi")) else str(x.get("numune_tipi")),
                      seyreltici=None if pd.isna(x.get("seyreltici")) else str(x.get("seyreltici")),
                      yakit_turu=None if pd.isna(x.get("yakit_turu")) else str(x.get("yakit_turu"))) or {}
        except Exception:
            m = {}
        satirlar.append({f"motor_{k}": m.get(k) for k in ("yanma", "min_oksijen", "yayilma_hizi", "mesafe")})
        satirlar[-1]["motor_kaynagi"] = m.get("motor_kaynagi")
        satirlar[-1]["motor_yakit_turu"] = m.get("yakit_turu")
    out = pd.DataFrame(satirlar, index=df.index)
    for c in ("motor_yanma", "motor_min_oksijen", "motor_yayilma_hizi", "motor_mesafe"):
        out[c] = out[c].astype(float)
    return out


def g_bandi(g):
    if pd.isna(g):
        return "bilinmiyor"
    return "uzay (µg)" if g < 0.01 else ("kısmi g (Ay/Mars)" if g < 0.9 else "Dünya (1 g)")


def ozet(alt, ad):
    from sklearn.metrics import roc_auc_score
    a = alt.dropna(subset=["motor_yanma"])
    if a.empty:
        return None
    dogru = ((a.motor_yanma > 0.5).astype(int) == a.yanar).mean()
    auc = roc_auc_score(a.yanar, a.motor_yanma) if a.yanar.nunique() == 2 else float("nan")
    return {"grup": ad, "nokta": len(a), "dogruluk": dogru, "auc": auc}


def kontrol():
    df = etiketli()
    df = hafif_cv_ekle(pd.concat([df, motoru_calistir(df)], axis=1))
    df["g_bandi"] = df.g_seviyesi.map(g_bandi)
    df["nasa"] = df.etiket_kaynagi.isin(["psi", "makale_elle"])
    df["motor_turu"], df["tablo_mtime"] = tablo_imzasi()
    global CIKTI_CSV
    CIKTI_CSV = YAZ / "engine_comparison.csv"
    YAZ.mkdir(parents=True, exist_ok=True)
    df.to_csv(CIKTI_CSV, index=False, encoding="utf-8-sig")

    print(f"Motor: {motor_modulu.MOTOR_TURU.upper()} | {df.motor_yanma.notna().sum()}/{len(df)} noktada sonuç verdi\n")
    satirlar = [ozet(df, "HEPSİ"), ozet(df[df.nasa], "NASA + elle (güvenilir)")]
    satirlar += [ozet(df[df.g_bandi == b], b) for b in ("uzay (µg)", "kısmi g (Ay/Mars)", "Dünya (1 g)")]
    satirlar += [ozet(df[df.nasa & (df.g_bandi == "uzay (µg)")], "NASA, sadece uzay")]
    if df.motor_yanma_cv.notna().any():
        cvd = df[df.motor_yanma_cv.notna()].drop(columns="motor_yanma").rename(columns={"motor_yanma_cv": "motor_yanma"})
        satirlar += [ozet(cvd, "NASA + elle (çapraz doğr.)")]
    if "motor_yakit_turu" in df:
        for tt, ad in (("kati", "katı"), ("sivi", "sıvı"), ("gaz", "gaz")):
            satirlar += [ozet(df[df.motor_yakit_turu.eq(tt)], f"yakıt: {ad}")]
            if df.motor_yanma_cv.notna().any():
                c = df[df.motor_yakit_turu.eq(tt) & df.motor_yanma_cv.notna()]
                c = c.drop(columns="motor_yanma").rename(columns={"motor_yanma_cv": "motor_yanma"})
                satirlar += [ozet(c, f"yakıt: {ad} (dürüst)")]
    t = pd.DataFrame([s for s in satirlar if s])
    print("Motorun yandı/söndü tahmini gerçekle ne kadar tutuyor:")
    for _, s in t.iterrows():
        print(f"  {s.grup:26s} {s.nokta:5d} nokta | doğruluk %{100 * s.dogruluk:.0f} | AUC {s.auc:.2f}")

    h = df.dropna(subset=["motor_yayilma_hizi", "alev_yayilma_hizi_mm_s"]) if "alev_yayilma_hizi_mm_s" in df else []
    h = h[(h.alev_yayilma_hizi_mm_s > 0) & (h.motor_yayilma_hizi > 0)] if len(h) else h
    if len(h):
        kat = 10 ** np.abs(np.log10(h.motor_yayilma_hizi / h.alev_yayilma_hizi_mm_s))
        print(f"\nAlev yayılma hızı ({len(h)} ölçüm): motor ortalama {np.median(kat):.1f} kat yanılıyor "
              f"(1 = tam doğru); %{100 * (kat < 2).mean():.0f}'inde 2 kattan az hata")
    grafik(t)
    print(f"\nKaydedildi: {CIKTI_CSV}, {CIKTI_PNG}")


def grafik(t):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.barh(t.grup[::-1], 100 * t.dogruluk[::-1], color="#1565C0")
    for i, (d, n) in enumerate(zip(100 * t.dogruluk[::-1], t.nokta[::-1])):
        ax.text(d + 1, i, f"%{d:.0f}  ({n} nokta)", va="center", fontsize=9)
    ax.set_xlim(0, 110)
    ax.set_xlabel("Motorun yandı/söndü tahmininin doğruluğu (%)")
    ax.set_title(f"Fizik motoru – gerçek deneylerle karşılaştırma ({motor_modulu.MOTOR_TURU} motor)")
    fig.tight_layout()
    fig.savefig(CIKTI_PNG, dpi=130)


def yaz(v, bicim=".2f", birim=""):
    """None / NaN değerleri 'yok' olarak yazar."""
    return "yok" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:{bicim}}{birim}"


def yakin_maske(k, g, oksijen, basinc, malzeme):
    """"Yakın deney" tanımı (güven skoru ve tahmin.yakin_deneyler aynı tanımı kullanır):
    aynı ana malzeme (malzeme_ana) + aynı g bandı + |ΔO2| <= PENCERE["oksijen"]
    + |Δlog10 basınç| <= PENCERE["log_basinc"] (basıncı bilinmeyen deney basınçtan elenmez)."""
    from risk_model import malzeme_ana
    lp = np.log10(k.basinc_kpa.clip(lower=1))
    adlar = k.malzeme_sade.astype(str)
    ana = adlar.map({a: malzeme_ana(a) for a in adlar.unique()})
    return ((ana == malzeme_ana(str(malzeme)))
            & (k.g_seviyesi.map(g_bandi) == g_bandi(g))
            & ((k.oksijen_yuzde - oksijen).abs() <= PENCERE["oksijen"])
            & (lp.isna() | ((lp - math.log10(max(basinc, 1))).abs() <= PENCERE["log_basinc"])))


def guven_skoru(g, oksijen, basinc, malzeme, motor_sonucu, karsilastirma=None, p_model=None):
    """0-100 = 100 × (0.4 × veri + 0.3 × uyum + 0.3 × motor).
    veri : aynı malzemeden yakın deney sayısı / 15 (en fazla 1)
    uyum : 1 - |yakın deneylerin yanma oranı - modelin yanma ihtimali (p_model)|.
           Yakın deney yoksa (ya da p_model verilmediyse) hesaplanmaz, ağırlığı veriye geçer:
           100 × (0.7 × veri + 0.3 × motor).
    motor: motorun sonuç verdiği yakın deneylerde, rastgeleden ne kadar iyi olduğu (0 = yazı tura, 1 = mükemmel):
           iki sınıf da >=3 ise max(0, 2(AUC-0.5)), yoksa 0.6 × max(0, 2(doğruluk-0.5));
           motor bu koşulda sonuç vermiyorsa 0.
    Malzemeler malzeme_ana() ile eşleştirilir. g üç banda ayrılır (g_bandi: uzay < 0.01, kısmi 0.01-0.9,
    Dünya >= 0.9); yakın deney sadece sorguyla aynı bantta sayılır, log g penceresi yok."""
    from sklearn.metrics import roc_auc_score
    k = karsilastirma if karsilastirma is not None else pd.read_csv(CIKTI_CSV, low_memory=False)
    yakin = k[yakin_maske(k, g, oksijen, basinc, malzeme)]
    veri = min(1.0, len(yakin) / YAKIN_DENEY_TAVAN)

    etiketli = yakin.yanar.dropna()
    yanma_orani = float(etiketli.mean()) if len(etiketli) else None
    if yanma_orani is None or p_model is None:
        uyum = None
    else:
        uyum = 1.0 - abs(yanma_orani - float(p_model))

    y = yakin.dropna(subset=["motor_yanma"]).copy()
    cv_var = "motor_yanma_cv" in y and y.motor_yanma_cv.notna().any()
    if cv_var:      # hafif motor: kalibrasyon noktalarında çapraz doğrulama tahmini
        y["motor_yanma"] = y.motor_yanma_cv.fillna(y.motor_yanma)
    cv_not = f", {int(y.motor_yanma_cv.notna().sum())} noktada çapraz doğrulama tahmini" if cv_var else ""
    yanan, sonen = int((y.yanar == 1).sum()), int((y.yanar == 0).sum())
    motor_biliyor = motor_sonucu.get("yanma") is not None
    if not motor_biliyor:
        motor_basari, yontem = 0.0, "motor bu koşulu bilmiyor"
    elif len(y) == 0:
        motor_basari, yontem = 0.0, "ölçülemedi (motorun sonuç verdiği yakın deney yok)"
    elif yanan >= EN_AZ_SINIF and sonen >= EN_AZ_SINIF:
        auc = float(roc_auc_score(y.yanar, y.motor_yanma))
        motor_basari, yontem = max(0.0, 2 * (auc - 0.5)), f"max(0, 2(AUC-0.5)), AUC {auc:.2f}{cv_not}"
    else:
        dogru = float(((y.motor_yanma > 0.5).astype(int) == y.yanar).mean())
        motor_basari = TEK_SINIF_CEZASI * max(0.0, 2 * (dogru - 0.5))
        yontem = (f"bir sınıfta <{EN_AZ_SINIF} nokta: {TEK_SINIF_CEZASI} × max(0, 2(doğruluk-0.5)), "
                  f"doğruluk {dogru:.2f}{cv_not}")
    if uyum is None:
        agirlik = {"veri": 0.7, "uyum": 0.0, "motor": 0.3}
        skor = 100 * (0.7 * veri + 0.3 * motor_basari)
    else:
        agirlik = {"veri": 0.4, "uyum": 0.3, "motor": 0.3}
        skor = 100 * (0.4 * veri + 0.3 * uyum + 0.3 * motor_basari)
    return {"guven": round(skor), "yakin_deney": len(yakin), "veri_bileseni": veri,
            "uyum_bileseni": uyum, "yanma_orani": yanma_orani, "agirliklar": agirlik,
            "motorlu_yakin": len(y), "yanan": yanan, "sonen": sonen,
            "motor_basari": motor_basari, "motor_yontem": yontem}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--guven", action="store_true")
    p.add_argument("--g", type=float, default=0.38)
    p.add_argument("--oksijen", type=float, default=30)
    p.add_argument("--basinc", type=float, default=70)
    p.add_argument("--akis", type=float, default=0)
    p.add_argument("--kalinlik", type=float, default=0.2)
    p.add_argument("--malzeme", default="pmma")
    a = p.parse_args()
    if not a.guven:
        kontrol()
        return
    if not onbellek_gecerli():
        print(f"{CIKTI_CSV} yok ya da başka bir motorla/tabloyla hesaplanmış -> kontrol yeniden çalışıyor\n")
        kontrol()
        print()
    m = motor(a.g, a.oksijen, a.basinc, a.akis, a.kalinlik, a.malzeme, None) or {}
    import predict as tahmin_modulu        # döngüsel içe aktarmayı önlemek için burada
    p = tahmin_modulu.tahmin(a.malzeme, a.oksijen, a.basinc, a.g, akis=a.akis,
                             kalinlik=a.kalinlik)["yanma_ihtimali"]
    gv = guven_skoru(a.g, a.oksijen, a.basinc, a.malzeme, m, p_model=p)
    print(f"Koşul: g {a.g:g}, O2 %{a.oksijen:g}, {a.basinc:g} kPa, akış {a.akis:g} cm/s, "
          f"kalınlık {a.kalinlik:g} mm, {a.malzeme}")
    if m.get("yanma") is None:
        print(f"Motor ({motor_modulu.MOTOR_TURU}): motor bu koşulu bilmiyor")
    else:
        print(f"Motor ({motor_modulu.MOTOR_TURU}): yanma {yaz(m.get('yanma'))}, "
              f"sınır {yaz(m.get('min_oksijen'), '.1f', ' %')}, yayılma {yaz(m.get('yayilma_hizi'), '.2f', ' mm/s')}, "
              f"sıcaklık {yaz(m.get('sicaklik'), '.0f', ' K')}"
              + (f", tabloya uzaklık {yaz(m.get('mesafe'))}" if motor_modulu.MOTOR_TURU == "tablo" else ""))
    w = gv["agirliklar"]
    if gv["uyum_bileseni"] is None:
        print(f"Güven skoru: {gv['guven']}/100 = 100 × ({w['veri']} × {gv['veri_bileseni']:.2f} + "
              f"{w['motor']} × {gv['motor_basari']:.2f})   [yakın deney yok -> uyum hesaplanmadı]")
    else:
        print(f"Güven skoru: {gv['guven']}/100 = 100 × ({w['veri']} × {gv['veri_bileseni']:.2f} + "
              f"{w['uyum']} × {gv['uyum_bileseni']:.2f} + {w['motor']} × {gv['motor_basari']:.2f})")
    print(f"  veri bileşeni : {gv['veri_bileseni']:.2f}  (aynı ana malzemeden yakın deney {gv['yakin_deney']} / "
          f"{YAKIN_DENEY_TAVAN})")
    if gv["uyum_bileseni"] is not None:
        print(f"  uyum bileşeni : {gv['uyum_bileseni']:.2f}  (yakın deneylerde yanma oranı {gv['yanma_orani']:.2f}, "
              f"model {p:.3f})")
    print(f"  motor bileşeni: {gv['motor_basari']:.2f}  [{gv['motor_yontem']}]  "
          f"(motorun sonuç verdiği yakın deney {gv['motorlu_yakin']}: {gv['yanan']} yanan / {gv['sonen']} sönen)")


if __name__ == "__main__":
    main()
