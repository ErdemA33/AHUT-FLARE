#!/usr/bin/env python3
"""
damla_test.py — damla motoru iyileştirmeleri için regresyon testi.

Her çalıştırmada şunları hesaplar ve bir önceki kayıtla karşılaştırır (değişen her sayı önce -> sonra):
  1. tahmin()  : tahmin_ornekler.json'daki 5 örnek + sıvı yakıt örnekleri (ORNEKLER_SIVI). sure_sn hariç
                 tüm alanlar (iç içe sözlükler düzleştirilir; uyarılar metin olarak).
  2. flex      : FLEX dürüst test sonuçları (damla_motoru.py --dogrula-hizli; ~9 dk). --dogrulama-yok ile
                 yeniden çalıştırılmaz, mevcut damla_dogrulama_*.csv okunur.
  3. dogrulama : motor_dogrulama.json (tahmin.py'nin ağırlıkları buradan).
  4. kontrol   : kalibrasyonda kullanılmayan makale damla verisi (psi_etiketli_flex2.csv; flex2_kontrol)
                 ve g bandına göre (µg / kısmi g / 1 g) ayrımı.
  5. ek        : damla_motoru'nun yeni özet çıktıları (varsa: kismi_g, belirsizlik ...) — damla_test_ek().

Kullanım:
  python3 damla_test.py                      # hesapla, damla_test_kayit/son.json ile karşılaştır, son.json'u güncelle
  python3 damla_test.py --kaydet v1          # ayrıca damla_test_kayit/v1.json olarak sakla
  python3 damla_test.py --once v1            # karşılaştırmayı v1 ile yap
  python3 damla_test.py --dogrulama-yok      # FLEX dürüst testini yeniden çalıştırma (hızlı)
Çıkış kodu 0 (yalnız rapor; karar insanda / aşama betiğinde).
"""
import argparse
import contextlib
import io
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

KOK = Path(__file__).resolve().parent
KAYIT = KOK / "damla_test_kayit"

ORNEKLER_SIVI = [
    ("heptan damla ISS", dict(malzeme="n-heptane", oksijen=21, basinc=101.3, g=1e-4, akis=0, kalinlik=2.0,
                              numune_tipi="droplet")),
    ("heptan damla ISS akış bilinmiyor", dict(malzeme="n-heptane", oksijen=21, basinc=101.3, g=1e-4)),
    ("heptan damla ISS %15 O2", dict(malzeme="n-heptane", oksijen=15, basinc=101.3, g=1e-4, akis=0, kalinlik=3.0,
                                     numune_tipi="droplet")),
    ("heptan damla Ay", dict(malzeme="n-heptane", oksijen=21, basinc=101.3, g=0.165, akis=0, kalinlik=2.0,
                             numune_tipi="droplet")),
    ("heptan damla Mars", dict(malzeme="n-heptane", oksijen=21, basinc=101.3, g=0.38, akis=0, kalinlik=2.0,
                               numune_tipi="droplet")),
    ("heptan damla Dünya", dict(malzeme="n-heptane", oksijen=21, basinc=101.3, g=1.0, akis=0, kalinlik=2.0,
                                numune_tipi="droplet")),
    ("heptan damla ISS akış 10", dict(malzeme="n-heptane", oksijen=21, basinc=101.3, g=1e-4, akis=10, kalinlik=2.0,
                                      numune_tipi="droplet")),
    ("heptan damla ISS He", dict(malzeme="n-heptane", oksijen=21, basinc=101.3, g=1e-4, akis=0, kalinlik=2.0,
                                 numune_tipi="droplet", seyreltici="he")),
    ("heptan damla ISS CO2 70 kPa", dict(malzeme="n-heptane", oksijen=25, basinc=70, g=1e-4, akis=0, kalinlik=2.5,
                                         numune_tipi="droplet", seyreltici="co2")),
    ("metanol damla ISS", dict(malzeme="methanol", oksijen=21, basinc=101.3, g=1e-4, akis=0, kalinlik=2.0,
                               numune_tipi="droplet")),
    ("metanol damla ISS %14 O2", dict(malzeme="methanol", oksijen=14, basinc=101.3, g=1e-4, akis=0, kalinlik=2.0,
                                      numune_tipi="droplet")),
    ("etanol damla ISS", dict(malzeme="ethanol", oksijen=21, basinc=101.3, g=1e-4, akis=0, kalinlik=2.0,
                              numune_tipi="droplet")),
    ("n-dekan damla ISS", dict(malzeme="n-decane", oksijen=21, basinc=101.3, g=1e-4, akis=0, kalinlik=2.0,
                               numune_tipi="droplet")),
    ("1-propanol damla ISS", dict(malzeme="1-propanol", oksijen=21, basinc=101.3, g=1e-4, akis=0, kalinlik=2.0,
                                  numune_tipi="droplet")),
    ("heptan havuz ISS", dict(malzeme="n-heptane", oksijen=21, basinc=101.3, g=1e-4, akis=0, kalinlik=5.0,
                              numune_tipi="pool")),
    ("hidrolik yağı (LLM önbelleği)", dict(malzeme="hidrolik yağı", oksijen=21, basinc=101.3, g=1e-4, akis=0)),
]


def duzlestir(x, on=""):
    out = {}
    if isinstance(x, dict):
        for k, v in x.items():
            out.update(duzlestir(v, f"{on}.{k}" if on else str(k)))
    elif isinstance(x, (list, tuple)) and x and all(isinstance(v, str) for v in x):
        out[on] = " | ".join(x)
    elif isinstance(x, (list, tuple)):
        for i, v in enumerate(x):
            out.update(duzlestir(v, f"{on}[{i}]"))
    elif isinstance(x, (np.floating, float)):
        out[on] = None if not math.isfinite(float(x)) else float(x)
    elif isinstance(x, (np.integer, np.bool_)):
        out[on] = x.item()
    else:
        out[on] = x
    return out


