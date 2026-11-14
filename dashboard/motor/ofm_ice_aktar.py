#!/usr/bin/env python3
"""ofm_ice_aktar.py — OpenFOAM motorunun koşu sonuçlarını (katı / sıvı / gaz) içe aktarır, analiz eder, tabloya ve dizine yazar.

    python3 ofm_ice_aktar.py KAYNAK [KAYNAK ...] [--gelen ofm_gelen] [--sonuc ofm_sonuclar] [--render dashboard/render]

KAYNAK: .tar.gz / .tgz / .zip arşivi ya da koşu klasörü (içinde BILGI.json). OpenFOAM motorunun klasörlerine YAZILMAZ (arşiv açılır / klasör
kopyalanır). Adımlar: BILGI.json denetimi → ofm_analiz.analiz_tur (yakıt türüne göre) → ofm_karsilastir (deney) →
<sonuc>/<koşu>.json özeti → ofm_kosular.json dizini → openfoam_sonuclar_ofm.csv (ofm_sonuc_donustur) → video/görüntüler render/'a
(vaka adlandırmasıyla, "kosu-<koşu>" etiketiyle; doğrulanmadıysa "_dogrulanmadi").
Ortam: AHUT_OFM_KOK (kök), AHUT_RENDER (render klasörü) — testlerde geçici klasöre yönlendirmek için.
"""
import argparse
import json
import os
import re
import shutil
import sys
import tarfile
import time
import zipfile
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))
import ofm_analiz as ba  # noqa: E402
import ofm_karsilastir as bk  # noqa: E402
import ofm_motor as bm  # noqa: E402
import ofm_sonuc_donustur as bsd  # noqa: E402

TURLER = ("kati", "sivi", "gaz")
DENEYLER = ("saffire3", "bass4", "flex", "bre", "yok")
MEDYA = {".mp4", ".webm", ".gif", ".png", ".jpg", ".jpeg"}
G_UZAY = 0.0001


def _guvenli_ac(arsiv: Path, hedef: Path) -> Path:
    hedef.mkdir(parents=True, exist_ok=True)
    kok = hedef.resolve()
    def kontrol(ad):
        if not (kok / ad).resolve().is_relative_to(kok):
            raise SystemExit(f"{arsiv.name}: güvensiz yol ({ad})")
    if arsiv.suffix == ".zip":
        with zipfile.ZipFile(arsiv) as z:
            for ad in z.namelist():
                kontrol(ad)
            z.extractall(hedef)
            ust = {n.split("/")[0] for n in z.namelist() if n.strip("/")}
    else:
        with tarfile.open(arsiv) as t:
            for u in t.getmembers():
                kontrol(u.name)
                if u.issym() or u.islnk():
                    raise SystemExit(f"{arsiv.name}: bağlantı içeriyor ({u.name})")
            t.extractall(hedef)
            ust = {u.name.split("/")[0] for u in t.getmembers() if u.name.strip("/")}
    ust = [u for u in ust if (hedef / u / "BILGI.json").exists()]
    if len(ust) != 1:
        raise SystemExit(f"{arsiv.name}: tek bir koşu klasörü (BILGI.json'lu) bekleniyordu, bulunan: {sorted(ust)}")
    return hedef / ust[0]


