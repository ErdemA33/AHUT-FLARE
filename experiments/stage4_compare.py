#!/usr/bin/env python3
"""Aşama 4: ayrıntılı mod (su emmeli, C_rad kalibre) ile hızlı modu aynı FLEX alt kümesinde karşılaştırır.
Girdi: data/droplet_validation_detailed.csv (kalibre_ayrintili_main çıktısı), data/droplet_engine_parameters.json.
Çıktı: experiments/stage4_comparison.json. İkisi de alt küme içinde (hızlı mod tüm FLEX ile kalibre)."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "scripts"))
import droplet_engine as dm  # noqa: E402

a = pd.read_csv(KOK / "data/droplet_validation_detailed.csv")
t = dm.flex_oku()
X = dm.flex_bilesim(t)
idx = [int(np.nonzero(t.test.to_numpy() == x)[0][0]) for x in a.test]
ta = t.iloc[idx].reset_index(drop=True)
p, pa = dm.varsayilan_parametreler()
oh = dm.hizli_tahmin(p, ta, X[:, idx])
ok = a.ayr_yanma.notna().to_numpy()
oa = {"yanma": a.ayr_yanma.to_numpy(float), "K": a.ayr_K.to_numpy(float),
      "sonme_capi": a.ayr_sonme_capi.to_numpy(float)}
sonuc = {"alt_kume_n": int(len(a)), "ayrintili_sonuc_veren": int(ok.sum()),
         "ayrintili_parametreler": pa,
         "ayrintili": dm.olcutler(ta[ok].reset_index(drop=True), {k: v[ok] for k, v in oa.items()}),
         "hizli_ayni_testler": dm.olcutler(ta[ok].reset_index(drop=True),
                                           {k: np.asarray(v)[ok] for k, v in oh.items() if k in ("yanma", "K", "sonme_capi")}),
         "hizli_alt_kume_tumu": dm.olcutler(ta, {k: v for k, v in oh.items() if k in ("yanma", "K", "sonme_capi")})}
# K hatası: yalnız ayrıntılı modun K verdiği testlerde, iki mod için aynı kümede (NaN medyanı bozmasın)
Kobs = ta.yanma_hizi_mm2_s.to_numpy(float)
mk = ok & np.isfinite(oa["K"]) & np.isfinite(Kobs) & (Kobs > 0.05)
sonuc["K_ortak_n"] = int(mk.sum())
sonuc["ayrintili"]["K_medyan_hata_yuzde"] = float(np.median(np.abs(oa["K"][mk] / Kobs[mk] - 1)) * 100)
sonuc["hizli_ayni_testler"]["K_medyan_hata_yuzde"] = float(np.median(np.abs(np.asarray(oh["K"])[mk] / Kobs[mk] - 1)) * 100)
for y in ("NC7H16", "CH3OH"):
    m = ok & (ta.yakit == y).to_numpy()
    if m.sum() >= 4:
        sonuc[f"ayrintili {y}"] = dm.olcutler(ta[m].reset_index(drop=True), {k: v[m] for k, v in oa.items()})
        sonuc[f"hizli {y}"] = dm.olcutler(ta[m].reset_index(drop=True),
                                          {k: np.asarray(v)[m] for k, v in oh.items() if k in ("yanma", "K", "sonme_capi")})
if "ayr_T_maks" in a:
    sonuc["T_alev_medyan_K"] = float(a.ayr_T_maks.median())
(KOK / "experiments" / "stage4_comparison.json").write_text(json.dumps(sonuc, ensure_ascii=False, indent=1,
                                                                        default=float), encoding="utf-8")
print(json.dumps(sonuc, ensure_ascii=False, indent=1, default=float))