def tahminler():
    import tahmin as T
    ornek = [(o["ad"], o["girdi"]) for o in json.loads((KOK / "tahmin_ornekler.json").read_text(encoding="utf-8"))]
    out = {}
    with contextlib.redirect_stdout(sys.stderr):
        for ad, girdi in ornek + ORNEKLER_SIVI:
            r = T.tahmin(**girdi)
            r.pop("sure_sn", None)
            out.update(duzlestir(r, f"tahmin[{ad}]"))
    return out


def flex(yeniden):
    if yeniden:
        bas = time.time()
        r = subprocess.run([sys.executable, "damla_motoru.py", "--dogrula-hizli"], cwd=KOK, capture_output=True,
                           text=True)
        if r.returncode != 0:
            raise SystemExit("damla_motoru.py --dogrula-hizli başarısız:\n" + r.stderr[-3000:])
        print(f"  FLEX dürüst test yeniden çalıştı ({time.time() - bas:.0f} s)", file=sys.stderr)
    out = {}
    t = pd.read_csv(KOK / "damla_dogrulama_ozet_hizli.csv")
    for r in t.to_dict("records"):
        on = f"flex[{r.pop('deney')} / {r.pop('alt_kume')}]"
        out.update(duzlestir(r, on))
    g = pd.read_csv(KOK / "damla_dogrulama_gruplar.csv")
    for r in g.to_dict("records"):
        on = f"flex_grup[{r.pop('yakit')} {r.pop('seyreltici')} / {r.pop('model')}]"
        out.update(duzlestir(r, on))
    ek = KOK / "damla_dogrulama_ek.json"          # yeni aşamaların ek dürüst testleri (varsa)
    if ek.exists():
        out.update(duzlestir(json.loads(ek.read_text(encoding="utf-8")), "flex_ek"))
    return out


def dogrulama():
    d = json.loads((KOK / "motor_dogrulama.json").read_text(encoding="utf-8"))
    d.pop("uretim", None)
    return duzlestir(d, "motor_dogrulama")


def kontrol():
    import damla_motoru as dm
    from sklearn.metrics import roc_auc_score
    p, _ = dm.varsayilan_parametreler()
    with contextlib.redirect_stdout(io.StringIO()):
        d, m = dm.flex2_kontrol(p)
    out = duzlestir(m, "kontrol[flex2 makale damla, hepsi]")
    bant = np.where(d.g_seviyesi < 0.01, "µg", np.where(d.g_seviyesi < 0.9, "kısmi g", "1 g"))
    for b in ("µg", "kısmi g", "1 g"):
        x = d[bant == b]
        if len(x):
            y = x.yanar.to_numpy()
            out[f"kontrol[flex2 {b}].n"] = int(len(x))
            out[f"kontrol[flex2 {b}].dogruluk"] = float(((x.model > 0.5).astype(int) == y).mean())
            out[f"kontrol[flex2 {b}].auc"] = float(roc_auc_score(y, x.model)) if len(set(y)) == 2 else None
    if hasattr(dm, "damla_test_ek"):
        with contextlib.redirect_stdout(io.StringIO()):
            out.update(duzlestir(dm.damla_test_ek(), "ek"))
    return out


def karsilastir(once, sonra):
    deg, yeni, gitti = [], [], []
    for k in sorted(set(once) | set(sonra)):
        if k not in once:
            yeni.append(k)
        elif k not in sonra:
            gitti.append(k)
        else:
            a, b = once[k], sonra[k]
            if isinstance(a, float) and isinstance(b, float):
                if not math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9):
                    deg.append(k)
            elif a != b:
                deg.append(k)
    return deg, yeni, gitti


def kisalt(v):
    if isinstance(v, float):
        return f"{v:.4g}"
    s = str(v)
    return s if len(s) < 140 else s[:137] + "..."


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--kaydet")
    a.add_argument("--once", default="son")
    a.add_argument("--dogrulama-yok", action="store_true")
    arg = a.parse_args()
    KAYIT.mkdir(exist_ok=True)
    bas = time.time()
    s = {}
    s.update(flex(not arg.dogrulama_yok))
    s.update(dogrulama())
    s.update(kontrol())
    s.update(tahminler())
    oncef = KAYIT / f"{arg.once}.json"
    if oncef.exists():
        o = json.loads(oncef.read_text(encoding="utf-8"))
        deg, yeni, gitti = karsilastir(o, s)
        print(f"Karşılaştırma: {oncef.name} -> şimdi | {len(s)} değer, {len(deg)} değişti, {len(yeni)} yeni, "
              f"{len(gitti)} kalktı")
        for k in deg:
            print(f"  DEĞİŞTİ {k}: {kisalt(o[k])} -> {kisalt(s[k])}")
        for k in yeni:
            print(f"  YENİ    {k}: {kisalt(s[k])}")
        for k in gitti:
            print(f"  KALKTI  {k}: {kisalt(o[k])}")
    else:
        print(f"Önceki kayıt yok ({oncef.name}); {len(s)} değer kaydedildi.")
    js = json.dumps(s, ensure_ascii=False, indent=0, sort_keys=True)
    (KAYIT / "son.json").write_text(js, encoding="utf-8")
    if arg.kaydet:
        (KAYIT / f"{arg.kaydet}.json").write_text(js, encoding="utf-8")
    print(f"({time.time() - bas:.0f} s)")


if __name__ == "__main__":
    main()
