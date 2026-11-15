#!/usr/bin/env python3
"""
scripts/predict.py — Dashboard ekibinin kullanacağı TEK giriş noktası.

    from predict import tahmin
    sonuc = tahmin("pmma", oksijen=30, basinc=70, g=0.38)

Komut satırı:
    python3 scripts/predict.py --malzeme pmma --oksijen 30 --basinc 70 --g 0.38 [--llm]

Dönen sözlük (json.dumps ile doğrudan yazılabilir; numpy tipi yok, NaN yerine None):
  (python3 scripts/predict.py --malzeme pmma --oksijen 30 --basinc 70 --g 0.38 gerçek çıktısı)
  {
    "girdi": {
      "malzeme": "pmma",
      "oksijen": 30,
      "basinc": 70,
      "g": 0.38,
      "akis": null,
      "kalinlik": 0.2,
      "numune_tipi": "thin_sheet",
      "yakit_turu": "kati",
      "akis_yonu": null,
      "seyreltici": "n2"
    },
    "yanma_ihtimali": 0.999,
    "belirsizlik": 0.001,
    "risk_seviyesi": "ÇOK YÜKSEK",
    "sonme_siniri": 15.75,
    "guvenlik_katsayisi": 0.525,
    "sinirlama": {
      "uzay": {
        "g": 0.0001,
        "yanma_ihtimali": 0.99,
        "belirsizlik": 0.011,
        "sonme_siniri": 17.25,
        "guvenlik_katsayisi": 0.575,
        "risk_seviyesi": "ÇOK YÜKSEK"
      },
      "gercek_g": {
        "g": 0.38,
        "yanma_ihtimali": 0.999,
        "belirsizlik": 0.001,
        "sonme_siniri": 15.75,
        "guvenlik_katsayisi": 0.525,
        "risk_seviyesi": "ÇOK YÜKSEK"
      },
      "dunya": {
        "g": 1.0,
        "yanma_ihtimali": 0.998,
        "belirsizlik": 0.002,
        "sonme_siniri": 16.25,
        "guvenlik_katsayisi": 0.542,
        "risk_seviyesi": "ÇOK YÜKSEK"
      }
    },
    "motor": {
      "yanma": 0.92,
      "min_oksijen": 13.091,
      "yayilma_hizi": 0.811,
      "sicaklik": 2426.664
    },
    "motor_turu": "hafif",
    "motor_akis": 0.0,
    "guven": {
      "skor": 0,
      "veri_bileseni": 0.0,
      "uyum_bileseni": null,
      "motor_bileseni": 0.0,
      "agirliklar": {
        "veri": 0.7,
        "uyum": 0.0,
        "motor": 0.3
      },
      "yakin_deney_yanma_orani": null,
      "yakin_deney": 0,
      "motorlu_yakin_deney": 0,
      "yanan": 0,
      "sonen": 0,
      "motor_yontemi": "ölçülemedi (motorun sonuç verdiği yakın deney yok)"
    },
    "kullanilan_varsayilanlar": {
      "numune_tipi": "thin_sheet",
      "kalinlik": 0.2,
      "yakit_turu": "kati"
    },
    "uyarilar": [
      "Hava akışı bilinmiyor; en kötü durum (akış var) varsayıldı.",
      "Kısmi g için deney verisi az; uzay, gerçek g ve Dünya sonuçlarının en kötüsü alındı.",
      "Güven düşük (16/100): bu koşula yakın NASA deneyi yok; kalibrasyon kapsamı dışı."
    ],
    "sure_sn": 0.566
  }

Alanlar:
  yanma_ihtimali / belirsizlik : 0..1, risk modelinin ortalaması / modeller arası standart sapma
  sonme_siniri                 : % O2; bunun altında alev sönüyor (model, %5-60 arası 0.25 adımla taranır).
                                 None = bu aralıkta hiç "yanar" demedi (bkz. uyarilar)
  guvenlik_katsayisi           : sonme_siniri / ortam oksijeni; > 1 güvenli, < 1 yanabilir
  sinirlama                    : sadece 0.01 <= g < 0.9 (Ay/Mars): model uzay (g=1e-4), gerçek g ve Dünya (g=1)
                                 için ayrı hesaplanır ("uzay", "gercek_g", "dunya"); ana sonuç en kötüsüdür
                                 (en yüksek ihtimal, en düşük sınır). Diğer g'lerde None
  kullanilan_varsayilanlar     : kullanıcı vermediği için MALZEME_VARSAYILAN'dan doldurulan alanlar
  girdi                        : hesapta gerçekten kullanılan değerler (varsayılanlar dahil); akis None = bilinmiyor
  motor / motor_turu           : fizik motorunun (scripts/engine.py, yakıt türüne göre yönlendirici) çıktısı; yoksa None
  motor_kaynagi                : damla (sıvı) / gaz (gaz yakıt, scripts/gas_engine.py) / hafif (katı) / ofm_tablo / ofm+hafif
  motor (damla)                : + motor_kalibre, tasinim_dogrulanmadi, kismi_g_dogrulanmadi, soguk_alev,
                                 soguk_alev_suresi_s, sonme_turu (isinim/kimyasal/None), isinim_temsili
  motor (gaz)                  : + sonme_turu (isinim/kimyasal/yok), alev_boyu mm (düz y_f / jet L_f),
                                 alev_yaricapi mm (küre / düz), kalibre_degil (True -> motor ağırlığı 0), geometri ...
  yanma_birlesik / agirliklar  : model ve motorun dürüst-test AUC'lerine göre ağırlıklı ortalaması
                                 (güç = max(0, 2(AUC-0.5)); data/engine_validation.json)
  llm_siniflandirma            : sadece listede olmayan malzemede (llm_analysis.malzeme_siniflandir); tanınmazsa
                                 sayılar None ve uyarı "malzeme tanınmadı, listeden seçin"
  motor_akis                   : motorun kullandığı akış (cm/s); akis None ise 0/5/10/20 içinden yanması en yüksek
  motor_belirsizlik            : yalnız damla motorunda: {"yanma": ±, "yanma_hizi_K": ± mm²/s, "min_oksijen": ± %,
                                 "n", "yontem"} — FLEX deney grubu bootstrap (50 kalibrasyon), ± = 16-84 yüzdelik
                                 yarı genişliği (yalnız kalibrasyon belirsizliği); diğer motorlarda None
  guven                        : engine_check.guven_skoru bileşenleriyle (skor 0-100):
                                 100 × (0.4 veri + 0.3 uyum + 0.3 motor); uyum = 1 - |yakın deney yanma oranı - p|.
                                 Yakın deney yoksa uyum None ve ağırlığı veriye geçer (0.7 veri + 0.3 motor)
  uyarilar                     : kısa Türkçe cümleler; boş liste = uyarı yok
  sure_sn                      : bu çağrının süresi (ilk çağrı modeli yüklediği için daha uzun)
  llm_yorum                    : sadece llm=True ise; LLM çalışmazsa "LLM yorumu alınamadı"
"""
import argparse
import contextlib
import json
import math
import os
import sys
import time

import joblib
import numpy as np
import pandas as pd

import ofm_engine as openfoam_motor
import engine as motor_modulu
import engine_check as mk
import risk_model as rm_modul
from pathlib import Path

KOK_TAHMIN = Path(__file__).resolve().parent.parent

TARAMA = np.arange(5.0, 60.0 + 1e-9, 0.25)     # sönme sınırı için oksijen taraması (%)
SINIRLAMA_G = (0.01, 0.9)                      # bu aralıktaki g için uzay/Dünya sınırlaması
UZAY_G, DUNYA_G = 1e-4, 1.0
GUVEN_ESIK, BELIRSIZLIK_ESIK = 50, 0.3

# Kullanıcı vermediyse kullanılan malzeme varsayılanları: (numune_tipi, kalinlik mm, yakit_turu).
# Anahtar risk_model.malzeme_ana() ile aranır ("cast pmma" -> pmma varsayılanları).
MALZEME_VARSAYILAN = {
    "pmma": ("thin_sheet", 0.2, "kati"),
    "sibal": ("fabric", 0.33, "kati"),
    "cotton": ("fabric", 0.3, "kati"),
    "nomex": ("fabric", 0.37, "kati"),
    "silicone": ("thin_sheet", 0.36, "kati"),
    "n-heptane": ("droplet", 1.0, "sivi"),
    "methanol": ("droplet", 1.0, "sivi"),
    "methane": ("gas_jet", None, "gaz"),
}

MOTOR_AKISLAR = (0.0, 5.0, 10.0, 20.0)   # cm/s; akış bilinmiyorsa motor bunlarla çalıştırılır

_model = None            # modül seviyesinde önbellek: model bir kez yüklenir
_karsilastirma = None    # engine_check'ün deney-motor karşılaştırma tablosu


def _modeli_al():
    global _model
    if _model is None:
        _model = joblib.load(rm_modul.MODEL_DOSYASI)
    return _model


