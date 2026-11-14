#!/usr/bin/env python3
"""
ofm_sonuc_donustur.py — OpenFOAM motorunun koşu sonuçlarını openfoam_sonuclar.csv biçimine çevirir.

    python3 ofm_sonuc_donustur.py KOSU [KOSU ...] [--kilit ofm_motor_v2/MOTOR_KILIT.json]
                                    [--cikti ofm_sonuclar/openfoam_sonuclar_ofm.csv]

KOSU: koşu klasörü (içinde postProcessing/ olan; ofm_analiz.analiz ile okunur) ya da ofm_analiz.py'nin
yazdığı JSON. Koşu klasörlerine YAZMAZ.

ÖNEMLİ: çıktı bilerek openfoam_sonuclar.csv DEĞİL. motor.py çalışma klasöründeki openfoam_sonuclar.csv'yi
kendiliğinden okur; tablo henüz sisteme bağlanmayacak (kullanıcı kararı, 2026-11-12). Bağlamak için dosyayı
elle o adla kopyalamak gerekir.

Sütunlar (motor.py belge dizesi): g, basinc, akis, kalinlik, malzeme, oksijen, yandi, yayilma_hizi,
min_oksijen, sicaklik, kaynak  (+ bilgi sütunları: tutusma_zamani_s, durum, sim_suresi_s, deney_farki_mm_s).

Girdi koşulları koşudan okunamaz; MOTOR_KILIT.json "ortam" ve "sibal" bölümlerinden alınır:
  g        : "yok (0 g)" -> 0.0001 (sistemin "uzay" kodlaması; hafif_motor G_UZAY)
  oksijen  : Y_O2, Y_N2, Y_H2O, Y_CO2 kütle kesirlerinden mol yüzdesi
  basinc   : p / 1000 (kPa);  akis: U_in · 100 (cm/s);  kalinlik: 2 · yarim_kalinlik (mm)
  malzeme  : "cotton-fiberglass (sibal)" (hafif_motor / motor.py adı)
Çıktı eşlemesi (ofm_analiz.py durum ölçütleri):
  yandi        : "yanıyor" -> 1; "söndü", "tutuşmadı" -> 0; "belirsiz ..." -> boş
  yayilma_hizi : ofm_analiz yayılma hızı (mm/s; alev cephesi = yerel kütle kaybı >= %10 olan en büyük x)
  sicaklik     : gaz max T (K);  min_oksijen: boş (tek koşu O2 taraması değil)
"""
import argparse
import csv
import json
from pathlib import Path

KOK = Path(__file__).resolve().parent
VARSAYILAN_KILIT = KOK / "ofm_motor_v2" / "MOTOR_KILIT.json"
VARSAYILAN_CIKTI = KOK / "ofm_sonuclar" / "openfoam_sonuclar_ofm.csv"
SUTUNLAR = ["g", "basinc", "akis", "kalinlik", "malzeme", "oksijen", "yandi", "yayilma_hizi", "min_oksijen",
            "sicaklik", "kaynak", "tutusma_zamani_s", "durum", "sim_suresi_s", "deney_farki_mm_s"]
M = {"O2": 31.998, "N2": 28.014, "H2O": 18.015, "CO2": 44.009}
G_UZAY = 0.0001
MALZEME = "cotton-fiberglass (sibal)"
DENEY_HIZ = 2.3   # mm/s, Saffire-III S1 (NTRS 20180005168, Tablo 1)


def kosullar(kilit):
    o, s = kilit["ortam"], kilit["sibal"]
    n = {k: o[f"Y_{k}"] / M[k] for k in M}
    g = o.get("g")
    g = G_UZAY if (g is None or isinstance(g, str) or float(g) <= G_UZAY) else float(g)
    return {"g": g, "basinc": round(o["p"] / 1000.0, 3), "akis": round(o["U_in"] * 100.0, 2),
            "kalinlik": round(2 * s["yarim_kalinlik_m"] * 1000.0, 3), "malzeme": MALZEME,
            "oksijen": round(100.0 * n["O2"] / sum(n.values()), 2)}


