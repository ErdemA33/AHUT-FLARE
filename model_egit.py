#!/usr/bin/env python3
"""
Düzeltme modelini (Random Forest) eğitir ve tahmin yapar.

Kullanım:
  python model_egit.py                       # 3 hedefin hepsi için eğit + test et
  python model_egit.py --hedef sonme         # sadece biri: yayilma / sonme / sicaklik
  python model_egit.py --tahmin --g 0.38 --oksijen 21 --basinc 70 --malzeme pmma --numune thin_sheet

Kurulum: pip install pandas scikit-learn joblib

OpenFOAM motorunun fizik motoru hazır olunca: aşağıdaki motor() fonksiyonunu onunkiyle değiştir ve
MOTOR_KULLAN = True yap. Model o zaman sonucu değil, motorun hatasını öğrenir.
"""

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

# ============================== AYARLAR ==============================
VERI = Path("kullanilabilir.csv")
MODEL_KLASORU = Path("modeller")
MOTOR_KULLAN = False          # OpenFOAM motorunun motoru gelince True
AGAC_SAYISI = 300
# ======================================================================

# hedef adı: (sütun, log ölçekte mi öğrenilsin, alt sınır, üst sınır, birim)
HEDEFLER = {
    "yayilma": ("alev_yayilma_hizi_mm_s", True, 1e-3, 500, "mm/s"),
    "sonme":   ("min_oksijen_yuzde", False, 1, 100, "% O2"),
    "sicaklik": ("alev_sicakligi_k", False, 500, 3500, "K"),
}

SAYISAL = ["log_g", "oksijen_yuzde", "log_basinc", "akis_hizi_cm_s", "log_kalinlik"]
KATEGORIK = ["malzeme_sade", "numune_tipi", "yakit_turu", "akis_yonu", "seyreltici",
             "veri_turu", "yayilma_yonu"]


def motor(df):
    """OpenFOAM motorunun fizik motoru buraya gelecek. Her satır için hedefin motor tahminini döndürür.
    Şimdilik yok: None döndürür."""
    return None


def ozellik_hazirla(df):
    df = df.copy()
    for c in ["g_seviyesi", "oksijen_yuzde", "basinc_kpa", "akis_hizi_cm_s", "kalinlik_mm"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    d = pd.DataFrame(index=df.index)
    d["log_g"] = np.log10(df["g_seviyesi"].clip(lower=1e-6))          # 1e-4 ile 1 arası düzgün dağılsın
    d["oksijen_yuzde"] = df["oksijen_yuzde"]
    d["log_basinc"] = np.log10(df["basinc_kpa"].clip(lower=0.01))
    d["akis_hizi_cm_s"] = df["akis_hizi_cm_s"]
    d["log_kalinlik"] = np.log10(df["kalinlik_mm"].clip(lower=1e-4))
    for c in KATEGORIK:
        d[c] = df[c].astype("string").str.lower().fillna("bilinmiyor") if c in df else "bilinmiyor"
    return d


def model_kur():
    on_isleme = ColumnTransformer([
        ("sayi", SimpleImputer(strategy="median", add_indicator=True), SAYISAL),
        ("kat", OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=5,
                              sparse_output=False), KATEGORIK),
    ])
    rf = RandomForestRegressor(n_estimators=AGAC_SAYISI, min_samples_leaf=3, max_features=0.5,
                               n_jobs=-1, random_state=42)
    return Pipeline([("on", on_isleme), ("rf", rf)])


