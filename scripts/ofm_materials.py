#!/usr/bin/env python3
"""ofm_materials.py — OpenFOAM katı piroliz vakası için parametreleri MALZEME KÜTÜPHANESİNDEN kurar.

Kütüphaneden (material_library.json): yoğunluk, net ısıl değer (yakıt buharı kütle kesri Y_F0 için).
Kütüphanede olmayanlar (ısıl iletkenlik, ısıl yayınım, gazlaşma ısısı, piroliz kinetiği): ofm_material_params.json
(kaynaklı, "dogrulandi" bayraklı). Biri eksikse malzeme DESTEKLENMEZ ve neyin eksik olduğu söylenir; sessiz doldurma yok.

    parametre_seti(malzeme_id, kutuphane_malzemesi) -> {"tam": bool, "eksik": [...], "dogrulanmadi": [...],
        "piroliz": {...}, "rho":, "Cv":, "kappa":, "Yf0":, "kaynaklar": {...}}
Dönüş "piroliz" anahtarları sibalPyrolysis fvModels girdileriyle birebir aynıdır (A1 ... cpF).
"""
import json
from pathlib import Path

DOSYA = Path(__file__).resolve().parent / "ofm_material_params.json"
GEREKLI = ("kappa", "alpha", "Lv", "A1", "E1", "n1")


def _tablo():
    return json.loads(DOSYA.read_text(encoding="utf-8"))


def _kut(m, *adlar):
    """Kütüphane özelliği (deger, kaynak) ya da None."""
    oz = (m or {}).get("ozellikler") or {}
    for a in adlar:
        if a in oz and oz[a].get("deger") is not None:
            return oz[a]
    return None


def parametre_seti(malzeme_id, kutuphane_malzemesi):
    t = _tablo()
    tab = t["malzemeler"].get(malzeme_id, {})
    ref = t["referans_isil_deger_MJ_kg"]
    eksik, dogrulanmadi, kaynaklar = [], [], {}
    rho_k = _kut(kutuphane_malzemesi, "yogunluk")
    dhc_k = _kut(kutuphane_malzemesi, "isil_deger_net", "isil_deger")
    if not rho_k:
        eksik.append("yoğunluk (kütüphanede yok)")
    if not dhc_k:
        eksik.append("net ısıl değer (kütüphanede yok)")
    for a in GEREKLI:
        if a not in tab:
            eksik.append(f"{a} (ofm_material_params.json'da '{malzeme_id}' için yok)")
    if eksik:
        return {"tam": False, "eksik": eksik, "dogrulanmadi": [], "kaynaklar": {}}
    rho = float(rho_k["deger"])
    dhc = float(dhc_k["deger"])
    kaynaklar["rho"] = rho_k.get("kaynak")
    kaynaklar["Y_F0"] = f"net ısıl değer {dhc:g} MJ/kg ({dhc_k.get('kaynak')}) / {ref['deger']:g} MJ/kg: {ref['kaynak']}"
    if not ref.get("dogrulandi"):
        dogrulanmadi.append("Y_F0 = ısıl değer / 50 MJ/kg yaklaşımı")
    v = {k: tab[k]["deger"] for k in tab}
    for k, e in tab.items():
        kaynaklar[k] = e["kaynak"]
        if not e.get("dogrulandi"):
            dogrulanmadi.append(f"{k}: {e['kaynak'][:60]}")
    cp = v["kappa"] / (rho * v["alpha"])
    rin = v.get("rhoInert_orani", 0.01) * rho
    piroliz = dict(A1=v["A1"], E1=v["E1"], n1=v["n1"], rho01=rho - rin, A2=0.0, E2=245890.0, n2=1.0, rho02=1.0, nu=0.0,
                   rhoInert=rin, cpInert=cp, cpComb=cp, XL0=v["Lv"], TL=300.0, cpF=v.get("cpF", 1380.0))
    return {"tam": True, "eksik": [], "dogrulanmadi": dogrulanmadi, "kaynaklar": kaynaklar, "piroliz": piroliz,
            "rho": rho, "Cv": cp, "kappa": v["kappa"], "Yf0": min(1.0, dhc / ref["deger"]), "dhc_MJ_kg": dhc}
