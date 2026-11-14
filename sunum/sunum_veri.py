#!/usr/bin/env python3
"""
sunum_veri.py — sunum grafiklerinin hesaplanan verisi (tahmin.py çağrıları; yeni simülasyon yok).
Çıktılar sunum/veri/ altında; sunum_grafik.py bunları okur (yoksa uyarır).
  harita.csv   : PMMA ince levha, oksijen × basınç, g = 0,165 (Ay) ve 0,38 (Mars) -> yanma_birlesik
  u_egrisi.csv : PMMA ince levha, %21 O2, 101,3 kPa, akış 0; g taraması -> motor min O2 + model sönme sınırı
  ornek_guven.json : güven skoru örnek vakası (PMMA, ISS)
  kevlar.json  : Kevlar, ISS, %21 O2 (model-motor çelişki uyarısı)
Kullanım: python3 sunum/sunum_veri.py [harita|u|guven|kevlar ...]   (boş = hepsi)
"""
import contextlib
import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

KOK = Path(__file__).resolve().parent.parent
VERI = Path(__file__).resolve().parent / "veri"
sys.path.insert(0, str(KOK))


def _t(*a, **k):
    import tahmin as T
    with contextlib.redirect_stdout(io.StringIO()):
        return T.tahmin(*a, **k)


def harita():
    sat = []
    for g in (0.165, 0.38):
        for b in np.arange(30, 106, 5.0):
            for o in np.arange(8, 41, 1.0):
                r = _t("pmma", float(o), float(b), g)
                sat.append({"g": g, "basinc_kpa": b, "oksijen": o, "yanma_birlesik": r["yanma_birlesik"],
                            "yanma_ihtimali": r["yanma_ihtimali"],
                            "motor_yanma": r["motor"] and r["motor"]["yanma"]})
        print("harita g", g, "bitti", flush=True)
    pd.DataFrame(sat).to_csv(VERI / "harita.csv", index=False)


def u():
    sat = []
    for g in np.logspace(-4, 0, 25):
        r = _t("pmma", 21.0, 101.3, float(g), akis=0)
        sat.append({"g": g, "motor_min_o2": r["motor"] and r["motor"].get("min_oksijen"),
                    "model_sonme_siniri": r["sonme_siniri"], "yanma_birlesik": r["yanma_birlesik"]})
    pd.DataFrame(sat).to_csv(VERI / "u_egrisi.csv", index=False)


def u3():
    """U eğrisi tanısı: g × O2 taraması, risk modeli / hafif motor / birleşik ayrı ayrı (PMMA ince, durgun)."""
    sat = []
    for g in (1e-4, 1e-3, 3e-3, 0.01, 0.03, 0.1, 0.165, 0.38, 0.6, 1.0):
        for o in np.arange(8, 30.01, 0.5):
            r = _t("pmma", float(o), 101.3, g, akis=0)
            sat.append({"g": g, "oksijen": o, "model": r["yanma_ihtimali"], "motor": r["motor"] and r["motor"]["yanma"],
                        "birlesik": r["yanma_birlesik"], "model_sonme_siniri": r["sonme_siniri"],
                        "motor_min_o2": r["motor"] and r["motor"].get("min_oksijen"),
                        "kalinlik": r.get("kalinlik") or (r.get("girdi") or {}).get("kalinlik")})
        print("u3 g", g, flush=True)
    pd.DataFrame(sat).to_csv(VERI / "u_bilesenler.csv", index=False)


def guven():
    r = _t("pmma", 21.0, 101.3, 1e-4, akis=0)
    (VERI / "ornek_guven.json").write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str), "utf-8")


def kevlar():
    r = _t("kevlar", 21.0, 101.3, 1e-4)
    (VERI / "kevlar.json").write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str), "utf-8")


if __name__ == "__main__":
    VERI.mkdir(exist_ok=True)
    is_ = sys.argv[1:] or ["guven", "kevlar", "u", "harita"]
    for a in is_:
        {"harita": harita, "u": u, "u3": u3, "guven": guven, "kevlar": kevlar}[a]()
        print(a, "tamam", flush=True)
