#!/usr/bin/env python3
"""
motor.py  —  fizik motoru ile ML modeli arasındaki TEK bağlantı noktası: yakıt türüne göre motor seçer.

    motor(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi, seyreltici="n2",
          yakit_turu=None, min_oksijen_hesapla=True)
        g        : yerçekimi, Dünya = 1   (ISS ~1e-4, Ay 0.165, Mars 0.38)
        oksijen  : % O2,  basinc : kPa,  akis : cm/s (yoksa 0),  kalinlik : mm (damlada ilk çap)
        malzeme  : "pmma", "cotton", "n-heptane" ...;  numune_tipi : "thin_sheet", "droplet" ... (None olabilir)
        seyreltici : "n2", "co2", "he", "ar", "xe"
        yakit_turu : "kati" / "sivi" / "gaz"; verilmezse malzemeden bulunur
        min_oksijen_hesapla : False -> damla motorunda sönme sınırı taraması atlanır (eğri çizimi için hızlı)
    -> {"yanma": 0..1, "min_oksijen": %, "yayilma_hizi": mm/s, "sicaklik": K, "mesafe": tabloya uzaklık,
        "motor_kaynagi": "damla" | "gaz" | "ofm_tablo" | "hafif" | "ofm+hafif" | "sentetik",
        "motor_auc": o motorun o yakıt grubundaki dürüst test AUC'si (motor_dogrulama.json; yoksa None),
        "yakit_turu": kullanılan yakıt türü}
    Damla motorunda ayrıca "yanma_hizi_K" (mm²/s) ve "sonme_capi" (mm), "motor_kalibre" (yakıt FLEX
    kalibrasyonunda mı), "tasinim_dogrulanmadi" (akis > 0) döner. "motor_uyarilari": tahmin.py'nin uyarılarına
    eklenecek kısa cümleler (havuz, kalibre edilmemiş yakıt, doğrulanmamış akış düzeltmesi).

Yönlendirme (MOTOR_TURU = "yonlendirici", varsayılan):
    yakıt türü: yakit_turu verilmişse o; yoksa tahmin.MALZEME_VARSAYILAN'dan; numune_tipi "droplet" ise sıvı;
                damla_motoru'nun tanıdığı yakıtlar (etanol, n-dekan, 1-propanol) da sıvı sayılır.
    sıvı        -> damla_motoru (hızlı mod, FLEX ile kalibre). Damla motoru yakıtı tanımıyorsa hafif motor.
                   numune_tipi "pool" (havuz) -> damla motoru KULLANILMAZ: hafif motor + uyarı (havuz modeli yok).
    gaz         -> gaz_motoru.py (gaz oturumu). Geometri numune_tipi'nden: gas_jet -> jet; porous_sphere / sızıntı /
                   nokta kaynak -> küre; flat / burner -> düz. motor_auc geometri başına (motor_dogrulama.json:
                   düz 0.946, jet 0.816 kontrol seti "jet sabitleri kalibre değil", küre null). kalibre_degil = True
                   -> motor_auc None (ağırlık 0) + uyarı. Gaz motoru sonuç vermezse eski yol (tablo/hafif).
    katı / (gaz)-> OpenFOAM motorunun tablosu (openfoam_sonuclar.csv) varsa ve en yakın koşu mesafesi <= 1.5 ise
                   w = 1 - mesafe/1.5, sonuç = w·tablo + (1-w)·hafif ("ofm+hafif"; mesafe 0 ise "ofm_tablo");
                   tablo yoksa ya da koşu uzaksa sadece hafif motor.
MOTOR_TURU ortam değişkeniyle tek motor zorlanabilir (test için): "hafif", "damla", "gaz", "tablo", "sentetik".
Eski davranış (yönlendirici öncesi) motor_eski.py'de.

openfoam_sonuclar.csv sütunları (OpenFOAM motorunun doldurması gereken):
    g, oksijen, basinc, akis, kalinlik, malzeme,             <- girdiler
    yandi (1/0), yayilma_hizi (mm/s), min_oksijen (%), sicaklik (K)   <- çıktılar (bilinmeyen boş)
"""

import json
import math
import os
from pathlib import Path

import numpy as np

KOK = Path(__file__).resolve().parent
MOTOR_TURU = os.environ.get("MOTOR_TURU", "yonlendirici")
TABLO = KOK / "openfoam_sonuclar.csv"
DOGRULAMA = KOK / "motor_dogrulama.json"
KOMSU_SAYISI = 4
MAKS_MESAFE = 1.5     # en yakın tablo koşuluna uzaklık bundan büyükse tablo kullanılmaz

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
    dogal = 25.0 * g ** (1 / 3)
    toplam_akis = math.hypot(dogal, akis)
    akis_cezasi = 4.0 * math.exp(-toplam_akis / 3.0) + 0.02 * max(toplam_akis - 30, 0)
    basinc_etkisi = -4.0 * math.log10(basinc / 101.3)
    kalinlik_etkisi = 1.0 * math.log10(kalinlik / 0.2)
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


