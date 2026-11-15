#!/usr/bin/env python3
"""
scripts/of_droplet_validation.py — sıvı (n-heptan damla) OpenFOAM motorunu NASA FLEX deneyleriyle karşılaştırma vakaları.

Temel vaka scripts/of_single_droplet.py ile aynı (aachenBomb tabanlı tek damla, g = 0, tek adım kimya, ışınımsız; P1 iki
denemede ıraksadığı için ilk turda yok). Fark: her FLEX testinin koşulu vakaya yazılır:
  basınç (kPa), O2 / N2 / CO2 mol kesirleri (-> kütle kesri), ilk damla çapı d0 (mm).
He seyrelticili testler şimdilik yok (tek adım mekanizmada He türü yok).

Vaka klasörü: of_kosular/droplet_validation/t<test>_<kimlik>/   (kos.sh, BILGI.json; koşudan sonra sonuc.json)
Sonuç kriteri — FLEX etiketiyle aynı tanım (scripts/psi_flex.py): yanar = 0 ⇔ alev, damla çapı d0'ın %85'ine inmeden söndü.
  Ateşleme: t=0'da 4 mm / 1500 K küre + ilk 0.3 s 5 W ısı kaynağı (FLEX sıcak tel ateşleyicisi gibi).
  t85 = d/d0 ilk kez <= 0.85 olduğu an.  Alev yaşıyor = en yüksek gaz sıcaklığı >= 1500 K (ateşleme küresi 1500 K ile
  başlar ve sönerse bunun altına iner).  skor = [0.5 s, t85] aralığında en yüksek T'nin en küçüğü (5'li kayan medyan);
  yanar_of = skor >= 1500 K.  t85'e ulaşılmadan koşu bittiyse ve alev yaşıyorsa sonuç belirsiz (None).
  Koşu süresi her vaka için t85'i kapsayacak şekilde seçilir (bitis_s; damla biterse stopAtEmptyClouds durdurur).

Kullanım:
  python3 scripts/of_droplet_validation.py --liste                # FLEX'ten 16 test seç -> liste.json (OpenFOAM gerekmez)
  python3 scripts/of_droplet_validation.py --kur                  # listedeki vakaları kur (chemkinToFoam, blockMesh, setFields)
  bash of_kosular/droplet_validation/<vaka>/kos.sh 15     # tek vaka (uygulamadan: Çözüm İzleyici > Doğrulama koşuları)
  python3 scripts/of_droplet_validation.py --analiz <vaka_klasoru># kos.sh sonunda kendiliğinden çalışır -> sonuc.json
  python3 scripts/of_droplet_validation.py --ozet                 # biten vakalardan AUC, doğruluk, K karşılaştırması -> ozet.json
"""
import argparse
import csv
import json
import math
import shutil
import statistics
import sys
import time
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "scripts"))
import of_single_droplet as TD  # noqa: E402  (blockMesh, bulut, kontrol, kabuk, cellMax/log okuyucular)

DD_KOK = TD.OF_KOK / "droplet_validation"
LISTE = DD_KOK / "liste.json"
FLEX_CSV = KOK / "data/droplet_validation.csv"
K_TAHMIN = 0.5         # mm²/s: süre tahmini için (OpenFOAM ışınımsız K genelde bundan büyük -> t85 daha erken gelir)
SURE_MIN, SURE_MAKS = 2.0, 15.0
ORAN = 0.85            # psi_flex.HEMEN_SONDU_ORANI
# FLEX'teki sıcak tel ateşleyicinin taklidi: setFields küresine ek olarak ilk ATES_SURE s boyunca ATES_Q W ısı.
# (Yalnız t=0 sıcak küresi düşük O2'de / küçük damlada 2 ms'de yanıp sönüyor; damla kendi alevini kuramıyordu.)
ATES_Q, ATES_SURE = 5.0, 0.3
ATESLEYICI = (
    "atesleyici\n{\n    type            heatSource;\n"
    f"    cellZone\n    {{\n        type        sphere;\n        zoneType    cell;\n"
    f"        centre      (0 0 0);\n        radius      {TD.R_ATES};\n    }}\n"
    f"    Q               table ((0 {ATES_Q}) ({ATES_SURE} {ATES_Q}) ({ATES_SURE + 0.01:.2f} 0) (1000 0));\n}}\n")


def bitis_suresi(d0_mm):
    """t85'i %30 payla kapsayan benzetim süresi (s)."""
    t85 = (1 - ORAN ** 2) * d0_mm ** 2 / K_TAHMIN
    return round(min(SURE_MAKS, max(SURE_MIN, 1.3 * t85)), 1)
T_ESIK = 1500.0        # K
SKOR_BAS = 0.5         # s
M = {"O2": 31.998, "N2": 28.014, "CO2": 44.009}


