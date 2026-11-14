#!/usr/bin/env python3
"""
motor.py  —  fizik motoru ile ML modeli arasındaki TEK bağlantı noktası.

Herkes motoru bu fonksiyonla çağırır:

    motor(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi)
        g        : yerçekimi, Dünya = 1   (ISS ~1e-4, Ay 0.165, Mars 0.38)
        oksijen  : % O2
        basinc   : kPa
        akis     : cm/s (zorlanmış hava akışı; yoksa 0)
        kalinlik : mm
        malzeme  : "pmma", "cotton", "n-heptane" ...
        numune_tipi : "thin_sheet", "droplet" ...   (bilinmeyenler None gelebilir)
    -> {"yanma": 0..1 (yanar mı),  "min_oksijen": %,  "yayilma_hizi": mm/s,
        "sicaklik": K,  "mesafe": tabloda en yakın koşula uzaklık (0 = birebir)}

MOTOR_TURU (ortam değişkeni MOTOR_TURU ile seçilir; verilmezse tablo varsa "tablo", yoksa "hafif"):
    "hafif"    -> hafif_motor.py: yarı-ampirik fizik (alev sıcaklığı, Damköhler, ışınım, de Ris),
                  NASA PSI + elle çıkarılan etiketlerle kalibre (hafif_motor_parametreleri.json)
    "sentetik" -> fizik kurallarına benzeyen basit formüller (kalibrasyonsuz, karşılaştırma için)
    "tablo"    -> OpenFOAM motorunun sonuçları (openfoam_sonuclar.csv); en yakın koşullar
                  arasından ağırlıklı ortalama alınır

openfoam_sonuclar.csv sütunları (OpenFOAM motorunun doldurması gereken):
    g, oksijen, basinc, akis, kalinlik, malzeme,             <- girdiler
    yandi (1/0), yayilma_hizi (mm/s), min_oksijen (%), sicaklik (K)   <- çıktılar (bilinmeyen boş)
"""

import math
import os
from pathlib import Path

import numpy as np

MOTOR_TURU = os.environ.get("MOTOR_TURU", "tablo" if Path("openfoam_sonuclar.csv").exists() else "hafif")
TABLO = Path("openfoam_sonuclar.csv")
KOMSU_SAYISI = 4
MAKS_MESAFE = 1.5     # en yakın tablo koşuluna uzaklık bundan büyükse tahmin yok ({} döner)

# ------------------------------------------------------------------ sentetik motor
# Malzemenin 1 g, 1 atm, durgun havadaki yaklaşık en düşük oksijen sınırı (LOI benzeri, %)
TEMEL_SINIR = {"pmma": 17.5, "cotton": 18.5, "sibal": 18.5, "cotton-fiberglass (sibal)": 18.5,
               "paper": 18.0, "cellulose": 18.0, "nomex": 28.0, "silicone": 24.0,
               "polyethylene": 17.5, "n-heptane": 15.0, "n-decane": 14.5, "methanol": 12.0,
               "ethanol": 13.0, "1-propanol": 13.5, "methane": 12.0, "ethylene": 10.5,
               "propane": 11.5}


