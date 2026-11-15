#!/usr/bin/env python3
"""ofm_case.py — OpenFOAM motorunun Saffire-III S1 vakasını (motor_c/vaka) bir KOPYAYA hazırlar: O2, basınç, akış, g, bitiş zamanı, çekirdek sayısı.
Paketin kendisine dokunulmaz. Kalınlık OpenFOAM vaka ağında sabittir (mesh_olustur.py pakette yok): ±%5'ten farklıysa vaka DESTEKLENMEZ.

    destek(kosul)            -> {"destekli": bool, "neden": str|None, ...}     (ayrıntılı çözüm bu vakayı koşabilir mi?)
    hazirla(hedef, paket, kosul, cekirdek, bitis_s) -> {"notlar": [...], "bilgi": {...}}
    kaldirma_kontrol(log_metni) -> (tamam: bool|None, mesaj)                 (ilk dakikada günlükten kaldırmanın açık olduğunu denetler)

Desteklenen: katı SIBAL (kilitli, deneyle doğrulanmış) ve MALZEME KÜTÜPHANESİNDEN kurulan katılar (ofm_materials.py: yoğunluk ve net ısıl değer
kütüphaneden, k / α / Lv / kinetik kaynaklı tablodan; "doğrulanmadı" bayraklı parametreler koşu bilgisine yazılır). Kalınlık farklıysa ağ yeniden üretilir.
SIVI (damla): 1B küresel damla buharlaşma + yanma vakası (ofm_droplet_case.py; libFlameInFreefallDroplet), yakıt kütüphane kimliğinden SIVI_ESLEME ile
pakettin damlaYakitlar tablosuna eşlenir. Gaz için şablon YOK (destek() nedenini söyler).
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import ofm_materials

DESTEK = {"kati": {"sibal", "cotton-fiberglass", "cotton fiberglass"}}   # yakıt türü -> malzeme adları
KALINLIK_AG_MM = 0.32          # MOTOR_KILIT sibal.yarim_kalinlik_m × 2 (ağ buna göre)
KALINLIK_TOL = 0.05
G0 = 9.81
M = {"O2": 31.998, "N2": 28.014, "H2O": 18.015, "CO2": 44.009}
DOSYA_KOPYA = [("kinetik", ["reactions", "chemistryProperties", "reactionProperties"], "constant/fluid"),
               ("radyasyon", ["radiationProperties", "fvModels"], "constant/fluid"),
               ("piroliz", ["fvModels", "physicalProperties"], "constant/sibal")]


def _norm(a):
    return re.sub(r"\s+", " ", str(a or "").lower().replace("_", " ")).strip()


def desteklenen_mi(malzeme, yakit_turu="kati"):
    return _norm(malzeme) in {_norm(x) for x in DESTEK.get(yakit_turu, set())}


SIVI_ESLEME = {"n-heptane": "NC7H16", "methanol": "CH3OH", "ethanol": "C2H5OH", "n-decane": "NC10H22"}   # kütüphane kimliği -> damlaYakitlar
FLEX_KALIBRE = {"NC7H16", "CH3OH"}      # damlaYakitlar'da flexKalibre true olanlar; diğerleri tek adım kinetik, FLEX'e kalibre DEĞİL
GAZ_ESLEME = {"methane": "CH4", "ethane": "C2H6", "propane": "C3H8", "ethylene": "C2H4", "acetylene": "C2H2"}   # kütüphane kimliği -> gaz_yakitlar.json
GAZ_CAP_MM = (2.0, 15.0)                # gözenekli küre çapı
GAZ_BITIS_S = 5.0
GAZ_O2_ARALIK = (15.0, 60.0)
SIVI_CAP_MM = (0.3, 3.0)
SIVI_BITIS_S = 4.0                      # damla d²/d0² = 0.2'ye inince kendiliğinden durur; bu üst sınır
SIVI_O2_ARALIK = (5.0, 60.0)
KALINLIK_ARALIK_MM = (0.05, 1.0)   # kütüphane malzemeleri için ağ yeniden üretilebilen kalınlık (ince katı)


def destek(kosul, yakit_turu=None, malzeme_kanonik=None, kutuphane=None):
    """kosul: {malzeme, oksijen, basinc, g, akis, kalinlik, ...}. yakit_turu/malzeme_kanonik biliniyorsa (tahmin çıktısından) verilir.
    kutuphane: malzeme kütüphanesindeki kayıt (dict) — SIBAL dışı malzemeler için vakayı kütüphaneden kurmaya yarar."""
    ad = malzeme_kanonik or kosul.get("malzeme")
    tur = yakit_turu or ("kati" if desteklenen_mi(ad, "kati") else None)
    if not (tur and desteklenen_mi(ad, tur)):
        lt = (kutuphane or {}).get("yakit_turu")
        if lt == "kati":
            ps = ofm_materials.parametre_seti(kutuphane["id"], kutuphane)
            if not ps["tam"]:
                return {"destekli": False, "kod": "malzeme", "eksik": ps["eksik"],
                        "neden": f"'{kutuphane['id']}' için OpenFOAM vakası kurulamıyor, eksik parametre: " + "; ".join(ps["eksik"])}
            kal = kosul.get("kalinlik")
            if kal is None:
                kal = (kutuphane.get("varsayilan") or {}).get("kalinlik_veya_cap_mm")
            if kal is None or not (KALINLIK_ARALIK_MM[0] <= kal <= KALINLIK_ARALIK_MM[1]):
                return {"destekli": False, "kod": "kalinlik",
                        "neden": f"Kütüphane malzemesi için kalınlık {KALINLIK_ARALIK_MM[0]:g}–{KALINLIK_ARALIK_MM[1]:g} mm olmalı (verilen: {kal})."}
            if not (0 < (kosul.get("basinc") or 0) < 400):
                return {"destekli": False, "kod": "basinc", "neden": "Basınç 0–400 kPa aralığında olmalı."}
            return {"destekli": True, "neden": None, "ozel_malzeme": True, "malzeme_id": kutuphane["id"], "kalinlik_ag_mm": float(kal),
                    "dogrulanmadi": ps["dogrulanmadi"], "parametreler": ps}
        if lt == "sivi":
            yid = SIVI_ESLEME.get(kutuphane["id"])
            if not yid:
                return {"destekli": False, "kod": "yakit_turu",
                        "neden": f"'{kutuphane['id']}' için damla modülünde yakıt tablosu yok (var: " + ", ".join(sorted(SIVI_ESLEME)) + ")."}
            cap = kosul.get("kalinlik")
            if cap is None:
                cap = (kutuphane.get("varsayilan") or {}).get("kalinlik_veya_cap_mm")
            if cap is None:
                cap = 1.0
            if not (SIVI_CAP_MM[0] <= cap <= SIVI_CAP_MM[1]):
                return {"destekli": False, "kod": "kalinlik", "tur": "sivi",
                        "neden": f"Damla çapı {SIVI_CAP_MM[0]:g}–{SIVI_CAP_MM[1]:g} mm olmalı (verilen: {cap})."}
            if (kosul.get("g") or 0) > 0.01:
                return {"destekli": False, "kod": "g", "tur": "sivi",
                        "neden": "Damla vakası 1B küresel simetriktir: yalnız mikroyerçekimi (g ≈ 0) çözülür; kaldırma/akış yok."}
            if not (0 < (kosul.get("basinc") or 0) < 400):
                return {"destekli": False, "kod": "basinc", "tur": "sivi", "neden": "Basınç 0–400 kPa aralığında olmalı."}
            o2 = kosul.get("oksijen")
            if o2 is not None and not (SIVI_O2_ARALIK[0] <= o2 <= SIVI_O2_ARALIK[1]):
                return {"destekli": False, "kod": "oksijen", "tur": "sivi", "neden": f"O₂ %{SIVI_O2_ARALIK[0]:g}–{SIVI_O2_ARALIK[1]:g} aralığında olmalı."}
            dog = [] if yid in FLEX_KALIBRE else [f"{yid}: tek adım Westbrook-Dryer kinetiği FLEX'e kalibre DEĞİL (doğrulanmadı)"]
            return {"destekli": True, "neden": None, "tur": "sivi", "yakit_id": yid, "malzeme_id": kutuphane["id"], "cap_mm": float(cap),
                    "dogrulanmadi": dog, "bitis_s": SIVI_BITIS_S}
        if lt == "gaz":
            yid = GAZ_ESLEME.get(kutuphane["id"])
            if not yid:
                return {"destekli": False, "kod": "yakit_turu",
                        "neden": f"'{kutuphane['id']}' için gaz vakasında tek adım kinetik ve termo tablosu yok (var: " + ", ".join(sorted(GAZ_ESLEME)) + ")."}
            cap = kosul.get("kalinlik")
            if cap is None:
                cap = (kutuphane.get("varsayilan") or {}).get("kalinlik_veya_cap_mm") or 6.4
            if not (GAZ_CAP_MM[0] <= cap <= GAZ_CAP_MM[1]):
                return {"destekli": False, "kod": "kalinlik", "tur": "gaz", "neden": f"Küre çapı {GAZ_CAP_MM[0]:g}–{GAZ_CAP_MM[1]:g} mm olmalı (verilen: {cap})."}
            if (kosul.get("g") or 0) > 0.01:
                return {"destekli": False, "kod": "g", "tur": "gaz",
                        "neden": "Gaz vakası 1B küresel simetriktir (gözenekli küre brülör): yalnız mikroyerçekimi (g ≈ 0) çözülür."}
            if not (kosul.get("akis") and kosul["akis"] > 0):
                return {"destekli": False, "kod": "akis", "tur": "gaz", "neden": "Yakıt çıkış hızı (akış, cm/s) gerekli: küre yüzeyinden verilen yakıt debisini belirler."}
            if not (0 < (kosul.get("basinc") or 0) < 400):
                return {"destekli": False, "kod": "basinc", "tur": "gaz", "neden": "Basınç 0–400 kPa aralığında olmalı."}
            o2 = kosul.get("oksijen")
            if o2 is not None and not (GAZ_O2_ARALIK[0] <= o2 <= GAZ_O2_ARALIK[1]):
                return {"destekli": False, "kod": "oksijen", "tur": "gaz", "neden": f"O₂ %{GAZ_O2_ARALIK[0]:g}–{GAZ_O2_ARALIK[1]:g} aralığında olmalı."}
            q = ((kutuphane.get("ozellikler") or {}).get("isil_deger_net") or {}).get("deger")
            if not q:
                return {"destekli": False, "kod": "malzeme", "tur": "gaz", "neden": "Kütüphanede net ısıl değer yok."}
            return {"destekli": True, "neden": None, "tur": "gaz", "yakit_id": yid, "malzeme_id": kutuphane["id"], "cap_mm": float(cap),
                    "Q_MJ_kg": float(q), "bitis_s": GAZ_BITIS_S,
                    "dogrulanmadi": ["tek adım yanma kinetiği: Westbrook & Dryer 1981, değerler hafızadan, makale tablosuyla doğrulanmadı",
                                     "LJ (Chapman-Enskog taşınım) değerleri GRI-Mech 3.0 tran.dat, hafızadan",
                                     "ışınım modeli yok: ışınımla sönme yakalanmaz; vaka deneyle karşılaştırılmadı"]}
        return {"destekli": False, "neden": "Ayrıntılı motor bu malzeme/yakıt için hazır değil (malzeme kütüphanede yok ya da yakıt türü bilinmiyor).", "kod": "malzeme"}
    kal = kosul.get("kalinlik")
    if kal is not None and abs(kal - KALINLIK_AG_MM) / KALINLIK_AG_MM > KALINLIK_TOL:
        return {"destekli": False, "kod": "kalinlik",
                "neden": f"OpenFOAM vakasının ağı {KALINLIK_AG_MM:g} mm kalınlık içindir; {kal:g} mm için yeniden ağ gerekir (pakette ağ betiği yok)."}
    if not (0 < (kosul.get("basinc") or 0) < 400):
        return {"destekli": False, "kod": "basinc", "neden": "Basınç 0–400 kPa aralığında olmalı."}
    return {"destekli": True, "neden": None, "kalinlik_ag_mm": KALINLIK_AG_MM}


def kilit_oku(paket):
    return json.loads((Path(paket) / "MOTOR_KILIT.json").read_text(encoding="utf-8"))


def kutle_kesirleri(kilit, oksijen_mol):
    """Kilitteki H2O ve CO2 mol kesirleri korunur; O2 mol kesri oksijen_mol/100; N2 geri kalan. -> mass fractions."""
    o = kilit["ortam"]
    n = {k: o[f"Y_{k}"] / M[k] for k in M}
    top = sum(n.values())
    x = {k: v / top for k, v in n.items()}
    x["O2"] = oksijen_mol / 100.0
    x["N2"] = 1.0 - x["O2"] - x["H2O"] - x["CO2"]
    if x["N2"] <= 0:
        raise ValueError("O2 oranı bu bileşimde çok yüksek (N2 negatif).")
    kutle = {k: x[k] * M[k] for k in M}
    s = sum(kutle.values())
    return {k: v / s for k, v in kutle.items()}


def _sayi_degistir(dosya, eski, yeni):
    s = Path(dosya).read_text(encoding="utf-8")
    Path(dosya).write_text(s.replace(eski, yeni), encoding="utf-8")


def _gecerli_kopya_yok(ad):
    return ad.startswith("processor") or ad.startswith("log.") or ad == "postProcessing" or bool(re.fullmatch(r"\d+(\.\d+)?", ad) and ad != "0")


def agi_yeniden_uret(hedef, kalinlik_mm):
    """Numune kalınlığına göre ağı yeniden üretir (paketteki mesh_olustur.py'de yarım kalınlık h değiştirilir; OpenFOAM 14'te
    splitMeshRegions bölge listesi ister). Yalnız hedef KOPYADA çalışır."""
    mo = Path(hedef) / "mesh_olustur.py"
    s = mo.read_text(encoding="utf-8")
    s, n = re.subn(r"^h = [0-9.eE+-]+(\s*#.*)?$", f"h = {kalinlik_mm / 2.0 * 1e-3:.6e}                  # yarim kalinlik (ofm_case.agi_yeniden_uret)", s, count=1, flags=re.M)
    if n != 1:
        raise ValueError("mesh_olustur.py içinde yarım kalınlık satırı (h = ...) bulunamadı")
    mo.write_text(s, encoding="utf-8")
    komut = ("source /opt/openfoam14/etc/bashrc >/dev/null 2>&1; python3 mesh_olustur.py && blockMesh > log.blockMesh 2>&1 && "
             "splitMeshRegions -cellZones '(fluid sibal tel)' > log.splitMeshRegions 2>&1")
    r = subprocess.run(["bash", "-c", komut], cwd=str(hedef), capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError("ağ üretimi başarısız: " + (r.stderr or r.stdout)[-300:])
    for f in (Path(hedef) / "0").glob("cellToRegion*"):
        f.unlink()


def _yama(metin, desen, yeni):
    s, n = re.subn(desen, yeni, metin, count=1, flags=re.S)
    if n != 1:
        raise ValueError(f"vaka dosyasında yama deseni bulunamadı: {desen[:40]}")
    return s


def malzeme_yaz(hedef, ps):
    """Kütüphaneden kurulan katı malzemeyi vakaya yazar: piroliz (fvModels), rho/Cv/kappa (physicalProperties), Yf0 (0/fluid/CH4)."""
    F = r"([0-9.eE+-]+)"
    fv = Path(hedef) / "constant/sibal/fvModels"
    s = fv.read_text(encoding="utf-8")
    for k, v in ps["piroliz"].items():
        s = _yama(s, rf"\b{k}(\s+){F};", lambda m, k=k, v=v: f"{k}{m.group(1)}{v:.6g};")
    s = re.sub(r"[ \t]*//[^\n]*", "", s)          # SIBAL'e ait kaynak yorumları (0.32 mm, Olson vb.) bu malzeme için geçersiz
    fv.write_text("// kütüphane malzemesi (ofm_materials.py); kaynaklar koşu BILGI.json'unda\n" + s, encoding="utf-8")
    pp = Path(hedef) / "constant/sibal/physicalProperties"
    s = pp.read_text(encoding="utf-8")
    for ad, v in (("rho", f"{ps['rho']:.2f}"), ("Cv", f"{ps['Cv']:.1f}"), ("kappa", f"{ps['kappa']:g}")):
        s = _yama(s, rf"({ad}\s*\{{ type uniform; value )[0-9.eE+-]+;", lambda m, v=v: f"{m.group(1)}{v};")
    pp.write_text(s, encoding="utf-8")
    ch4 = Path(hedef) / "0/fluid/CH4"
    ch4.write_text(_yama(ch4.read_text(encoding="utf-8"), rf"(Yf0\s+){F};", lambda m: f"{m.group(1)}{ps['Yf0']:.6g};"), encoding="utf-8")



def damla_kutuphanesi_var():
    """libFlameInFreefallDroplet.so derlenmiş mi: $FOAM_USER_LIBBIN, yoksa ~/OpenFOAM/*-14/platforms/*/lib."""
    import os
    adaylar = [Path(os.environ["FOAM_USER_LIBBIN"])] if os.environ.get("FOAM_USER_LIBBIN") else []
    adaylar += sorted(Path.home().glob("OpenFOAM/*-14/platforms/*/lib"))
    return any((d / "libFlameInFreefallDroplet.so").is_file() for d in adaylar)


def hazirla_sivi(hedef, paket, kosul, yakit_id, cap_mm, bitis_s=SIVI_BITIS_S):
    """Damla (1B küresel, küçülen çap, tek adım yanma) vakasını üretir; seri koşar (50 hücre). Dönüş: {"notlar"}."""
    hedef, paket = Path(hedef), Path(paket)
    tablo = paket / "damla_buharlasma" / "tablolar" / "damlaYakitlar"
    if not tablo.is_file():
        raise FileNotFoundError(f"damlaYakitlar yok: {tablo}")
    if not damla_kutuphanesi_var():
        raise FileNotFoundError("libFlameInFreefallDroplet.so derlenmemiş (paket: damla_buharlasma/Allwmake)")
    kod = Path(__file__).resolve().parent / "ofm_droplet_case.py"
    komut = ["python3", "-I", str(kod), str(hedef), "--yakit", yakit_id, "--yakit-tablo", str(tablo), "--tip", "yanan", "--cap", "kuculen",
             "--bitis", f"{bitis_s:g}", "--d0", f"{cap_mm / 1000.0:.9f}".rstrip("0"), "--p", f"{(kosul.get('basinc') or 101.325) * 1000.0:g}"]
    if kosul.get("oksijen") is not None:
        komut += ["--x-o2", f"{kosul['oksijen'] / 100.0:g}"]
    r = subprocess.run(komut, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("damla vakası üretilemedi: " + (r.stderr or r.stdout)[-400:])
    (hedef / "kos.sh").write_text("#!/bin/bash\nsource /opt/openfoam14/etc/bashrc >/dev/null 2>&1\ncd \"$(dirname \"$0\")\"\n"
                                  "exec foamMultiRun\n", encoding="utf-8")
    notlar = [f"yakıt {yakit_id} (kütüphane → damlaYakitlar), damla çapı {cap_mm:g} mm, 1B küresel, küçülen çap, tek adım yanma, dt 0.000001 s (seri)",
              "damla modülü ışınımı kendi hesaplar; OpenFOAM ışınım modeli açılmadı"]
    return {"notlar": notlar, "kilit": None}


def hazirla_gaz(hedef, kosul, yakit_id, cap_mm, q_mj_kg, bitis_s=GAZ_BITIS_S):
    """Gözenekli küre brülör (1B küresel) gaz vakasını üretir (ofm_gas_case.py); seri koşar. Dönüş: {"notlar"}."""
    hedef = Path(hedef)
    if not damla_kutuphanesi_var():
        raise FileNotFoundError("libFlameInFreefallDroplet.so derlenmemiş (ateşleme kaynağı için; paket: damla_buharlasma/Allwmake)")
    kod = Path(__file__).resolve().parent / "ofm_gas_case.py"
    komut = ["python3", "-I", str(kod), str(hedef), "--yakit", yakit_id, "--d-mm", f"{cap_mm:g}", "--akis", f"{kosul['akis']:g}",
             "--Q", f"{q_mj_kg * 1e6:g}", "--bitis", f"{bitis_s:g}", "--dt", "0.000005", "--p", f"{(kosul.get('basinc') or 101.325) * 1000.0:g}"]
    if kosul.get("oksijen") is not None:
        komut += ["--x-o2", f"{kosul['oksijen'] / 100.0:g}"]
    r = subprocess.run(komut, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("gaz vakası üretilemedi: " + (r.stderr or r.stdout)[-400:])
    (hedef / "kos.sh").write_text("#!/bin/bash\nsource /opt/openfoam14/etc/bashrc >/dev/null 2>&1\ncd \"$(dirname \"$0\")\"\nexec foamMultiRun\n", encoding="utf-8")
    return {"notlar": [f"yakıt {yakit_id}, küre çapı {cap_mm:g} mm, çıkış hızı {kosul['akis']:g} cm/s, 1B küresel, tek adım yanma, dt 0.000005 s (seri)",
                       "OpenFOAM ışınım modeli yok"], "kilit": None}


def hazirla(hedef, paket, kosul, cekirdek, bitis_s=10.0, malzeme=None):
    hedef, paket = Path(hedef), Path(paket)
    kilit = kilit_oku(paket)
    notlar = []
    shutil.copytree(paket / "vaka", hedef, ignore=lambda d, adlar: [a for a in adlar if _gecerli_kopya_yok(a) and Path(d) == paket / "vaka"])
    for klasor, dosyalar, hd in DOSYA_KOPYA:
        for f in dosyalar:
            shutil.copy2(paket / klasor / f, hedef / hd / f)
    # --- kütüphane malzemesi (SIBAL dışı): katı özellikleri, piroliz, Y_F0 ve (gerekirse) ağ kalınlığı
    if malzeme:
        ps, kal = malzeme["parametreler"], float(malzeme["kalinlik_mm"])
        if abs(kal - KALINLIK_AG_MM) / KALINLIK_AG_MM > KALINLIK_TOL:
            agi_yeniden_uret(hedef, kal)
            notlar.append(f"ağ yeniden üretildi: numune kalınlığı {kal:g} mm (paket ağı {KALINLIK_AG_MM:g} mm)")
        malzeme_yaz(hedef, ps)
        notlar.append(f"malzeme '{malzeme['id']}' kütüphaneden: rho {ps['rho']:g}, cp {ps['Cv']:.0f}, k {ps['kappa']:g}, Y_F0 {ps['Yf0']:.4g} "
                      f"(net ısıl değer {ps['dhc_MJ_kg']:g} MJ/kg)")
        if ps["dogrulanmadi"]:
            notlar.append("DOĞRULANMADI parametreler: " + "; ".join(ps["dogrulanmadi"]))
    # --- O2 (mol %), N2: kilit bileşiminden
    ok = kosul.get("oksijen")
    if ok is not None:
        yeni = kutle_kesirleri(kilit, float(ok))
        for tur in ("O2", "N2"):
            eski = f"{kilit['ortam']['Y_' + tur]:g}"
            for f in [hedef / "0" / "fluid" / tur]:
                s = f.read_text(encoding="utf-8")
                if eski not in s:
                    raise ValueError(f"{f.name}: kilit değeri {eski} dosyada bulunamadı")
                f.write_text(s.replace(eski, f"{yeni[tur]:.6f}"), encoding="utf-8")
        notlar.append(f"O2 %{ok:g} mol → Y_O2 {yeni['O2']:.6f}, Y_N2 {yeni['N2']:.6f} (H2O, CO2 kilit değerinde)")
    # --- basınç
    p_kilit = f"{kilit['ortam']['p']:g}"
    p = kosul.get("basinc")
    if p is not None:
        _sayi_degistir(hedef / "0" / "fluid" / "p", p_kilit, f"{p * 1000.0:g}")
        notlar.append(f"basınç {p:g} kPa")
    # --- akış
    u_kilit = f"{kilit['ortam']['U_in']:g}"
    akis = kosul.get("akis")
    if akis is not None:
        _sayi_degistir(hedef / "0" / "fluid" / "U", f"({u_kilit} 0 0)", f"({akis / 100.0:g} 0 0)")
        notlar.append(f"akış {akis:g} cm/s")
    else:
        notlar.append(f"akış bilinmiyor: Saffire değeri {kilit['ortam']['U_in'] * 100:g} cm/s kullanıldı")
    # --- yerçekimi
    g = kosul.get("g")
    if g is not None and g > 0.01:
        gv = G0 * g
        (hedef / "constant" / "fluid" / "g").write_text(
            'FoamFile { format ascii; class uniformDimensionedVectorField; location "constant/fluid"; object g; }\n'
            f"dimensions [0 1 -2 0 0 0 0];\nvalue (0 {-gv:g} 0);\n", encoding="utf-8")
        pr = f"{(p if p is not None else kilit['ortam']['p'] / 1000.0) * 1000.0:g}"
        (hedef / "0" / "fluid" / "p_rgh").write_text(
            'FoamFile { format ascii; class volScalarField; location "0/fluid"; object p_rgh; }\n'
            f"dimensions [1 -1 -2 0 0 0 0];\ninternalField uniform {pr};\nboundaryField\n{{\n"
            "    #includeEtc \"caseDicts/setConstraintTypes\"\n"
            "    inlet { type fixedFluxPressure; value uniform " + pr + "; }\n"
            "    outlet { type prghTotalPressure; p0 uniform " + pr + "; value uniform " + pr + "; }\n"
            "    top { type fixedFluxPressure; value uniform " + pr + "; }\n"
            "    base { type fixedFluxPressure; value uniform " + pr + "; }\n"
            "    fluid_to_sibal { type fixedFluxPressure; value uniform " + pr + "; }\n"
            "    fluid_to_tel { type fixedFluxPressure; value uniform " + pr + "; }\n}\n", encoding="utf-8")
        fv = hedef / "system" / "fluid" / "fvSolution"
        s = fv.read_text(encoding="utf-8")
        s = s.replace("    pFinal\n", "    p_rgh\n    {\n        $p;\n    }\n\n    p_rghFinal\n    {\n        $p_rgh;\n        relTol 0;\n    }\n\n    pFinal\n", 1)
        fv.write_text(s, encoding="utf-8")
        notlar.append(f"g = {g:g} g₀ ({gv:g} m/s², −y yönü): constant/fluid/g + 0/fluid/p_rgh eklendi; ilk dakikada kaldırma denetlenecek")
    # --- bitiş zamanı, çekirdek
    cd = hedef / "system" / "controlDict"
    cd.write_text(re.sub(r"endTime\s+[0-9.eE+-]+;", f"endTime         {bitis_s:g};", cd.read_text(encoding="utf-8")), encoding="utf-8")
    dp = hedef / "system" / "decomposeParDict"
    dp.write_text(re.sub(r"numberOfSubdomains\s+\d+;", f"numberOfSubdomains {int(cekirdek)};", dp.read_text(encoding="utf-8")), encoding="utf-8")
    (hedef / "kos.sh").write_text("#!/bin/bash\nsource /opt/openfoam14/etc/bashrc >/dev/null 2>&1\ncd \"$(dirname \"$0\")\"\n"
                                  "decomposePar -allRegions -force > log.decomposePar 2>&1 || exit 1\n"
                                  f"exec mpirun --oversubscribe -np {int(cekirdek)} foamMultiRun -parallel\n", encoding="utf-8")
    return {"notlar": notlar, "kilit": kilit}


def kaldirma_kontrol(log_metni, g_acik):
    """g > 0 koşusunda günlükten: p_rgh çözülüyor mu (kaldırma formülasyonu devrede)? -> (tamam|None, mesaj)."""
    if not g_acik:
        return None, "g ≈ 0: kaldırma beklenmiyor"
    if re.search(r"Solving for p_rgh", log_metni):
        return True, "kaldırma açık: p_rgh çözülüyor"
    if re.search(r"Solving for p\b", log_metni):
        return False, "kaldırma KAPALI görünüyor: günlükte p_rgh yok, yalnız p çözülüyor"
    return None, "kaldırma denetlenemedi: günlükte henüz basınç çözümü yok"