# ------------------------------------------------------------------ yakıt türü
_varsayilan = None


def _malzeme_varsayilan():
    """tahmin.MALZEME_VARSAYILAN (döngüsel içe aktarmayı önlemek için ilk kullanımda)."""
    global _varsayilan
    if _varsayilan is None:
        from tahmin import MALZEME_VARSAYILAN
        _varsayilan = MALZEME_VARSAYILAN
    return _varsayilan


# gaz motoru geometrisi: numune_tipi -> gaz_motoru.py'nin tanıdığı ad (küre / düz / jet)
GAZ_GEOMETRI = {"gas_jet": "gas_jet", "jet": "gas_jet", "coflow": "gas_jet", "slice": "gas_jet",
                "porous_sphere": "porous_sphere", "sphere": "porous_sphere", "kure": "porous_sphere",
                "sızıntı": "sizinti", "sizinti": "sizinti", "leak": "leak", "nokta kaynak": "porous_sphere",
                "nokta_kaynak": "porous_sphere", "point_source": "porous_sphere", "s-flame": "porous_sphere",
                "flat": "flat_burner", "flat_burner": "flat_burner", "burner": "flat_burner", "bre": "flat_burner",
                "duz": "flat_burner"}
GAZ_GEO_AD = {"gas_jet": "jet", "porous_sphere": "kure", "sizinti": "kure", "leak": "kure",
              "flat_burner": "duz"}


def yakit_turu_bul(malzeme, numune_tipi=None, yakit_turu=None):
    if yakit_turu in ("kati", "sivi", "gaz"):
        return yakit_turu
    if str(numune_tipi or "").lower() in ("droplet", "pool"):
        return "sivi"
    if str(numune_tipi or "").lower().strip() in GAZ_GEOMETRI:
        return "gaz"
    from risk_modeli import malzeme_ana
    v = _malzeme_varsayilan().get(malzeme_ana(str(malzeme or "")))
    if v and v[2]:
        return v[2]
    import damla_motoru
    if damla_motoru.yakit_bul(malzeme):
        return "sivi"
    return "kati"


# ------------------------------------------------------------------ dürüst test AUC'leri
_dogrulama = None


def dogrulama():
    global _dogrulama
    if _dogrulama is None:
        _dogrulama = json.loads(DOGRULAMA.read_text(encoding="utf-8")) if DOGRULAMA.exists() else {}
    return _dogrulama


def gaz_auc(geometri):
    """Gaz motoru: geometri başına dürüst AUC (motor_dogrulama.json -> gaz.geometri; küre null)."""
    g = (dogrulama().get("motorlar", {}).get("gaz") or {}).get("geometri") or {}
    return (g.get(geometri) or {}).get("auc")


def motor_auc(kaynak, yakit_turu, yakit=None):
    """Damla motorunda yakıt bazında dürüst AUC (motor_dogrulama.json -> damla.yakitlar):
    n-heptan / metanol: o yakıt kalibrasyon dışında bırakılarak test; kalibre edilmemiş yakıtlar: kontrol
    verisiyle ölçülmüşse o, yoksa None (tahmin.py'de motor ağırlığı 0)."""
    d = dogrulama().get("motorlar", {})
    try:
        if kaynak == "damla":
            yk = (d["damla"].get("yakitlar") or {})
            if yakit is not None and yk:
                return (yk.get(yakit) or {}).get("auc")
            return d["damla"]["sivi"]["auc"]
        if kaynak in ("hafif", "ofm+hafif"):
            return d["hafif"][yakit_turu]["auc"]
        if kaynak == "ofm_tablo":
            return (d.get("ofm") or {}).get(yakit_turu, {}).get("auc")
    except (KeyError, TypeError):
        return None
    return None


# ------------------------------------------------------------------ motorlar
def _hafif(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi, seyreltici):
    import hafif_motor
    return hafif_motor.motor(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi, seyreltici or "n2")


