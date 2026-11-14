#!/usr/bin/env python3
"""
"Yanar mı, söner mi?" modeli + yangın risk seviyesi + yanabilirlik haritası.

Fizik kuralları modele zorla öğretiliyor:
  - oksijen artınca yanma ihtimali AZALMAZ
  - basınç artınca yanma ihtimali AZALMAZ

Kullanım:
  python risk_modeli.py                                   # eğit + test et
  python risk_modeli.py --risk --g 0.38 --oksijen 21 --basinc 70 --malzeme pmma
  python risk_modeli.py --harita --malzeme pmma --basinc 70      # PNG harita çizer

Kurulum: pip install pandas scikit-learn joblib matplotlib
Girdi: veri_temiz.csv (temizle.py'nin çıktısı), bu kodla aynı klasörde.
"""

import argparse
import re
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import GroupKFold

# ============================== AYARLAR ==============================
_KOK = Path(__file__).resolve().parent   # yollar çalışma klasörüne değil bu dosyanın klasörüne bağlı
VERI = _KOK / "veri_temiz.csv"
MODEL_DOSYASI = _KOK / "modeller" / "risk.joblib"
MODEL_SAYISI = 15             # belirsizlik için kaç model birlikte eğitilsin
SINIR_PAYLARI = [1.0, 3.0]    # sönme sınırının kaç % O2 üstü "yanar", altı "söner" sayılsın
GEMMA3_DOSYASI = _KOK / "etiketli_gemma3.csv"   # veri_cikar3.py çıktısı; varsa eski Gemma verisi yerine kullanılır
PSI_DOSYALARI = "psi_etiketli*.csv"   # varsa NASA PSI deney noktaları eklenir (BASS, BASS-II ...)
PSI_AGIRLIK = 3.0             # PSI noktaları makalelerden 3 kat daha güvenilir sayılır
SONDU_MU_KULLAN = False       # Gemma'nın "söndü mü" etiketleri çok gürültülü (testte yazı-tura); kapalı
MOTOR_GIRDI = False           # True: fizik motorunun (motor.py) sonuçları modele ek girdi olarak verilir
MALZEME_BIRLESTIR = False     # True: malzeme adları malzeme_ana() ile ana gruplara birleştirilir (ESANLAMLI yerine)
G_ALT_SINIR = 1e-4            # bunun altındaki g (0 dahil) = 1e-4: bütün uzay deneyleri tek bant
# risk seviyeleri: yanma ihtimali (%)
RISK = [(20, "DÜŞÜK"), (50, "ORTA"), (80, "YÜKSEK"), (101, "ÇOK YÜKSEK")]
# ======================================================================

SAYISAL = ["log_g", "oksijen_yuzde", "log_basinc", "akis_hizi_cm_s", "log_kalinlik"]
KATEGORIK = ["malzeme_sade", "numune_tipi", "yakit_turu", "akis_yonu", "seyreltici"]
# fizik kuralları: +1 = artınca yanma ihtimali azalmaz, 0 = kural yok
# Gemma'nın sönme sınırı temizliği
SINIR_ARALIGI = (5, 50)         # bu aralık dışındaki "en düşük oksijen" değerleri büyük ihtimalle yanlış okuma
ORTAM_KOPYASINI_AT = True       # sınır = ortamdaki oksijen ise Gemma ortam değerini kopyalamış demektir
KURAL = {"oksijen_yuzde": 1, "log_basinc": 1, "motor_yanma": 1, "motor_pay": 1}
MOTOR_SUTUNLARI = ["motor_yanma", "motor_pay"]   # motorun yanma ihtimali, oksijen - motorun sönme sınırı
if MOTOR_GIRDI:
    SAYISAL = SAYISAL + MOTOR_SUTUNLARI


def motor_ozellikleri(df):
    """Her satır için motor.py'yi çalıştırır (OpenFOAM tablosu ya da sentetik motor)."""
    from motor import motor
    sayi = lambda v: None if pd.isna(v) else float(v)
    yanma, pay = [], []
    for _, x in df.iterrows():
        try:
            m = motor(sayi(x.get("g_seviyesi")), sayi(x.get("oksijen_yuzde")), sayi(x.get("basinc_kpa")),
                      sayi(x.get("akis_hizi_cm_s")), sayi(x.get("kalinlik_mm")),
                      None if pd.isna(x.get("malzeme_sade")) else str(x.get("malzeme_sade")),
                      None if pd.isna(x.get("numune_tipi")) else str(x.get("numune_tipi"))) or {}
        except Exception:
            m = {}
        yanma.append(m.get("yanma"))
        o2 = sayi(x.get("oksijen_yuzde"))
        pay.append(o2 - m["min_oksijen"] if m.get("min_oksijen") is not None and o2 is not None else None)
    return pd.DataFrame({"motor_yanma": yanma, "motor_pay": pay}, index=df.index).astype(float)


