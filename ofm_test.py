#!/usr/bin/env python3
"""ofm_test.py — OpenFOAM motoru uçtan uca (küçük SAHTE katı, sıvı, gaz koşu klasörleriyle; gerçek koşu değildir):
içe aktar → analiz → doğrulama → tablo (CSV) → dizin → render → yönlendirici (tahmin.ofm, ağırlık).
Geçici klasörde çalışır; projenin dosyalarına yazmaz.   python3 ofm_test.py
"""
import json
import math
import os
import sys
import tarfile
import tempfile
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))


def _yaz(yol, metin):
    yol = Path(yol); yol.parent.mkdir(parents=True, exist_ok=True); yol.write_text(metin, encoding="utf-8")


def _dat(yol, baslik, satirlar):
    _yaz(yol, "# Time\t" + baslik + "\n" + "".join("\t".join(f"{v:.8g}" for v in s) + "\n" for s in satirlar))


def sahte_kati(kok: Path, ad="sahte_saffire_2b", akis=25.0):
    """sibal: tutuşma 4 s, alev ucu 3 mm/s (deney 2,3 mm/s ±%50 içinde), 12 s."""
    c = kok / ad
    _yaz(c / "BILGI.json", json.dumps({"kosu": ad, "yakit_turu": "kati", "malzeme": "sibal", "deney": "saffire3", "boyut": "2B",
        "motor": "MOTOR_KILIT 1", "numune_x0_m": 0.15, "numune_x1_m": 1.09, "endTime_s": 12.0,
        "kosullar": {"g": 0, "oksijen": 21.0, "basinc": 101.3, "akis": akis, "kalinlik_mm": 0.33}, "notlar": "SAHTE test koşusu"}))
    _dat(c / "postProcessing/fluid/gazMax/0/volFieldValue.dat", "max(T)\tmax(CO2)\tmax(CH4)",
         [(t / 2, 1900.0 if t / 2 >= 4 else 400.0, 0.01, 0.0) for t in range(0, 25)])
    _dat(c / "postProcessing/tel/telT/0/volFieldValue.dat", "max(T)", [(t, 900.0) for t in range(0, 13)])
    _yaz(c / "constant/sibal/fvModels", "rho01 426.5;\nrhoInert 142.2;\n")
    for t in range(1, 13):
        n = 20
        xs = [0.15 + i * 0.002 for i in range(n)]
        ileri = 0.15 + max(0.0, t - 4) * 0.003
        rhoV = [(10.0 if x <= ileri else 426.5) for x in xs]
        satir = "".join(f"{x:.6f} {v:.3f} 0.0 300\n" for x, v in zip(xs, rhoV))
        _yaz(c / f"postProcessing/sibal/sibalYuzey/{t}/ust.xy", "# face_x rhoV rhoCh T\n" + satir)
    (c / "postProcessing/sibal/sibalKutle/0").mkdir(parents=True)
    (c / "postProcessing/fluid/sensGaz/0").mkdir(parents=True)
    _yaz(c / "log.run.son", "End\n")
    (c / "video.gif").write_bytes(b"GIF89a")
    return c


def sahte_sivi(kok: Path, ad="sahte_heptan_damla", eksik_alev=True):
    """n-heptan damlası (FLEX): K, FLEX'in en yakın testinin 1,1 katı; sönme çapı da FLEX'ten 1,1 kat (varsa)."""
    import pandas as pd
    d = pd.read_csv(KOK / "damla_flex_alev_ozet.csv")
    d = d[(d.yakit == "heptane") & d.yanma_hizi_mm2_s.notna() & d.sonme_capi_mm.notna()]
    r = d.iloc[((d.oksijen_yuzde - 21).abs() + (d.basinc_kpa - 101.3).abs() / 30).argmin()]
    K, d_s, d0 = float(r.yanma_hizi_mm2_s) * 1.1, float(r.sonme_capi_mm) * 1.1, 2.0
    t_s = (d0 ** 2 - d_s ** 2) / K
    c = kok / ad
    _yaz(c / "BILGI.json", json.dumps({"kosu": ad, "yakit_turu": "sivi", "malzeme": "n-heptane", "deney": "flex", "boyut": "2B",
        "kosullar": {"g": 0, "oksijen": 21.0, "basinc": 101.3, "akis": 0, "cap_mm": d0}, "cap_birim": "m", "notlar": "SAHTE test koşusu"}))
    ts = [i * 0.05 for i in range(0, int((t_s + 1.5) / 0.05) + 1)]
    _dat(c / "postProcessing/fluid/gazMax/0/volFieldValue.dat", "max(T)",
         [(t, 1800.0 if 0.1 <= t < t_s else (300.0 if t < 0.1 else 500.0)) for t in ts])
    _dat(c / "postProcessing/damla/damlaCap/0/damlaCap.dat", "d",
         [(t, math.sqrt(max(d0 ** 2 - K * t, 1e-6)) * 1e-3) for t in ts if d0 ** 2 - K * t > 0.01])
    if not eksik_alev:
        _dat(c / "postProcessing/fluid/alevYaricap/0/alevYaricap.dat", "r_f", [(t, 0.004 + 0.001 * t) for t in ts])
    (c / "video.mp4").write_bytes(b"\x00\x00\x00 ftypmp42")
    return c, {"K": K, "d_sonme": d_s, "t_sonme": t_s}


