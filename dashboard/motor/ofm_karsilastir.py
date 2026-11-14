#!/usr/bin/env python3
"""ofm_karsilastir.py — OpenFOAM koşu sonucunu DENEYLE karşılaştırır ve doğrulama başarısını verir.

    karsilastir(sonuc, bilgi) -> {"deney", "olculer": [...], "basari": 0..1 | None, "aciklama"}

basari = tutan ölçülerin oranı (her ölçü deneyin tolerans bandında mı). Ölçü yoksa ya da deney "yok" ise basari None:
yönlendirici (ofm_motor.py) bu durumda OpenFOAM vaka ağırlığını 0 yapar ve "ayrıntılı motor bu koşulda doğrulanmadı" uyarısı verir.
Deney verisi yoksa / koşuyla karşılaştırılamıyorsa uydurulmaz; ne olduğu "aciklama"ya yazılır.

Deneyler:
  saffire3 / bass4 : ofm_dogrulama.DENEY (yayılma hızı ±%50, tutuşma aralığı, BASS yanma süresi ±%50)
  flex  (sıvı)     : damla_flex_alev_ozet.csv — aynı yakıt, en yakın FLEX testi (|ΔO2|/3 + |Δlog p|/0,3 <= 1,5):
                     tutuşma, K (±%35), sönme çapı (±%35)
  bre   (gaz)      : tahmin.yakin_deneyler — en yakın deneylerin yandı/söndü çoğunluğu ile OpenFOAM motorunun yandı/söndü'sü
"""
import math
from pathlib import Path

KOK = Path(__file__).resolve().parent
TOL_K = 0.35
TOL_YAYILMA = 0.50
YAKIT_ESLEME = {"heptane": "heptane", "n-heptane": "heptane", "heptan": "heptane", "nc7h16": "heptane",
                "methanol": "methanol", "metanol": "methanol", "ch3oh": "methanol"}


def _olcu(ad, ofm, deney, birim, tol_goreli=None, aralik=None):
    if ofm is None or (deney is None and aralik is None):
        return {"ad": ad, "ofm": ofm, "deney": deney if aralik is None else f"{aralik[0]}–{aralik[1]}", "birim": birim, "tuttu": None, "not": "değer yok"}
    if aralik is not None:
        tuttu = aralik[0] <= ofm <= aralik[1]
        return {"ad": ad, "ofm": ofm, "deney": f"{aralik[0]}–{aralik[1]}", "birim": birim, "tuttu": bool(tuttu)}
    fark = (ofm - deney) / abs(deney) if deney else None
    return {"ad": ad, "ofm": ofm, "deney": deney, "birim": birim, "tolerans": f"±%{tol_goreli * 100:g}",
            "fark_goreli": None if fark is None else round(fark, 3),
            "tuttu": None if fark is None else bool(abs(fark) <= tol_goreli)}


def _yandi(s):
    return s.get("tutusma_zamani_s") is not None


def _kati(sonuc, bilgi):
    import ofm_dogrulama as bd
    dz = bd.DENEY.get(bilgi.get("deney"))
    if not dz:
        return None, [], "deney tanımsız"
    o = []
    hiz = sonuc.get("yayilma_hizi_mm_s")
    o.append(_olcu("yayılma hızı", hiz, dz["yayilma_mm_s"], "mm/s", TOL_YAYILMA))
    if dz.get("tutusma"):
        o.append(_olcu("tutuşma zamanı", sonuc.get("tutusma_zamani_s"), None, "s", aralik=tuple(dz["tutusma"])))
    if bilgi.get("deney") == "bass4":
        x1 = bilgi.get("numune_x1_m", dz["numune_x1"]) - 0.002
        uc = [c["t"] for c in sonuc.get("alev_cephesi", []) if c.get("x_m") is not None and c["x_m"] >= x1]
        o.append(_olcu("yanma süresi", uc[0] if uc else None, dz["yanma_suresi_s"], "s", TOL_YAYILMA))
    return dz["ad"], o, None