def _damla(g, oksijen, basinc, akis, kalinlik, malzeme, seyreltici, min_oksijen_hesapla, belirsizlik_hesapla=False):
    """damla_motoru hızlı mod. min_oksijen_hesapla=False iken sınır taraması atlanır
    (damla_motoru.py değiştirilmeden, iç fonksiyonlarıyla)."""
    import damla_motoru as dm
    yakit = dm.yakit_bul(malzeme)
    if yakit is None or oksijen is None or basinc is None:
        return {}
    p, _ = dm.varsayilan_parametreler()
    g = 1e-4 if g is None else float(g)
    akis = 0.0 if akis is None else float(akis)
    d0 = 2.0 if kalinlik is None or not kalinlik > 0 else float(kalinlik)
    X = dm.ortam_bilesimi(oksijen, seyreltici or "n2")
    o, _h = dm._hizli_tek(p, yakit, X, float(basinc), d0, g, akis)
    sc = float(o["sonme_capi"][0])
    bayrak, uyari = dm.durum_notlari(yakit, g, akis)
    sa, sa_t = dm.soguk_alev(yakit, X, float(o["yanma"][0]), sc, float(o["K"][0]))
    tur_s = dm.sonme_turu(p, yakit, X, float(basinc), d0, g, akis, None if math.isnan(sc) else sc)
    if tur_s == "kimyasal" and yakit in dm.SU_EMEN and p.get("ln_kw", -50.0) > -40:
        # yalnız ETİKET (sayılar değişmez): su emme kapatılınca (k_w -> 0) sönme kalkıyor ya da sönme çapı yarıdan
        # fazla küçülüyorsa sönmeyi süren su emmedir (alkol damlası alevin ürettiği suyu emer; Dryer ve ark. 2014)
        o_w, _ = dm._hizli_tek(dict(p, ln_kw=-60.0), yakit, X, float(basinc), d0, g, akis)
        sc_w = float(o_w["sonme_capi"][0])
        if math.isnan(sc_w) or sc_w < 0.5 * sc:
            tur_s = "su_emme"
    if sa:
        uyari = uyari + [dm.SOGUK_UYARI + (f" (tahmini soğuk alev süresi ~{sa_t:.1f} s, kaba)" if sa_t else "")]
    return {"yanma": float(o["yanma"][0]),
            "min_oksijen": dm.min_oksijen_bul(p, yakit, X, float(basinc), d0, g, akis) if min_oksijen_hesapla
            else None,
            "yayilma_hizi": None, "yanma_hizi_K": float(o["K"][0]),
            "sonme_capi": None if math.isnan(sc) else sc, "sicaklik": float(o["Tf0"][0]), "mesafe": 0.0,
            "motor_kalibre": bayrak["kalibre"], "tasinim_dogrulanmadi": bayrak["tasinim_dogrulanmadi"],
            "kismi_g_dogrulanmadi": bayrak["kismi_g_dogrulanmadi"],
            "soguk_alev": sa, "soguk_alev_suresi_s": sa_t,
            "sonme_turu": tur_s, "isinim_temsili": dm.ISINIM_NOTU,
            "motor_uyarilari": uyari, "_yakit": yakit,
            "_belirsizlik": dm.belirsizlik(yakit, X, float(basinc), d0, g, akis) if belirsizlik_hesapla else None}


def _gaz(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi, seyreltici, min_oksijen_hesapla):
    """gaz_motoru.py (gaz oturumu; değiştirilmeden kullanılır). Geometri numune_tipi'nden:
    gas_jet -> jet; porous_sphere / sızıntı / nokta kaynak -> küre; flat / burner -> düz.
    kalibre_degil = True ise motor() motor_auc'yi None yapar (tahmin.py'de motor ağırlığı 0) ve uyarır."""
    import gaz_motoru as gm
    nt = GAZ_GEOMETRI.get(str(numune_tipi or "").lower().strip(), "gas_jet")
    # DİKKAT: sistemde 'akis' ORTAM hava akışı; gaz_motoru'nda 'akis' YAKIT çıkış hızı -> geçirilmez
    # (gaz motoru varsayılan debiyi kullanır; ortam akışı gaz motorunda modellenmiyor).
    m = gm.gaz_motoru(g, oksijen, basinc, None, kalinlik, malzeme, nt, seyreltici or "n2",
                      min_oksijen_hesapla=min_oksijen_hesapla)
    if not m or m.get("yanma") is None:
        return {}
    m = dict(m)
    uy = list(m.pop("uyarilar", None) or [])
    kal = [u[len("KALİBRE DEĞİL: "):] for u in uy if u.startswith("KALİBRE DEĞİL: ")]
    uy = [u for u in uy if not u.startswith("KALİBRE DEĞİL: ")]
    if akis is not None and akis > 0:
        uy.append("Ortam hava akışı gaz motorunda modellenmiyor (gaz motorunda 'akış' yakıt çıkış hızıdır); "
                  "varsayılan yakıt debisiyle hesaplandı.")
    if m.get("kalibre_degil"):
        uy.append("Gaz motoru bu koşulda kalibre değil (" + "; ".join(kal or ["neden belirtilmedi"])
                  + "): motor ağırlığı 0.")
    m["motor_uyarilari"] = uy
    m["_geometri"] = GAZ_GEO_AD.get(nt, m.get("geometri"))
    return m