def _karsilastirmayi_al():
    """Güven skoru için engine_comparison.csv; yoksa / başka motorla hesaplanmışsa yeniden üretilir.
    kontrol() ekrana yazdığı için çıktısı stderr'e yönlendirilir (stdout'taki JSON bozulmasın)."""
    global _karsilastirma
    if _karsilastirma is None:
        if not mk.onbellek_gecerli():
            with contextlib.redirect_stdout(sys.stderr):
                mk.kontrol()
        _karsilastirma = pd.read_csv(mk.CIKTI_CSV, low_memory=False)
    return _karsilastirma


def _temiz(x):
    """JSON'a uygun hale getir: numpy -> python, NaN/inf -> None."""
    if isinstance(x, dict):
        return {str(k): _temiz(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, np.ndarray)):
        return [_temiz(v) for v in x]
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, (np.integer, int)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        x = float(x)
        return None if math.isnan(x) or math.isinf(x) else x
    if x is None or x is pd.NA:
        return None
    return x


def _yuvarla(v, n=3):
    return None if v is None else round(float(v), n)


def _kosullar(g, oksijenler, basinc, akis, kalinlik, malzeme, numune_tipi, yakit_turu, akis_yonu, seyreltici):
    return pd.DataFrame({
        "g_seviyesi": float(g), "oksijen_yuzde": np.asarray(oksijenler, dtype=float),
        "basinc_kpa": float(basinc), "akis_hizi_cm_s": np.nan if akis is None else float(akis),
        "kalinlik_mm": np.nan if kalinlik is None else float(kalinlik),
        "malzeme_sade": malzeme, "numune_tipi": numune_tipi, "yakit_turu": yakit_turu,
        "akis_yonu": akis_yonu, "seyreltici": seyreltici})


def _model_hesap(g, oksijen, **kw):
    """Tek bir g için: ihtimal, belirsizlik, sönme sınırı, güvenlik katsayısı, risk. Tek model çağrısı."""
    p, s, _ = _modeli_al().ihtimal(_kosullar(g, np.r_[oksijen, TARAMA], **kw))
    p0, s0, pt = float(p[0]), float(s[0]), p[1:]
    sinir = float(TARAMA[np.argmax(pt >= 0.5)]) if (pt >= 0.5).any() else None
    return {"g": g, "yanma_ihtimali": _yuvarla(p0), "belirsizlik": _yuvarla(s0),
            "sonme_siniri": sinir,
            "guvenlik_katsayisi": None if sinir is None else _yuvarla(sinir / oksijen),
            "risk_seviyesi": rm_modul.risk_seviyesi(p0)}


# ------------------------------------------------------------------ malzeme kütüphanesi (eş anlamlı tanıma)
# data/material_library.json (yerleşik, kaynaklı) + user_materials.json (YANGIN_VERI_KLASORU; yalnız ONAYLI kayıtlar).
# Bilinen listede olmayan bir ad kütüphanede (ad / ad_en / id / eş anlamlı) eşleşirse LLM'e sorulmaz.
KUTUPHANE_DOSYASI = KOK_TAHMIN / "data/material_library.json"
KULLANICI_MALZEME_DOSYASI = "user_materials.json"
_kutuphane_onbellek = {"imza": None, "dizin": {}}


def _ad_norm(ad):
    """Büyük/küçük harf, Türkçe İ/ı, aksan (â, ü ...) ve boşluk farklarını yok sayar."""
    import unicodedata
    a = str(ad or "").replace("İ", "i").replace("I", "ı").lower().replace("ı", "i")
    a = "".join(c for c in unicodedata.normalize("NFKD", a) if not unicodedata.combining(c))
    return " ".join(a.replace("_", " ").split())


def _kullanici_dosyasi():
    kok = os.environ.get("YANGIN_VERI_KLASORU")
    return Path(kok) / KULLANICI_MALZEME_DOSYASI if kok else KOK_TAHMIN / KULLANICI_MALZEME_DOSYASI


def _kutuphane_dizini():
    dosyalar = [KUTUPHANE_DOSYASI, _kullanici_dosyasi()]
    imza = tuple((str(f), f.stat().st_mtime_ns if f.exists() else None) for f in dosyalar)
    if _kutuphane_onbellek["imza"] != imza:
        dizin = {}
        for f, kaynak in zip(dosyalar, ("kutuphane", "kullanici")):
            try:
                kayitlar = json.loads(f.read_text(encoding="utf-8")).get("malzemeler", [])
            except (OSError, ValueError):
                kayitlar = []
            for m in kayitlar:
                if kaynak == "kullanici" and m.get("onay") != "onayli":
                    continue                    # onaysız kullanıcı malzemesi (ve LLM önerisi) hiçbir hesaba girmez
                m = dict(m, _kaynak=kaynak)
                for ad in [m.get("id"), m.get("ad"), m.get("ad_en")] + list(m.get("es_anlamlilar") or []):
                    n = _ad_norm(ad)
                    if n and n not in dizin:     # yerleşik kütüphane önce: kullanıcı kaydı onu ezmez
                        dizin[n] = m
        _kutuphane_onbellek.update(imza=imza, dizin=dizin)
    return _kutuphane_onbellek["dizin"]


def kutuphanede_bul(ad):
    """Kütüphane kaydı (ya da None). Kayıtta '_kaynak' = 'kutuphane' | 'kullanici'."""
    return _kutuphane_dizini().get(_ad_norm(ad))


def _kutuphane_eslemesi(girilen, kayit, malzeme_biliniyor):
    """(model_malzeme, motor_malzeme, uyarılar, motor_sifir, bilgi)."""
    kid, benzer = kayit.get("id"), kayit.get("motor_benzeri")
    model_malzeme = kid if malzeme_biliniyor(kid) else (benzer or kid)
    durum = kayit.get("durum") or ("kullanıcı malzemesi" if kayit["_kaynak"] == "kullanici" else "")
    kalibre = durum == "motorda kalibre" and kayit["_kaynak"] == "kutuphane"
    zayif = "ZAYIF" in str(kayit.get("eslesme_gerekce") or "").upper()
    uyar = [f"'{girilen}' kütüphanede: {kayit.get('ad')} ({durum}); risk modeli '{model_malzeme}', "
            f"motor {('“' + benzer + '”') if benzer else 'yok'}."]
    if kayit["_kaynak"] == "kullanici":
        uyar.append("Kullanıcı malzemesi (onaylı, deney verisiyle doğrulanmadı): motor ağırlığı 0.")
    if benzer is None:
        uyar.append("Motor yok, model bu malzemeyi tanımıyor: yalnız risk modeli (genel girdilerle) kullanıldı; "
                    "sonucu dikkatle okuyun.")
    elif not kalibre:
        uyar.append(f"'{kayit.get('ad')}' motorda kalibre değil: motor ağırlığı 0 (benzer malzeme: {benzer}).")
    if zayif and benzer:
        uyar.append(f"zayıf eşleme: {benzer}")
    bilgi = {"girilen": girilen, "id": kid, "ad": kayit.get("ad"), "kaynak": kayit["_kaynak"], "durum": durum,
             "motor_benzeri": benzer, "model_malzeme": model_malzeme, "zayif_esleme": zayif,
             "motor_agirligi_sifir": not kalibre}
    return model_malzeme, benzer, uyar, not kalibre, bilgi


def _varsayilan_doldur(malzeme, numune_tipi, kalinlik, yakit_turu):
    """Verilmeyen numune_tipi / kalinlik / yakit_turu'nu MALZEME_VARSAYILAN'dan doldurur.
    (numune_tipi, kalinlik, yakit_turu, {doldurulan alan: değer}) döndürür."""
    varsayilanlar = {}
    v = MALZEME_VARSAYILAN.get(rm_modul.malzeme_ana(malzeme))
    if not v:                                  # tanınan ama varsayılanı olmayan malzeme (ör. etilen): kütüphaneden
        kayit = kutuphanede_bul(malzeme)
        if kayit is not None and kayit.get("_kaynak") == "kutuphane":
            kv = kayit.get("varsayilan") or {}
            v = (kv.get("numune_tipi"), kv.get("kalinlik_veya_cap_mm"), kayit.get("yakit_turu"))
    if v:
        verilen = {"numune_tipi": numune_tipi, "kalinlik": kalinlik, "yakit_turu": yakit_turu}
        for alan, deger in zip(verilen, v):
            if verilen[alan] is None and deger is not None:
                varsayilanlar[alan] = deger
    return (varsayilanlar.get("numune_tipi", numune_tipi), varsayilanlar.get("kalinlik", kalinlik),
            varsayilanlar.get("yakit_turu", yakit_turu), varsayilanlar)