# --------------------------------------------------------------- veri
def etiketli_veri(df):
    """Her satıra 'yandı (1) / söndü (0)' etiketi verir.
    1) sondu_mu sütunu     2) alev yayıldıysa: yandı
    3) sönme sınırı biliniyorsa: sınırın biraz üstü yandı, biraz altı söndü (yapay nokta)"""
    if GEMMA3_DOSYASI.exists():
        v = pd.read_csv(GEMMA3_DOSYASI, low_memory=False)
        print(f"  Gemma verisi: {GEMMA3_DOSYASI} ({len(v)} nokta, yeni betik)")
        return psi_ekle(v)
    df = df[(df.supheli == "hayir") & (df.veri_turu != "alinti")].copy()
    parcalar = []

    if SONDU_MU_KULLAN:
        a = df[df.sondu_mu.isin(["evet", "hayir"])].copy()
        a["yanar"] = (a.sondu_mu == "hayir").astype(int)
        a["etiket_kaynagi"] = "sondu_mu"
        parcalar.append(a)

    b = df[df.alev_yayilma_hizi_mm_s.notna() & df.sondu_mu.isna()].copy()
    b["yanar"] = 1
    b["etiket_kaynagi"] = "yayilma_hizi"
    parcalar.append(b)

    s = df[df.min_oksijen_yuzde.between(*SINIR_ARALIGI)]
    if ORTAM_KOPYASINI_AT:
        s = s[s.min_oksijen_yuzde.round(1) != s.oksijen_yuzde.round(1)]
    for pay in SINIR_PAYLARI:
        for yon, etiket in ((+1, 1), (-1, 0)):
            c = s.copy()
            c["oksijen_yuzde"] = (c.min_oksijen_yuzde + yon * pay).clip(0.5, 100)
            c["yanar"] = etiket
            c["etiket_kaynagi"] = "sonme_siniri"
            parcalar.append(c)

    v = pd.concat(parcalar, ignore_index=True)
    v = v[v.oksijen_yuzde.notna() | (v.etiket_kaynagi != "sonme_siniri")]
    return psi_ekle(v)


def psi_ekle(v):
    v = v.copy()
    v["agirlik"] = 1.0
    for dosya in sorted(_KOK.glob(PSI_DOSYALARI)):
        psi = pd.read_csv(dosya)
        psi["agirlik"] = PSI_AGIRLIK
        v = pd.concat([v, psi], ignore_index=True)
        print(f"  + {len(psi)} NASA PSI noktası eklendi ({dosya.name})")
    return v


# Aynı şeyin farklı yazılışlarını birleştir (ör. "helium" = "he")
ESANLAMLI = {
    "seyreltici": {"nitrogen": "n2", "air": "n2", "still air": "n2", "helium": "he", "argon": "ar",
                   "carbon dioxide": "co2", "xenon": "xe"},
    "malzeme_sade": {"heptane": "n-heptane", "propanol": "1-propanol", "n-propanol": "1-propanol"},
}


# malzeme_ana(): sıra önemli, ilk eşleşen kazanır. Anahtarın önünde harf olmamalı
# ("polyethylene" -> ethylene, "methanol" -> ethanol, "hexadecane" -> decane olmasın diye).
MALZEME_ANAHTARLARI = [
    (("pmma", "polymethylmethacrylate", "polymethyl methacrylate"), "pmma"),
    (("polyethylene", "ldpe", "hdpe"), "polyethylene"),
    (("polypropylene",), "polypropylene"),
    (("polystyrene",), "polystyrene"),
    (("methane",), "methane"),
    (("ethylene",), "ethylene"),
    (("propane",), "propane"),
    (("n-heptane", "heptane"), "n-heptane"),
    (("decane",), "n-decane"),
    (("methanol",), "methanol"),
    (("ethanol",), "ethanol"),
    (("propanol",), "1-propanol"),
    (("cotton", "sibal"), "cotton"),          # sibal / fiberglass geçiyorsa -> sibal (aşağıda)
    (("nomex",), "nomex"),
    (("silicone",), "silicone"),
    (("paper", "cellulos", "filter"), "cellulose"),
]
_MALZEME_DESENLERI = [(re.compile("|".join(rf"(?<![a-z]){re.escape(a)}" for a in anahtarlar)), ana)
                      for anahtarlar, ana in MALZEME_ANAHTARLARI]