# ------------------------------------------------------------------ test seçimi
def flex_heptan():
    out = []
    for a in csv.DictReader(open(FLEX_CSV, encoding="utf-8-sig")):
        if a["yakit"] != "NC7H16" or a["seyreltici"] not in ("n2", "co2") or not a["ilk_cap_mm"]:
            continue
        if float(a["he_yuzde"] or 0) > 0:
            continue
        out.append(a)
    return out


def sec(n_grup=4):
    """Her seyreltici (N2, CO2) için sınıra en yakın n_grup söndü (en yüksek O2) + n_grup yandı (en düşük O2)."""
    r = flex_heptan()
    secilen = []
    for sey in ("n2", "co2"):
        x = [a for a in r if a["seyreltici"] == sey]
        sondu = sorted((a for a in x if a["yanar"] == "0"), key=lambda a: -float(a["oksijen_yuzde"]))[:n_grup]
        yandi = sorted((a for a in x if a["yanar"] == "1"),
                       key=lambda a: (float(a["oksijen_yuzde"]), a["yanma_hizi_mm2_s"] == ""))[:n_grup]
        secilen += sondu + yandi
    liste = []
    for a in secilen:
        liste.append({"ad": f"t{a['test']}_{a['kimlik']}", "test": a["test"], "kimlik": a["kimlik"],
                      "seyreltici": a["seyreltici"], "basinc_kpa": float(a["basinc_kpa"]),
                      "o2": float(a["oksijen_yuzde"]), "n2": float(a["n2_yuzde"] or 0), "co2": float(a["co2_yuzde"] or 0),
                      "d0_mm": float(a["ilk_cap_mm"]), "flex_yanar": int(a["yanar"]), "flex_sonu": a["test_sonu"],
                      "flex_K": float(a["yanma_hizi_mm2_s"]) if a["yanma_hizi_mm2_s"] else None,
                      "flex_sonme_capi_mm": float(a["sonme_capi_mm"]) if a["sonme_capi_mm"] else None})
    return liste


