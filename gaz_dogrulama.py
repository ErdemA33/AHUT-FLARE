#!/usr/bin/env python3
"""
gaz_dogrulama.py — gaz_motoru.py'nin dürüst testleri, profil ve grafik (python3 gaz_motoru.py --dogrula / --profil
/ --grafik ile çağrılır).

Dürüst testler (hiçbirinde test verisi kalibrasyona girmez):
  A) BRE içinde: gün (test serisi) dışarıda bırakma (8 kat), yakıt seyreltmesi X_f dışarıda (1.0 <-> 0.5),
     basınç dışarıda (1 bar <-> 0.56-0.71 bar), O2 dışarıda (>= 0.30 ile kalibre -> < 0.30 test)
  B) Deney bazında: BRE ile kalibre -> küre (Irace 2021, 4 etiketli test; PSI-10 Flame Design T_ad / Z_st),
                    küre (Irace 4 test) ile kalibre -> BRE (geometri katsayıları kuramsal, k_v = k_y = 1)
     Pozitif-yalnız (tutuşmuş alevler, sönme etiketi yok): PSI-20 BRE özeti (CH4 = dışarıdaki yakıt),
     PSI-23 s-Flame (He seyreltici, H2 / CH4 / karışımlar), PSI-21/22 CLD / E-FIELD (jet geometrisi):
     "yanabilir" = bilinmeyen debi aralığında (deney donanım aralığı) yanma >= 0.5 olan bir debi var mı.
  C) Literatür kontrol seti: etiketli_gemma3.csv gaz noktaları (makalelerden; 1 g ve µg ayrı).
Çıktılar: gaz_dogrulama.csv (nokta bazında), gaz_dogrulama_ozet.csv, gaz_dogrulama_ozet.json
"""
import json
import math
import os
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

import gaz_motoru as gm

KOK = gm.KOK


def _isci(arg):
    """kalibrasyon işçisi: (ad, eğitim maskesi, sabit_ek) -> parametreler"""
    os.environ["OMP_NUM_THREADS"] = "1"
    ad, egitim, sabit_ek = arg
    t = gm.bre_oku()
    par, kay, _ = gm.kalibre(t[np.asarray(egitim)].reset_index(drop=True), baslangic_sayisi=8, sabit_ek=sabit_ek)
    return ad, par, kay


def _isci_irace(_):
    """küre (Irace 4 test) ile kalibre: yalnız ln_Crad ve s (k_s = 1, geometri kuramsal)."""
    from scipy.optimize import minimize
    ir = gm.irace_oku()
    gi = gm.irace_girdi(ir)
    y = ir.yanar.to_numpy(float)

    is_m = gm.IS_MODELI != "0"     # is modelinde ışınım serbestliği fv_ppm (C_gaz = 1)
    ad0 = "fv_ppm" if is_m else "ln_Crad"

    def f(v):
        par = {"ln_Crad": 0.0, "fv_ppm": 0.0, "ln_ks": 0.0, "s": v[1], "k_v": 1.0, "k_y": 1.0, ad0: v[0]}
        q = np.clip(gm.hesapla(par, **gi)["yanma"], 1e-6, 1 - 1e-6)
        return -np.sum(y * np.log(q) + (1 - y) * np.log(1 - q))
    en = None
    for x0 in ([0.0, 0.3], [1.0, 0.5], [-1.0, 0.2], [2.0, 1.0]):
        x0 = [min(max(x0[0], gm.SINIRLAR[ad0][0] if is_m else -3), 20 if is_m else 3), x0[1]]
        x0[0] = abs(x0[0]) if is_m else x0[0]
        r = minimize(f, x0, method="L-BFGS-B", bounds=[(0.0, 20.0) if is_m else gm.SINIRLAR["ln_Crad"],
                                                       gm.SINIRLAR["s"]])
        en = r if en is None or r.fun < en.fun else en
    return {"ln_Crad": 0.0, "fv_ppm": 0.0, "ln_ks": 0.0, "s": float(en.x[1]), "k_v": 1.0, "k_y": 1.0,
            ad0: float(en.x[0])}, float(en.fun)


def isci_sayisi():
    n = gm.bos_cekirdek()
    print(f"çalışan python işi sayımına göre işçi: {n}")
    return n