def malzeme_ana(ad):
    """Malzeme adını ana gruba indirger (ör. 'cast pmma' -> 'pmma'); eşleşme yoksa adı aynen döndürür."""
    if ad is None or (not isinstance(ad, str) and pd.isna(ad)):
        return ad
    a = str(ad).lower().strip()
    for desen, ana in _MALZEME_DESENLERI:
        if desen.search(a):
            if ana == "cotton" and ("sibal" in a or "fiberglass" in a):
                return "sibal"
            return ana
    return a


def kategori_degeri(df, c):
    if c not in df:
        return pd.Series(pd.NA, index=df.index, dtype="string")
    d = df[c].astype("string").str.lower().str.strip()
    if c == "malzeme_sade" and MALZEME_BIRLESTIR:
        return d.map(malzeme_ana, na_action="ignore").astype("string")
    return d.replace(ESANLAMLI.get(c, {}))


def ozellik(df, kategoriler=None):
    d = pd.DataFrame(index=df.index)
    sayi = lambda c: (pd.to_numeric(df[c], errors="coerce") if c in df
                      else pd.Series(np.nan, index=df.index))
    d["log_g"] = np.log10(sayi("g_seviyesi").clip(lower=G_ALT_SINIR))
    d["oksijen_yuzde"] = sayi("oksijen_yuzde")
    d["log_basinc"] = np.log10(sayi("basinc_kpa").clip(lower=0.01))
    d["akis_hizi_cm_s"] = sayi("akis_hizi_cm_s")
    d["log_kalinlik"] = np.log10(sayi("kalinlik_mm").clip(lower=1e-4))
    if MOTOR_GIRDI:
        d = d.join(motor_ozellikleri(df))
    if kategoriler is None:   # eğitimde: en az 5 kez geçen değerleri öğren
        kategoriler = {}
        for c in KATEGORIK:
            say = kategori_degeri(df, c).value_counts()
            kategoriler[c] = list(say[say >= 5].index)
    for c in KATEGORIK:
        deger = kategori_degeri(df, c)
        d[c] = deger.map({k: i for i, k in enumerate(kategoriler[c])}).astype(float)  # bilinmeyen -> NaN
    return d, kategoriler


class HGB(HistGradientBoostingClassifier):
    def _sirala(self):
        if not hasattr(self, "_kat0"):
            self._kat0 = np.asarray(self.categorical_features, dtype=bool)
            self._kural0 = np.asarray(self.monotonic_cst, dtype=int)
            self._sira = np.r_[np.where(self._kat0)[0], np.where(~self._kat0)[0]]
            self.categorical_features = [bool(v) for v in self._kat0[self._sira]]
            self.monotonic_cst = [int(v) for v in self._kural0[self._sira]]

    def fit(self, X, y, sample_weight=None):
        self._sirala()
        return super().fit(np.asarray(X, dtype=float)[:, self._sira], y, sample_weight=sample_weight)

    def predict_proba(self, X):
        return super().predict_proba(np.asarray(X, dtype=float)[:, self._sira])

    def predict(self, X):
        return super().predict(np.asarray(X, dtype=float)[:, self._sira])


def model_kur(tohum):
    sutunlar = SAYISAL + KATEGORIK
    return HGB(
        max_iter=300, learning_rate=0.05, min_samples_leaf=10, l2_regularization=1.0,
        categorical_features=[c in KATEGORIK for c in sutunlar],
        monotonic_cst=[KURAL.get(c, 0) for c in sutunlar], random_state=tohum)


class RiskModeli:
    """Birkaç modelin ortalaması: ihtimal + ne kadar emin olduğu."""

    def __init__(self):
        self.modeller, self.kategoriler, self.egitim_X = [], None, None

    def egit(self, df, model_sayisi=None):
        X, self.kategoriler = ozellik(df)
        y = df["yanar"].values
        rng = np.random.default_rng(0)
        self.modeller = []
        for i in range(model_sayisi or MODEL_SAYISI):
            secim = rng.integers(0, len(X), len(X))            # her model verinin farklı bir örneğini görsün
            agirlik = df["agirlik"].values[secim] if "agirlik" in df else None
            self.modeller.append(model_kur(i).fit(X.iloc[secim], y[secim], sample_weight=agirlik))
        self.egitim_X = X
        return self

    def ihtimal(self, df):
        X, _ = ozellik(df, self.kategoriler)
        p = np.stack([m.predict_proba(X)[:, 1] for m in self.modeller])
        return p.mean(axis=0), p.std(axis=0), X

    def yakin_deney(self, X1):
        e, yakin = self.egitim_X, pd.Series(True, index=self.egitim_X.index)
        for c, tol in (("log_g", 0.25), ("oksijen_yuzde", 5), ("log_basinc", 0.3)):
            if pd.notna(X1[c].iloc[0]):
                yakin &= (e[c] - X1[c].iloc[0]).abs() <= tol
        if pd.notna(X1["malzeme_sade"].iloc[0]):
            yakin &= e["malzeme_sade"] == X1["malzeme_sade"].iloc[0]
        return int(yakin.sum())