def _flex(sonuc, bilgi, kosul):
    import pandas as pd
    f = KOK / "damla_flex_alev_ozet.csv"
    if not f.exists():
        return None, [], "damla_flex_alev_ozet.csv yok"
    d = pd.read_csv(f)
    yakit = YAKIT_ESLEME.get(str(bilgi.get("malzeme", "")).lower().strip())
    d = d[(d.yakit.astype(str).str.lower() == yakit)] if yakit else d.iloc[0:0]
    d = d.dropna(subset=["basinc_kpa", "oksijen_yuzde"])
    if d.empty:
        return None, [], "FLEX'te bu yakıt için test yok"
    o2, p = kosul.get("oksijen") or 21.0, kosul.get("basinc") or 101.3
    uz = ((d.oksijen_yuzde - o2).abs() / 3.0) + (d.basinc_kpa.apply(lambda x: abs(math.log10(max(x, 1)) - math.log10(max(p, 1)))) / 0.3)
    i = uz.idxmin()
    if uz[i] > 1.5:
        return None, [], f"en yakın FLEX testi uzak (mesafe {uz[i]:.2f} > 1,5)"
    t = d.loc[i]
    o = [_olcu("tutuşma (yandı)", 1.0 if _yandi(sonuc) else 0.0, 1.0, "", 0.5)]
    o[0]["tuttu"] = bool(_yandi(sonuc))
    o.append(_olcu("K", sonuc.get("K_mm2_s"), None if pd.isna(t.yanma_hizi_mm2_s) else float(t.yanma_hizi_mm2_s), "mm²/s", TOL_K))
    o.append(_olcu("sönme çapı", sonuc.get("sonme_capi_mm"), None if pd.isna(t.sonme_capi_mm) else float(t.sonme_capi_mm), "mm", TOL_K))
    ad = f"NASA FLEX test {t.test:g} ({t.yakit}, %{t.oksijen_yuzde:g} O₂, {t.basinc_kpa:g} kPa; mesafe {uz[i]:.2f})"
    return ad, [x for x in o if x["tuttu"] is not None], None


def _bre(sonuc, bilgi, kosul):
    try:
        import tahmin
        y = tahmin.yakin_deneyler(en_fazla=5, malzeme=bilgi.get("malzeme"), oksijen=kosul.get("oksijen") or 21.0,
                                  basinc=kosul.get("basinc") or 101.3, g=kosul.get("g") or 1.0)
    except Exception as e:  # noqa: BLE001
        return None, [], f"yakın deney sorgusu çalışmadı: {type(e).__name__}"
    y = [x for x in y if x.get("yanar") is not None]
    if not y:
        return None, [], "yakında deney yok"
    oran = sum(x["yanar"] for x in y) / len(y)
    deney_yandi = 1.0 if oran >= 0.5 else 0.0
    o = [{"ad": "yandı / söndü", "ofm": 1.0 if _yandi(sonuc) else 0.0, "deney": deney_yandi, "birim": f"(en yakın {len(y)} deneyin %{oran * 100:.0f}'i yandı)",
          "tuttu": bool((1.0 if _yandi(sonuc) else 0.0) == deney_yandi)}]
    return f"yakın deneyler (BRE / S-Flame / PSI; {len(y)} deney)", o, None


def karsilastir(sonuc, bilgi, kosul=None):
    kosul = kosul or {}
    deney = (bilgi.get("deney") or "yok").lower()
    tur = sonuc.get("yakit_turu")
    if deney in ("yok", "", "none"):
        return {"deney": "yok", "olculer": [], "basari": None, "aciklama": "BILGI.json'da deney yok: doğrulanmadı"}
    ad, olculer, hata = (None, [], f"deney '{deney}' bu yakıt türü ({tur}) için tanımlı değil")
    if tur == "kati" and deney in ("saffire3", "bass4"):
        ad, olculer, hata = _kati(sonuc, bilgi)
    elif tur == "sivi" and deney == "flex":
        ad, olculer, hata = _flex(sonuc, bilgi, kosul)
    elif tur == "gaz" and deney in ("bre", "sflame", "s-flame"):
        ad, olculer, hata = _bre(sonuc, bilgi, kosul)
    olc = [x for x in olculer if x.get("tuttu") is not None]
    basari = (sum(1 for x in olc if x["tuttu"]) / len(olc)) if olc else None
    return {"deney": deney, "deney_adi": ad, "olculer": olculer, "basari": None if basari is None else round(basari, 3),
            "aciklama": hata or (f"{sum(1 for x in olc if x['tuttu'])}/{len(olc)} ölçü deney bandında" if olc else "karşılaştırılabilir ölçü yok")}
