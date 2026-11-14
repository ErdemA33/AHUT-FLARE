#!/usr/bin/env python3
"""ofm_motor.py — OpenFOAM motorunun ayrıntılı (OpenFOAM) motoru: içe aktarılmış koşuların dizini ve yönlendirici girişi.

OpenFOAM motoru AYRI bir kaynaktır: hızlı motorlara ve model sayılarına dokunmaz. tahmin.tahmin() yalnız "ofm" alanını ekler;
birleşik ihtimale ancak koşu yakınsa (mesafe <= 1,5) VE o koşunun deneyle doğrulama başarısı varsa katılır:

    HIZLI mod ağırlığı = min(0,5; doğrulama_başarısı × (1 − mesafe / 1,5))   (tavan yalnız Hızlı modda; Ayrıntılı modda ana sonuç OpenFOAM motorundan; başarı yoksa: 0 + "ayrıntılı motor bu koşulda doğrulanmadı")
    birleşik = (1 − ağırlık) × birleşik_önceki + ağırlık × (OpenFOAM yandı ? 1 : 0)

Mesafe (motor.py tablosuyla aynı ölçekler): sqrt( Δlog10 g /1 )² + (ΔO2 /3)² + (Δlog10 p /0,5)² + (Δakış /10)² [+ (Δlog10 kalınlık /0,3)²
(iki koşuda da kalınlık/çap varsa)). Aynı malzeme ve aynı yakıt türü şart.
Dizin: <AHUT_OFM_KOK ya da bu klasör>/ofm_sonuclar/ofm_kosular.json (ofm_ice_aktar.py yazar).
"""
import json
import math
import os
import re
from pathlib import Path

KOK = Path(__file__).resolve().parent
MAKS_MESAFE = 1.5
MAKS_AGIRLIK = 0.5      # YALNIZ Hızlı modda birleşik ihtimal için: tek bir koşu birleşik ihtimalin yarısından fazlasını belirlemez.
                        # Ayrıntılı modda ana sonuç doğrudan OpenFOAM motorundan gelir (tavan yok; "agirlik_tavansiz" yalnız bilgi).
UYARI_DOGRULANMADI = "Ayrıntılı motor bu koşulda doğrulanmadı: OpenFOAM koşusu yakın ama deneyle karşılaştırması yok, ağırlığı 0."


def kok() -> Path:
    return Path(os.environ.get("AHUT_OFM_KOK") or KOK)


def dizin_yolu() -> Path:
    return kok() / "ofm_sonuclar" / "ofm_kosular.json"


def kosular() -> list:
    try:
        return json.loads(dizin_yolu().read_text(encoding="utf-8")).get("kosular", [])
    except (OSError, ValueError):
        return []


def kayit_yaz(kosular_liste: list) -> None:
    y = dizin_yolu()
    y.parent.mkdir(parents=True, exist_ok=True)
    gecici = y.with_suffix(".tmp")
    gecici.write_text(json.dumps({"kosular": kosular_liste}, ensure_ascii=False, indent=1), encoding="utf-8")
    gecici.replace(y)


def malzeme_norm(ad) -> str:
    return re.sub(r"\s+", " ", str(ad or "").lower().replace("_", " ")).strip()


def ayni_malzeme(a, b) -> bool:
    a, b = malzeme_norm(a), malzeme_norm(b)
    return bool(a) and bool(b) and (a == b or a in b or b in a)


def mesafe(k, g, oksijen, basinc, akis, kalinlik) -> float:
    lg = lambda x: math.log10(max(x if x is not None else 1.0, 1e-6))
    t = ((lg(k.get("g")) - lg(g)) / 1.0) ** 2
    t += (((k.get("oksijen") or 20.95) - (oksijen or 20.95)) / 3.0) ** 2
    t += ((math.log10(max(k.get("basinc") or 101.3, 1)) - math.log10(max(basinc or 101.3, 1))) / 0.5) ** 2
    t += (((k.get("akis") or 0.0) - (akis or 0.0)) / 10.0) ** 2
    if k.get("kalinlik") and kalinlik:
        t += ((math.log10(k["kalinlik"]) - math.log10(kalinlik)) / 0.3) ** 2
    return math.sqrt(t)


def yakin_kosular(g, oksijen, basinc, akis, kalinlik, malzeme, yakit_turu, en_fazla=5) -> list:
    """Mesafesi <= 1,5 olan koşular, yakından uzağa; her biri kayda 'mesafe' ve 'agirlik' alanları eklenmiş kopya."""
    cikti = []
    for k in kosular():
        if k.get("yakit_turu") != yakit_turu or not ayni_malzeme(k.get("malzeme"), malzeme):
            continue
        d = mesafe(k.get("kosullar", {}), g, oksijen, basinc, akis, kalinlik)
        if d > MAKS_MESAFE:
            continue
        basari = (k.get("dogrulama") or {}).get("basari")
        yandi = k.get("yandi")
        w_ham = 0.0 if basari is None or yandi is None else max(0.0, basari * (1.0 - d / MAKS_MESAFE))
        cikti.append({**k, "mesafe": round(d, 3), "agirlik": round(min(MAKS_AGIRLIK, w_ham), 3), "agirlik_tavansiz": round(w_ham, 3)})
    return sorted(cikti, key=lambda x: x["mesafe"])[:en_fazla]


def degerlendir(g, oksijen, basinc, akis, kalinlik, malzeme, yakit_turu):
    """tahmin.tahmin()'in 'ofm' alanı: en yakın koşu (mesafe <= 1,5) ya da None."""
    y = yakin_kosular(g, oksijen, basinc, akis, kalinlik, malzeme, yakit_turu)
    if not y:
        return None
    k = y[0]
    return {"kosu": k["kosu"], "yakit_turu": k["yakit_turu"], "malzeme": k["malzeme"], "deney": k.get("deney"), "boyut": k.get("boyut"),
            "kosullar": k.get("kosullar"), "mesafe": k["mesafe"], "yandi": k.get("yandi"), "durum": (k.get("sonuc") or {}).get("durum"),
            "sonuc": k.get("sonuc"), "dogrulama": k.get("dogrulama"), "egri": k.get("egri"), "eksik": k.get("eksik") or [],
            "render": k.get("render") or [], "agirlik": k["agirlik"], "agirlik_tavansiz": k["agirlik_tavansiz"],
            "uyari": UYARI_DOGRULANMADI if k["agirlik"] == 0 else None,
            "yakin_sayisi": len(y), "kaynak": "OpenFOAM motoru (OpenFOAM)"}
