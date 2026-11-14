"""Yapisal-hata karar fonksiyonu ve Faz B erken durma kurali (ON-YAZILI; plan Revize 3).

Yapisal sonuc yalnizca su 4 sart BIRLIKTE saglanirsa verilir:
  a. vekil gercek-CFD LOO testini gecti
  b. taranan alt kutuda uyumlu theta yok
  c. sonuc vekil varyansi x2 iken de degismiyor (yine bos)
  d. 'test edilemedi' listesi doldurulmus (bos degil)
Biri saglanmazsa sonuc 'belirsiz'. Uyumlu theta varsa 'uyumlu_bolge_var'.
"""

# Faz B durma esikleri (kullanici tarafindan kabul edildi, sonuc goruldukten sonra DEGISTIRILMEZ)
FAZ_B_MAKS_KOSU = 4
HACIM_AZALMA_ESIK = 0.10        # art arda iki kosuda goreli azalma < %10
ARDISIK_BASARISIZ_MAKS = 2
KORELASYON_ESIK = 0.5           # |rho| > 0.5 ise tam kovaryans (karar kapisi: ilk 4 Faz A kosusundan sonra)


def yapisal_karar(loo_gecti, uyumlu_sayisi, dayanikli_bos, test_edilemedi):
    a = bool(loo_gecti)
    b = uyumlu_sayisi == 0
    c = bool(dayanikli_bos)
    d = len(test_edilemedi) > 0
    ayr = dict(a_loo=a, b_bos=b, c_dayanikli=c, d_liste=d)
    if uyumlu_sayisi > 0:
        return "uyumlu_bolge_var", ayr
    if a and b and c and d:
        return "yapisal (yalniz bu parametre kumesi ve taranan alt kutu kapsaminda; neden soylenmez)", ayr
    return "belirsiz", ayr


def korelasyon_modu(R_esdeger):
    """R: {sensor: korelasyon matrisi}. Herhangi bir sensorde disk-kose |rho| > esik ise 'tam', degilse 'kosegen'."""
    import numpy as np
    for s, R in R_esdeger.items():
        R = np.asarray(R)
        if R.shape[0] > 1:
            off = R[~np.eye(R.shape[0], dtype=bool)]
            if np.max(np.abs(off)) > KORELASYON_ESIK:
                return "tam"
    return "kosegen"


def faz_b_dur(hacimler, loo_gecti, yapisal_sartlar, ardisik_basarisiz, sure_bitti, dis_nokta_yapildi):
    """hacimler: [Faz B oncesi, 1. kosu sonrasi, ...] uyumlu bolge hacim orani (Faz B kosu sayisi = len-1).
    Dondurur (dur: bool, neden: str). Sira: azami -> zorunlu dis nokta -> yapisal -> basarisizlik -> sure -> hacim."""
    n = len(hacimler) - 1
    if n >= FAZ_B_MAKS_KOSU:
        return True, "azami 4 Faz B kosusu"
    if not dis_nokta_yapildi:
        return False, "zorunlu ilk Faz B kosusu (Ta1 < 21000) henuz yapilmadi"
    if yapisal_sartlar:
        return True, "uyumlu bolge bos ve yapisal sartlar b-d saglandi"
    if ardisik_basarisiz >= ARDISIK_BASARISIZ_MAKS:
        return True, "art arda iki tutusmama/cokme"
    if sure_bitti:
        return True, "sure butcesi bitti"
    if n >= 2 and loo_gecti:
        az = []
        for i in (n - 1, n):
            onceki, yeni = hacimler[i - 1], hacimler[i]
            az.append((onceki - yeni) / onceki if onceki > 0 else 0.0)
        if all(a < HACIM_AZALMA_ESIK for a in az):
            return True, "uyumlu bolge hacmi art arda iki kosuda goreli < %10 azaldi ve LOO gecti"
    return False, "devam"


# ---- Erken radyometre testi: DONDURULMUS TANIM (kullanici karari 08.11; ilk CFD'den sonra DEGISMEZ) ----
# Etiket: [tahmin: tasarim secimi, olculmedi]
# Gostergeler: R13 varis +1 ve +3 mW/cm2 (sensorlu_hedef02'de 1.08 ve 2.88 s: tutusmadan, 3.686 s, once; t < 3 s). Her gosterge AYRI sinanir.
# Model degerleri: varisi ufukta gorulen, tutusan tum CFD kosularindan (en az ERKEN_RAD_MIN_KOSU kosu; yoksa "bilinmiyor").
# aralik = max(model) - min(model)  [saniye];  fark = |deney varisi - medyan(model)|  [saniye];  oran = aralik / fark
# oran < ERKEN_RAD_ORAN (kesin esitsizlik) ve fark > 0  -> "parametre kumesi bu gostergeyi degistiremiyor (dogrudan gozlem)"
# fark == 0 -> "gosterge uyumlu";  aksi -> "gosterge parametrelerle degisiyor"
ERKEN_RAD_ORAN = 0.25
ERKEN_RAD_MIN_KOSU = 3
ERKEN_RAD_GOSTERGELER = ("R13_+1", "R13_+3")
ERKEN_RAD_ETIKET = "[tahmin: tasarim secimi, olculmedi]"


def erken_radyometre_testi(model_degerleri, deney_degeri):
    import numpy as np
    v = np.asarray([x for x in model_degerleri if x == x], float)
    if len(v) < ERKEN_RAD_MIN_KOSU:
        return "bilinmiyor (yetersiz kosu)"
    aralik = float(v.max() - v.min())
    fark = float(abs(deney_degeri - np.median(v)))
    if fark == 0.0:
        return "gosterge uyumlu"
    if aralik / fark < ERKEN_RAD_ORAN:
        return "parametre kumesi bu gostergeyi degistiremiyor (dogrudan gozlem)"
    return "gosterge parametrelerle degisiyor"