def _birlestir(p_model, m, motor_kaynagi):
    """güç = max(0, 2(AUC - 0.5)); w_motor = güç_motor / (güç_model + güç_motor).
    Model AUC'si: NASA AUC (sıvıda modelin FLEX AUC'si kayıtlıysa o). Motor AUC'si: o motorun o yakıt
    grubundaki dürüst testi (data/engine_validation.json). Tablo kullanıldıysa motor gücü (1 - mesafe/1.5) ile azalır."""
    d = motor_modulu.dogrulama().get("model", {})
    auc_model = d.get("flex_auc") if (m.get("yakit_turu") == "sivi" and d.get("flex_auc")) else d.get("nasa_auc")
    guc_model = max(0.0, 2 * (auc_model - 0.5)) if auc_model is not None else 1.0
    if m.get("yanma") is None:
        return p_model, {"model": 1.0, "motor": 0.0}
    auc_motor = m.get("motor_auc")
    guc_motor = max(0.0, 2 * (auc_motor - 0.5)) if auc_motor is not None else 0.0
    if motor_kaynagi in ("ofm_tablo", "ofm+hafif") and m.get("mesafe") is not None:
        guc_motor *= max(0.0, 1 - m["mesafe"] / motor_modulu.MAKS_MESAFE)
    w = guc_motor / (guc_model + guc_motor) if guc_model + guc_motor > 0 else 0.0
    return _yuvarla((1 - w) * p_model + w * m["yanma"]), {"model": _yuvarla(1 - w), "motor": _yuvarla(w)}


# ------------------------------------------------------------------ güven skoru v2
# güven = 100 × (0.35 veri + 0.25 uyum + 0.25 motor + 0.15 kesinlik) × cezalar   (ayrıntı: docs/DASHBOARD.md 3.3b)
GUVEN_V2_AGIRLIK = {"veri": 0.35, "uyum": 0.25, "motor": 0.25, "kesinlik": 0.15}
KAYNAK_AGIRLIGI = {"psi": 1.0, "makale_elle": 0.8, "gemma": 0.5, "topluluk_onayli": 0.6, "topluluk_onaysiz": 0.2}
KAYNAK_ADI_V2 = {"psi": "NASA PSI", "makale_elle": "makale (elle)", "gemma": "Gemma (otomatik)",
                 "topluluk_onayli": "topluluk (onaylı)", "topluluk_onaysiz": "topluluk (onaysız)"}
CEZA_CELISKI, CEZA_KAPSAM = 0.8, 0.6
CEZA_LLM_ESLEME = 0.8      # Aşama: v1/v2 karşılaştırması (2026-11-15): listede olmayan malzeme LLM ile benzerine eşlendiyse
                           # yakın deneyler o benzer malzemenin (ör. kevlar -> nomex); veri bileşeni bu malzeme için değil
GUVEN_BANT = ((75, "yüksek"), (50, "orta"), (0, "düşük"))


def _kaynak_grubu(e):
    e = str(e)
    return "psi" if e == "psi" else ("makale_elle" if e == "makale_elle" else "gemma")


def _kalibrasyon_mesafesi(g, oksijen, basinc, malzeme, motor_kaynagi, k):
    """En yakın kalibrasyon noktasına normalize mesafe: max(|ΔO2| / PENCERE O2, |Δlog p| / PENCERE log p),
    aynı ana malzeme ve aynı g bandında. Kalibrasyon noktaları: NASA PSI + elle etiketli deneyler (risk modeli ve
    hafif / damla motoru bunlarla kalibre); gaz motorunda BRE testleri (gaz_veri, Dehghani 2021 Tablo 2, etilen,
    µg). Nokta yoksa None (kapsam dışı)."""
    lp0 = math.log10(max(basinc, 1))
    nasa = k[k.etiket_kaynagi.isin(["psi", "makale_elle"])]
    m = nasa
    ana = m.malzeme_sade.astype(str).map({a: rm_modul.malzeme_ana(a) for a in m.malzeme_sade.astype(str).unique()})
    m = m[(ana == rm_modul.malzeme_ana(str(malzeme))) & (m.g_seviyesi.map(mk.g_bandi) == mk.g_bandi(g))]
    d = []
    if len(m):
        do = (m.oksijen_yuzde - oksijen).abs() / mk.PENCERE["oksijen"]
        dp = ((np.log10(m.basinc_kpa.clip(lower=1)) - lp0).abs() / mk.PENCERE["log_basinc"]).fillna(0)
        d.append(float(np.maximum(do, dp).min()))
    if motor_kaynagi == "gaz" and rm_modul.malzeme_ana(str(malzeme)) in ("ethylene", "c2h4") and g < 0.01:
        try:
            b = pd.read_csv(KOK_TAHMIN / "gas_data" / "bre_dehghani2021_table2.csv")
            do = (100 * b.X_O2 - oksijen).abs() / mk.PENCERE["oksijen"]
            dp = (np.log10((100 * b.p_bar).clip(lower=1)) - lp0).abs() / mk.PENCERE["log_basinc"]
            d.append(float(np.maximum(do, dp).min()))
        except (OSError, AttributeError, KeyError):
            pass
    return min(d) if d else None


def _bre_yakin(g, oksijen, basinc, malzeme):
    """NASA ACME BRE testleri (gas_data/bre_dehghani2021_table2.csv; etilen düz brülör, ISS): yakın olanların
    (sayı, yanan) çifti. Yalnız etilen ve µg; yakınlık engine_check.PENCERE ile (yakıt seyreltmesi ve kütle
    akısı dikkate alınmaz). Uygun değilse None."""
    if rm_modul.malzeme_ana(str(malzeme)) not in ("ethylene", "c2h4") or g >= 0.01:
        return None
    try:
        b = pd.read_csv(KOK_TAHMIN / "gas_data" / "bre_dehghani2021_table2.csv")
    except OSError:
        return None
    m = (((100 * b.X_O2 - oksijen).abs() <= mk.PENCERE["oksijen"])
         & ((np.log10(100 * b.p_bar) - math.log10(max(basinc, 1))).abs() <= mk.PENCERE["log_basinc"]))
    return int(m.sum()), int((b.sonuc[m] == "FT").sum())


def _guven_v2(g, oksijen, basinc, malzeme, p_birlesik, p_model, belirsizlik, motor_sonuc, motor_belirsizlik,
              motor_kaynagi, k, llm_eslendi=None, eslesme_kaynagi="LLM"):
    yakin = k[mk.yakin_maske(k, g, oksijen, basinc, malzeme)]
    grup = yakin.etiket_kaynagi.map(_kaynak_grubu)
    sayi = {kk: int((grup == kk).sum()) for kk in ("psi", "makale_elle", "gemma")}
    w = grup.map(KAYNAK_AGIRLIGI)
    top_w, yanan_w = float(w.sum()), float((w * yakin.yanar.fillna(0)).sum())
    bre = _bre_yakin(g, oksijen, basinc, malzeme)
    if bre is not None:          # NASA ACME BRE (etilen, µg) testleri engine_comparison.csv'de yok: NASA PSI sayılır
        sayi["psi"] += bre[0]
        top_w += KAYNAK_AGIRLIGI["psi"] * bre[0]
        yanan_w += KAYNAK_AGIRLIGI["psi"] * bre[1]
    try:
        import community_data as community_data
        t = community_data.yakin_kayitlar(malzeme, g, oksijen, basinc, mk.PENCERE)
    except Exception:          # depo yok / okunamadı: topluluk katkısı 0
        t = {"onayli": 0, "onaysiz": 0, "yanan": 0, "yanan_onayli": 0}
    sayi["topluluk_onayli"], sayi["topluluk_onaysiz"] = t["onayli"], t["onaysiz"]
    tw_on, tw_off = KAYNAK_AGIRLIGI["topluluk_onayli"], KAYNAK_AGIRLIGI["topluluk_onaysiz"]
    top_w += tw_on * t["onayli"] + tw_off * t["onaysiz"]
    yanan_w += tw_on * t["yanan_onayli"] + tw_off * (t["yanan"] - t["yanan_onayli"])
    veri = min(1.0, top_w / mk.YAKIN_DENEY_TAVAN)
    oran = yanan_w / top_w if top_w > 0 else None
    uyum = None if oran is None or p_birlesik is None else 1.0 - abs(oran - p_birlesik)
    auc = (motor_sonuc or {}).get("motor_auc")
    kalibre_degil = (motor_sonuc is None or auc is None or (motor_sonuc or {}).get("kalibre_degil") is True
                     or (motor_sonuc or {}).get("motor_kalibre") is False)
    motor_b = 0.0 if kalibre_degil else max(0.0, 2 * (auc - 0.5))
    mb = (motor_belirsizlik or {}).get("yanma")
    en_buyuk = max(x for x in (belirsizlik, mb, 0.0) if x is not None)
    kesinlik = min(1.0, max(0.0, 1 - 2 * en_buyuk))
    agirlik = dict(GUVEN_V2_AGIRLIK)
    if uyum is None:                     # yakın deney yok: uyumun ağırlığı veriye geçer (v1 ile aynı mantık)
        agirlik["veri"] += agirlik.pop("uyum")
        agirlik["uyum"] = 0.0
    ham = (agirlik["veri"] * veri + agirlik["uyum"] * (uyum or 0) + agirlik["motor"] * motor_b
           + agirlik["kesinlik"] * kesinlik)
    cezalar, carpan = [], 1.0
    if motor_sonuc is not None and p_model is not None and (p_model >= 0.5) != (motor_sonuc["yanma"] > 0.5):
        cezalar.append({"ad": "model–motor çelişkisi", "carpan": CEZA_CELISKI})
        carpan *= CEZA_CELISKI
    if llm_eslendi:
        cezalar.append({"ad": f"malzeme {eslesme_kaynagi} ile eşlendi", "carpan": CEZA_LLM_ESLEME,
                        "ayrinti": f"'{llm_eslendi}' -> '{malzeme}': yakın deneyler benzer malzemenin"})
        carpan *= CEZA_LLM_ESLEME
    mesafe = _kalibrasyon_mesafesi(g, oksijen, basinc, malzeme, motor_kaynagi, k)
    if mesafe is None or mesafe > 1.0:
        cezalar.append({"ad": "kalibrasyon kapsamı dışı", "carpan": CEZA_KAPSAM,
                        "mesafe": None if mesafe is None else round(mesafe, 2),
                        "esik": "en yakın NASA / kalibrasyon noktası PENCERE dışında (|ΔO2| > 3 ya da |Δlog p| > 0.3, "
                                "aynı malzeme ve g bandı)"})
        carpan *= CEZA_KAPSAM
    skor = int(round(100 * ham * carpan))
    bant = next(ad for esik, ad in GUVEN_BANT if skor >= esik)
    return {"skor": skor, "bant": bant,
            "bilesenler": {"veri": _yuvarla(veri), "uyum": None if uyum is None else _yuvarla(uyum),
                           "motor": _yuvarla(motor_b), "kesinlik": _yuvarla(kesinlik)},
            "agirliklar": {kk: _yuvarla(v) for kk, v in agirlik.items()},
            "ham_skor": _yuvarla(100 * ham, 1), "cezalar": cezalar,
            "kalibrasyon_mesafesi": None if mesafe is None else _yuvarla(mesafe, 2),
            "yakin_deney_kaynaklari": {KAYNAK_ADI_V2[kk]: v for kk, v in sayi.items()},
            "agirlikli_yakin_deney": _yuvarla(top_w, 2),
            "yakin_deney_yanma_orani": None if oran is None else _yuvarla(oran),
            "ayrinti": {"motor": "kalibre değil / dürüst AUC yok -> 0" if kalibre_degil
                        else f"max(0, 2(AUC-0.5)), AUC {auc:.3f}",
                        "kesinlik": f"1 - 2 × max(model ±{belirsizlik or 0:.3f}"
                                    + (f", motor ±{mb:.3f}" if mb is not None else ", motor belirsizliği yok")
                                    + ")",
                        "kaynak_agirliklari": KAYNAK_AGIRLIGI}}


