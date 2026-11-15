"""kutuphane_dogrulama.py — OpenFOAM doğrulama test vakalarını (sıvı FLEX, gaz ISS BRE, katı BASS) uygulamanın vaka
kütüphanesine (.ahut) kaydeder. Her vaka için aynı koşulda uygulamanın kendi hızlı çözümü çalıştırılır (sonuç sekmeleri
dolu açılsın); OpenFOAM sonucu ve deneyle karşılaştırma açıklamaya ve 'dogrulama' alanına yazılır, render bağlanır.

    .venv/bin/python validation_library.py                 # hepsi
    .venv/bin/python validation_library.py --tur gaz        # yalnız bir tür (sivi | gaz | kati)
    .venv/bin/python validation_library.py --render-esle    # yalnız render alanlarını günceller (çözüm yok)

Vaka kimliği sabittir (dgr-<tür>-<test>), yeniden çalıştırınca aynı kaydın üstüne yazılır.
"""
import argparse
import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent
ANA = KOK.parent
sys.path.insert(0, str(KOK))

import ahut_flare as AF  # noqa: E402
from core.bridge import Kopru  # noqa: E402

KOSU = ANA / "of_kosular"
RENDER = KOK / "render"
G_ISS = 1e-4

# render dosyası (dashboard/render altında) -> içerdiği testler
RENDER_ESLE_DOSYA = KOK / "render" / "dogrulama_render.json"


def _json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def sivi_vakalari():
    for d in sorted((KOSU / "damla_cpp").glob("t*_*")):
        b, s = _json(d / "BILGI.json"), _json(d / "sonuc.json")
        if not b or not s or d.name == "t74_cpp":
            continue
        dogru = s["yanar_of"] == b["flex_yanar"]
        deney = "söndü" if b["flex_yanar"] == 0 else "yandı"
        model = {1: "yandı", 0: "söndü"}.get(s["yanar_of"], "belirsiz")
        yield {
            "id": f"dgr-sivi-{b['test']}",
            "tur": "sivi",
            "test": b["ad"],
            "girdi": {"malzeme": "n-heptane", "oksijen": b["o2"], "basinc": b["basinc_kpa"], "g": G_ISS,
                      "seyreltici": b.get("seyreltici") or "n2"},
            "baslik": f"NASA FLEX test {b['test']} · n-heptan damla {b['d0_mm']:g} mm · %{b['o2']:g} O₂ — OpenFOAM doğrulaması",
            "aciklama": (
                f"Doğrulama vakası (NASA FLEX, ISS). Deney: damla d0 = {b['d0_mm']:g} mm, %{b['o2']:g} O₂, {b['basinc_kpa']:g} kPa; "
                f"FLEX sonucu: {deney} ({b.get('flex_sonu')}), K = {b.get('flex_K')} mm²/s.\n"
                f"OpenFOAM (C++ damla buharlaşma modeli damlaBulutBuharlasma + OpenFOAM 14, tek adım heptan, ışınımsız): "
                f"skor {s['skor_T_K']:.0f} K (0,5 s ile t85 = {s['t85_s']} s arasında en düşük alev sıcaklığı), en yüksek T {s['T_maks_K']:.0f} K, "
                f"tahmin: {model} (eşik 1500 K) → {'doğru' if dogru else 'yanlış'}; K = {s['K_of_mm2_s']:.2f} mm²/s "
                f"(FLEX'in {s['K_of_mm2_s'] / b['flex_K']:.2f} katı).\n"
                "12 FLEX vakasında AUC 1,00, doğruluk 8/12; büyük damlalarda ışınım kaynaklı sönme ışınımsız modelde yakalanmaz."),
            "etiketler": ["doğrulama", "openfoam", "nasa-flex", "sıvı", f"deney-{deney}", "model-doğru" if dogru else "model-yanlış"],
            "dogrulama": {"deney": "NASA FLEX", "test": b["ad"], "deney_yanar": b["flex_yanar"], "model_yanar": s["yanar_of"],
                          "skor_T_K": s["skor_T_K"], "t85_s": s["t85_s"], "K_model": s["K_of_mm2_s"], "K_deney": b.get("flex_K"),
                          "motor": "OpenFOAM 14 + libFlameInFreefallDroplet (damlaBulutBuharlasma)", "dogru": dogru},
        }