def veri_hazirla(df, hedef):
    sutun, log, alt, ust, _ = HEDEFLER[hedef]
    d = df[df[sutun].between(alt, ust)].copy()
    d = d.drop_duplicates(subset=["makale_id", sutun, "g_seviyesi", "oksijen_yuzde",
                                  "basinc_kpa", "malzeme_sade"])
    X = ozellik_hazirla(d)
    if hedef == "sonme":
        X["oksijen_yuzde"] = 0.0   # çoğu satırda ortam oksijeni = sönme sınırı; kopya olmasın
    y = np.log10(d[sutun]) if log else d[sutun].astype(float)
    m = motor(d) if MOTOR_KULLAN else None
    if m is not None:
        m = np.log10(np.clip(m, alt, None)) if log else np.asarray(m, float)
        y = y - m                          # model motorun hatasını öğrenir
    return d, X, y, m


def geri_cevir(tahmin, hedef, motor_tahmini=None):
    if motor_tahmini is not None:
        tahmin = tahmin + motor_tahmini
    return 10 ** tahmin if HEDEFLER[hedef][1] else tahmin


def agac_dagilimi(model, X):
    """Her ağacın ayrı tahmini -> ortalama ve yayılım (belirsizlik)."""
    Xd = model.named_steps["on"].transform(X)
    tum = np.stack([a.predict(Xd) for a in model.named_steps["rf"].estimators_])
    return tum.mean(axis=0), tum.std(axis=0)


def egit(df, hedef):
    sutun, log, *_, birim = HEDEFLER[hedef]
    d, X, y, m = veri_hazirla(df, hedef)
    gruplar = d["makale_id"]
    print(f"\n=== {hedef} ({sutun}) — {len(d)} satır, {gruplar.nunique()} makale")
    if len(d) < 50:
        print("   Çok az veri, atlandı.")
        return

    # Test: aynı makalenin satırları hem eğitimde hem testte olmasın
    kat = min(5, gruplar.nunique())
    gercek, tahmin, temel = [], [], []
    for egitim_i, test_i in GroupKFold(n_splits=kat).split(X, y, gruplar):
        mdl = model_kur().fit(X.iloc[egitim_i], y.iloc[egitim_i])
        mt = None if m is None else m[test_i]
        tahmin += list(geri_cevir(mdl.predict(X.iloc[test_i]), hedef, mt))
        temel += list(geri_cevir(np.full(len(test_i), y.iloc[egitim_i].median()), hedef, mt))
        gercek += list(d[sutun].iloc[test_i])
    gercek, tahmin, temel = map(np.array, (gercek, tahmin, temel))

    def hata(t):
        if log:   # yayılma hızında "kaç kat yanıldı" daha anlamlı
            return f"ortalama {10 ** np.mean(np.abs(np.log10(t / gercek))):.2f} kat"
        return f"ortalama ±{np.mean(np.abs(t - gercek)):.1f} {birim}"
    print(f"   Model hatası     : {hata(tahmin)}")
    print(f"   Basit tahmin     : {hata(temel)}   (hep ortanca değeri söyleseydik)")
    if not log:
        r2 = 1 - np.sum((gercek - tahmin) ** 2) / np.sum((gercek - gercek.mean()) ** 2)
        print(f"   R² (1 = mükemmel): {r2:.2f}")

    # Son model: bütün veriyle
    mdl = model_kur().fit(X, y)
    isimler = mdl.named_steps["on"].get_feature_names_out()
    onem = pd.Series(mdl.named_steps["rf"].feature_importances_, index=isimler)
    onem = onem.groupby(lambda s: s.split("__")[1].split("_bilinmiyor")[0].rsplit("_", 1)[0]
                        if s.startswith("kat__") else s.split("__")[1]).sum()
    print("   En etkili girdiler:", ", ".join(f"{k} %{v * 100:.0f}" for k, v in
                                           onem.sort_values(ascending=False).head(6).items()))

    MODEL_KLASORU.mkdir(exist_ok=True)
    joblib.dump({"model": mdl, "egitim_X": X, "hedef": hedef}, MODEL_KLASORU / f"{hedef}.joblib")
    print(f"   Kaydedildi: {MODEL_KLASORU / (hedef + '.joblib')}")