def liste_yaz():
    DD_KOK.mkdir(parents=True, exist_ok=True)
    l = sec()
    for v in l:
        v["bitis_s"] = bitis_suresi(v["d0_mm"])
    LISTE.write_text(json.dumps({"olusturma": time.strftime("%Y-%m-%d %H:%M"), "oran": ORAN, "esik_K": T_ESIK,
                                 "kaynak": FLEX_CSV.name, "vakalar": l}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(l)} test -> {LISTE}")
    for v in l:
        print(f"  {v['ad']:18s} {v['seyreltici']:3s} p={v['basinc_kpa']:6.1f} O2={v['o2']:4.1f} d0={v['d0_mm']:.2f} "
              f"süre={v['bitis_s']:4.1f}s FLEX yanar={v['flex_yanar']} ({v['flex_sonu']}) K={v['flex_K']}")
    return l


# ------------------------------------------------------------------ vaka kurulumu
def kutle_kesri(v):
    x = {"O2": v["o2"], "N2": v["n2"], "CO2": v["co2"]}
    top = sum(x.values())
    if abs(top - 100) > 5:                          # FLEX yüzdeleri yuvarlanmış (ör. 14 + 84 = 98): normalize edilir
        raise SystemExit(f"{v['ad']}: mol kesirleri toplamı {top} (100'den çok farklı)")
    m = sum(x[k] * M[k] for k in x)
    return {k: x[k] * M[k] / m for k in x}


def sifir(vk, v, y):
    p = v["basinc_kpa"] * 1000.0
    io = lambda d: (f"        type            inletOutlet;\n        inletValue      uniform {d};\n"   # noqa: E731
                    f"        value           uniform {d};\n")
    s = {"p": TD.alan("p", "[pressure]", f"uniform {p:.1f}",
                      f"        type            totalPressure;\n        p0              uniform {p:.1f};\n"
                      f"        value           uniform {p:.1f};\n"),
         "U": TD.alan("U", "[velocity]", "uniform (0 0 0)",
                      "        type            pressureInletOutletVelocity;\n        value           uniform (0 0 0);\n",
                      "volVectorField"),
         "T": TD.alan("T", "[temperature]", "uniform 300", io(300)),
         "Ydefault": TD.alan("Ydefault", "[]", "uniform 0", io(0)),
         "C7H16": TD.alan("C7H16", "[]", "uniform 0", io(0))}
    for k in ("O2", "N2", "CO2"):
        s[k] = TD.alan(k, "[]", f"uniform {y[k]:.6f}", io(f"{y[k]:.6f}"))
    z = vk / "0"
    if z.exists():
        shutil.rmtree(z)
    z.mkdir()
    for ad, icerik in s.items():
        (z / ad).write_text(icerik)


def kos_sh(vk):
    betik = KOK / "scripts/of_droplet_validation.py"
    (vk / "kos.sh").write_text(
        "#!/bin/bash\n"
        "# Uygulamanın koşu kuyruğundan: bash kos.sh <cekirdek>. Çıktı log.run'a gider (kuyruk yönlendirir).\n"
        "N=${1:-15}\n"
        'cd "$(dirname "$0")"\n'
        f"source {TD.BASHRC} >/dev/null 2>&1\n"
        'sed -i "s/^numberOfSubdomains .*/numberOfSubdomains $N;/" system/decomposeParDict\n'
        "rm -rf processor* postProcessing sonuc.json\n"
        'decomposePar -force > log.decomposePar 2>&1 || { echo "decomposePar başarısız"; exit 1; }\n'
        'echo "AHUT damla doğrulama: $N çekirdek, $(date)"\n'
        "mpirun --oversubscribe -np $N foamRun -parallel\n"
        "rc=$?\n"
        f'python3 "{betik}" --analiz "$PWD" || echo "analiz başarısız"\n'
        "exit $rc\n")


def kur_vaka(v):
    vk = DD_KOK / v["ad"]
    TD.guvenli_sil(vk)
    shutil.copytree(TD.foam_tut() / "multicomponentFluid/aachenBomb", vk)
    for f in ("Allrun", "Allrun-parallel", "Allclean", "constant/dynamicMeshDict"):
        (vk / f).unlink(missing_ok=True)
    y = kutle_kesri(v)
    TD.blockmesh(vk)
    sifir(vk, v, y)
    TD.D0 = v["d0_mm"] / 1000.0                     # bulut() enjeksiyon çapını modül değişkeninden okur
    TD.bulut(vk, False)
    (vk / "constant/g").write_text(TD.baslik("uniformDimensionedVectorField", "g", "constant") +
                                   "dimensions      [acceleration];\nvalue           (0 0 0);\n")
    (vk / "constant/momentumTransport").write_text(TD.baslik("dictionary", "momentumTransport", "constant") +
                                                   "simulationType  laminar;\n")
    (vk / "constant/reactionProperties").write_text(TD.baslik("dictionary", "reactionProperties", "constant") +
                                                    "reactionModel  laminar;\n")
    (vk / "constant/fvModels").write_text(TD.baslik("dictionary", "fvModels", "constant") +
                                          'clouds\n{\n    type    clouds;\n    libs    ("liblagrangianParcel.so");\n}\n' +
                                          ATESLEYICI)
    k = 1 - TD.Y_ATES
    (vk / "system/setFieldsDict").write_text(
        TD.baslik("dictionary", "setFieldsDict", "system") +
        "zones\n{\n    sicakBolge\n    {\n        type        sphere;\n        centre      (0 0 0);\n"
        f"        radius      {TD.R_ATES};\n        values\n        {{\n            T {TD.T_ATES};\n"
        f"            C7H16 {TD.Y_ATES};\n            O2 {y['O2'] * k:.6f};\n            N2 {y['N2'] * k:.6f};\n"
        f"            CO2 {y['CO2'] * k:.6f};\n        }}\n    }}\n}}\n")
    (vk / "system/decomposeParDict").write_text(
        TD.baslik("dictionary", "decomposeParDict", "system") +
        "numberOfSubdomains 15;\n\ndecomposer      scotch;\n")
    bitis = bitis_suresi(v["d0_mm"])
    TD.kontrol(vk, bitis)
    log = vk / "log.hazirlik"
    log.unlink(missing_ok=True)
    for cmd in ("chemkinToFoam chemkin/chem.inp chemkin/therm.dat chemkin/transportProperties "
                "constant/reactions constant/speciesThermo", "blockMesh", "setFields"):
        rc = TD.kabuk(cmd, vk, log=log)
        if rc != 0:
            raise SystemExit(f"{v['ad']}: '{cmd.split()[0]}' başarısız (rc={rc}), bkz. {log}")
    kos_sh(vk)
    (vk / "BILGI.json").write_text(json.dumps({**v, "bitis_s": bitis, "kutle_kesri": y, "isinim": False,
                                               "kurulum": time.strftime("%Y-%m-%d %H:%M")},
                                              ensure_ascii=False, indent=1), encoding="utf-8")
    return vk


def kur(adlar=None):
    if not LISTE.exists():
        liste_yaz()
    l = json.loads(LISTE.read_text(encoding="utf-8"))["vakalar"]
    for v in l:
        if adlar and v["ad"] not in adlar:
            continue
        if not adlar and (DD_KOK / v["ad"] / "kos.sh").exists():     # adsız --kur: yalnız eksikler
            continue
        vk = kur_vaka(v)
        print(f"Kuruldu: {vk}")


# ------------------------------------------------------------------ analiz
def analiz(vk):
    vk = Path(vk).resolve()
    b = json.loads((vk / "BILGI.json").read_text(encoding="utf-8"))
    t_T, T = TD.cellmax_oku(vk)
    t, d, _ = TD.log_serileri(vk / "log.run") if (vk / "log.run").exists() else ([], [], [])
    d0 = b["d0_mm"]
    t85 = next((tt for tt, dd in zip(t, d) if dd <= ORAN * d0), None)
    t_son = max(t_T) if t_T else None
    ust = t85 if t85 is not None else t_son
    seri = [(tt, x) for tt, x in zip(t_T, T) if ust is not None and SKOR_BAS <= tt <= ust]
    yum = [statistics.median(x for _, x in seri[max(0, i - 2):i + 3]) for i in range(len(seri))]
    skor = min(yum) if yum else None
    if skor is None:
        yanar = None
    elif skor < T_ESIK:
        yanar = 0
    else:
        yanar = 1 if t85 is not None else None          # alev yaşıyor ama %85'e ulaşılmadı: belirsiz
    K = TD.K_hesapla(t, d, d0_mm=d0, t_bas=0.1, t_son=b.get("bitis_s", 15)) if len(t) >= 5 else None
    r = {"ad": b["ad"], "t_son_s": t_son, "t85_s": t85, "skor_T_K": skor, "esik_K": T_ESIK, "yanar_of": yanar,
         "T_maks_K": max(T) if T else None, "K_of_mm2_s": K, "d_son_mm": d[-1] if d else None,
         "flex_yanar": b["flex_yanar"], "flex_K": b.get("flex_K"), "analiz": time.strftime("%Y-%m-%d %H:%M")}
    (vk / "sonuc.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False))
    return r


def _auc(y, p):
    poz = [s for yy, s in zip(y, p) if yy == 1]
    neg = [s for yy, s in zip(y, p) if yy == 0]
    if not poz or not neg:
        return None
    return sum(1.0 if a > b else 0.5 if a == b else 0.0 for a in poz for b in neg) / (len(poz) * len(neg))


def ozet():
    l = json.loads(LISTE.read_text(encoding="utf-8"))["vakalar"] if LISTE.exists() else []
    satir = []
    for v in l:
        f = DD_KOK / v["ad"] / "sonuc.json"
        durum = "bitti" if f.exists() else ("kuruldu" if (DD_KOK / v["ad"] / "kos.sh").exists() else "kurulmadı")
        s = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        satir.append({**v, "durum": durum, **{k: s.get(k) for k in ("skor_T_K", "yanar_of", "K_of_mm2_s", "t_son_s", "t85_s")}})
    b = [x for x in satir if x["durum"] == "bitti" and x["yanar_of"] is not None]
    y, p = [x["flex_yanar"] for x in b], [x["skor_T_K"] for x in b]
    dogru = sum(1 for x in b if x["yanar_of"] == x["flex_yanar"])
    kk = [(x["K_of_mm2_s"], x["flex_K"]) for x in b if x["K_of_mm2_s"] and x["flex_K"]]
    o = {"n": len(b), "n_toplam": len(satir), "auc": _auc(y, p), "dogruluk": dogru / len(b) if b else None,
         "yandi_n": sum(y), "sondu_n": len(y) - sum(y),
         "K_oran_medyan": statistics.median([a / c for a, c in kk]) if kk else None, "K_n": len(kk),
         "belirsiz_n": sum(1 for x in satir if x["durum"] == "bitti" and x["yanar_of"] is None),
         "not": "AUC: skor = [0.5 s, t85] en yüksek T'nin en küçüğü; n < 10 ya da tek sınıf varsa güvenilmez.",
         "vakalar": satir, "zaman": time.strftime("%Y-%m-%d %H:%M")}
    if DD_KOK.exists():
        (DD_KOK / "ozet.json").write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")
    return o


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--liste", action="store_true")
    ap.add_argument("--kur", nargs="*", metavar="AD")
    ap.add_argument("--analiz", metavar="VAKA")
    ap.add_argument("--ozet", action="store_true")
    a = ap.parse_args()
    if a.liste:
        liste_yaz()
    if a.kur is not None:
        kur(a.kur or None)
    if a.analiz:
        analiz(a.analiz)
    if a.ozet:
        o = ozet()
        print(json.dumps({k: v for k, v in o.items() if k != "vakalar"}, ensure_ascii=False, indent=1))
        for x in o["vakalar"]:
            print(f"  {x['ad']:18s} {x['durum']:9s} FLEX={x['flex_yanar']} OF={x['yanar_of']} skor={x['skor_T_K']}")


if __name__ == "__main__":
    main()
