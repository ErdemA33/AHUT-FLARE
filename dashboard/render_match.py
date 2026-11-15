#!/usr/bin/env python3
"""render_match.py — OpenFOAM videolarını (of_visual/, masaüstü) render/ klasörüne dashboard'un adlandırma biçimiyle kopyalar.

    python3 render_match.py              # render_matching.csv'deki her satırı render/'a kopyala (var olanı atlar)
    python3 render_match.py --liste      # yalnız hedef adları göster

Biçim (core/system.py::_vaka_eslesmesi):  <malzeme>_g<g>_o<O2 %>_p<kPa>[_<etiket>...].<uzantı>
  - g Dünya g'si cinsinden (uzay = 0, Ay 0.165, Mars 0.38, Dünya 1); çok panelli videolarda sol (üst) panelin g'si.
  - Etiket parçaları g/o/p/a harfiyle BAŞLAMAMALI (sayı sanılır ve eşleşme bozulur); bu yüzden "gaz" yerine "metan".
  - Sızıntı koşuları "_dogrulanmadi" etiketi taşır: GÖSTERİM, deney verisiyle doğrulanmadı.
Kaynaklara dokunulmaz; yalnız kopyalanır.
"""
import argparse
import csv
import shutil
import sys
from pathlib import Path

BURASI = Path(__file__).resolve().parent
ANA = BURASI.parent
RENDER = BURASI / "render"
TABLO = BURASI / "render_matching.csv"
sys.path.insert(0, str(BURASI))
from core.system import _vaka_eslesmesi  # noqa: E402


def sayi(x):
    x = float(x)
    return str(int(x)) if x == int(x) else f"{x:g}"


def hedef_ad(s):
    kaynak = Path(s["kaynak"])
    ad = f"{s['malzeme']}_g{sayi(s['g'])}_o{sayi(s['oksijen'])}_p{sayi(s['basinc'])}_{s['etiket']}"
    if s["dogrulanmadi"] == "1":
        ad += "_dogrulanmadi"
    return ad + kaynak.suffix.lower()


def kaynak_yolu(k):
    p = Path(k).expanduser()
    return p if p.is_absolute() else ANA / p


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--liste", action="store_true")
    k = a.parse_args()
    RENDER.mkdir(exist_ok=True)
    kopyalanan = atlanan = 0
    with open(TABLO, encoding="utf-8") as f:
        for s in csv.DictReader(f):
            ad, kaynak = hedef_ad(s), kaynak_yolu(s["kaynak"])
            vaka = _vaka_eslesmesi(ad)
            assert vaka and vaka["malzeme"] == s["malzeme"], f"adlandırma eşleşmedi: {ad}"
            if k.liste:
                print(f"{s['kaynak']:45s} -> {ad}")
                continue
            if not kaynak.is_file():
                print(f"YOK: {kaynak}")
                continue
            h = RENDER / ad
            if h.exists() and h.stat().st_size == kaynak.stat().st_size:
                atlanan += 1
                continue
            shutil.copy2(kaynak, h)
            kopyalanan += 1
    if not k.liste:
        print(f"{kopyalanan} kopyalandı, {atlanan} zaten vardı -> {RENDER}")


if __name__ == "__main__":
    main()