def _sentetik(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi):
    """Gerçek fizik DEĞİL; yalnızca yön olarak doğru davranan kaba kurallar."""
    g = 1.0 if g is None else max(g, 1e-6)
    basinc = 101.3 if basinc is None else max(basinc, 1.0)
    akis = 0.0 if akis is None else akis
    kalinlik = 0.2 if kalinlik is None else max(kalinlik, 0.01)
    sinir = TEMEL_SINIR.get(str(malzeme).lower(), 18.0)

    # kaldırma kuvvetiyle oluşan doğal akış (cm/s): yerçekimi azaldıkça azalır
    dogal = 25.0 * g ** (1 / 3)
    toplam_akis = math.hypot(dogal, akis)
    # akış çok azsa oksijen gelmez (alev boğulur), çok fazlaysa alevi üfler: en uygun ~10 cm/s
    akis_cezasi = 4.0 * math.exp(-toplam_akis / 3.0) + 0.02 * max(toplam_akis - 30, 0)
    basinc_etkisi = -4.0 * math.log10(basinc / 101.3)        # basınç düşerse sınır yükselir
    kalinlik_etkisi = 1.0 * math.log10(kalinlik / 0.2)       # kalın numune daha zor tutuşur
    min_o2 = sinir + akis_cezasi + basinc_etkisi + kalinlik_etkisi - 1.5 * (toplam_akis > 3) * (g < 0.5)

    if oksijen is None:
        oksijen = 20.95
    fark = oksijen - min_o2
    yanma = 1 / (1 + math.exp(-fark / 0.8))
    yayilma = max(fark, 0) * 0.25 * (oksijen / 21) * (basinc / 101.3) ** 0.5 / kalinlik ** 0.5
    sicaklik = 1200 + 45 * max(fark, 0)
    return {"yanma": yanma, "min_oksijen": min_o2, "yayilma_hizi": yayilma,
            "sicaklik": sicaklik, "mesafe": 0.0}


# ------------------------------------------------------------------ OpenFOAM tablo motoru
_tablo = None


def _tabloyu_oku():
    global _tablo
    if _tablo is None:
        import pandas as pd
        t = pd.read_csv(TABLO)
        t["malzeme"] = t["malzeme"].astype(str).str.lower().str.strip()
        t["_lg"] = np.log10(t["g"].clip(lower=1e-6))
        t["_lp"] = np.log10(t["basinc"].clip(lower=1))
        _tablo = t
    return _tablo


def _tablodan(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi):
    t = _tabloyu_oku()
    aday = t[t.malzeme == str(malzeme).lower().strip()]
    if aday.empty:
        return {}
    lg = math.log10(max(g if g is not None else 1.0, 1e-6))
    lp = math.log10(max(basinc if basinc is not None else 101.3, 1))
    # ölçekler: 1 birim = log g'de 1 basamak, 3 puan oksijen, basınçta yarım basamak, 10 cm/s akış
    d = np.sqrt(((aday._lg - lg) / 1.0) ** 2 + ((aday.oksijen - (oksijen or 20.95)) / 3.0) ** 2
                + ((aday._lp - lp) / 0.5) ** 2 + ((aday.akis.fillna(0) - (akis or 0)) / 10.0) ** 2)
    if d.min() > MAKS_MESAFE:      # tablo bu koşulu kapsamıyor -> uydurma, tahmin verme
        return {}
    en_yakin = d.nsmallest(KOMSU_SAYISI).index
    w = 1 / (d[en_yakin] + 1e-3)
    sec = aday.loc[en_yakin]
    ort = lambda c: (float(np.nansum(sec[c] * w) / np.sum(w[sec[c].notna()]))
                     if c in sec and sec[c].notna().any() else None)
    return {"yanma": ort("yandi"), "min_oksijen": ort("min_oksijen"),
            "yayilma_hizi": ort("yayilma_hizi"), "sicaklik": ort("sicaklik"),
            "mesafe": float(d[en_yakin].min())}


def motor(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi, seyreltici=None):
    """seyreltici: "n2", "co2", "he", "ar", "xe" (sadece hafif motor kullanır; None = n2)."""
    if MOTOR_TURU == "tablo":
        return _tablodan(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi)
    if MOTOR_TURU == "hafif":
        import hafif_motor
        return hafif_motor.motor(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi, seyreltici or "n2")
    return _sentetik(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi)


if __name__ == "__main__":
    print(f"Motor türü: {MOTOR_TURU}")
    for ad, g in (("ISS", 1e-4), ("Ay", 0.165), ("Mars", 0.38), ("Dünya", 1.0)):
        m = motor(g, 21, 101.3, 0, 0.2, "pmma", "thin_sheet")
        sinir = "yok" if m.get("min_oksijen") is None else f"%{m['min_oksijen']:.1f}"
        print(f"  PMMA, %21 O2, 1 atm, {ad:6s}: yanma {m['yanma']:.2f}, "
              f"sınır {sinir}, yayılma {m['yayilma_hizi']:.2f} mm/s")
