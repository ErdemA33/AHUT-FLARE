"""Sahte arka uç: gerçek tahmin.py YOKKEN arayüzü denemek için (python3 dashboard_sunucu.py --mock).

Gerçek modelle ilgisi yok; sadece DASHBOARD.md'deki çıktı biçimlerini üretir. Sayılar anlamsızdır.
"""
import math
import time

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


def _p(o2, g, basinc):
    esik = 15 + 4 * math.log10(max(g, 1e-5)) * -0.5 + (101.3 - basinc) * 0.08
    return 1 / (1 + math.exp(-(o2 - esik) / 2.2))


def _sonme(g, basinc):
    for i in range(0, 221):
        o = 5 + 0.25 * i
        if _p(o, g, basinc) >= 0.5:
            return o
    return None


def _sonuc(g, o2, basinc):
    p = _p(o2, g, basinc)
    return {"yanma_ihtimali": round(p, 3), "belirsizlik": round(0.05 + 0.25 * (1 - abs(2 * p - 1)), 3),
            "sonme_siniri": _sonme(g, basinc)}


def _seviye(p):
    return "DÜŞÜK" if p < .2 else "ORTA" if p < .5 else "YÜKSEK" if p < .8 else "ÇOK YÜKSEK"


def tahmin(malzeme, oksijen, basinc, g, akis=None, kalinlik=None, numune_tipi=None, yakit_turu=None,
           akis_yonu=None, seyreltici="n2", llm=False):
    bas = time.perf_counter()
    var = {}
    d = MALZEME_VARSAYILAN.get(malzeme)
    uyar = []
    if d:
        for ad, v, kul in (("numune_tipi", d[0], numune_tipi), ("kalinlik", d[1], kalinlik),
                           ("yakit_turu", d[2], yakit_turu)):
            if kul is None and v is not None:
                var[ad] = v
        numune_tipi = numune_tipi or d[0]
        kalinlik = kalinlik if kalinlik is not None else d[1]
        yakit_turu = yakit_turu or d[2]
    elif numune_tipi is None:
        uyar.append(f"'{malzeme}' için varsayılan yok ve numune tipi verilmedi; sonuç daha belirsiz.")
    if akis is None:
        uyar.append("Hava akışı bilinmiyor; en kötü durum (akış var) varsayıldı.")
    sinirlama = None
    if 0.01 <= g < 0.9:
        sinirlama = {"uzay": dict(g=1e-4, **_sonuc(1e-4, oksijen, basinc)),
                     "gercek_g": dict(g=g, **_sonuc(g, oksijen, basinc)),
                     "dunya": dict(g=1.0, **_sonuc(1.0, oksijen, basinc))}
        for k, v in sinirlama.items():
            v["guvenlik_katsayisi"] = round(v["sonme_siniri"] / oksijen, 3) if v["sonme_siniri"] else None
            v["risk_seviyesi"] = _seviye(v["yanma_ihtimali"])
        kotu = max(sinirlama.values(), key=lambda h: h["yanma_ihtimali"])
        ana = {"yanma_ihtimali": kotu["yanma_ihtimali"], "belirsizlik": kotu["belirsizlik"],
               "sonme_siniri": min(v["sonme_siniri"] for v in sinirlama.values() if v["sonme_siniri"])}
        uyar.append("Kısmi g için deney verisi az; uzay, gerçek g ve Dünya sonuçlarının en kötüsü alındı.")
    else:
        ana = _sonuc(g, oksijen, basinc)
    p = ana["yanma_ihtimali"]
    gk = round(ana["sonme_siniri"] / oksijen, 3) if ana["sonme_siniri"] else None
    skor = 0 if (g < 0.9 and g > 0.01 and basinc < 80) else round(35 + 40 * (1 - abs(2 * p - 1)))
    if skor < 50:
        uyar.append("Güven düşük: bu koşula yakın deney az ya da fizik motoru orada zayıf.")
    if ana["belirsizlik"] > 0.3:
        uyar.append("Model belirsizliği yüksek.")
    mp = max(0, min(1, p + (0.35 if oksijen > 24 and p < .5 else 0)))
    motor = {"yanma": round(mp, 3), "min_oksijen": 16.0, "yayilma_hizi": None if yakit_turu != "kati" else 2.3,
             "sicaklik": 1450.0}
    if (p > .5) != (mp > .5):
        uyar.append("Model ile fizik motoru çelişiyor: model %d, motor %d (yanma ihtimali, %%)." % (p * 100, mp * 100))
    r = {
        "girdi": {"malzeme": malzeme, "oksijen": oksijen, "basinc": basinc, "g": g, "akis": akis,
                  "kalinlik": kalinlik, "numune_tipi": numune_tipi, "yakit_turu": yakit_turu,
                  "akis_yonu": akis_yonu, "seyreltici": seyreltici},
        **ana, "risk_seviyesi": _seviye(p), "guvenlik_katsayisi": gk, "sinirlama": sinirlama,
        "motor": motor, "motor_turu": "hafif", "motor_akis": akis if akis is not None else 10.0,
        "guven": {"skor": skor, "veri_bileseni": 0.6, "uyum_bileseni": 0.7 if skor else None,
                  "motor_bileseni": 0.5, "agirliklar": {"veri": 0.4, "uyum": 0.3, "motor": 0.3},
                  "yakin_deney": 12 if skor else 0, "yanan": 8, "sonen": 4, "motorlu_yakin_deney": 12,
                  "yakin_deney_yanma_orani": 0.67 if skor else None, "motor_yontemi": "SAHTE VERİ (mock)"},
        "kullanilan_varsayilanlar": var, "uyarilar": uyar, "sure_sn": round(time.perf_counter() - bas, 3),
    }
    if llm:
        time.sleep(3)
        r["llm_yorum"] = ("KARAR: " + r["risk_seviyesi"] + " risk.\nGerekçe:\n- Bu bir mock yorumdur.\n"
                          "- Gerçek yorum EVREN LLM'den gelir.\nÖneri: oksijeni düşürün.\nGüvenilirlik: orta.")
    return r