# ------------------------------------------------------------------ yanabilirlik taraması (pozitif-yalnız)
def yanabilir(par, gi_list):
    """her durum için birden çok (debi, basınç ..) varyantı: en az biri yanma >= 0.5 ise yanabilir."""
    out = []
    for gi in gi_list:
        r = gm.hesapla(par, **gi)
        out.append(float(r["yanma"].max()))
    return np.array(out)


def _tekrar(gi1, n, **degis):
    d = {k: np.repeat(v, n, axis=-1) if isinstance(v, np.ndarray) else v for k, v in gi1.items()}
    for k, v in degis.items():
        d[k] = np.asarray(v, float)
    return d


def sflame_girdi(t):
    gil = []
    for x in t.itertuples():
        Xd, _ = gm.yakit_akimi(x.yakit.replace("with", " "), None, "he" if x.seyreltici == "he" else None)
        XF = gm.vektor(Xd)[:, None]
        XO = gm.ortam(x.oksijen, x.seyreltici)[:, None]
        md = np.geomspace(0.2, 20, 25) * 1e-6        # s-Flame debileri tabloda yok: 0.2-20 mg/s taranır
        gil.append(dict(geo=np.zeros(len(md), int), XF=np.repeat(XF, len(md), 1), XO=np.repeat(XO, len(md), 1),
                        p=np.full(len(md), 1.0e5), g=np.full(len(md), 1e-4), mdot=md,
                        Rs=np.full(len(md), 6.4e-3 / 2), U=np.zeros(len(md)), Ts=np.full(len(md), 300.0)))
    return gil


def psi20_girdi(t):
    gil = []
    for x in t.itertuples():
        Xd, _ = gm.yakit_akimi(x.yakit.replace("100%", "").replace("50%", "50% "), None, None)
        XF = gm.vektor(Xd)[:, None]
        XO = gm.ortam(x.oksijen, "n2")[:, None]
        mm, pp = np.meshgrid(np.geomspace(0.5, 12.0, 14), np.array([0.56, 0.7, 1.0]))   # Tablo 1 (~1-12) + 0.5
        mm, pp = mm.ravel(), pp.ravel()
        Rb = x.cap_mm / 2e3
        n = len(mm)
        gil.append(dict(geo=np.ones(n, int), XF=np.repeat(XF, n, 1), XO=np.repeat(XO, n, 1), p=pp * 1e5,
                        g=np.full(n, 1e-4), mdot=mm * 1e-3 * math.pi * Rb ** 2, Rs=np.full(n, Rb), U=np.zeros(n),
                        Ts=np.full(n, 300.0)))
    return gil


def jet_girdi(t, kullan="x_ust"):
    gil = []
    O = gm.oz()
    for x in t.itertuples():
        xf = getattr(x, kullan)
        XF = gm.vektor({x.yakit: xf, "N2": 1 - xf} if xf < 1 else {x.yakit: 1.0})[:, None]
        XO = gm.ortam(21, "n2")[:, None]
        U = np.geomspace(0.05, 1.0, 15)            # CLD/E-FIELD: E-FIELD 15-19 cm/s; aralık 5-100 cm/s
        Rs = 2.1e-3 / 2
        MF = float((XF[:, 0] * O.M).sum())
        rhoF = 1.0e5 * MF / (gm.R_U * gm.T_INF)
        n = len(U)
        gil.append(dict(geo=np.full(n, 2), XF=np.repeat(XF, n, 1), XO=np.repeat(XO, n, 1), p=np.full(n, 1.0e5),
                        g=np.full(n, 1e-4), mdot=rhoF * U * math.pi * Rs ** 2, Rs=np.full(n, Rs), U=U,
                        Ts=np.full(n, 300.0)))
    return gil


# ------------------------------------------------------------------ literatür kontrol seti
DESTEK_SEYR = {None, "n2", "co2", "he", "ar", "air", "nitrogen", "helium", "argon"}


