#!/usr/bin/env python3
"""
engine_validation_generate.py — engine_validation.json'u MEVCUT doğrulama çıktılarından üretir (sayı uydurmaz).

Kaynaklar:
  damla : droplet_validation_summary_fast.csv  -> "N2 ile kalibre / test CO2+He" satırı (dürüst test)
          yakitlar: n-heptan / metanol "yakıt dışarıda" satırları; kalibre edilmemiş yakıtlar FLEX dışı
          etiketli damla deneyleriyle (yeterli veri yoksa auc null)
  hafif : light_engine_validation.csv        -> deney ailesi bazında 5'li GroupKFold sonuçları
          light_engine_validation_points.csv -> aynı CV'nin nokta tahminleri; yakıt türüne göre AUC
          (numune_tipi: droplet/pool -> sıvı, gas_jet -> gaz, diğerleri -> katı)
  ofm : henüz doğrulama yok -> null
  model : risk_model.py'nin kendi testi (makaleye göre ayrılmış test kümesi); betik risk_model.py'yi
          GEÇİCİ bir klasörde yeniden eğitip çıktısından okur (proje dosyalarına dokunmaz; eğitim deterministik).

Kullanım:  python3 engine_validation_generate.py   [--sadece-damla: model AUC'sini yeniden hesaplamadan]
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

KOK = Path(__file__).resolve().parent
CIKTI = KOK / "engine_validation.json"


def _auc(y, p):
    return float(roc_auc_score(y, p)) if len(set(y)) == 2 else None


KONTROL_EN_AZ = 20         # kalibre edilmemiş yakıtta kontrol AUC'si için en az nokta
KONTROL_SINIF_EN_AZ = 5    # ... ve her sınıftan (yanar / söner) en az nokta


def damla_kontrol():
    """Kalibre edilmemiş yakıtlar (etanol, n-dekan, 1-propanol): FLEX dışı etiketli damla deneylerinde
    (engine_check.etiketli(): makale elle + otomatik) damla motorunun AUC'si. Bu yakıtlar kalibrasyonda hiç
    görülmediği için bu da dürüst bir testtir; yeterli veri yoksa None."""
    import droplet_engine as dm
    import engine as mo
    import engine_check as mk
    df = mk.etiketli()
    df = df[df.numune_tipi.eq("droplet") & ~df.makale_id.astype(str).str.startswith("PSI-69")].copy()
    df["yk"] = df.malzeme_sade.map(dm.yakit_bul)
    out = {}
    for y in dm.YAKIT:
        if y in dm.KALIBRE_YAKITLAR:
            continue
        x = df[df.yk.eq(y) & df.oksijen_yuzde.notna() & df.basinc_kpa.notna() & df.g_seviyesi.notna()]
        tah = []
        for r in x.itertuples():
            m = mo._damla(r.g_seviyesi, r.oksijen_yuzde, r.basinc_kpa, None if pd.isna(r.akis_hizi_cm_s)
                          else r.akis_hizi_cm_s, None if pd.isna(r.kalinlik_mm) else r.kalinlik_mm, r.malzeme_sade,
                          None if pd.isna(r.seyreltici) else r.seyreltici, False)
            tah.append(m.get("yanma", np.nan))
        x = x.assign(tah=tah).dropna(subset=["tah"])
        yan = int(x.yanar.sum())
        yeterli = len(x) >= KONTROL_EN_AZ and min(yan, len(x) - yan) >= KONTROL_SINIF_EN_AZ
        out[y] = {"ad": dm.YAKIT_AD_TR.get(y, y), "n": int(len(x)), "yanan": yan,
                  "auc": _auc(x.yanar, x.tah) if yeterli else None,
                  "dogruluk": float(((x.tah > 0.5) == x.yanar).mean()) if len(x) else None,
                  "kalibre": False,
                  "test": ("kalibre edilmedi; FLEX dışı etiketli damla deneyleri (makale elle + otomatik) ile kontrol"
                           if yeterli else f"kalibre edilmedi; kontrol verisi yetersiz ({len(x)} nokta, {yan} yanan)"
                           " -> motor ağırlığı 0")}
    return out


def damla():
    t = pd.read_csv(KOK / "droplet_validation_summary_fast.csv")
    s = t[(t.deney == "N2 ile kalibre") & (t.alt_kume == "test CO2+He")].iloc[0]
    alt = {r.alt_kume: {"n": int(r.n), "auc": float(r.auc), "dogruluk": float(r.dogruluk)}
           for r in t[t.deney == "N2 ile kalibre"].itertuples()}
    yakitlar = {}
    for y, ad in (("NC7H16", "n-heptan"), ("CH3OH", "metanol")):
        r = t[(t.deney == "yakıt dışarıda") & (t.alt_kume == f"test {y}")].iloc[0]
        yakitlar[y] = {"ad": ad, "n": int(r.n), "auc": float(r.auc), "dogruluk": float(r.dogruluk), "kalibre": True,
                       "test": "FLEX: bu yakıt kalibrasyon dışında bırakıldı, diğer yakıtla kalibre edilen motorla test"}
    yakitlar.update(damla_kontrol())
    return {"sivi": {"auc": float(s.auc), "dogruluk": float(s.dogruluk), "n": int(s.n),
                     "test": "FLEX: N2'li testlerle kalibre, CO2'li ve He'li testlerde dene"},
            "ayrinti": alt, "yakitlar": yakitlar,
            "yakit_notu": "engine.py damla motorunda motor_auc'yi yakıt bazında buradan alır; auc null = ağırlık 0",
            "kaynak": "droplet_validation_summary_fast.csv; kalibre edilmemiş yakıtlar: engine_check.etiketli()"}


def hafif():
    n = pd.read_csv(KOK / "light_engine_validation_points.csv")
    tur = np.where(n.numune_tipi.isin(["droplet", "pool"]), "sivi",
                   np.where(n.numune_tipi.eq("gas_jet"), "gaz", "kati"))
    out = {}
    for tt in ("kati", "sivi", "gaz"):
        x = n[tur == tt]
        if len(x) == 0:
            out[tt] = None
            continue
        out[tt] = {"auc": _auc(x.yanar, x.hafif), "dogruluk": float(((x.hafif > 0.5) == x.yanar).mean()),
                   "n": int(len(x)), "test": "deney ailesi bazında 5'li GroupKFold (aile tamamen testte)"}
    aile = pd.read_csv(KOK / "light_engine_validation.csv")
    out["aileler"] = {r.aile: {"n": int(r.nokta), "auc": None if pd.isna(r.auc) else float(r.auc),
                               "dogruluk": float(r.dogruluk)} for r in aile.itertuples()}
    out["kaynak"] = "light_engine_validation.csv, light_engine_validation_points.csv"
    return out


def model():
    """risk_model.py'yi geçici klasörde yeniden eğitir, test AUC'lerini çıktısından okur."""
    gerek = ["risk_model.py", "engine.py", "data_clean.csv", "labeled_gemma3.csv"] + \
        [p.name for p in KOK.glob("psi_labeled*.csv")]
    with tempfile.TemporaryDirectory() as d:
        for f in gerek:
            if (KOK / f).exists():
                shutil.copy2(KOK / f, d)
        r = subprocess.run([sys.executable, "risk_model.py"], cwd=d, capture_output=True, text=True,
                           timeout=900)
    c = r.stdout
    tum = re.search(r"AUC\s*:\s*([\d.]+)", c)
    nasa = re.search(r"AUC \(sadece NASA PSI \+ elle çıkarılan[^)]*\):\s*([\d.]+)", c)
    if not nasa:
        raise SystemExit("risk_model.py çıktısında NASA AUC bulunamadı:\n" + c[-2000:] + r.stderr[-1000:])
    return {"nasa_auc": float(nasa.group(1)), "tum_test_auc": float(tum.group(1)) if tum else None,
            "flex_auc": None,
            "test": "risk_model.py: makaleye göre ayrılmış test kümesi (model o makaleleri görmedi)",
            "not": "FLEX'e özel model AUC'si risk_model.py tarafından raporlanmıyor -> sıvıda da NASA AUC kullanılır"}


def gaz():
    """gas_validation_summary.json (gas_validation.py; gaz oturumu) 'GEOMETRİ BAŞINA AUC' satırları. Küre: 4 test ->
    AUC sıralama ölçemez, null (ağırlık 0). Jet: kontrol seti, jet sabitleri kalibre değil."""
    d = json.loads((KOK / "gas_validation_summary.json").read_text(encoding="utf-8"))
    sat = {r["alt_kume"].split()[0]: r for r in d["ozet"] if r["deney"] == "GEOMETRİ BAŞINA AUC"}
    geo = {}
    for ad, r in sat.items():
        e = {"n": int(r["n"]), "auc": r["auc"], "dogruluk": r["dogruluk"], "test": r["alt_kume"]}
        if ad == "kure":
            e.update(auc=None, not_="yalnız 4 test (Irace 2021): AUC ölçülen 1.00 ama n çok küçük -> null (ağırlık 0)",
                     auc_olculen=r["auc"])
        if ad == "jet":
            e["not_"] = "jet sabitleri kalibre değil (SLICE tablosu yok); literatür kontrol seti"
        geo[ad] = {k.rstrip("_"): v for k, v in e.items()}
    return {"geometri": geo, "kaynak": "gas_validation_summary.json (gas_engine_report.md)",
            "not": "engine.py: motor_auc = geometri AUC'si; gas_engine kalibre_degil=True döndürürse None (ağırlık 0)"}


def main():
    bas = time.time()
    if "--sadece-damla" in sys.argv:          # model AUC'si (risk_model yeniden eğitimi, uzun) aynı kalır
        d = json.loads(CIKTI.read_text(encoding="utf-8"))
        d["uretim"] = time.strftime("%Y-%m-%d %H:%M")
        d["motorlar"]["damla"] = damla()
        d["motorlar"]["gaz"] = gaz()
        CIKTI.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k: v["auc"] for k, v in d["motorlar"]["damla"]["yakitlar"].items()}, ensure_ascii=False))
        print(f"Kaydedildi: {CIKTI.name} (yalnız damla, {time.time() - bas:.0f} s)")
        return
    d = {"uretim": time.strftime("%Y-%m-%d %H:%M"),
         "aciklama": "Her motorun kendi yakıt grubundaki dürüst test (kalibrasyonda görülmeyen veri) sonuçları. "
                     "predict.py model-motor ağırlıklarını buradan alır.",
         "model": model(),
         "motorlar": {"damla": damla(), "hafif": hafif(), "gaz": gaz(), "ofm": None}}
    CIKTI.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"model": d["model"]["nasa_auc"], "damla_sivi": d["motorlar"]["damla"]["sivi"]["auc"],
                      "hafif": {k: (v or {}).get("auc") for k, v in d["motorlar"]["hafif"].items()
                                if k in ("kati", "sivi", "gaz")}}, ensure_ascii=False))
    print(f"Kaydedildi: {CIKTI.name} ({time.time() - bas:.0f} s)")


if __name__ == "__main__":
    main()