def oksijen_egrisi(malzeme="pmma", basinc=101.3, g=1.0, **_):
    o = [5 + 0.25 * i for i in range(221)]
    ih, alt, ust = [], [], []
    gs = [1e-4, g, 1.0] if 0.01 <= g < 0.9 else [g]
    for x in o:
        s = max(gs, key=lambda gg: _p(x, gg, basinc))
        p = _p(x, s, basinc)
        u = 0.05 + 0.25 * (1 - abs(2 * p - 1))
        ih.append(round(p, 4)); alt.append(round(max(0, p - u), 4)); ust.append(round(min(1, p + u), 4))
    return {"oksijen": o, "ihtimal": ih, "alt": alt, "ust": ust,
            "sonme_siniri": min(filter(None, [_sonme(gg, basinc) for gg in gs]), default=None)}


def yanabilirlik_haritasi(n_g=40, n_o2=40, basinc=101.3, **_):
    gs = [10 ** (-5 + 5 * i / (n_g - 1)) for i in range(n_g)]
    os_ = [5 + 55 * j / (n_o2 - 1) for j in range(n_o2)]
    return {"g": gs, "oksijen": os_, "ihtimal": [[round(_p(o, gg, basinc), 4) for o in os_] for gg in gs]}


def akis_egrisi(oksijen=21, **_):
    a = [10 ** (-1 + 3 * i / 39) for i in range(40)]
    return {"akis": a, "motor_yanma": [round(max(0, min(1, 0.3 + oksijen / 40 + 0.4 * math.exp(-((math.log10(x) - 0.7) ** 2) / 0.4)
                                                           - 0.7 * (x / 100) ** 1.5)), 4) for x in a]}


def yakin_deneyler(en_fazla=10, malzeme="pmma", oksijen=21, basinc=101.3, g=1.0, **_):
    out = []
    for i in range(en_fazla):
        o = oksijen + (i % 5 - 2) * 1.2
        out.append({"kaynak": ["NASA PSI", "makale (elle)", "makale (otomatik, Gemma)"][i % 3],
                    "makale_id": f"PSI-25_T{i}" if i % 3 == 0 else f"2001007{4000 + i}",
                    "link": None if i % 3 == 0 else "https://ntrs.nasa.gov/citations/20010074095",
                    "aciklama": "NASA PSI-25 (BASS-II) – Experimental table" if i % 3 == 0 else None,
                    "g": g, "oksijen": round(o, 1), "basinc": basinc, "akis": 5.0 if i % 2 else None,
                    "malzeme": malzeme, "yanar": 1 if o > 16 else 0})
    return out