def bilgi_denetle(case: Path):
    """BILGI.json'u okur, koşulları normalleştirir. Dönüş: (bilgi, koşullar, sorunlar)."""
    sorunlar = []
    try:
        b = json.loads((case / "BILGI.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {}, {}, [f"BILGI.json okunamadı: {e}"]
    tur = {"katı": "kati", "sıvı": "sivi"}.get(str(b.get("yakit_turu", "")).lower(), str(b.get("yakit_turu", "")).lower())
    if tur not in TURLER:
        sorunlar.append(f"yakit_turu {TURLER} olmalı (bulunan: {b.get('yakit_turu')!r})")
    for a in ("kosu", "malzeme", "boyut"):
        if not b.get(a):
            sorunlar.append(f"'{a}' yok")
    if str(b.get("deney", "yok")).lower() not in DENEYLER:
        sorunlar.append(f"deney {DENEYLER} olmalı")
    k = b.get("kosullar") or {}
    for a in ("g", "oksijen", "basinc"):
        if k.get(a) is None:
            sorunlar.append(f"kosullar.{a} yok")
    kal = k.get("kalinlik_mm", k.get("cap_mm"))
    g = k.get("g")
    kos = {"g": G_UZAY if (g is not None and float(g) <= G_UZAY) else g, "oksijen": k.get("oksijen"), "basinc": k.get("basinc"),
           "akis": k.get("akis", 0.0), "kalinlik": kal}
    b["yakit_turu"], b["deney"] = tur, str(b.get("deney", "yok")).lower()
    return b, kos, sorunlar


def _egri(sonuc, bilgi, kos):
    """Arayüzdeki deney karşılaştırma grafiği için {x, y, ad, ...} ve deney referansı."""
    if sonuc.get("yakit_turu") == "kati" and sonuc.get("alev_cephesi"):
        pts = [(c["t"], c["x_m"] * 1000.0) for c in sonuc["alev_cephesi"] if c.get("x_m") is not None]
        x0 = bilgi.get("numune_x0_m")
        ref = None
        import ofm_dogrulama as bd
        dz = bd.DENEY.get(bilgi.get("deney"))
        if dz and pts and x0 is not None and sonuc.get("tutusma_zamani_s") is not None:
            t0 = sonuc["tutusma_zamani_s"]
            ref = [{"x": t0, "y": x0 * 1000.0}, {"x": pts[-1][0], "y": x0 * 1000.0 + dz["yayilma_mm_s"] * (pts[-1][0] - t0)}]
        return {"ad": "alev ucu x (mm) – zaman (s)", "x": [a for a, _ in pts], "y": [b for _, b in pts], "deney_dogru": ref}
    if sonuc.get("yakit_turu") == "sivi" and sonuc.get("d2_t"):
        d = sonuc["d2_t"]
        return {"ad": "d² (mm²) – zaman (s)", "x": [p["t"] for p in d], "y": [p["d2_mm2"] for p in d], "deney_dogru": None}
    return None


def _render_kopyala(case: Path, kayit, render: Path):
    kopya = []
    if not render.is_dir():
        return kopya
    k = kayit["kosullar"]
    ad = re.sub(r"[^\w.-]+", "-", kayit["malzeme"]).replace("_", "-").strip("-").lower()
    etiket = "kosu-" + re.sub(r"[^\w.-]+", "-", kayit["kosu"]).replace("_", "-").strip("-")
    sayi = lambda x: str(int(x)) if float(x) == int(float(x)) else f"{float(x):g}"
    dogrulanmadi = (kayit.get("dogrulama") or {}).get("basari") is None
    adaylar = [p for p in sorted(case.rglob("*")) if p.is_file() and p.suffix.lower() in MEDYA and "postProcessing" not in p.parts]
    for i, p in enumerate(adaylar):
        hedef = f"{ad}_g{sayi(k['g'])}_o{sayi(k['oksijen'])}_p{sayi(k['basinc'])}_{etiket}{'' if i == 0 else f'-{i + 1}'}" \
                f"{'_dogrulanmadi' if dogrulanmadi else ''}{p.suffix.lower()}"
        shutil.copy2(p, render / hedef)
        kopya.append(hedef)
    return kopya


def ice_aktar(kaynak, gelen: Path, sonuc: Path, render: Path | None):
    kaynak = Path(kaynak).expanduser().resolve()
    gelen.mkdir(parents=True, exist_ok=True)
    if kaynak.is_dir():
        case = gelen / kaynak.name
        if case.resolve() != kaynak:
            if case.exists():
                shutil.rmtree(case)
            shutil.copytree(kaynak, case, ignore=lambda d, adlar: [a for a in adlar if a.startswith("processor") or (Path(d) == kaynak and re.fullmatch(r"\d+(\.\d+)?", a) and a != "0")])
    else:
        case = _guvenli_ac(kaynak, gelen)
    bilgi, kos, sorunlar = bilgi_denetle(case)
    if sorunlar:
        return {"kosu": case.name, "hata": "BILGI.json eksik/hatalı", "sorunlar": sorunlar}
    s = ba.analiz_tur(case)
    dog = bk.karsilastir(s, bilgi, kos)
    tut = s.get("tutusma_zamani_s")
    d = str(s.get("durum") or "")
    yandi = None if d.startswith("belirsiz") else (1 if tut is not None else 0)
    kayit = {"kosu": bilgi["kosu"], "yakit_turu": bilgi["yakit_turu"], "malzeme": bilgi["malzeme"], "deney": bilgi["deney"],
             "boyut": bilgi["boyut"], "kosullar": kos, "yandi": yandi, "sonuc": {k: v for k, v in s.items() if k not in ("d2_t", "alev_cephesi", "alev_cephesi_genislik_ortalamasi", "deney")},
             "dogrulama": dog, "egri": _egri(s, bilgi, kos), "eksik": s.get("eksik", []), "gelen_yolu": str(case),
             "notlar": bilgi.get("notlar"), "ice_aktarma": time.strftime("%Y-%m-%d %H:%M:%S")}
    kayit["render"] = _render_kopyala(case, kayit, render) if render else []
    sonuc.mkdir(parents=True, exist_ok=True)
    (sonuc / f"{kayit['kosu']}.json").write_text(json.dumps({**kayit, "tam_sonuc": s}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    liste = [k for k in bm.kosular() if k.get("kosu") != kayit["kosu"]] + [kayit]
    bm.kayit_yaz(liste)
    bsd.csv_yaz([bsd.kayit_satiri(k) for k in liste], sonuc / "openfoam_sonuclar_ofm.csv")
    return kayit


def main():
    a = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    a.add_argument("kaynaklar", nargs="+")
    a.add_argument("--gelen", default=str(bm.kok() / "ofm_gelen"))
    a.add_argument("--sonuc", default=str(bm.kok() / "ofm_sonuclar"))
    a.add_argument("--render", default=os.environ.get("AHUT_RENDER") or str(KOK / "dashboard" / "render"))
    k = a.parse_args()
    os.environ.setdefault("AHUT_OFM_KOK", str(Path(k.sonuc).resolve().parent))
    kod = 0
    for src in k.kaynaklar:
        r = ice_aktar(src, Path(k.gelen), Path(k.sonuc), Path(k.render) if k.render else None)
        if r.get("hata"):
            kod = 1
            print(f"HATA {r['kosu']}: {r['hata']}: " + "; ".join(r["sorunlar"]))
            continue
        dg = r["dogrulama"]
        print(f"{r['kosu']} [{r['yakit_turu']}, {r['boyut']}]: {r['sonuc'].get('durum')}; deney {dg['deney']}: "
              f"{'doğrulanmadı' if dg['basari'] is None else 'başarı %.2f' % dg['basari']}; eksik: {len(r['eksik'])}; render: {len(r['render'])}")
        for e in r["eksik"]:
            print("   EKSİK:", e)
    return kod


if __name__ == "__main__":
    sys.exit(main())