def risk_seviyesi(p):
    return next(ad for sinir, ad in RISK if p * 100 < sinir)


# --------------------------------------------------------------- eğit
def deney_grubu(makale_id):
    m = str(makale_id)
    if m.startswith("PSI-"):
        k = m.split("_")[0]
        return "SAFFIRE" if k in ("PSI-98", "PSI-99", "PSI-100") else k
    if m.lower().startswith("saffire"):
        return "SAFFIRE"
    return m


def egit_ve_test(df_ham):
    df = etiketli_veri(df_ham)
    print(f"Etiketli veri: {len(df)} nokta, {df.makale_id.nunique()} makale")
    print("  etiket kaynakları:", df.etiket_kaynagi.value_counts().to_dict())
    print(f"  yandı: {int(df.yanar.sum())} | söndü: {int((1 - df.yanar).sum())}")

    gercek, tahmin, kaynak = [], [], []
    # Sıkı test: aynı NASA deneyinin (ör. FLEX'in 273 testi) bütün testleri hep birlikte
    # ya eğitimde ya testte olur; model test ettiği deneyi hiç görmemiş olur.
    for eg, te in GroupKFold(n_splits=5).split(df, df.yanar, df.makale_id.map(deney_grubu)):
        rm = RiskModeli().egit(df.iloc[eg], model_sayisi=3)   # test sırasında hızlı olsun
        p, _, _ = rm.ihtimal(df.iloc[te])
        gercek += list(df.yanar.iloc[te])
        tahmin += list(p)
        kaynak += list(df.etiket_kaynagi.iloc[te])
    gercek, tahmin = np.array(gercek), np.array(tahmin)
    cogunluk = max(gercek.mean(), 1 - gercek.mean())
    print("\nTest (model hiç görmediği makalelerde):")
    print(f"  Doğruluk  : %{accuracy_score(gercek, tahmin > 0.5) * 100:.0f}   "
          f"(hep '{'yanar' if gercek.mean() > 0.5 else 'söner'}' deseydik: %{cogunluk * 100:.0f})")
    print(f"  AUC       : {roc_auc_score(gercek, tahmin):.2f}   (0.5 = yazı tura, 1 = mükemmel)")
    kaynak = np.array(kaynak)
    g = np.isin(kaynak, ["psi", "makale_elle"])
    if g.any() and len(set(gercek[g])) == 2:
        print(f"  AUC (sadece NASA PSI + elle çıkarılan, en güvenilir): {roc_auc_score(gercek[g], tahmin[g]):.3f}")
    for k in sorted(set(kaynak)):
        m = kaynak == k
        print(f"    {k:22}: doğruluk %{accuracy_score(gercek[m], tahmin[m] > 0.5) * 100:.0f} ({m.sum()} nokta)")

    rm = RiskModeli().egit(df)
    MODEL_DOSYASI.parent.mkdir(exist_ok=True)
    joblib.dump(rm, MODEL_DOSYASI)
    print(f"\nKaydedildi: {MODEL_DOSYASI}")

    # fizik kuralı kontrolü
    ornek = pd.DataFrame({"g_seviyesi": 0.38, "basinc_kpa": 70, "malzeme_sade": "pmma",
                          "numune_tipi": "thin_sheet", "yakit_turu": "kati",
                          "oksijen_yuzde": [15, 18, 21, 25, 30]})
    p, _, _ = rm.ihtimal(ornek)
    print("Kural kontrolü (PMMA, Mars, 70 kPa) oksijen 15→30:",
          " → ".join(f"%{x * 100:.0f}" for x in p))


# --------------------------------------------------------------- kullan
def kosul(arg, **degis):
    k = {"g_seviyesi": arg.g, "oksijen_yuzde": arg.oksijen, "basinc_kpa": arg.basinc,
         "akis_hizi_cm_s": arg.akis, "kalinlik_mm": arg.kalinlik, "malzeme_sade": arg.malzeme,
         "numune_tipi": arg.numune, "yakit_turu": arg.yakit, "akis_yonu": arg.akis_yonu,
         "seyreltici": "n2"}
    k.update(degis)
    return pd.DataFrame([k])