def yakin_deney_sayisi(egitim_X, satir):
    """Yerçekimi, oksijen ve basınç olarak bu koşula yakın kaç deney var?"""
    yakin = pd.Series(True, index=egitim_X.index)
    if pd.notna(satir["log_g"].iloc[0]):
        yakin &= (egitim_X["log_g"] - satir["log_g"].iloc[0]).abs() <= 0.25   # ~1.8 kat: Mars ile Dünya karışmasın
    if pd.notna(satir["oksijen_yuzde"].iloc[0]):
        yakin &= (egitim_X["oksijen_yuzde"] - satir["oksijen_yuzde"].iloc[0]).abs() <= 5
    if pd.notna(satir["log_basinc"].iloc[0]):
        yakin &= (egitim_X["log_basinc"] - satir["log_basinc"].iloc[0]).abs() <= 0.3   # ~2 kat
    return int(yakin.sum())


def tahmin_et(arg):
    satir = pd.DataFrame([{
        "g_seviyesi": arg.g, "oksijen_yuzde": arg.oksijen, "basinc_kpa": arg.basinc,
        "akis_hizi_cm_s": arg.akis, "kalinlik_mm": arg.kalinlik, "malzeme_sade": arg.malzeme,
        "numune_tipi": arg.numune, "yakit_turu": None, "akis_yonu": arg.akis_yonu,
        "seyreltici": "n2", "veri_turu": "deney", "yayilma_yonu": None}])
    X = ozellik_hazirla(satir)
    print(f"\nKoşul: g={arg.g}, O2=%{arg.oksijen}, {arg.basinc} kPa, malzeme={arg.malzeme}\n")
    for hedef, (sutun, log, *_, birim) in HEDEFLER.items():
        yol = MODEL_KLASORU / f"{hedef}.joblib"
        if not yol.exists():
            continue
        paket = joblib.load(yol)
        Xh = X.copy()
        if hedef == "sonme":
            Xh["oksijen_yuzde"] = 0.0
        ort, std = agac_dagilimi(paket["model"], Xh)
        mt = None
        if MOTOR_KULLAN and motor(satir) is not None:
            mt = np.log10(motor(satir)) if log else np.asarray(motor(satir), float)
        orta = geri_cevir(ort, hedef, mt)[0]
        alt, ust = geri_cevir(ort - std, hedef, mt)[0], geri_cevir(ort + std, hedef, mt)[0]
        n = yakin_deney_sayisi(paket["egitim_X"], X)
        guven = "yüksek" if n >= 20 else "orta" if n >= 5 else "DÜŞÜK"
        print(f"  {sutun:24}: {orta:8.2f} {birim}   (aralık {alt:.2f} – {ust:.2f})   "
              f"güven: {guven} ({n} yakın deney)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hedef", choices=list(HEDEFLER), help="sadece bu hedefi eğit")
    p.add_argument("--tahmin", action="store_true", help="eğitilmiş modelle tahmin yap")
    p.add_argument("--g", type=float, default=1.0)
    p.add_argument("--oksijen", type=float, default=21)
    p.add_argument("--basinc", type=float, default=101.3)
    p.add_argument("--akis", type=float)
    p.add_argument("--kalinlik", type=float)
    p.add_argument("--malzeme", default="pmma")
    p.add_argument("--numune", default="thin_sheet")
    p.add_argument("--akis-yonu", dest="akis_yonu")
    arg = p.parse_args()

    if arg.tahmin:
        tahmin_et(arg)
        return
    if not VERI.exists():
        sys.exit(f"{VERI} bulunamadı. Bu kodu kullanilabilir.csv ile aynı klasörde çalıştır.")
    df = pd.read_csv(VERI, low_memory=False)
    print(f"{VERI}: {len(df)} satır | motor: {'açık' if MOTOR_KULLAN else 'kapalı'}")
    for hedef in ([arg.hedef] if arg.hedef else HEDEFLER):
        egit(df, hedef)


if __name__ == "__main__":
    main()