def _taninmadi(malzeme, oksijen, basinc, g, akis, kalinlik, numune_tipi, yakit_turu, akis_yonu, seyreltici,
               llm_sinif, bas, adimlar=None):
    """Malzeme tanınmadı (LLM reddetti ya da bağlantı yok): sayı üretmeden döner."""
    sebep = {"reddedildi": "LLM önerisi denetimden geçmedi", "baglanti_yok": "LLM'e ulaşılamadı"}.get(
        llm_sinif.get("durum"), "tanınmadı")
    return _temiz({
        "girdi": {"malzeme": malzeme, "oksijen": oksijen, "basinc": basinc, "g": g, "akis": akis,
                  "kalinlik": kalinlik, "numune_tipi": numune_tipi, "yakit_turu": yakit_turu,
                  "akis_yonu": akis_yonu, "seyreltici": seyreltici},
        "yanma_ihtimali": None, "yanma_birlesik": None, "agirliklar": None, "belirsizlik": None,
        "risk_seviyesi": None, "sonme_siniri": None, "guvenlik_katsayisi": None, "sinirlama": None,
        "motor": None, "motor_turu": motor_modulu.MOTOR_TURU, "motor_kaynagi": None, "motor_akis": None,
        "motor_belirsizlik": None, "guven": None, "guven_v1": None, "guven_v2": None, "kullanilan_varsayilanlar": {},
        "llm_siniflandirma": {k: llm_sinif.get(k) for k in ("girilen", "durum", "sebep", "kaynak")},
        "adimlar": _adimlari_tamamla(adimlar or [], "malzeme tanınmadı: sayı üretilmedi"),
        "uyarilar": [f"'{malzeme}' malzemesi tanınmadı, listeden seçin ({sebep}"
                     + (f": {llm_sinif['sebep']}" if llm_sinif.get("sebep") else "") + ")."],
        "sure_sn": round(time.perf_counter() - bas, 3)})


OZEL_BASLIK = {"oksitleyici": "Oksitleyici: yanmaz ama yangını şiddetlendirir",
               "yanmaz": "Yanıcı değil", "pil": "Pil: termal kaçak modeli yok"}


GAZ_VARSAYILAN_NUMUNE = "porous_sphere"     # sızıntı (küre)
GAZ_DEBISIZ_UYARI = ("Numune tipi verilmedi: varsayılan sızıntı (küre). Debi bilinmiyor; gaz motoru kullanılmadı "
                     "(motor ağırlığı 0, sonuç yalnız risk modeli).")


def _guven_dusuk_cumlesi(v2, v1, motor_sonuc, motor_sifir):
    """Düşük güvenin somut sebepleri (v2 varsa onun skoru ve bileşenleri)."""
    skor = v2.get("skor") if v2.get("skor") is not None else v1.get("skor")
    sebep = []
    nasa = (v2.get("yakin_deney_kaynaklari") or {}).get("NASA PSI")
    if nasa == 0:
        sebep.append("bu koşula yakın NASA deneyi yok")
    elif nasa is not None and nasa < 5:
        sebep.append(f"bu koşula yakın NASA deneyi az ({nasa})")
    for c in v2.get("cezalar") or []:
        sebep.append(c.get("ad"))
    if motor_sonuc is None or motor_sifir:
        sebep.append("fizik motoru kullanılmadı (ağırlık 0)")
    elif ((v2.get("bilesenler") or {}).get("motor") or 0) < 0.3:
        sebep.append("motor bu koşulda zayıf")
    return f"Güven düşük ({skor}/100): " + ("; ".join(dict.fromkeys(s for s in sebep if s)) or
                                             "bileşenlerin toplamı eşiğin altında") + "."


def _ozel_durum(girilen, kayit, oksijen, basinc, g, akis, kalinlik, numune_tipi, yakit_turu, akis_yonu, seyreltici,
                bas, adimlar):
    """Kütüphanede 'ozel' işaretli malzeme (oksitleyici / yanmaz / pil): yakıt olarak çözülmez, sayı üretilmez."""
    oz = kayit.get("ozel") or {}
    uyar = [f"'{girilen}' = {kayit.get('ad')}: {oz.get('uyari')}."]
    if oz.get("tur") == "oksitleyici":
        uyar.append("Oksitleyici sızıntısı yakındaki malzemelerin yanma riskini artırır: ortam oksijenini yükselterek "
                    "o malzemeleri değerlendirin.")
    if kayit.get("notlar"):
        uyar.append(kayit["notlar"])
    return _temiz({
        "girdi": {"malzeme": girilen, "oksijen": oksijen, "basinc": basinc, "g": g, "akis": akis,
                  "kalinlik": kalinlik, "numune_tipi": numune_tipi, "yakit_turu": yakit_turu,
                  "akis_yonu": akis_yonu, "seyreltici": seyreltici},
        "yanma_ihtimali": None, "yanma_birlesik": None, "agirliklar": None, "belirsizlik": None,
        "risk_seviyesi": None, "sonme_siniri": None, "guvenlik_katsayisi": None, "sinirlama": None,
        "motor": None, "motor_turu": motor_modulu.MOTOR_TURU, "motor_kaynagi": None, "motor_akis": None,
        "motor_belirsizlik": None, "guven": None, "guven_v1": None, "guven_v2": None, "kullanilan_varsayilanlar": {},
        "ozel_durum": {"tur": oz.get("tur"), "baslik": OZEL_BASLIK.get(oz.get("tur"), oz.get("tur")),
                       "uyari": oz.get("uyari"), "id": kayit.get("id"), "ad": kayit.get("ad"),
                       "kategori": kayit.get("kategori")},
        "kutuphane_eslesme": {"girilen": girilen, "id": kayit.get("id"), "ad": kayit.get("ad"), "kaynak": "kutuphane",
                              "durum": kayit.get("durum"), "motor_benzeri": None, "model_malzeme": None,
                              "zayif_esleme": False, "motor_agirligi_sifir": True},
        "adimlar": _adimlari_tamamla(adimlar, f"{oz.get('tur')}: yakıt olarak çözülmez"),
        "uyarilar": uyar, "sure_sn": round(time.perf_counter() - bas, 3)})


# ------------------------------------------------------------------ işlem kaydı ("adimlar")
ADIM_ADLARI = {1: "girdi ve varsayılanlar", 2: "malzeme tanıma", 3: "risk modeli", 4: "yönlendirici seçimi",
               5: "fizik motoru", 6: "birleştirme ağırlıkları", 7: "Ay/Mars sınırlama", 8: "sönme sınırı ve güvenlik katsayısı",
               9: "güven skoru", 10: "uyarılar", 11: "LLM yorumu", 12: "kayıt"}
KAYIT_DOSYASI_ORTAM = "TAHMIN_KAYIT"     # bu ortam değişkeni bir dosya yolu ise her tahmin JSON satırı olarak eklenir


