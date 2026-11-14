#!/usr/bin/env python3
"""ornek_guncelle.py — uygulamayla gelen örnek vakaları (veri/ornekler/*.ahut) ve Topluluk önbelleğindeki
(veri/topluluk_onbellek.json) vakaları güncel backend ile YENİDEN ÇÖZER: güven (v1 + v2), birleşik ihtimal,
motor kaynağı, adımlar vb. yeni alanlar sonuca girer. Girdiler, başlık, açıklama, yazar ve yorumlar korunur.

    python3 ornek_guncelle.py            # yaz
    python3 ornek_guncelle.py --kontrol  # yalnız eski / yeni güven tablosu
"""
import argparse
import json
import sys
from pathlib import Path

BURASI = Path(__file__).resolve().parent
sys.path.insert(0, str(BURASI))
import ahut_flare as A  # noqa: E402  (yolları ve ortam değişkenlerini ayarlar)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--kontrol", action="store_true")
    k = a.parse_args()
    from cekirdek.kopru import Kopru
    api = Kopru(surum=A.SURUM, arayuz=A.ARAYUZ, motor_yolu=A.MOTOR, veri=A.VERI, render=A.RENDER,
                anahtar=A.ANAHTAR, mock=False, ornekler=A.ORNEKLER, site=A.SITE)
    if api.motoru_yukle()["durum"] != "hazir":
        sys.exit("model yüklenemedi")
    zaman = __import__("datetime").datetime.now().isoformat(timespec="seconds")

    def coz(p):
        s = api.coz(p["girdi"])
        if "hata" in s["tahmin"]:
            raise RuntimeError(s["tahmin"]["hata"])
        yeni = {"tahmin": s["tahmin"]["veri"]}
        for ad in ("oksijen_egrisi", "harita", "akis_egrisi", "yakin"):
            yeni[ad] = s[ad].get("veri") if isinstance(s.get(ad), dict) else None
        return yeni

    def tablo(ad, eski, yeni):
        g1 = (eski.get("guven") or {}).get("skor")
        g2 = (yeni.get("guven_v2") or {}).get("skor")
        print(f"{ad[:46]:46s} güven(eski) {str(g1):>4s} -> v1 {str((yeni.get('guven') or {}).get('skor')):>4s}, "
              f"v2 {str(g2):>4s} | risk {eski.get('risk_seviyesi')} -> {yeni.get('risk_seviyesi')} | "
              f"birleşik {yeni.get('yanma_birlesik')} ({yeni.get('motor_kaynagi')})")

    for f in sorted(A.ORNEKLER.glob("*.ahut")):
        p = json.loads(f.read_text(encoding="utf-8"))
        yeni = coz(p)
        tablo(f.name, p["sonuc"]["tahmin"], yeni["tahmin"])
        if not k.kontrol:
            p["sonuc"] = yeni
            p["guncelleme"] = zaman
            p["yeniden_cozum"] = {"zaman": zaman, "not": "ornek_guncelle.py: güncel backend ile yeniden çözüldü"}
            f.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    ob = A.VERI / "topluluk_onbellek.json"
    if ob.exists():
        o = json.loads(ob.read_text(encoding="utf-8"))
        for dosya, p in (o.get("paketler") or {}).items():
            yeni = coz(p)
            tablo("önbellek: " + dosya, p["sonuc"]["tahmin"], yeni["tahmin"])
            if not k.kontrol:
                p["sonuc"] = yeni
                p["yeniden_cozum"] = {"zaman": zaman, "not": "ornek_guncelle.py"}
        if not k.kontrol:
            o["liste"] = [dict(api.depo.ozet(o["paketler"][x["dosya"]]), kaynak=x.get("kaynak"), dosya=x.get("dosya"),
                               adres=x.get("adres")) if x.get("dosya") in o["paketler"] else x for x in o.get("liste", [])]
            ob.write_text(json.dumps(o, ensure_ascii=False), encoding="utf-8")
    print("tamam" + (" (yazılmadı)" if k.kontrol else ""))


if __name__ == "__main__":
    main()