def _karistir(tablo, hafif, w):
    """w·tablo + (1-w)·hafif; biri eksikse diğeri."""
    out = {}
    for k in ("yanma", "min_oksijen", "yayilma_hizi", "sicaklik"):
        a, b = tablo.get(k), hafif.get(k)
        out[k] = (w * a + (1 - w) * b) if a is not None and b is not None else (a if b is None else b)
    out["mesafe"] = tablo.get("mesafe")
    return out


def motor(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi, seyreltici="n2",
          yakit_turu=None, min_oksijen_hesapla=True, belirsizlik_hesapla=False):
    """belirsizlik_hesapla=True: damla motorunda bootstrap ± (~1 s; yalnız tahmin()'in son çağrısında)."""
    tur = yakit_turu_bul(malzeme, numune_tipi, yakit_turu)
    seyreltici = seyreltici or "n2"
    if MOTOR_TURU == "hafif":
        m, kaynak = _hafif(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi, seyreltici), "hafif"
    elif MOTOR_TURU == "damla":
        m, kaynak = _damla(g, oksijen, basinc, akis, kalinlik, malzeme, seyreltici, min_oksijen_hesapla), "damla"
    elif MOTOR_TURU == "gaz":
        m, kaynak = _gaz(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi, seyreltici,
                         min_oksijen_hesapla), "gaz"
    elif MOTOR_TURU == "tablo":
        m = _tablodan(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi) if TABLO.exists() else {}
        kaynak = "ofm_tablo"
    elif MOTOR_TURU == "sentetik":
        m, kaynak = _sentetik(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi), "sentetik"
    else:                                   # yönlendirici
        m, kaynak = {}, None
        havuz = str(numune_tipi or "").lower() == "pool"
        if tur == "sivi" and not havuz:
            m = _damla(g, oksijen, basinc, akis, kalinlik, malzeme, seyreltici, min_oksijen_hesapla,
                       belirsizlik_hesapla)
            kaynak = "damla" if m.get("yanma") is not None else None
        elif tur == "gaz":
            m = _gaz(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi, seyreltici, min_oksijen_hesapla)
            kaynak = "gaz" if m.get("yanma") is not None else None
        if kaynak is None:
            h = _hafif(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi, seyreltici) or {}
            t = _tablodan(g, oksijen, basinc, akis, kalinlik, malzeme, numune_tipi) \
                if tur != "sivi" and TABLO.exists() else {}
            if t.get("yanma") is not None and t["mesafe"] <= MAKS_MESAFE:
                w = 1 - t["mesafe"] / MAKS_MESAFE
                m = _karistir(t, h, w) if h.get("yanma") is not None else t
                kaynak = "ofm_tablo" if (w >= 0.999 or h.get("yanma") is None) else "ofm+hafif"
                m["tablo_agirligi"] = w
            else:
                m, kaynak = h, "hafif"
            if tur == "sivi" and havuz and m:
                m = dict(m)
                m["motor_uyarilari"] = ["Havuz yangını modeli yok: sıvı havuzu için damla motoru değil hafif "
                                        "motor kullanıldı (hafif motorun sıvıdaki dürüst AUC'si düşük)."]
    if not m or m.get("yanma") is None:
        return {}
    m = dict(m)
    yakit = m.pop("_yakit", None)
    geo = m.pop("_geometri", None)
    m["motor_kaynagi"] = kaynak
    if kaynak == "gaz":
        m["motor_auc"] = None if m.get("kalibre_degil") else gaz_auc(geo)
    else:
        m["motor_auc"] = motor_auc(kaynak, tur, yakit)
    m["yakit_turu"] = tur
    return m


if __name__ == "__main__":
    print(f"Motor türü: {MOTOR_TURU}")
    for ad, g in (("ISS", 1e-4), ("Ay", 0.165), ("Mars", 0.38), ("Dünya", 1.0)):
        m = motor(g, 21, 101.3, 0, 0.2, "pmma", "thin_sheet")
        sinir = "yok" if m.get("min_oksijen") is None else f"%{m['min_oksijen']:.1f}"
        print(f"  PMMA, %21 O2, 1 atm, {ad:6s}: yanma {m['yanma']:.2f}, sınır {sinir}, "
              f"yayılma {m['yayilma_hizi']:.2f} mm/s, kaynak {m['motor_kaynagi']}, AUC {m['motor_auc']}")
    m = motor(1e-4, 21, 101.3, 0, 2.0, "methanol", "droplet")
    print(f"  metanol damla 2 mm, ISS: yanma {m['yanma']:.2f}, sınır {m['min_oksijen']}, K {m['yanma_hizi_K']:.3f}, "
          f"kaynak {m['motor_kaynagi']}, AUC {m['motor_auc']}")