def sahte_gaz(kok: Path, ad="sahte_metan_alev", deney="bre"):
    c = kok / ad
    _yaz(c / "BILGI.json", json.dumps({"kosu": ad, "yakit_turu": "gaz", "malzeme": "methane", "deney": deney, "boyut": "3B",
        "kosullar": {"g": 0, "oksijen": 21.0, "basinc": 101.3, "akis": 0, "cap_mm": 5.0}, "notlar": "SAHTE test koşusu"}))
    _dat(c / "postProcessing/fluid/gazMax/0/volFieldValue.dat", "max(T)", [(t * 0.5, 2100.0 if t > 1 else 300.0) for t in range(0, 21)])
    _dat(c / "postProcessing/fluid/alevBoyutu/0/alevBoyutu.dat", "L\tR", [(t * 0.5, 0.03, 0.006) for t in range(0, 21)])
    return c


def main():
    tmp = Path(tempfile.mkdtemp(prefix="ofm_test_"))
    os.environ["AHUT_OFM_KOK"] = str(tmp)
    render = tmp / "render"; render.mkdir()
    os.environ["AHUT_RENDER"] = str(render)
    import ofm_ice_aktar as ia, ofm_motor as bm, ofm_sonuc_donustur as bsd
    gelen_ham = tmp / "ofm_ham"; gelen_ham.mkdir()
    kati = sahte_kati(gelen_ham)
    sivi, ref = sahte_sivi(gelen_ham)
    gaz = sahte_gaz(gelen_ham)
    gaz_yok = sahte_gaz(gelen_ham, "sahte_metan_dogrulanmamis", deney="yok")
    # katı: arşivle (tar.gz); diğerleri klasör olarak
    arsiv = tmp / "sahte_saffire_2b.tar.gz"
    with tarfile.open(arsiv, "w:gz") as t:
        t.add(kati, arcname=kati.name)
    sonuc = tmp / "ofm_sonuclar"; gelen = tmp / "ofm_gelen"
    sonuclar = {}
    for kaynak in (arsiv, sivi, gaz, gaz_yok):
        r = ia.ice_aktar(kaynak, gelen, sonuc, render)
        sonuclar[r["kosu"]] = r
    sirala = []
    def kontrol(ad, kosul, ayrinti=""):
        sirala.append(kosul)
        print(("GEÇTİ " if kosul else "KALDI ") + ad + (f"  [{ayrinti}]" if ayrinti else ""))
    k, s, g, gy = (sonuclar[x] for x in ("sahte_saffire_2b", "sahte_heptan_damla", "sahte_metan_alev", "sahte_metan_dogrulanmamis"))
    kontrol("katı: içe aktarıldı, durum 'yanıyor', tutuşma 4 s", k["sonuc"]["durum"] == "yanıyor" and k["sonuc"]["tutusma_zamani_s"] == 4.0, str(k["sonuc"].get("durum")))
    kontrol("katı: yayılma hızı ~3 mm/s, Saffire deneyi bandında (başarı 1.0)", k["dogrulama"]["basari"] == 1.0 and abs(k["sonuc"]["yayilma_hizi_mm_s"] - 3.0) < 0.3,
            f"{k['sonuc']['yayilma_hizi_mm_s']} mm/s; {k['dogrulama']['aciklama']}")
    kontrol("katı: eksik çıktı listesi (sibalKutle/sensGaz klasörleri boş değil → yalnız beklenenler)", isinstance(k["eksik"], list), str(k["eksik"]))
    kontrol("sıvı: K FLEX'in 1,1 katı ve tolerans içinde", s["sonuc"]["K_mm2_s"] is not None and abs(s["sonuc"]["K_mm2_s"] - ref["K"]) / ref["K"] < 0.05,
            f"K={s['sonuc']['K_mm2_s']} (beklenen {ref['K']:.3f})")
    kontrol("sıvı: sönme çapı bulundu", s["sonuc"]["sonme_capi_mm"] is not None and abs(s["sonuc"]["sonme_capi_mm"] - ref["d_sonme"]) < 0.08, str(s["sonuc"]["sonme_capi_mm"]))
    kontrol("sıvı: FLEX karşılaştırması başarı 1.0", s["dogrulama"]["basari"] == 1.0, f"{s['dogrulama']['deney_adi']}")
    kontrol("sıvı: eksik çıktı yazıldı (alevYaricap yok), uydurulmadı", any("alevYaricap" in e for e in s["eksik"]) and s["sonuc"]["alev_yaricapi_maks_mm"] is None)
    kontrol("gaz: Tmax 2100, alev boyu 30 mm, yarıçap 6 mm", g["sonuc"]["gaz_T_maks_K"] == 2100.0 and g["sonuc"]["alev_boyu_mm"] == 30.0 and g["sonuc"]["alev_yaricapi_mm"] == 6.0)
    kontrol("gaz (deney yok): doğrulanmadı → başarı None", gy["dogrulama"]["basari"] is None)
    # CSV
    csv_yol = sonuc / "openfoam_sonuclar_ofm.csv"
    import csv
    satirlar = list(csv.DictReader(open(csv_yol, encoding="utf-8-sig")))
    kontrol("tablo: openfoam_sonuclar_ofm.csv 4 satır, motor.py'nin okuduğu ada yazılmadı", len(satirlar) == 4 and csv_yol.name != "openfoam_sonuclar.csv", str([(x['malzeme'], x['yandi']) for x in satirlar]))
    kontrol("dizin: 4 koşu kayıtlı", len(bm.kosular()) == 4)
    kontrol("render: katı gif ve sıvı mp4 vaka adlandırmasıyla kopyalandı", len(k["render"]) == 1 and len(s["render"]) == 1 and k["render"][0].startswith("sibal_g0.0001_o21_p101.3_kosu-"), str(k["render"] + s["render"]))
    import sys as _s; _s.path.insert(0, str(KOK / "dashboard")); from cekirdek import sistem
    liste = sistem.render_listesi(render)
    kontrol("render: arayüz listesi vakayı dosya adından okuyor", all(x["vaka"] for x in liste) and len(liste) == 2, str([x["ad"] for x in liste]))
    # yönlendirici
    import tahmin
    t0 = tahmin.tahmin(malzeme="sibal", oksijen=21, basinc=101.3, g=0.0001, akis=25, kalinlik=0.33)
    kontrol("yönlendirici: yakın doğrulanmış katı koşu → 'ofm' alanı, ağırlık > 0", t0.get("ofm") and t0["ofm"]["agirlik"] > 0, str(t0.get("ofm", {}) and {kk: t0["ofm"][kk] for kk in ("kosu", "mesafe", "agirlik")}))
    kontrol("yönlendirici: birleşik ağırlıklarda 'ofm' anahtarı, tavan 0,5", "ofm" in t0["agirliklar"] and t0["agirliklar"]["ofm"] == 0.5, str(t0["agirliklar"]))
    os.environ["AHUT_OFM_KOK"] = str(tmp / "bos"); (tmp / "bos").mkdir()
    t_ref = tahmin.tahmin(malzeme="sibal", oksijen=21, basinc=101.3, g=0.0001, akis=25, kalinlik=0.33)
    kontrol("yönlendirici: OpenFOAM koşusu yokken 'ofm' alanı yok (sayılar değişmedi)", "ofm" not in t_ref and set(t_ref["agirliklar"]) == {"model", "motor"})
    os.environ["AHUT_OFM_KOK"] = str(tmp)
    t1 = tahmin.tahmin(malzeme="methane", oksijen=21, basinc=101.3, g=0.0001, akis=0)
    # iki gaz koşusu da yakın: doğrulanmışı (bre) varsa onunla; ağırlık yanma ihtimaline katılır
    kontrol("yönlendirici: gaz koşusu (bre) yakın, 'ofm' alanı var", bool(t1.get("ofm")), str(t1.get("ofm", {}) and (t1["ofm"]["kosu"], t1["ofm"]["agirlik"])))
    # doğrulanmamış tek koşu: ağırlık 0 + uyarı
    bm_liste = [x for x in bm.kosular() if x["kosu"] != "sahte_metan_alev"]
    bm.kayit_yaz(bm_liste)
    t2 = tahmin.tahmin(malzeme="methane", oksijen=21, basinc=101.3, g=0.0001, akis=0)
    kontrol("yönlendirici: doğrulanmamış koşu → ağırlık 0 + uyarı", t2.get("ofm") and t2["ofm"]["agirlik"] == 0 and any("doğrulanmadı" in u for u in t2["uyarilar"]),
            str(t2.get("ofm", {}) and t2["ofm"]["uyari"]))
    kontrol("yönlendirici: ağırlık 0 iken birleşik ihtimal değişmedi", "ofm" not in t2["agirliklar"])
    # --- Ayrıntılı çözüm: destek denetimi, vaka hazırlama (kopya), ağırlık tavanı yalnız Hızlı modda
    import ofm_vaka as bv
    paket = Path(os.environ.get("AHUT_MOTOR_C") or Path.home() / "Desktop" / "motor_c")
    kontrol("destek: PMMA desteklenmiyor (yalnız katı/SIBAL)", not bv.destek({"malzeme": "pmma", "kalinlik": 0.2}, malzeme_kanonik="pmma")["destekli"])
    kontrol("destek: SIBAL (kalınlık 0,33 mm ağ 0,32 mm'ye ±%5 içinde) destekleniyor", bv.destek({"malzeme": "sibal", "kalinlik": 0.33, "basinc": 101.3}, malzeme_kanonik="sibal")["destekli"])
    kontrol("destek: SIBAL ama kalınlık 0,6 mm → ağ uymuyor, desteklenmiyor", not bv.destek({"malzeme": "sibal", "kalinlik": 0.6, "basinc": 101.3}, malzeme_kanonik="sibal")["destekli"])
    kontrol("destek: sıvı (n-heptan) henüz desteklenmiyor", not bv.destek({"malzeme": "n-heptane"}, malzeme_kanonik="n-heptane")["destekli"])
    if (paket / "vaka").is_dir():
        kilit = bv.kilit_oku(paket)
        ky = bv.kutle_kesirleri(kilit, 21.2)
        kontrol("vaka: O2 kütle kesirleri toplamı 1, kilit bileşimine yakın", abs(sum(ky.values()) - 1) < 1e-9 and abs(ky["O2"] - kilit["ortam"]["Y_O2"]) < 1e-4, f"{ky['O2']:.6f}")
        h0, h1 = tmp / "vaka_g0", tmp / "vaka_g"
        bv.hazirla(h0, paket, {"oksijen": 30, "basinc": 70, "akis": 15, "g": 0}, 2, 3.0)
        n1 = bv.hazirla(h1, paket, {"oksijen": 30, "basinc": 70, "akis": 15, "g": 0.38}, 2, 3.0)["notlar"]
        okuma = lambda d, f: (d / f).read_text()
        kontrol("vaka: O2/basınç/akış/endTime/çekirdek kopyaya yazıldı", "0.329" in okuma(h0, "0/fluid/O2") and "70000" in okuma(h0, "0/fluid/p") and "(0.15 0 0)" in okuma(h0, "0/fluid/U")
                and "endTime         3;" in okuma(h0, "system/controlDict") and "numberOfSubdomains 2;" in okuma(h0, "system/decomposeParDict"))
        kontrol("vaka: g=0'da constant/fluid/g ve p_rgh YOK; g>0'da var", not (h0 / "constant/fluid/g").exists() and (h1 / "constant/fluid/g").exists() and (h1 / "0/fluid/p_rgh").exists() and "p_rgh" in okuma(h1, "system/fluid/fvSolution"))
        kontrol("vaka: paket (motor_c) değişmedi — 0/fluid/O2 hâlâ kilit değeri", "0.235494" in (paket / "vaka/0/fluid/O2").read_text())
    kontrol("kaldırma denetimi: günlükte p_rgh → açık; yalnız p → KAPALI", bv.kaldirma_kontrol("DICPCG:  Solving for p_rgh, Initial", True)[0] is True and bv.kaldirma_kontrol("DICPCG:  Solving for p, Initial", True)[0] is False)
    os.environ["AHUT_OFM_KOK"] = str(tmp)
    y = bm.yakin_kosular(0.0001, 21, 101.3, 25, 0.33, "sibal", "kati")
    kontrol("ağırlık: tavan 0,5 yalnız 'agirlik' (Hızlı birleşik); 'agirlik_tavansiz' tavansız (Ayrıntılı ana sonuç tavansız)", y and y[0]["agirlik"] == 0.5 and y[0]["agirlik_tavansiz"] == 1.0, str(y and (y[0]["agirlik"], y[0]["agirlik_tavansiz"])))
    print(f"\n{sum(sirala)}/{len(sirala)} GEÇTİ (geçici klasör: {tmp})")
    return 0 if all(sirala) else 1


if __name__ == "__main__":
    sys.exit(main())