def _adim(adimlar, no, t0, karar, ayrinti=None):
    adimlar.append({"no": no, "ad": ADIM_ADLARI[no], "sure_ms": round(1000 * (time.perf_counter() - t0), 2),
                    "karar": karar, "ayrinti": ayrinti or {}})


def _adimlari_tamamla(adimlar, sebep):
    var = {a["no"] for a in adimlar}
    out = list(adimlar) + [{"no": n, "ad": ADIM_ADLARI[n], "sure_ms": 0.0, "karar": f"atlandı ({sebep})",
                            "ayrinti": {}} for n in ADIM_ADLARI if n not in var]
    return sorted(out, key=lambda a: a["no"])


def _yonlendirme_nedeni(motor_kaynagi, yakit_turu, numune_tipi):
    if motor_kaynagi == "damla":
        return f"yakıt türü '{yakit_turu}' (sıvı), numune '{numune_tipi}' -> damla motoru (FLEX ile kalibre)"
    if motor_kaynagi == "gaz":
        return f"yakıt türü '{yakit_turu}' (gaz), numune '{numune_tipi}' -> gaz motoru (geometri numune tipinden)"
    if motor_kaynagi in ("ofm_tablo", "ofm+hafif"):
        return "katı yakıt ve yakın OpenFOAM tablosu var -> tablo (+ hafif motor)"
    if motor_kaynagi == "hafif":
        return (f"yakıt türü '{yakit_turu}' -> hafif motor (katı yakıt; ya da sıvı havuz / gaz motoru sonuç vermedi)")
    return f"motor sonucu yok (kaynak: {motor_kaynagi})"