def literatur_girdi(L):
    satir, gil, atla = [], [], {}
    for k, x in L.iterrows():
        Xd, notlar = gm.yakit_akimi(x.malzeme_sade, None, None)
        sy = None if pd.isna(x.seyreltici) else str(x.seyreltici).lower()
        if Xd is None:
            atla["yakıt tanınmadı"] = atla.get("yakıt tanınmadı", 0) + 1
            continue
        if sy not in DESTEK_SEYR:
            atla[f"seyreltici {sy}"] = atla.get(f"seyreltici {sy}", 0) + 1
            continue
        if pd.isna(x.oksijen_yuzde) or not 0 < x.oksijen_yuzde <= 100:
            atla["O2 yok"] = atla.get("O2 yok", 0) + 1
            continue
        hz, _ = gm.girdi_hazirla(x.g_seviyesi if x.g_seviyesi > 0 else 1e-4, x.oksijen_yuzde,
                                 x.basinc_kpa if pd.notna(x.basinc_kpa) and x.basinc_kpa > 0 else 101.325,
                                 x.akis_hizi_cm_s if pd.notna(x.akis_hizi_cm_s) and x.akis_hizi_cm_s > 0 else None,
                                 None, x.malzeme_sade, "gas_jet", sy or "n2")
        if hz is None:
            atla["girdi"] = atla.get("girdi", 0) + 1
            continue
        gil.append(hz[0])
        satir.append(k)
    return satir, gil, atla


def birlestir(gil):
    return {k: np.concatenate([g[k] for g in gil], axis=-1) for k in gil[0]}