def risk_goster(rm, arg):
    p, s, X = rm.ihtimal(kosul(arg))
    p, s = p[0], s[0]
    n = rm.yakin_deney(X)
    guven = "yüksek" if n >= 20 else "orta" if n >= 5 else "DÜŞÜK"
    print(f"\nKoşul: {arg.malzeme}, g={arg.g}, O2=%{arg.oksijen}, {arg.basinc} kPa")
    print(f"  Yanma ihtimali : %{p * 100:.0f}  (±{s * 100:.0f})")
    print(f"  Risk seviyesi  : {risk_seviyesi(p)}")
    print(f"  Güven          : {guven} ({n} yakın deney)")
    if guven == "DÜŞÜK":
        print("  Not: bu koşula yakın deney az; sonucu dikkatli yorumla.")


def harita_ciz(rm, arg):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap, BoundaryNorm

    g_ler = np.logspace(-4, 0, 60)
    o2_ler = np.linspace(10, 40, 61)
    izgara = pd.concat([kosul(arg, g_seviyesi=g, oksijen_yuzde=o) for o in o2_ler for g in g_ler],
                       ignore_index=True)
    p, s, _ = rm.ihtimal(izgara)
    P = p.reshape(len(o2_ler), len(g_ler)) * 100

    fig, ax = plt.subplots(figsize=(8, 5.5))
    renk = ListedColormap(["#2e7d32", "#f9a825", "#ef6c00", "#c62828"])
    cizim = ax.pcolormesh(g_ler, o2_ler, P, cmap=renk, norm=BoundaryNorm([0, 20, 50, 80, 100], 4),
                          shading="auto")
    ax.contour(g_ler, o2_ler, P, levels=[50], colors="black", linewidths=1.5)
    ax.set_xscale("log")
    for g, ad in ((0.16, "Ay"), (0.38, "Mars"), (1, "Dünya"), (1e-4, "Mikro-g")):
        ax.axvline(g, color="white", ls="--", lw=0.8)
        ax.text(g, 40.3, ad, ha="center", va="bottom", fontsize=9)
    ax.axhline(21, color="white", ls=":", lw=0.8)
    ax.set_xlabel("Yerçekimi (Dünya = 1)")
    ax.set_ylabel("Oksijen (%)")
    ax.set_title(f"Yanabilirlik haritası: {arg.malzeme}, {arg.basinc} kPa\n"
                 f"siyah çizgi = %50 yanma ihtimali (yanabilirlik sınırı)", fontsize=11)
    bar = fig.colorbar(cizim, ax=ax, ticks=[10, 35, 65, 90])
    bar.ax.set_yticklabels(["Düşük", "Orta", "Yüksek", "Çok yüksek"])
    bar.set_label("Yangın riski")
    fig.tight_layout()
    dosya = f"yanabilirlik_haritasi_{arg.malzeme.replace(' ', '_')}_{int(arg.basinc)}kPa.png"
    fig.savefig(dosya, dpi=150)
    print(f"Harita kaydedildi: {dosya}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--risk", action="store_true", help="tek bir koşul için risk hesapla")
    p.add_argument("--harita", action="store_true", help="yerçekimi-oksijen haritası çiz")
    p.add_argument("--g", type=float, default=1.0)
    p.add_argument("--oksijen", type=float, default=21)
    p.add_argument("--basinc", type=float, default=101.3)
    p.add_argument("--akis", type=float)
    p.add_argument("--kalinlik", type=float)
    p.add_argument("--malzeme", default="pmma")
    p.add_argument("--numune", default="thin_sheet")
    p.add_argument("--yakit", default="kati")
    p.add_argument("--akis-yonu", dest="akis_yonu")
    arg = p.parse_args()

    if arg.risk or arg.harita:
        if not MODEL_DOSYASI.exists():
            sys.exit("Önce modeli eğit: python risk_modeli.py")
        rm = joblib.load(MODEL_DOSYASI)
        risk_goster(rm, arg) if arg.risk else harita_ciz(rm, arg)
        return
    if not VERI.exists():
        sys.exit(f"{VERI} bulunamadı. temizle.py'nin çıktısını bu klasöre koy.")
    egit_ve_test(pd.read_csv(VERI, low_memory=False))


if __name__ == "__main__":
    # Modül üzerinden çalıştır: kaydedilen model sınıfları "__main__" değil "risk_modeli" modülüne ait olsun
    # (yoksa joblib.load başka betiklerden çağrılınca RiskModeli'yi bulamaz).
    import risk_modeli
    risk_modeli.main()