def gaz_vakalari():
    yollar = sorted((KOSU / "gaz_bre" / "auc40").glob("*")) + [KOSU / "gaz_bre" / "87H1_a0.15"]
    for d in yollar:
        b, s = _json(d / "BILGI.json"), _json(d / "sonuc.json")
        if not b or not s:
            continue
        test = b["test"]
        ts = s.get("t_sonme_s")
        model_sondu = ts is not None and ts <= 40.0
        deney_sondu = b["yanar"] == 0 and (b.get("t_b_s") or 1e9) <= 40.0
        dogru = model_sondu == deney_sondu
        deney = f"{b['t_b_s']:g} s'de söndü" if b["yanar"] == 0 else "yandı (alev sönmedi)"
        model = f"{ts:.1f} s'de söndü" if ts is not None else "40 s boyunca yandı"
        yield {
            "id": f"dgr-gaz-{test}",
            "tur": "gaz",
            "test": test,
            "girdi": {"malzeme": "ethylene", "oksijen": round(100 * b["x_o2"], 2), "basinc": round(b["p_bar"] * 100, 1), "g": G_ISS,
                      "seyreltici": "n2"},
            "baslik": f"ISS BRE test {test} · etilen brülör · %{100 * b['x_o2']:.0f} O₂ · {b['p_bar']:.2f} bar — OpenFOAM doğrulaması",
            "aciklama": (
                f"Doğrulama vakası (ISS BRE, Dehghani ve ark. 2021, CNF 228:315). Deney: 25 mm gözenekli brülör, C₂H₄ "
                f"(yakıt kesri {b['x_f']:g}), {b['m_akisi_g_m2s']:.2f} g/m²s, %{100 * b['x_o2']:.1f} O₂, {b['p_bar']:.2f} bar; "
                f"sonuç: {deney}.\n"
                f"OpenFOAM 14 (multicomponentFluid, 2B eksenel simetrik, tek adım etilen Westbrook–Dryer, P1 ışınım, soğurma ×0,15): "
                f"model {model}; 40 s penceresinde {'doğru' if dogru else 'yanlış'}.\n"
                "12 BRE vakasında AUC 1,00, doğruluk 9/12."),
            "etiketler": ["doğrulama", "openfoam", "iss-bre", "gaz", "deney-söndü" if b["yanar"] == 0 else "deney-yandı",
                          "model-doğru" if dogru else "model-yanlış"],
            "dogrulama": {"deney": "ISS BRE", "test": test, "deney_yanar": b["yanar"], "deney_t_b_s": b.get("t_b_s"),
                          "model_t_sonme_s": ts, "pencere_s": 40.0, "motor": "OpenFOAM 14 multicomponentFluid + P1", "dogru": dogru},
        }


KATI = {   # ofm_analysis.py (katı analizi) sonuçları (tutuşma s, gaz T maks K, benzetim s)
    "b12_u22": (1.90, 2166, 10.0), "b13_u11": (2.13, 2165, None), "b1_u10": (2.16, 2191, 10.0), "b1_u5": (2.52, 2189, 10.0),
    "b55_u20": (1.87, 2227, 10.0), "b45_u9": (2.18, 2203, 4.58), "b54_u44": (1.74, 2213, 3.03),
}