# ------------------------------------------------------------------ ana doğrulama
def dogrula_main():
    bas = time.time()
    t = gm.bre_oku()
    gi_bre = gm.bre_girdi(t)
    par_tum = gm.varsayilan_parametreler()           # --kalibre sonucu (yeniden kalibre edilmez)
    n = len(t)
    gunler = sorted(t.gun.unique())
    isler = [(f"gun_{g}", (t.gun != g).to_numpy().tolist(), None) for g in gunler]
    xf1 = (t.X_f == 1).to_numpy()
    p1 = (t.p_bar > 0.9).to_numpy()
    o_hi = (t.X_O2 >= 0.30).to_numpy()
    isler += [("Xf1_ile", xf1.tolist(), None), ("Xf05_ile", (~xf1).tolist(), None),
              ("p1bar_ile", p1.tolist(), None), ("pdusuk_ile", (~p1).tolist(), None),
              ("O2yuksek_ile", o_hi.tolist(), None)]
    with Pool(isci_sayisi()) as havuz:
        irace_is = havuz.apply_async(_isci_irace, (None,))
        sonuc = {ad: (par, kay) for ad, par, kay in havuz.map(_isci, isler)}
        par_kure, kay_kure = irace_is.get()
    print(f"kalibrasyonlar bitti: {time.time() - bas:.0f} s")

    tahmin = {}
    r_tum = gm.hesapla(par_tum, **gi_bre)
    # gün dışarıda: her test kendi gününün dışarıda bırakıldığı modelle
    cv = {k: np.full(n, np.nan) for k in ("yanma", "chi_r", "q_flux", "y_f", "R", "T_f")}
    for g in gunler:
        m = (t.gun == g).to_numpy()
        r = gm.hesapla(sonuc[f"gun_{g}"][0], **gi_bre)
        for k in cv:
            cv[k][m] = r[k][m]
    tahmin["gun_disarida"] = cv

    def tek(ad, maske_test):
        r = gm.hesapla(sonuc[ad][0], **gi_bre)
        return {k: np.where(maske_test, r[k], np.nan) for k in cv}
    ozet = []

    def ekle(deney, alt, tt, rr, notu=""):
        o = gm.bre_olcutler(tt.reset_index(drop=True), {k: np.asarray(v) for k, v in rr.items()})
        ozet.append({"deney": deney, "alt_kume": alt, **o, "not": notu})

    ekle("BRE içeride (tüm veriyle kalibre)", "59 test", t, r_tum, "eğitim hatası, dürüst değil")
    ekle("BRE gün dışarıda (8 kat)", "59 test", t, cv, "her gün kalan 7 günle kalibre")
    for ad, mk, aciklama in (("Xf1_ile", ~xf1, "X_f=1 ile kalibre -> X_f=0.5 (N2 seyreltik yakıt) test"),
                             ("Xf05_ile", xf1, "X_f=0.5 ile kalibre -> X_f=1 test"),
                             ("p1bar_ile", ~p1, "~1 bar ile kalibre -> 0.56-0.71 bar test"),
                             ("pdusuk_ile", p1, "0.56-0.71 bar ile kalibre -> ~1 bar test"),
                             ("O2yuksek_ile", ~o_hi, "X_O2>=0.30 ile kalibre -> X_O2<0.30 test")):
        rr = tek(ad, mk)
        ekle(f"BRE dışarıda: {ad}", aciklama, t[mk], {k: v[mk] for k, v in rr.items()})
        tahmin[ad] = rr

    # ---- küre: Irace 2021 (BRE ile kalibre -> küre)
    ir = gm.irace_oku()
    gi_ir = gm.irace_girdi(ir)
    r_ir = gm.hesapla(par_tum, **gi_ir)
    o_ir = gm.olcut(ir.yanar, r_ir["yanma"])
    ozet.append({"deney": "BRE ile kalibre -> küre (Irace 2021)", "alt_kume": "4 test (3 yanar, 1 ışınımla söndü)",
                 **o_ir, "R_f_kuram_hata_medyan_yuzde":
                 float(np.median(np.abs(r_ir["R"] * 1e3 / ir.R_f_kuram_mm - 1)) * 100),
                 "not": f"alev 3 (SE, ölçülen sönme T 1140 K): model T_f {r_ir['T_f'][2]:.0f} K, yanma "
                        f"{r_ir['yanma'][2]:.2f}; sönme türü {gm.SONME_AD[int(r_ir['tur'][2])]}"})
    # ---- küre ile kalibre -> BRE
    r_kb = gm.hesapla(par_kure, **gi_bre)
    ekle("küre (Irace 4 test) ile kalibre -> BRE", "59 test", t, r_kb,
         f"yalnız ln_Crad={par_kure['ln_Crad']:.2f}, fv_ppm={par_kure.get('fv_ppm', 0):.2f}, s={par_kure['s']:.2f}; "
         f"k_s=1, k_v=k_y=1 (yarım küre kuramı)")
    geo_b = gm.geometri_uydur(t, gi_bre)
    r_kb2 = gm.hesapla({**par_kure, **geo_b}, **gi_bre)
    ekle("küre (Irace 4 test) ile kalibre -> BRE (geometri BRE boyut ölçümünden)", "59 test", t, r_kb2,
         f"k_v={geo_b['k_v']:.3f}, k_y={geo_b['k_y']:.3f} etiketsiz boyut ölçümünden; sönme etiketleri kullanılmadı")
    # ---- PSI-10 Flame Design: T_ad / Z_st
    p10 = gm.psi10_oku()
    gi10 = gm.psi10_girdi(p10)
    r10 = gm.hesapla(par_tum, **gi10)
    eT = r10["T_ad"] - p10["Tad (K)"].to_numpy()
    eZ = r10["Zst"] - p10["mean Zst"].to_numpy()
    ozet.append({"deney": "PSI-10 Flame Design (küre, 147 sayısal test)", "alt_kume": "T_ad ve Z_st",
                 "n": len(p10), "T_ad_hata_medyan_K": float(np.median(np.abs(eT))),
                 "T_ad_hata_ort_K": float(eT.mean()), "T_ad_hata_maks_K": float(np.abs(eT).max()),
                 "Z_st_hata_maks": float(np.abs(eZ).max()),
                 "not": f"tabloda sönme sonucu yok -> yanma değerlendirilemez (bilgi: model {int((r10['yanma'] >= 0.5).sum())}"
                        f"/{len(p10)} testi kararlı diyor; Snegirev 2022 bu deneyden 19 kendiliğinden sönen alevi "
                        f"inceledi, toplam ve test kimlikleri yayında yok)"})
    # ---- pozitif-yalnız: s-Flame, PSI-20 BRE, CLD/E-FIELD
    sf = gm.sflame_oku()
    y_sf = yanabilir(par_tum, sflame_girdi(sf))
    for ad, mk in (("hepsi", np.ones(len(sf), bool)), ("He seyreltici", (sf.seyreltici == "he").to_numpy()),
                   ("N2 seyreltici", (sf.seyreltici == "n2").to_numpy()),
                   ("H2 içeren", sf.yakit.str.contains("H2").to_numpy())):
        ozet.append({"deney": "PSI-23 s-Flame (küre, pozitif-yalnız)", "alt_kume": ad, "n": int(mk.sum()),
                     "yanabilir_dogru_orani": float((y_sf[mk] >= 0.5).mean()),
                     "not": "tutuşmuş alevler; debi tabloda yok (0.2-20 mg/s tarandı)"})
    b20 = gm.bre_psi20_oku()
    y20 = yanabilir(par_tum, psi20_girdi(b20))
    for ad, mk in (("CH4 (kalibrasyon dışı yakıt)", b20.yakit.str.contains("CH4").to_numpy()),
                   ("C2H4", b20.yakit.str.contains("C2H4").to_numpy()),
                   ("50 mm brülör", (b20.cap_mm == 50).to_numpy())):
        ozet.append({"deney": "PSI-20 BRE özeti (düz, pozitif-yalnız)", "alt_kume": ad, "n": int(mk.sum()),
                     "yanabilir_dogru_orani": float((y20[mk] >= 0.5).mean()),
                     "not": "tutuşan alevlerin O2 değerleri; m'' 0.5-12 g/m2s, p 0.56-1 bar tarandı; tutuşma kararlı yanma demek değil (Dehghani: 59 tutuşmanın 30'u SE)"})
    jt = gm.jet_psi_oku()
    y_j = yanabilir(par_tum, jet_girdi(jt, "x_ust"))
    y_ja = yanabilir(par_tum, jet_girdi(jt, "x_alt"))
    for ad, mk in (("CLD", (jt.deney == "CLD").to_numpy()), ("E-FIELD", (jt.deney == "E-FIELD").to_numpy())):
        ozet.append({"deney": "PSI-21/22 jet (pozitif-yalnız, kalibre değil)", "alt_kume": ad + " (aralık üstü)",
                     "n": int(mk.sum()), "yanabilir_dogru_orani": float((y_j[mk] >= 0.5).mean()),
                     "not": "hava, 2.1 mm lüle, U 5-100 cm/s tarandı"})
    m = (jt.deney == "CLD").to_numpy() & (jt.x_alt > 0).to_numpy()
    ozet.append({"deney": "PSI-21/22 jet (pozitif-yalnız, kalibre değil)", "alt_kume": "CLD (aralık altı)",
                 "n": int(m.sum()), "yanabilir_dogru_orani": float((y_ja[m] >= 0.5).mean()),
                 "not": "en düşük derişim (0% alt uçlu 1 gün çıkarıldı); tablo notu: bazı alevler buna ulaşmadan "
                        "söndü (pozitif olmayabilir)"})

    # ---- literatür kontrol seti (GAZ_KONTROL=0: hiç hesaplanmaz / yazdırılmaz — geliştirme sırasında bakmamak için)
    kontrol = os.environ.get("GAZ_KONTROL", "1") == "1"
    L = gm.literatur_oku() if kontrol else gm.literatur_oku().iloc[:0]
    idx, gil, atla = literatur_girdi(L)
    Lk = L.loc[idx].reset_index(drop=True)
    rL = gm.hesapla(par_tum, **birlestir(gil)) if gil else {"yanma": np.zeros(0), "T_f": np.zeros(0)}
    Lk["model_yanma"] = rL["yanma"]
    Lk["model_T"] = rL["T_f"]
    for ad, mk in [] if not kontrol else (("hepsi", np.ones(len(Lk), bool)), ("1 g", (Lk.g_seviyesi >= 0.5).to_numpy()),
                   ("µg (g<=1e-3)", (Lk.g_seviyesi <= 1e-3).to_numpy()),
                   ("deney", (Lk.veri_turu == "deney").to_numpy()),
                   ("N2/CO2/He/Ar seyreltici verilmiş", Lk.seyreltici.notna().to_numpy())):
        o = gm.olcut(Lk.yanar[mk], Lk.model_yanma[mk])
        ozet.append({"deney": "literatür kontrol (etiketli_gemma3, gaz, kalibrasyonda yok)", "alt_kume": ad, **o,
                     "not": "geometri/akış çoğunlukla yok: varsayılan jet (3.2 mm, 30 cm/s)"})
    ozet.append({"deney": "literatür kontrol (etiketli_gemma3, gaz, kalibrasyonda yok)", "alt_kume": "dışarıda kalan",
                 "n": int(sum(atla.values())), "not": json.dumps(atla, ensure_ascii=False)})

    # ---- geometri başına AUC
    geo_auc = {"duz (BRE gün dışarıda)": gm.olcut(t.yanar, cv["yanma"]),
               "kure (Irace, BRE ile kalibre)": o_ir,
               **({"jet (literatür kontrol)": gm.olcut(Lk.yanar, Lk.model_yanma)} if kontrol else {})}
    for k, v in geo_auc.items():
        ozet.append({"deney": "GEOMETRİ BAŞINA AUC", "alt_kume": k, **v})

    oz = pd.DataFrame(ozet)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 90)
    kol = [c for c in ["deney", "alt_kume", "n", "auc", "dogruluk", "yanabilir_dogru_orani",
                       "X_r_mutlak_hata_medyan_FT", "q_merkez_hata_medyan_yuzde_FT", "y_f_hata_medyan_yuzde",
                       "R_eff_hata_medyan_yuzde", "R_f_kuram_hata_medyan_yuzde", "T_ad_hata_medyan_K", "not"]
           if c in oz.columns]
    print(oz[kol].round(3).to_string(index=False))
    oz.to_csv(KOK / "gaz_dogrulama_ozet.csv", index=False, encoding="utf-8-sig")
    # ---- nokta bazında çıktı
    parcalar = []
    b = t[["test", "X_O2", "X_f", "p_bar", "m_akisi_g_m2s", "sonuc", "yanar", "alev_boyu_y_f_mm", "R_eff_mm",
           "isinim_orani_X_r", "q_merkez_kW_m2"]].copy()
    b.insert(0, "kaynak", "BRE Dehghani2021 T2")
    b["model_yanma_icerde"] = r_tum["yanma"]
    b["model_yanma_gun_disarida"] = cv["yanma"]
    b["model_yanma_kureden"] = r_kb["yanma"]
    b["model_yanma_kureden_geo"] = r_kb2["yanma"]
    b["model_T_f"] = r_tum["T_f"]
    b["model_X_r"] = r_tum["chi_r"]
    b["model_q_kW_m2"] = r_tum["q_flux"]
    b["model_y_f_mm"] = r_tum["y_f"] * 1e3
    b["model_R_eff_mm"] = r_tum["R"] * 1e3
    b["model_sonme_turu"] = [gm.SONME_AD[int(v)] for v in r_tum["tur"]]
    parcalar.append(b)
    c = ir.copy()
    c.insert(0, "kaynak", "Flame Design Irace2021")
    c["model_yanma"] = r_ir["yanma"]
    c["model_T_f"] = r_ir["T_f"]
    c["model_R_f_mm"] = r_ir["R"] * 1e3
    c["model_T_ad"] = r_ir["T_ad"]
    c["model_sonme_turu"] = [gm.SONME_AD[int(v)] for v in r_ir["tur"]]
    parcalar.append(c)
    d10 = p10[["Day", "Fuel", "Test", "Xfuel", "mtot (mg/s)", "XO2", "p_atm", "mean Zst", "Tad (K)"]].copy()
    d10.insert(0, "kaynak", "PSI-10 Flame Design")
    d10["model_T_ad"] = r10["T_ad"]
    d10["model_Z_st"] = r10["Zst"]
    d10["model_yanma"] = r10["yanma"]
    d10["model_R_f_mm"] = r10["R"] * 1e3
    parcalar.append(d10)
    sf2 = sf.copy()
    sf2.insert(0, "kaynak", "PSI-23 s-Flame")
    sf2["model_yanabilir"] = y_sf
    parcalar.append(sf2)
    b2 = b20.copy()
    b2.insert(0, "kaynak", "PSI-20 BRE ozet")
    b2["model_yanabilir"] = y20
    parcalar.append(b2)
    j2 = jt.copy()
    j2.insert(0, "kaynak", "PSI-21/22 jet")
    j2["model_yanabilir_ust"] = y_j
    j2["model_yanabilir_alt"] = y_ja
    parcalar.append(j2)
    l2 = Lk[["makale_id", "malzeme_sade", "g_seviyesi", "oksijen_yuzde", "seyreltici", "basinc_kpa",
             "akis_hizi_cm_s", "veri_turu", "yanar", "model_yanma", "model_T"]].copy()
    l2.insert(0, "kaynak", "literatur etiketli_gemma3")
    parcalar.append(l2)
    pd.concat(parcalar, ignore_index=True).to_csv(KOK / "gaz_dogrulama.csv", index=False, encoding="utf-8-sig")
    js = {"ozet": json.loads(oz.to_json(orient="records", force_ascii=False)),
          "parametreler_tum": par_tum, "parametreler_kalibrasyonlar": {k: v[0] for k, v in sonuc.items()},
          "parametreler_kure_ile": par_kure, "sure_s": time.time() - bas}
    (KOK / "gaz_dogrulama_ozet.json").write_text(json.dumps(js, ensure_ascii=False, indent=1, default=float),
                                                 encoding="utf-8")
    print(f"Kaydedildi: gaz_dogrulama.csv, gaz_dogrulama_ozet.csv, gaz_dogrulama_ozet.json ({time.time()-bas:.0f} s)")