def kayit_satiri(kayit):
    """ofm_ice_aktar.py'nin dizin kaydından (ofm_motor.kosular()) satır: koşullar BILGI.json'dan (her yakıt türü için).
    yandi: tutuşma oldu mu (1/0), katıda 'yanıyor' (motor.py/ofm_sonuc_donustur'daki eski eşleme) değil; sıvı/gazda tutuşma varsa 1."""
    k, s = kayit.get("kosullar") or {}, kayit.get("sonuc") or {}
    tut = s.get("tutusma_zamani_s")
    d = str(s.get("durum") or "")
    yandi = "" if d.startswith("belirsiz") else (1 if tut is not None else 0)
    hiz = s.get("yayilma_hizi_mm_s")
    return {"g": k.get("g"), "basinc": k.get("basinc"), "akis": k.get("akis"), "kalinlik": k.get("kalinlik"),
            "malzeme": kayit.get("malzeme"), "oksijen": k.get("oksijen"), "yandi": yandi,
            "yayilma_hizi": "" if hiz is None else hiz, "min_oksijen": "",
            "sicaklik": "" if s.get("gaz_T_maks_K") is None else s["gaz_T_maks_K"],
            "kaynak": f"OpenFOAM ({kayit.get('yakit_turu')}, {kayit.get('boyut')}, deney: {kayit.get('deney')}): {kayit.get('kosu')}",
            "tutusma_zamani_s": "" if tut is None else tut, "durum": d, "sim_suresi_s": s.get("simulasyon_suresi_s") or "",
            "deney_farki_mm_s": "" if hiz is None or kayit.get("deney") != "saffire3" else round(hiz - DENEY_HIZ, 3)}


def csv_yaz(satirlar, cikti):
    cikti = Path(cikti)
    if cikti.name == "openfoam_sonuclar.csv":
        raise SystemExit("openfoam_sonuclar.csv adı motor.py'ye bağlanır; başka ad ver")
    cikti.parent.mkdir(parents=True, exist_ok=True)
    with open(cikti, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=SUTUNLAR)
        w.writeheader()
        w.writerows(satirlar)


def sonuc_oku(yol):
    yol = Path(yol)
    if yol.suffix == ".json":
        return json.loads(yol.read_text(encoding="utf-8"))
    import ofm_analiz as ba
    return ba.analiz(yol)[0]


def satir(sonuc, kosul, kaynak):
    d = str(sonuc.get("durum") or "")
    yandi = 1 if d == "yanıyor" else (0 if d in ("söndü", "tutuşmadı") else "")
    hiz = sonuc.get("yayilma_hizi_mm_s")
    return {**kosul, "yandi": yandi, "yayilma_hizi": "" if hiz is None else hiz, "min_oksijen": "",
            "sicaklik": "" if sonuc.get("gaz_T_maks_K") is None else sonuc["gaz_T_maks_K"],
            "kaynak": kaynak, "tutusma_zamani_s": "" if sonuc.get("tutusma_zamani_s") is None
            else sonuc["tutusma_zamani_s"], "durum": d, "sim_suresi_s": sonuc.get("simulasyon_suresi_s") or "",
            "deney_farki_mm_s": "" if hiz is None else round(hiz - DENEY_HIZ, 3)}


def main():
    a = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    a.add_argument("kosular", nargs="+")
    a.add_argument("--kilit", default=str(VARSAYILAN_KILIT))
    a.add_argument("--cikti", default=str(VARSAYILAN_CIKTI))
    k = a.parse_args()
    cikti = Path(k.cikti)
    if cikti.name == "openfoam_sonuclar.csv":
        raise SystemExit("openfoam_sonuclar.csv adı motor.py'ye bağlanır; henüz bağlanmayacak -> başka ad ver")
    kilit = json.loads(Path(k.kilit).read_text(encoding="utf-8"))
    kosul = kosullar(kilit)
    kaynak_on = f"OpenFOAM ({kilit.get('surum', '?')}, {kilit.get('kaynak_kosu', '?')}; Saffire-III S1, 2B)"
    satirlar = []
    for y in k.kosular:
        s = sonuc_oku(y)
        satirlar.append(satir(s, kosul, f"{kaynak_on}: {Path(y).resolve()}"))
    cikti.parent.mkdir(parents=True, exist_ok=True)
    with open(cikti, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=SUTUNLAR)
        w.writeheader()
        w.writerows(satirlar)
    for r in satirlar:
        print({c: r[c] for c in ("g", "oksijen", "basinc", "akis", "kalinlik", "yandi", "yayilma_hizi", "durum")})
    print(f"Kaydedildi: {cikti} ({len(satirlar)} satır; motor.py'ye BAĞLI DEĞİL)")


if __name__ == "__main__":
    main()