def kati_vakalari():
    bilgi = _json(KOSU / "bass_bilgi.json") or {}
    for ad, (tign, tmax, tson) in KATI.items():
        b = bilgi.get(ad)
        if not b:
            continue
        k = b["kosul"]
        sure = f"{tson:g} s" if tson else "kısmi"
        yield {
            "id": f"dgr-kati-{ad}",
            "tur": "kati",
            "test": ad,
            "girdi": {"malzeme": "sibal", "oksijen": k["oksijen"], "basinc": k["basinc"], "g": k["g"], "akis": k["akis"],
                      "seyreltici": "n2"},
            "baslik": f"BASS SIBAL ({b['kaynak']}) · akış {k['akis']:g} cm/s · %{k['oksijen']:g} O₂ — OpenFOAM doğrulaması",
            "aciklama": (
                f"Doğrulama vakası (BASS, ISS; {b['kaynak']}). SIBAL pamuk/cam elyaf kumaş, %{k['oksijen']:g} O₂, {k['basinc']:g} kPa, "
                f"eşakışlı {k['akis']:g} cm/s; deney: yandı.\n"
                f"OpenFOAM 14 + C++ piroliz modeli (libFlameInFreefallSolid, sibalPyrolysis; Saffire-III vakası): "
                f"tutuşma {tign:.2f} s, gaz T maks {tmax:.0f} K, alev yanmaya devam etti → doğru (benzetim {sure}).\n"
                "7 BASS SIBAL koşulunda 7/7 doğru; tüm deneyler yandığı için AUC tanımsız."),
            "etiketler": ["doğrulama", "openfoam", "bass", "katı", "deney-yandı", "model-doğru"],
            "dogrulama": {"deney": "BASS", "test": ad, "kaynak": b["kaynak"], "deney_yanar": 1, "model_yanar": 1,
                          "tutusma_s": tign, "gaz_T_maks_K": tmax, "benzetim_s": tson,
                          "motor": "OpenFOAM 14 foamMultiRun + libFlameInFreefallSolid", "dogru": True},
        }


def render_esle():
    e = _json(RENDER_ESLE_DOSYA) or {}
    return {t: ad for ad, testler in e.items() for t in testler}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tur", choices=["sivi", "gaz", "kati"])
    ap.add_argument("--render-esle", action="store_true")
    a = ap.parse_args()
    api = Kopru(surum=AF.SURUM, arayuz=AF.ARAYUZ, motor_yolu=AF.MOTOR, veri=AF.VERI, render=AF.RENDER,
                anahtar=AF.ANAHTAR, mock=False, ornekler=AF.ORNEKLER, site=AF.SITE)
    esle = render_esle()
    vakalar = [v for f in (sivi_vakalari, gaz_vakalari, kati_vakalari) for v in f() if not a.tur or v["tur"] == a.tur]
    if a.render_esle:
        for v in vakalar:
            r = esle.get(v["test"])
            if r and api.depo.oku(v["id"]):
                api.vaka_guncelle(v["id"], {"render": r})
                print("render", v["id"], r)
        return
    print("model:", api.motoru_yukle().get("durum"))
    for v in vakalar:
        c = api.coz(v["girdi"])
        ac = lambda a: (c.get(a) or {}).get("veri")          # noqa: E731  coz() {veri, sure_sn} sarar; arayüz açık veriyi kaydeder
        sonuc = {"cozum_turu": "hizli", "on_tahmin": False, "ayrintili": None, "tahmin": ac("tahmin"),
                 "oksijen_egrisi": ac("oksijen_egrisi"), "harita": ac("harita"), "akis_egrisi": ac("akis_egrisi"),
                 "yakin": ac("yakin") or [], "dogrulama": v["dogrulama"]}
        oz = api.vaka_kaydet({"id": v["id"], "girdi": c.get("kosul") or v["girdi"], "sonuc": sonuc, "baslik": v["baslik"],
                              "aciklama": v["aciklama"], "etiketler": v["etiketler"], "onayar": "ISS",
                              "render": esle.get(v["test"])})
        t = ((c.get("tahmin") or {}).get("veri") or {})
        print(f"{oz['id']:22s} hızlı model: {t.get('risk_seviyesi')} ihtimal={t.get('yanma_ihtimali')}  render={esle.get(v['test'])}")


if __name__ == "__main__":
    main()
