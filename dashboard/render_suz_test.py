#!/usr/bin/env python3
"""render_suz_test.py — Render süzme mantığını (cekirdek/sistem.py::render_uygun) arayüz açmadan sınar.
Beş vaka tahmin() ile çözülür; tahmin()["girdi"] (malzeme, yakit_turu, g) süzgece verilir.
    python3 render_suz_test.py
"""
import sys
from pathlib import Path

BURASI = Path(__file__).resolve().parent
sys.path.insert(0, str(BURASI)); sys.path.insert(0, str(BURASI.parent))
from cekirdek import sistem  # noqa: E402
import tahmin  # noqa: E402

# (ad, girdi, beklenen mod, her renderın uygunluk koşulu)
VAKALAR = [
    ("PMMA Mars", dict(malzeme="pmma", g=0.38), "yok", None),
    ("metanol ISS", dict(malzeme="methanol", g=1e-4), "benzer", lambda x: x["yakit"] == "sivi"),
    ("heptan Mars", dict(malzeme="heptan", g=0.38), "tam", lambda x: x["vaka"]["malzeme"] == "n-heptane" and "mars" in x["paneller"]),
    ("metan ISS", dict(malzeme="metan", g=1e-4), "tam", lambda x: x["vaka"]["malzeme"] == "methane" and "uzay" in x["paneller"]),
    ("etilen ISS", dict(malzeme="etilen", g=1e-4), "benzer", lambda x: x["yakit"] == "gaz"),
]


def main():
    liste = sistem.render_listesi(BURASI / "render")
    assert len(liste) >= 30, f"render klasörü beklenenden küçük: {len(liste)}"
    ad_x = {x["ad"]: x for x in liste}
    kotu = 0
    for ad, k, beklenen, kosul in VAKALAR:
        g = tahmin.tahmin(oksijen=21, basinc=101.3, **k)["girdi"]
        for dil in ("tr", "en"):
            r = sistem.render_uygun(liste, g["malzeme"], g["yakit_turu"], g["g"], dil)
            secilen = [ad_x[a] for a in r["adlar"]]
            ok = r["mod"] == beklenen and (kosul is None or all(kosul(x) for x in secilen)) and bool(secilen) == (beklenen != "yok")
            if dil == "en":   # tr'de -en sürümleri yok, en'de tr'si olan çiftlerde yalnız -en
                ok = ok and all(x["dil"] == "en" or x["ad"].replace(".", "-en.", 1) not in ad_x for x in secilen)
            else:
                ok = ok and all(x["dil"] == "tr" for x in secilen)
            kotu += not ok
            print(f"{'GEÇTİ' if ok else 'KALDI':6s} {ad:12s} {dil}  {g['malzeme']}/{g['yakit_turu']}  -> {r['mod']:6s} {len(secilen):2d} render")
            if dil == "tr":
                for x in secilen:
                    print("          ", x["ad"].split("_p101.3_")[-1][:50], x["paneller"])
    print("hepsi geçti" if not kotu else f"{kotu} başarısız")
    return 1 if kotu else 0


if __name__ == "__main__":
    sys.exit(main())