# ------------------------------------------------------------------ profil: literatürde sabitlenen sayılar
def _profil_isci(arg):
    os.environ["OMP_NUM_THREADS"] = "1"
    tur, deger = arg
    import gaz_motoru as g2
    if tur == "T_kr":
        g2.YAKIT["C2H4"]["T_kr"] = deger
    else:
        g2.A_Q_CH4 = deger
        g2._DAQ = None
    t = g2.bre_oku()
    par, kay, _ = g2.kalibre(t, baslangic_sayisi=4)
    return tur, deger, kay, par


def profil_main():
    isler = [("T_kr", v) for v in (800, 900, 1000, 1050, 1100, 1150, 1200, 1300, 1400)] + \
            [("a_q", v) for v in (38, 120, 380, 1200, 3800)]
    with Pool(isci_sayisi()) as h:
        s = h.map(_profil_isci, isler)
    sat = [{"parametre": tur, "deger": d, "kayip": k, **{a: p[a] for a in gm.PARAM_ADLARI}} for tur, d, k, p in s]
    tab = pd.DataFrame(sat)
    print(tab.round(3).to_string(index=False))
    tab.to_csv(KOK / "gaz_profil.csv", index=False, encoding="utf-8-sig")


# ------------------------------------------------------------------ grafik
def grafik_main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    par = gm.varsayilan_parametreler()
    t = gm.bre_oku()
    gi = gm.bre_girdi(t)
    r = gm.hesapla(par, **gi)
    d = pd.read_csv(KOK / "gaz_dogrulama.csv", low_memory=False)
    b = d[d.kaynak == "BRE Dehghani2021 T2"]
    MAVI, TURUNCU, GRI, KOYU = "#2a6fdb", "#e07b39", "#9aa0a6", "#202124"
    fig, ax = plt.subplots(2, 3, figsize=(15, 9))
    # (a) kararlılık haritası, iki basınç
    for k, (pb, ad) in enumerate(((1.0, "≈1 bar"), (0.57, "0.56-0.71 bar"))):
        a = ax[0, 0] if k == 0 else ax[0, 1]
        mm, oo = np.meshgrid(np.geomspace(0.8, 13, 70), np.linspace(0.17, 0.42, 60))
        O = gm.oz()
        N = mm.size
        XF = np.zeros((O.ns, N))
        XF[O.i["C2H4"]] = 1.0
        XO = np.zeros((O.ns, N))
        XO[O.i["O2"]] = oo.ravel()
        XO[O.i["N2"]] = 1 - oo.ravel()
        rr = gm.hesapla(par, np.ones(N, int), XF, XO, np.full(N, pb * 1e5), np.full(N, 1e-4),
                        mm.ravel() * 1e-3 * math.pi * 0.0125 ** 2, np.full(N, 0.0125), np.zeros(N),
                        np.full(N, 300.0))
        cs = a.contourf(mm, oo, rr["yanma"].reshape(mm.shape), levels=[0, 0.5, 1], colors=["#f6d7c3", "#d6e4fa"])
        a.contour(mm, oo, rr["yanma"].reshape(mm.shape), levels=[0.5], colors=KOYU, linewidths=1.2)
        sec = (t.p_bar > 0.9) if pb > 0.9 else (t.p_bar < 0.9)
        x = t[sec & (t.X_f == 1)]
        for son, renk, mk in (("FT", MAVI, "o"), ("SE", TURUNCU, "x")):
            y = x[x.sonuc == son]
            a.scatter(y.m_akisi_g_m2s, y.X_O2, c=renk, marker=mk, s=40, label=f"{son} (X_f=1)", zorder=3)
        a.set_xscale("log")
        a.set_xlabel("yakıt kütle akısı m'' [g/m²s]")
        a.set_ylabel("ortam X_O2")
        a.set_title(f"BRE C2H4 (X_f=1), {ad}: model sınırı (yanma=0.5)")
        a.legend(fontsize=8, loc="upper right")
    # (b) ölçülen vs model: y_f, R_eff
    a = ax[0, 2]
    a.scatter(t.alev_boyu_y_f_mm, r["y_f"] * 1e3, c=MAVI, s=25, label="alev boyu y_f")
    a.scatter(t.R_eff_mm, r["R"] * 1e3, c=TURUNCU, s=25, marker="s", label="hacim-eşdeğer R_eff")
    lim = [5, 90]
    a.plot(lim, lim, color=GRI, lw=1)
    a.set_xscale("log"); a.set_yscale("log")
    a.set_xlabel("ölçülen [mm]"); a.set_ylabel("model [mm]")
    a.set_title("BRE alev boyutu (59 test)")
    a.legend(fontsize=8)
    # (c) X_r ve q (FT)
    a = ax[1, 0]
    ft = t.yanar == 1
    m = ft & t.isinim_orani_X_r.notna()
    a.scatter(t.isinim_orani_X_r[m], r["chi_r"][m], c=MAVI, s=30)
    a.plot([0.2, 0.7], [0.2, 0.7], color=GRI, lw=1)
    a.set_xlabel("ölçülen ışınım oranı X_r (FT)"); a.set_ylabel("model χ_r")
    a.set_title("BRE ışınım oranı")
    a = ax[1, 1]
    a.scatter(t.q_merkez_kW_m2[ft], r["q_flux"][ft], c=MAVI, s=30, label="FT")
    a.scatter(t.q_merkez_kW_m2[~ft], r["q_flux"][~ft], c=TURUNCU, s=30, marker="x", label="SE (geçici, uyumda yok)")
    a.plot([2, 13], [2, 13], color=GRI, lw=1)
    a.set_xlabel("ölçülen q''_merkez [kW/m²]"); a.set_ylabel("model q'' [kW/m²]")
    a.set_title("BRE brülöre ısı akısı")
    a.legend(fontsize=8)
    # (d) T_ad PSI-10
    a = ax[1, 2]
    p10 = d[d.kaynak == "PSI-10 Flame Design"]
    a.scatter(p10["Tad (K)"], p10.model_T_ad, c=MAVI, s=18, label="PSI-10 Flame Design (147)")
    ir = d[d.kaynak == "Flame Design Irace2021"]
    a.scatter(ir.T_ad_K, ir.model_T_ad, c=TURUNCU, s=40, marker="s", label="Irace 2021 Tablo 1")
    a.plot([1900, 2800], [1900, 2800], color=GRI, lw=1)
    a.set_xlabel("tablodaki T_ad [K]"); a.set_ylabel("model T_ad [K]")
    a.set_title("T_ad: model vs tablo (PSI-10, Irace)")
    a.legend(fontsize=8)
    for a in ax.ravel():
        a.grid(alpha=0.25)
    fig.suptitle("gaz_motoru.py — BRE kalibrasyonu ve kontroller", fontsize=13)
    fig.tight_layout()
    fig.savefig(KOK / "gaz_motoru.png", dpi=120)
    print("Kaydedildi: gaz_motoru.png")