def tahmin(malzeme, oksijen, basinc, g, akis=None, kalinlik=None, numune_tipi=None,
           yakit_turu=None, akis_yonu=None, seyreltici="n2", llm=False):
    """akis: None = bilinmiyor, 0 = akış yok (durgun ortam)."""
    bas = time.perf_counter()
    uyarilar = []
    adimlar = []
    girilen_malzeme = malzeme
    numune_verildi = numune_tipi is not None and str(numune_tipi).strip() != ""
    # --- bilinmeyen malzeme: LLM sınıflandırması (önbellekli); tanınmazsa uydurma yapılmaz
    llm_sinif = None
    kutup, kutup_bilgi, motor_sifir, kutup_varsay = None, None, False, {}
    motor_malzeme = None                       # None: motor, model ile aynı malzemeyle çalışır
    t0 = time.perf_counter()
    import llm_analysis as llm_analysis
    if not llm_analysis.malzeme_biliniyor(malzeme):
        kutup = kutuphanede_bul(malzeme)
    if kutup is not None and kutup.get("ozel") and kutup.get("_kaynak") == "kutuphane":
        _adim(adimlar, 2, t0, f"kütüphane: '{girilen_malzeme}' -> {kutup.get('id')} ({kutup['ozel'].get('tur')}: "
              f"yakıt olarak çözülmez)", {"kaynak": "kutuphane", "ozel": kutup["ozel"].get("tur")})
        return _ozel_durum(girilen_malzeme, kutup, oksijen, basinc, g, akis, kalinlik, numune_tipi, yakit_turu,
                           akis_yonu, seyreltici, bas, adimlar)
    if kutup is not None:
        model_m, motor_m, k_uyar, motor_sifir, kutup_bilgi = _kutuphane_eslemesi(girilen_malzeme, kutup,
                                                                                 llm_analysis.malzeme_biliniyor)
        uyarilar.extend(k_uyar)
        v = kutup.get("varsayilan") or {}
        for alan, deger in (("yakit_turu", kutup.get("yakit_turu")), ("numune_tipi", v.get("numune_tipi")),
                            ("kalinlik", v.get("kalinlik_veya_cap_mm"))):
            if deger is not None and {"yakit_turu": yakit_turu, "numune_tipi": numune_tipi,
                                      "kalinlik": kalinlik}[alan] is None:
                kutup_varsay[alan] = deger
        yakit_turu = kutup_varsay.get("yakit_turu", yakit_turu)
        numune_tipi = kutup_varsay.get("numune_tipi", numune_tipi)
        kalinlik = kutup_varsay.get("kalinlik", kalinlik)
        malzeme = model_m
        motor_malzeme = motor_m if motor_m is not None else False      # False: uygun motor yok
        _adim(adimlar, 2, t0, f"{'kullanıcı kütüphanesi' if kutup['_kaynak'] == 'kullanici' else 'kütüphane'}: "
              f"'{girilen_malzeme}' -> {kutup.get('id')} (model: {model_m}, motor: {motor_m or 'yok'})",
              {"kaynak": "kullanici_kutuphanesi" if kutup["_kaynak"] == "kullanici" else "kutuphane",
               "durum": kutup_bilgi["durum"], "zayif_esleme": kutup_bilgi["zayif_esleme"]})
    elif not llm_analysis.malzeme_biliniyor(malzeme):
        llm_sinif = llm_analysis.malzeme_siniflandir(malzeme)
        if llm_sinif["durum"] != "kabul":
            _adim(adimlar, 2, t0, f"tanınmadı ({llm_sinif.get('durum')}, kaynak: {llm_sinif.get('kaynak')})",
                  {"girilen": malzeme, "sebep": llm_sinif.get("sebep"),
                   "kaynak": "onbellek" if llm_sinif.get("kaynak") == "onbellek" else "llm"})
            return _taninmadi(malzeme, oksijen, basinc, g, akis, kalinlik, numune_tipi, yakit_turu, akis_yonu,
                              seyreltici, llm_sinif, bas, adimlar)
        uyarilar.append(f"'{malzeme}' listede yok, LLM bunu '{llm_sinif['benzer_malzeme']}' malzemesine "
                        f"benzetti ({llm_sinif['yakit_turu']}, {llm_sinif['numune_tipi']}) — kontrol edin.")
        malzeme = llm_sinif["benzer_malzeme"]
        numune_tipi = numune_tipi or llm_sinif["numune_tipi"]
        yakit_turu = yakit_turu or llm_sinif["yakit_turu"]
        _adim(adimlar, 2, t0, f"LLM ({'önbellek' if llm_sinif.get('kaynak') == 'onbellek' else 'EVREN'}): "
              f"'{girilen_malzeme}' -> '{malzeme}'", {"kaynak": "onbellek" if llm_sinif.get("kaynak") == "onbellek"
                                                       else "llm", "gerekce": llm_sinif.get("gerekce")})
    else:
        _adim(adimlar, 2, t0, f"listede: '{malzeme}'", {"kaynak": "liste", "ana_malzeme": rm_modul.malzeme_ana(malzeme)})
    t0 = time.perf_counter()
    numune_tipi, kalinlik, yakit_turu, varsayilanlar = _varsayilan_doldur(malzeme, numune_tipi, kalinlik,
                                                                          yakit_turu)
    if kutup_varsay:                           # kütüphaneden gelen varsayılanlar önce doldu
        varsayilanlar = {**{k_: v_ for k_, v_ in kutup_varsay.items()}, **varsayilanlar}
    if motor_malzeme is None:
        motor_malzeme = malzeme
    # gaz + numune tipi verilmedi: geometri ve debi bilinmez -> varsayılan sızıntı (küre), gaz motoru kullanılmaz
    gaz_debisiz = False
    if not numune_verildi and motor_malzeme is not False and \
            motor_modulu.yakit_turu_bul(motor_malzeme, numune_tipi, yakit_turu) == "gaz":
        gaz_debisiz = True
        numune_tipi = GAZ_VARSAYILAN_NUMUNE
        varsayilanlar["numune_tipi"] = GAZ_VARSAYILAN_NUMUNE
        uyarilar.append(GAZ_DEBISIZ_UYARI)
    if not MALZEME_VARSAYILAN.get(rm_modul.malzeme_ana(malzeme)) and numune_tipi is None:
        uyarilar.append(f"'{malzeme}' için varsayılan yok ve numune tipi verilmedi; sonuç daha belirsiz.")
    if akis is None:
        uyarilar.append("Hava akışı bilinmiyor; en kötü durum (akış var) varsayıldı.")
    kw = dict(basinc=basinc, akis=akis, kalinlik=kalinlik, malzeme=malzeme, numune_tipi=numune_tipi,
              yakit_turu=yakit_turu, akis_yonu=akis_yonu, seyreltici=seyreltici)
    _adim(adimlar, 1, t0, "varsayılan kullanıldı: " + (", ".join(f"{k} = {v}" for k, v in varsayilanlar.items())
                                                       if varsayilanlar else "yok"),
          {"girdi": {"malzeme": malzeme, "oksijen": oksijen, "basinc": basinc, "g": g, "akis": akis,
                     "kalinlik": kalinlik, "numune_tipi": numune_tipi, "yakit_turu": yakit_turu,
                     "seyreltici": seyreltici}, "akis_bilinmiyor": akis is None})

    # --- risk modeli (Ay/Mars: uzay ve Dünya ayrı, kötü durum)
    t0 = time.perf_counter()
    if SINIRLAMA_G[0] <= g < SINIRLAMA_G[1]:
        gercek = _model_hesap(g, oksijen, **kw)
        t_model = time.perf_counter() - t0
        t7 = time.perf_counter()
        uc = {"uzay": _model_hesap(UZAY_G, oksijen, **kw), "gercek_g": gercek,
              "dunya": _model_hesap(DUNYA_G, oksijen, **kw)}
        kotu = max(uc.values(), key=lambda h: h["yanma_ihtimali"])
        sinirlar = [h["sonme_siniri"] for h in uc.values() if h["sonme_siniri"] is not None]
        sinir = min(sinirlar) if sinirlar else None
        ana = {"yanma_ihtimali": kotu["yanma_ihtimali"], "belirsizlik": kotu["belirsizlik"],
               "sonme_siniri": sinir}
        sinirlama = uc
        uyarilar.append("Kısmi g için deney verisi az; uzay, gerçek g ve Dünya sonuçlarının en kötüsü alındı.")
        kotu_ad = next(a for a, h_ in uc.items() if h_ is kotu)
        adimlar.append({"no": 3, "ad": ADIM_ADLARI[3], "sure_ms": round(1000 * t_model, 2),
                        "karar": f"p = {gercek['yanma_ihtimali']} (gerçek g = {g})",
                        "ayrinti": {"belirsizlik": gercek["belirsizlik"], "risk": gercek["risk_seviyesi"]}})
        _adim(adimlar, 7, t7, f"uygulandı: en kötü durum '{kotu_ad}' (p = {kotu['yanma_ihtimali']})",
              {a: {"g": h_["g"], "p": h_["yanma_ihtimali"], "sonme_siniri": h_["sonme_siniri"]} for a, h_ in uc.items()})
    else:
        h = _model_hesap(g, oksijen, **kw)
        ana = {k: h[k] for k in ("yanma_ihtimali", "belirsizlik", "sonme_siniri")}
        sinirlama = None
        _adim(adimlar, 3, t0, f"p = {h['yanma_ihtimali']} (g = {g})",
              {"belirsizlik": h["belirsizlik"], "risk": h["risk_seviyesi"]})
        adimlar.append({"no": 7, "ad": ADIM_ADLARI[7], "sure_ms": 0.0,
                        "karar": f"uygulanmadı (g = {g}; sınırlama yalnız {SINIRLAMA_G[0]} ≤ g < {SINIRLAMA_G[1]})",
                        "ayrinti": {}})
    p, sinir = ana["yanma_ihtimali"], ana["sonme_siniri"]
    if sinir is None:
        uyarilar.append(f"Sönme sınırı %{TARAMA[0]:g}-{TARAMA[-1]:g} O2 aralığında bulunamadı "
                        "(model bu aralıkta hiç 'yanar' demedi).")
    elif sinir <= TARAMA[0]:
        uyarilar.append(f"Sönme sınırı taramanın alt ucunda (%{TARAMA[0]:g}); gerçek sınır daha düşük olabilir.")

    # --- fizik motoru (gerçek g ile)
    # akış bilinmiyorsa MOTOR_AKISLAR denenir, yanma ihtimali en yüksek olan alınır (en kötü durum)
    # (taramada sönme sınırı hesaplanmaz; seçilen akış için bir kez hesaplanır)
    t0 = time.perf_counter()
    m, motor_akis = {}, None
    akislar = [akis] if akis is not None else MOTOR_AKISLAR
    if motor_malzeme is False or gaz_debisiz:  # kütüphane: uygun motor yok (ör. MMH) / gaz: debi bilinmiyor
        akislar = []
    for a in akislar:
        try:
            aday = motor_modulu.motor(g, oksijen, basinc, a, kalinlik, motor_malzeme, numune_tipi, seyreltici=seyreltici,
                                      yakit_turu=yakit_turu, min_oksijen_hesapla=len(akislar) == 1,
                                      belirsizlik_hesapla=len(akislar) == 1) or {}
        except Exception:
            aday = {}
        if aday.get("yanma") is not None and (m.get("yanma") is None or aday["yanma"] > m["yanma"]):
            m, motor_akis = aday, a
    if len(akislar) > 1 and m.get("yanma") is not None and m.get("min_oksijen") is None:
        try:
            m = motor_modulu.motor(g, oksijen, basinc, motor_akis, kalinlik, motor_malzeme, numune_tipi,
                                   seyreltici=seyreltici, yakit_turu=yakit_turu, belirsizlik_hesapla=True) or m
        except Exception:
            pass
    motor_belirsizlik = m.pop("_belirsizlik", None) if isinstance(m, dict) else None
    m = {k: v for k, v in m.items() if v is not None and not (isinstance(v, float) and math.isnan(v))}
    for u in m.pop("motor_uyarilari", None) or []:      # motorun kendi uyarıları (havuz, kalibre edilmemiş yakıt...)
        if u not in uyarilar:
            uyarilar.append(u)
    motor_kaynagi = m.get("motor_kaynagi")
    if motor_kaynagi not in ("ofm_tablo", "ofm+hafif"):
        m.pop("mesafe", None)                  # tablo kullanılmadıysa anlamsız (hep 0)
        m.pop("tablo_agirligi", None)
    motor_sonuc = ({k: (_yuvarla(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v)
                    for k, v in m.items()} if m.get("yanma") is not None else None)
    if motor_sonuc is not None and "motor_auc" not in motor_sonuc:
        motor_sonuc["motor_auc"] = None        # dürüst test yok / yakıt kalibre edilmedi -> motor ağırlığı 0
    if motor_sonuc is not None and motor_kaynagi == "gaz":
        for k in ("sonme_turu", "alev_boyu", "alev_yaricapi"):
            motor_sonuc.setdefault(k, None)
        motor_sonuc.setdefault("kalibre_degil", True)
    if motor_sonuc is not None and motor_kaynagi == "damla":
        motor_sonuc.setdefault("soguk_alev", False)
        motor_sonuc.setdefault("soguk_alev_suresi_s", None)
        motor_sonuc.setdefault("sonme_turu", None)
    if motor_sonuc is None and motor_malzeme is not False and not gaz_debisiz:
        uyarilar.append("Fizik motoru bu koşulu bilmiyor.")
    elif motor_sonuc is not None and (p >= 0.5) != (motor_sonuc["yanma"] > 0.5):
        uyarilar.append(f"Model ve motor çelişiyor: model '{'yanar' if p >= 0.5 else 'söner'}', "
                        f"motor '{'yanar' if motor_sonuc['yanma'] > 0.5 else 'söner'}' diyor.")

    t_motor = time.perf_counter() - t0
    adimlar.append({"no": 4, "ad": ADIM_ADLARI[4], "sure_ms": 0.0,
                    "karar": f"{motor_kaynagi or 'yok'} (motor_turu = {motor_modulu.MOTOR_TURU})",
                    "ayrinti": {"neden": _yonlendirme_nedeni(motor_kaynagi, yakit_turu, numune_tipi),
                                "not": "seçim motor çağrısının içinde; süresi 5. adıma dahil"}})
    adimlar.append({"no": 5, "ad": ADIM_ADLARI[5], "sure_ms": round(1000 * t_motor, 2),
                    "karar": ("sonuç yok" if motor_sonuc is None else
                              f"yanma = {motor_sonuc['yanma']}" + (f", akış {motor_akis} cm/s" if motor_akis is not None
                                                                   else "")),
                    "ayrinti": {"denenen_akislar": list(akislar), "secilen_akis": motor_akis,
                                "motor_auc": None if motor_sonuc is None else motor_sonuc.get("motor_auc"),
                                "en_kotu_durum": len(akislar) > 1}})

    # --- model + motor ağırlıklı birleşim (ağırlık = dürüst testteki AUC'nin rastgeleden üstünlüğü)
    t0 = time.perf_counter()
    yanma_birlesik, agirliklar = _birlestir(p, m, motor_kaynagi)
    if motor_sifir and agirliklar.get("motor"):   # kütüphane eşlemesi: motor kalibre değil -> ağırlık 0
        yanma_birlesik, agirliklar = p, {"model": 1.0, "motor": 0.0}
    # --- OpenFOAM motorunun ayrıntılı motoru (ayrı kaynak): koşu yakınsa (mesafe <= 1.5) ve deneyle doğrulandıysa katılır; yoksa ağırlık 0 + uyarı.
    #     OpenFOAM koşusu yoksa hiçbir şey değişmez (scripts/ofm_engine.py, ofm_runs.json).
    ofm = None
    try:
        ofm = openfoam_motor.degerlendir(g, oksijen, basinc, akis, kalinlik, malzeme, yakit_turu)
    except Exception:       # dizin bozuksa tahmin yine çalışır
        ofm = None
    if ofm:
        w_b = ofm["agirlik"]
        if w_b > 0 and ofm.get("yandi") is not None and yanma_birlesik is not None:
            yanma_birlesik = _yuvarla((1 - w_b) * yanma_birlesik + w_b * float(ofm["yandi"]))
            agirliklar = {"model": _yuvarla(agirliklar["model"] * (1 - w_b)), "motor": _yuvarla(agirliklar["motor"] * (1 - w_b)),
                          "ofm": _yuvarla(w_b)}
        elif ofm.get("uyari"):
            uyarilar.append(ofm["uyari"])
    _adim(adimlar, 6, t0, f"birleşik = {yanma_birlesik} (model {agirliklar['model']}, motor {agirliklar['motor']})",
          {"kural": "güç = max(0, 2(AUC - 0.5)); w_motor = güç_motor / (güç_model + güç_motor)"})
    t0 = time.perf_counter()
    _adim(adimlar, 8, t0, "sönme sınırı bulunamadı" if sinir is None else
          f"sınır %{sinir:g} O2, güvenlik katsayısı {_yuvarla(sinir / oksijen)}",
          {"tanim": "katsayı = sönme sınırı / ortam O2; > 1 güvenli, < 1 yanabilir",
           "tarama": f"%{TARAMA[0]:g}-{TARAMA[-1]:g}, 0.25 adım"})

    # --- güven
    t0 = time.perf_counter()
    gv = mk.guven_skoru(g, oksijen, basinc, malzeme, m, karsilastirma=_karsilastirmayi_al(), p_model=p)
    guven = {"skor": gv["guven"], "veri_bileseni": _yuvarla(gv["veri_bileseni"]),
             "uyum_bileseni": None if gv["uyum_bileseni"] is None else _yuvarla(gv["uyum_bileseni"]),
             "motor_bileseni": _yuvarla(gv["motor_basari"]), "agirliklar": gv["agirliklar"],
             "yakin_deney_yanma_orani": None if gv["yanma_orani"] is None else _yuvarla(gv["yanma_orani"]),
             "yakin_deney": gv["yakin_deney"],
             "motorlu_yakin_deney": gv["motorlu_yakin"], "yanan": gv["yanan"], "sonen": gv["sonen"],
             "motor_yontemi": gv["motor_yontem"]}
    guven_dusuk_v1 = guven["skor"] < GUVEN_ESIK
    if ana["belirsizlik"] > BELIRSIZLIK_ESIK:
        uyarilar.append(f"Model belirsizliği yüksek (±{ana['belirsizlik']:.3f}).")
    guven_v2 = _guven_v2(g, oksijen, basinc, malzeme, yanma_birlesik, p, ana["belirsizlik"], motor_sonuc,
                         motor_belirsizlik, motor_kaynagi, _karsilastirmayi_al(),
                         llm_eslendi=(girilen_malzeme if (llm_sinif is not None or
                                      (kutup_bilgi and kutup_bilgi["model_malzeme"] != kutup_bilgi["id"])) else None),
                         eslesme_kaynagi="kütüphane" if kutup_bilgi else "LLM")
    if guven_v2.get("bant") == "düşük" or (guven_v2.get("skor") is None and guven_dusuk_v1):
        uyarilar.append(_guven_dusuk_cumlesi(guven_v2, guven, motor_sonuc, motor_sifir or gaz_debisiz))
    _adim(adimlar, 9, t0, f"v2 {guven_v2['skor']}/100 ({guven_v2['bant']}), v1 {guven['skor']}/100",
          {"v2_bilesenler": guven_v2["bilesenler"], "v2_cezalar": [c["ad"] for c in guven_v2["cezalar"]]})

    sonuc = {
        "girdi": {"malzeme": malzeme, "oksijen": oksijen, "basinc": basinc, "g": g, "akis": akis,
                  "kalinlik": kalinlik, "numune_tipi": numune_tipi, "yakit_turu": yakit_turu,
                  "akis_yonu": akis_yonu, "seyreltici": seyreltici},
        "yanma_ihtimali": p,
        "yanma_birlesik": yanma_birlesik,
        "agirliklar": agirliklar,
        "belirsizlik": ana["belirsizlik"],
        "risk_seviyesi": rm_modul.risk_seviyesi(p),
        "sonme_siniri": sinir,
        "guvenlik_katsayisi": None if sinir is None else _yuvarla(sinir / oksijen),
        "sinirlama": sinirlama,
        "motor": motor_sonuc,
        "motor_turu": motor_modulu.MOTOR_TURU,
        "motor_kaynagi": motor_kaynagi,
        "motor_akis": motor_akis,
        "motor_belirsizlik": ({k: (_yuvarla(v, 4) if isinstance(v, float) else v) for k, v in motor_belirsizlik.items()}
                              if motor_belirsizlik else None),
        "guven": guven,
        "kullanilan_varsayilanlar": varsayilanlar,
        "uyarilar": uyarilar,
    }
    if ofm:
        sonuc["ofm"] = ofm
    if gaz_debisiz:
        sonuc["gas_engine_kullanilmadi"] = "debi bilinmiyor (numune tipi verilmedi)"
    if kutup_bilgi is not None:
        sonuc["kutuphane_eslesme"] = kutup_bilgi
        if motor_sonuc is not None and motor_malzeme not in (None, False) and motor_malzeme != malzeme:
            sonuc["motor"]["benzer_malzeme"] = motor_malzeme
    if llm_sinif is not None:
        sonuc["llm_siniflandirma"] = {k: llm_sinif.get(k) for k in
                                      ("girilen", "durum", "yakit_turu", "benzer_malzeme", "numune_tipi",
                                       "gerekce", "kaynak")}
    t0 = time.perf_counter()
    sonuc["guven_v2"] = guven_v2               # LLM'in KARAR satırı v2 skorunu kullansın (aynı değer sonda yine yazılır)
    if llm:
        try:
            import llm_analysis as llm_analysis
            yorum = llm_analysis.yorumla(_temiz(sonuc))   # kendi hatalarını yakalar, metin döndürür
            sonuc["llm_yorum"] = str(yorum) if yorum else "LLM yorumu alınamadı (boş cevap)"
        except Exception as e:     # modül yok vb. -> dashboard çökmesin
            sonuc["llm_yorum"] = f"LLM yorumu alınamadı ({type(e).__name__})"
        if sonuc["llm_yorum"].startswith("LLM yorumu alınamadı"):
            sonuc["uyarilar"].append(sonuc["llm_yorum"] + ".")
        _adim(adimlar, 11, t0, "alınamadı" if sonuc["llm_yorum"].startswith("LLM yorumu alınamadı") else "alındı",
              {"uzunluk": len(sonuc["llm_yorum"])})
    else:
        adimlar.append({"no": 11, "ad": ADIM_ADLARI[11], "sure_ms": 0.0, "karar": "istenmedi (llm=False)",
                        "ayrinti": {}})
    adimlar.append({"no": 10, "ad": ADIM_ADLARI[10], "sure_ms": 0.0, "karar": f"{len(sonuc['uyarilar'])} uyarı",
                    "ayrinti": {"uyarilar": list(sonuc["uyarilar"])}})
    t0 = time.perf_counter()
    kayit = os.environ.get(KAYIT_DOSYASI_ORTAM)
    sonuc["guven_v1"] = guven
    sonuc["guven_v2"] = guven_v2
    sonuc["sure_sn"] = round(time.perf_counter() - bas, 3)
    if kayit:
        try:
            if os.environ.get("YANGIN_VERI_KLASORU") and not os.path.isabs(kayit):
                kayit = os.path.join(os.environ["YANGIN_VERI_KLASORU"], kayit)
            os.makedirs(os.path.dirname(os.path.abspath(kayit)), exist_ok=True)
            with open(kayit, "a", encoding="utf-8") as f:
                f.write(json.dumps(_temiz({k: v for k, v in sonuc.items() if k != "adimlar"}), ensure_ascii=False)
                        + "\n")
            _adim(adimlar, 12, t0, f"yazıldı: {kayit}")
        except OSError as e:
            _adim(adimlar, 12, t0, f"yazılamadı ({type(e).__name__})")
    else:
        adimlar.append({"no": 12, "ad": ADIM_ADLARI[12], "sure_ms": 0.0,
                        "karar": f"kapalı ({KAYIT_DOSYASI_ORTAM} ortam değişkeni yok)", "ayrinti": {}})
    sonuc["adimlar"] = sorted(adimlar, key=lambda a: a["no"])
    return _temiz(sonuc)


# ------------------------------------------------------------------ dashboard grafik yardımcıları
# Hepsi tahmin() ile aynı girdileri alır (malzeme, oksijen, basinc, g, akis, kalinlik, numune_tipi,
# yakit_turu, akis_yonu, seyreltici; fazladan anahtarlar -örn. llm- yok sayılır), varsayılanları aynı
# şekilde doldurur ve json.dumps ile yazılabilir dict/list döndürür.
HARITA_G = (1e-5, 1.0)          # yanabilirlik haritası g aralığı (log)
AKIS_ARALIGI = (0.1, 100.0)     # akış eğrisi aralığı, cm/s (log)
AKIS_NOKTA = 40
ETIKET_KAYNAGI_ADI = {"psi": "NASA PSI", "makale_elle": "makale (elle)",
                      "gemma3_test": "makale (otomatik, Gemma)", "gemma3_sinir": "makale (otomatik, Gemma)"}


def _kosul(malzeme, oksijen=None, basinc=101.3, g=1.0, akis=None, kalinlik=None, numune_tipi=None,
           yakit_turu=None, akis_yonu=None, seyreltici="n2", **_):
    import llm_analysis as llm_analysis  # listede olmayan malzeme: kütüphane, yoksa önbellekteki kabul edilmiş LLM eşleşmesi
    numune_verildi = numune_tipi is not None and str(numune_tipi).strip() != ""
    kayit = None if llm_analysis.malzeme_biliniyor(malzeme) else kutuphanede_bul(malzeme)
    if kayit is not None and kayit.get("ozel") and kayit.get("_kaynak") == "kutuphane":
        raise ValueError(f"{kayit.get('ad')}: {kayit['ozel'].get('uyari')}")   # oksitleyici / yanmaz / pil: eğri yok
    if kayit is not None:
        model_m = _kutuphane_eslemesi(malzeme, kayit, llm_analysis.malzeme_biliniyor)[0]
        v = kayit.get("varsayilan") or {}
        yakit_turu = yakit_turu or kayit.get("yakit_turu")
        numune_tipi = numune_tipi or v.get("numune_tipi")
        kalinlik = kalinlik if kalinlik is not None else v.get("kalinlik_veya_cap_mm")
        malzeme = model_m
    elif not llm_analysis.malzeme_biliniyor(malzeme):
        k = llm_analysis.onbellekten(malzeme)
        if k and k.get("durum") == "kabul":
            malzeme = k["benzer_malzeme"]
            numune_tipi = numune_tipi or k["numune_tipi"]
            yakit_turu = yakit_turu or k["yakit_turu"]
    numune_tipi, kalinlik, yakit_turu, _v = _varsayilan_doldur(malzeme, numune_tipi, kalinlik, yakit_turu)
    gaz_debisiz = False                         # tahmin() ile aynı kural: gaz + numune tipi yok -> küre, motor yok
    if not numune_verildi and not (kayit is not None and kayit.get("motor_benzeri") is None) and \
            motor_modulu.yakit_turu_bul(malzeme, numune_tipi, yakit_turu) == "gaz":
        numune_tipi, gaz_debisiz = GAZ_VARSAYILAN_NUMUNE, True
    return dict(malzeme=malzeme, oksijen=oksijen, basinc=float(basinc), g=float(g), akis=akis,
                kalinlik=kalinlik, numune_tipi=numune_tipi, yakit_turu=yakit_turu, akis_yonu=akis_yonu,
                seyreltici=seyreltici, gaz_debisiz=gaz_debisiz)


def _model_kw(k):
    return {a: k[a] for a in ("basinc", "akis", "kalinlik", "malzeme", "numune_tipi", "yakit_turu",
                              "akis_yonu", "seyreltici")}


def oksijen_egrisi(**kosul):
    """Oksijen %5-60 (0.25 adım, tahmin()'deki tarama) boyunca yanma ihtimali ve ±1 belirsizlik bandı.
    Kısmi g'de (0.01 <= g < 0.9) tahmin() gibi uzay / gerçek g / Dünya'nın en kötüsü alınır;
    sonme_siniri tahmin()'in döndürdüğüyle aynıdır."""
    k = _kosul(**kosul)
    gler = (UZAY_G, k["g"], DUNYA_G) if SINIRLAMA_G[0] <= k["g"] < SINIRLAMA_G[1] else (k["g"],)
    ps, ss = [], []
    for g in gler:
        p, s, _ = _modeli_al().ihtimal(_kosullar(g, TARAMA, **_model_kw(k)))
        ps.append(p), ss.append(s)
    ps, ss = np.array(ps), np.array(ss)
    i = ps.argmax(axis=0)
    p, s = ps[i, np.arange(len(TARAMA))], ss[i, np.arange(len(TARAMA))]
    sinir = float(TARAMA[np.argmax(p >= 0.5)]) if (p >= 0.5).any() else None
    r = lambda x: [round(float(v), 4) for v in x]
    return _temiz({"oksijen": r(TARAMA), "ihtimal": r(p), "alt": r(np.clip(p - s, 0, 1)),
                   "ust": r(np.clip(p + s, 0, 1)), "sonme_siniri": sinir})


def yanabilirlik_haritasi(n_g=40, n_o2=40, **kosul):
    """g (log, HARITA_G) × oksijen (%5-60) ızgarasında risk modelinin yanma ihtimali.
    ihtimal[i][j] = g[i], oksijen[j] noktası. Her g kendi değeriyle hesaplanır (en kötü durum alınmaz)."""
    k = _kosul(**kosul)
    gler = np.logspace(math.log10(HARITA_G[0]), math.log10(HARITA_G[1]), int(n_g))
    o2 = np.linspace(TARAMA[0], TARAMA[-1], int(n_o2))
    df = pd.concat([_kosullar(g, o2, **_model_kw(k)) for g in gler], ignore_index=True)
    p, _s, _ = _modeli_al().ihtimal(df)
    p = p.reshape(len(gler), len(o2))
    return _temiz({"g": [float(f"{v:.4g}") for v in gler], "oksijen": [round(float(v), 3) for v in o2],
                   "ihtimal": [[round(float(v), 4) for v in satir] for satir in p]})


def akis_egrisi(**kosul):
    """Akış 0.1-100 cm/s (log, AKIS_NOKTA nokta) boyunca fizik motorunun yanma ihtimali (U-şekli).
    Motor o koşulu bilmiyorsa ilgili değer None."""
    k = _kosul(**kosul)
    akislar = np.logspace(math.log10(AKIS_ARALIGI[0]), math.log10(AKIS_ARALIGI[1]), AKIS_NOKTA)
    yanma = []
    for a in ([] if k["gaz_debisiz"] else akislar):
        try:
            m = motor_modulu.motor(k["g"], k["oksijen"], k["basinc"], float(a), k["kalinlik"], k["malzeme"],
                                   k["numune_tipi"], seyreltici=k["seyreltici"], yakit_turu=k["yakit_turu"],
                                   min_oksijen_hesapla=False) or {}
        except Exception:
            m = {}
        y = m.get("yanma")
        yanma.append(None if y is None else round(float(y), 4))
    if k["gaz_debisiz"]:
        yanma = [None] * len(akislar)           # debi bilinmiyor: gaz motoru kullanılmadı
    return _temiz({"akis": [float(f"{v:.4g}") for v in akislar], "motor_yanma": yanma})


def _link(x):
    """'(doi, url)' metni, düz URL ya da açıklama -> URL (yoksa None)."""
    x = "" if x is None or (isinstance(x, float) and math.isnan(x)) else str(x)
    m = __import__("re").search(r"https?://[^'\")\s]+", x)
    return m.group(0) if m else None


def yakin_deneyler(en_fazla=10, **kosul):
    """Bu koşula yakın gerçek deneyler (engine_check.yakin_maske: güven skorundaki tanımın aynısı),
    yakınlığa göre sıralı (|ΔO2|/3 + |Δlog basınç|/0.3; eşitlikte NASA/elle önce)."""
    k = _kosul(**kosul)
    t = _karsilastirmayi_al()
    y = t[mk.yakin_maske(t, k["g"], k["oksijen"], k["basinc"], k["malzeme"])].copy()
    lp = np.log10(y.basinc_kpa.clip(lower=1))
    y["_uzak"] = ((y.oksijen_yuzde - k["oksijen"]).abs() / mk.PENCERE["oksijen"]
                  + ((lp - math.log10(max(k["basinc"], 1))).abs() / mk.PENCERE["log_basinc"]).fillna(1))
    y["_oncelik"] = (~y.etiket_kaynagi.isin(["psi", "makale_elle"])).astype(int)
    y = y.sort_values(["_uzak", "_oncelik"], kind="stable").head(int(en_fazla))
    sayi = lambda v: None if pd.isna(v) else float(v)
    cikti = []
    for _, x in y.iterrows():
        aciklama = None if pd.isna(x.link) or _link(x.link) else str(x.link)
        cikti.append({"kaynak": ETIKET_KAYNAGI_ADI.get(x.etiket_kaynagi, str(x.etiket_kaynagi)),
                      "makale_id": str(x.makale_id), "link": _link(x.link), "aciklama": aciklama,
                      "g": sayi(x.g_seviyesi), "oksijen": sayi(x.oksijen_yuzde), "basinc": sayi(x.basinc_kpa),
                      "akis": sayi(x.akis_hizi_cm_s), "malzeme": str(x.malzeme_sade),
                      "yanar": None if pd.isna(x.yanar) else int(x.yanar)})
    return _temiz(cikti)


def main():
    a = argparse.ArgumentParser(description="Yangın riski tahmini (JSON yazar)")
    a.add_argument("--malzeme", required=True)
    a.add_argument("--oksijen", type=float, required=True)
    a.add_argument("--basinc", type=float, required=True)
    a.add_argument("--g", type=float, required=True)
    a.add_argument("--akis", type=float, help="cm/s; verilmezse bilinmiyor, 0 = akış yok")
    a.add_argument("--kalinlik", type=float)
    a.add_argument("--numune-tipi", dest="numune_tipi")
    a.add_argument("--yakit-turu", dest="yakit_turu")
    a.add_argument("--akis-yonu", dest="akis_yonu")
    a.add_argument("--seyreltici", default="n2")
    a.add_argument("--llm", action="store_true")
    arg = vars(a.parse_args())
    print(json.dumps(tahmin(**arg), ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
