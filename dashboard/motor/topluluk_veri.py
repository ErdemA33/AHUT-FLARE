#!/usr/bin/env python3
"""
topluluk_veri.py — kullanıcıların malzeme / deney verisi eklediği topluluk katmanı (internetsiz, SQLite).

    import topluluk_veri as tv
    r = tv.ekle({"malzeme": "pmma", "g": 1e-4, "oksijen_yuzde": 21, "basinc_kpa": 101.3, "sonuc": "yandi",
                 "kaynak_turu": "kendi_deney", "kaynak": "Lab defteri s. 12", "ekleyen": "ayse"})
    tv.csv_yukle("topluluk_sablon.csv", ekleyen="ayse")
    tv.onayla(r["id"], moderator="mehmet")          # onaysiz -> onayli
    tv.reddet(r["id"], moderator="mehmet", gerekce="kaynak yok")
    tv.listele({"durum": "onayli", "malzeme": "pmma"})
    tv.disa_aktar("paket.json");  tv.ice_aktar("paket.json")     # içe aktarılanlar hep "onaysiz"
    tv.pdf_ekle("makale.pdf", ekleyen="ayse")       # isteğe bağlı: EVREN ile aday kayıtlar (internet gerekir)

Komut satırı:  python3 topluluk_veri.py listele [--durum onaysiz]
               python3 topluluk_veri.py yukle dosya.csv --ekleyen ad
               python3 topluluk_veri.py onayla ID --moderator ad
               python3 topluluk_veri.py disa paket.json | ice paket.json

KURAL: topluluk verisi risk modelinin ve motorların KALİBRASYONUNA GİRMEZ.
  - Depo `topluluk/topluluk.sqlite`; risk_modeli.py / hafif_motor.py yalnız `psi_etiketli*.csv`, `veri_temiz.csv`,
    `etiketli_gemma3.csv` dosyalarını okur, bu klasöre bakmaz.
  - Ek olarak bu modül, çağrı yığınında bir model / kalibrasyon betiği görürse (KALIBRASYON_BETIKLERI) ya da
    komut satırında kalibrasyon bayrağı varsa (--kalibre*, --bootstrap) veri vermeyi reddeder
    (ToplulukKalibrasyonHatasi). Tek izinli tüketici tahmin.py'nin güven skoru (yalnız yakın kayıt sayısı).

Otomatik kontroller (ekle / csv_yukle / ice_aktar):
  1) zorunlu alanlar ve sayıya çevirme (virgüllü ondalık kabul)
  2) fiziksel aralık (dışındaysa RED) ve birim şüphesi (etiket "birim_supheli" + not; reddedilmez)
  3) mükerrer kayıt (aynı malzeme + koşullar + sonuç + kaynak) -> eklenmez, mevcut id döner
  4) aynı koşuldaki NASA verisiyle çelişki (psi_etiketli*.csv, etiket_kaynagi psi / makale_elle):
     aynı ana malzeme, aynı g bandı, |ΔO2| <= 1, |Δlog10 p| <= 0.1 (+ biliniyorsa akış ve kalınlık yakın) ve
     NASA noktalarının en az 2/3'ü ters sonuçtaysa etiket "celiski" (reddedilmez).
"""
import argparse
import csv
import datetime as dt
import inspect
import json
import math
import os
import sqlite3
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent
# öncelik: TOPLULUK_DB > YANGIN_VERI_KLASORU/topluluk/ > bu klasör/topluluk/
DEPO = Path(os.environ.get("TOPLULUK_DB") or (Path(os.environ["YANGIN_VERI_KLASORU"]) if os.environ.get("YANGIN_VERI_KLASORU")
                                               else KOK) / "topluluk" / "topluluk.sqlite")
ANAHTAR = Path(os.environ.get("EVREN_ANAHTAR_DOSYASI") or KOK / "evren_anahtar.txt")
SABLON = KOK / "topluluk_sablon.csv"
SURUM = 1

ALANLAR = ["malzeme", "yakit_turu", "numune_tipi", "kalinlik_mm", "g", "oksijen_yuzde", "basinc_kpa", "akis_cm_s",
           "seyreltici", "sonuc", "yayilma_hizi_mm_s", "K_mm2_s", "sonme_capi_mm", "kaynak_turu", "kaynak", "yontem",
           "ekleyen", "tarih"]
ZORUNLU = ["malzeme", "g", "oksijen_yuzde", "basinc_kpa", "sonuc", "kaynak_turu", "kaynak", "ekleyen"]
SAYISAL = ["kalinlik_mm", "g", "oksijen_yuzde", "basinc_kpa", "akis_cm_s", "yayilma_hizi_mm_s", "K_mm2_s",
           "sonme_capi_mm"]
YAKIT_TURLERI = {"kati", "sivi", "gaz"}
KAYNAK_TURLERI = {"doi", "rapor", "kendi_deney", "makale_pdf"}
DURUMLAR = ("onaysiz", "onayli", "reddedildi")
SONUC_ESANLAM = {"yandi": "yandi", "yandı": "yandi", "1": "yandi", "evet": "yandi", "burned": "yandi",
                 "sustained": "yandi", "true": "yandi",
                 "sondu": "sondu", "söndü": "sondu", "0": "sondu", "hayir": "sondu", "hayır": "sondu",
                 "extinguished": "sondu", "not_sustained": "sondu", "no_ignition": "sondu", "false": "sondu"}
# (alt, üst) fiziksel sınırlar: dışındaysa RED.  Birim: kalınlık/çap mm, g g0, O2 % (mol), basınç kPa, akış cm/s
ARALIK = {"kalinlik_mm": (1e-4, 500.0), "g": (0.0, 10.0), "oksijen_yuzde": (0.0, 100.0), "basinc_kpa": (0.1, 20000.0),
          "akis_cm_s": (0.0, 2000.0), "yayilma_hizi_mm_s": (0.0, 2000.0), "K_mm2_s": (0.0, 20.0),
          "sonme_capi_mm": (0.0, 500.0)}
# birim şüphesi: (koşul, açıklama) -> etiket "birim_supheli"
SUPHE = [
    ("oksijen_yuzde", lambda v: 0 < v <= 1.0, "O2 ≤ 1: oran (0-1) girilmiş olabilir, % bekleniyor"),
    ("basinc_kpa", lambda v: v < 5.0, "basınç < 5 kPa: atm ya da bar girilmiş olabilir (kPa bekleniyor)"),
    ("basinc_kpa", lambda v: v > 2000.0, "basınç > 2000 kPa: Pa girilmiş olabilir"),
    ("g", lambda v: 9.0 <= v <= 10.5, "g ≈ 9.8: m/s² girilmiş olabilir (g0 cinsinden bekleniyor, Dünya = 1)"),
    ("akis_cm_s", lambda v: v > 300.0, "akış > 300 cm/s: mm/s girilmiş olabilir"),
    ("kalinlik_mm", lambda v: v > 50.0, "kalınlık/çap > 50 mm: µm girilmiş olabilir"),
    ("K_mm2_s", lambda v: v > 3.0, "K > 3 mm²/s: damla yanma hızı için olağan dışı"),
]
NASA_KOSUL = {"oksijen": 1.0, "log_basinc": 0.1, "akis_oran": 0.5, "akis_mutlak": 2.0, "kalinlik_oran": 2.0}
CELISKI_PAYI = 2 / 3
# Bu betikler (doğrudan çalıştırılırken ya da çağrı yığınında) topluluk verisini OKUYAMAZ
KALIBRASYON_BETIKLERI = {"risk_modeli.py", "hafif_motor.py", "damla_motoru.py", "gaz_motoru.py", "model_egit.py",
                         "motor_dogrulama_uret.py", "of_kalibre.py"}
KALIBRASYON_BAYRAKLARI = ("--kalibre", "--bootstrap", "--kalibre-hizli", "--kalibre-ayrintili")


class ToplulukHatasi(ValueError):
    """Kayıt reddedildi (eksik alan, fiziksel aralık dışı, geçersiz değer)."""


class ToplulukKalibrasyonHatasi(PermissionError):
    """Topluluk verisi model / motor kalibrasyonuna giremez."""


# ------------------------------------------------------------------ kalibrasyon engeli
def _kalibrasyon_engeli():
    ana = Path(getattr(sys.modules.get("__main__"), "__file__", "") or "").name
    if ana in KALIBRASYON_BETIKLERI or any(a.startswith(KALIBRASYON_BAYRAKLARI) for a in sys.argv[1:]):
        raise ToplulukKalibrasyonHatasi(
            f"Topluluk verisi kalibrasyona girmez ({ana or 'komut satırı'} {' '.join(sys.argv[1:])[:60]})")
    for c in inspect.stack()[2:]:
        if Path(c.filename).name in KALIBRASYON_BETIKLERI:
            raise ToplulukKalibrasyonHatasi(f"Topluluk verisi kalibrasyona girmez (çağıran: {Path(c.filename).name})")


# ------------------------------------------------------------------ depo
def _baglan():
    DEPO.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DEPO)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS kayitlar (
        id INTEGER PRIMARY KEY AUTOINCREMENT, veri TEXT NOT NULL, anahtar TEXT NOT NULL, durum TEXT NOT NULL,
        etiketler TEXT NOT NULL, notlar TEXT NOT NULL, moderator TEXT, karar_tarihi TEXT, gerekce TEXT,
        eklenme TEXT NOT NULL)""")
    c.execute("CREATE INDEX IF NOT EXISTS ix_anahtar ON kayitlar(anahtar)")
    return c


def _satir(r):
    return {"id": r["id"], **json.loads(r["veri"]), "durum": r["durum"], "etiketler": json.loads(r["etiketler"]),
            "kontrol_notlari": json.loads(r["notlar"]), "moderator": r["moderator"],
            "karar_tarihi": r["karar_tarihi"], "gerekce": r["gerekce"], "eklenme": r["eklenme"]}


def _simdi():
    return dt.datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------ doğrulama
def _sayi(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return None if isinstance(v, float) and math.isnan(v) else float(v)
    s = str(v).strip().replace(",", ".")
    if s == "" or s.lower() in ("nan", "none", "null", "-"):
        return None
    return float(s)


def _ana(malzeme):
    try:
        from risk_modeli import malzeme_ana
        return malzeme_ana(str(malzeme))
    except Exception:
        return str(malzeme).lower().strip()


def _g_bandi(g):
    return "uzay" if g < 0.01 else ("kismi" if g < 0.9 else "dunya")


def dogrula(kayit):
    """Kaydı temizler ve denetler. -> (temiz kayıt, etiketler, notlar). Kabul edilemezse ToplulukHatasi."""
    k = {a: kayit.get(a) for a in ALANLAR}
    hatalar, etiketler, notlar = [], [], []
    for a in ZORUNLU:
        if k.get(a) is None or str(k[a]).strip() == "":
            hatalar.append(f"'{a}' zorunlu")
    for a in SAYISAL:
        try:
            k[a] = _sayi(k.get(a))
        except (TypeError, ValueError):
            hatalar.append(f"'{a}' sayı değil: {k.get(a)!r}")
            k[a] = None
    if k.get("sonuc") is not None:
        s = SONUC_ESANLAM.get(str(k["sonuc"]).strip().lower())
        if s is None:
            hatalar.append(f"'sonuc' yandi/sondu olmalı: {k['sonuc']!r}")
        k["sonuc"] = s
    if k.get("yakit_turu"):
        k["yakit_turu"] = str(k["yakit_turu"]).strip().lower().replace("ı", "i")
        if k["yakit_turu"] not in YAKIT_TURLERI:
            hatalar.append(f"'yakit_turu' {sorted(YAKIT_TURLERI)} içinden olmalı: {k['yakit_turu']!r}")
    if k.get("kaynak_turu"):
        k["kaynak_turu"] = str(k["kaynak_turu"]).strip().lower()
        if k["kaynak_turu"] not in KAYNAK_TURLERI:
            hatalar.append(f"'kaynak_turu' {sorted(KAYNAK_TURLERI)} içinden olmalı: {k['kaynak_turu']!r}")
    for a, (lo, hi) in ARALIK.items():
        v = k.get(a)
        if v is not None and not (lo <= v <= hi):
            hatalar.append(f"'{a}' = {v:g} fiziksel aralık dışında ({lo:g}–{hi:g})")
    if k.get("oksijen_yuzde") is not None and k["oksijen_yuzde"] <= 0:
        hatalar.append("'oksijen_yuzde' 0'dan büyük olmalı")
    if (k.get("sonme_capi_mm") is not None and k.get("kalinlik_mm") is not None
            and k["sonme_capi_mm"] > k["kalinlik_mm"] * 1.0001):
        hatalar.append("sönme çapı ilk çaptan (kalinlik_mm) büyük olamaz")
    if k.get("sonuc") == "sondu" and k.get("yayilma_hizi_mm_s"):
        notlar.append("sonuç 'söndü' ama yayılma hızı verilmiş (geçici yayılma olabilir) — kontrol edin")
    if hatalar:
        raise ToplulukHatasi("; ".join(hatalar))
    for a, kosul, aciklama in SUPHE:
        if k.get(a) is not None and kosul(k[a]):
            notlar.append(aciklama)
            if "birim_supheli" not in etiketler and a != "K_mm2_s":
                etiketler.append("birim_supheli")
    k["malzeme"] = str(k["malzeme"]).strip()
    for a in ("numune_tipi", "seyreltici", "yontem", "kaynak", "ekleyen"):
        if k.get(a) is not None:
            k[a] = str(k[a]).strip() or None
    k["tarih"] = k.get("tarih") or dt.date.today().isoformat()
    return k, etiketler, notlar


def _anahtar(k):
    r = lambda v, n=4: "" if v is None else f"{round(v, n):g}"
    return "|".join([_ana(k["malzeme"]), r(k["g"], 6), r(k["oksijen_yuzde"], 2), r(k["basinc_kpa"], 2),
                     r(k.get("akis_cm_s"), 2), r(k.get("kalinlik_mm"), 4), str(k.get("seyreltici") or "").lower(),
                     k["sonuc"], str(k["kaynak"]).strip().lower()])


_NASA = None


def _nasa():
    global _NASA
    if _NASA is None:
        import pandas as pd
        parca = [pd.read_csv(f) for f in sorted(KOK.glob("psi_etiketli*.csv"))]
        d = pd.concat(parca, ignore_index=True) if parca else pd.DataFrame()
        if len(d):
            d = d[d.etiket_kaynagi.isin(["psi", "makale_elle"]) & d.yanar.isin([0, 1])].copy()
            d["ana"] = d.malzeme_sade.astype(str).map({a: _ana(a) for a in d.malzeme_sade.astype(str).unique()})
        _NASA = d
    return _NASA


def nasa_celiski(k):
    """Aynı koşuldaki NASA noktaları ve çelişki. -> {"n", "yanan", "celiski", "makaleler"} ya da None."""
    d = _nasa()
    if not len(d):
        return None
    m = ((d.ana == _ana(k["malzeme"])) & (d.g_seviyesi.map(_g_bandi) == _g_bandi(k["g"]))
         & ((d.oksijen_yuzde - k["oksijen_yuzde"]).abs() <= NASA_KOSUL["oksijen"]))
    lp = d.basinc_kpa.clip(lower=0.1).map(math.log10)
    m &= lp.isna() | ((lp - math.log10(max(k["basinc_kpa"], 0.1))).abs() <= NASA_KOSUL["log_basinc"])
    if k.get("akis_cm_s") is not None:
        tol = max(NASA_KOSUL["akis_mutlak"], NASA_KOSUL["akis_oran"] * k["akis_cm_s"])
        m &= d.akis_hizi_cm_s.isna() | ((d.akis_hizi_cm_s - k["akis_cm_s"]).abs() <= tol)
    if k.get("kalinlik_mm"):
        oran = d.kalinlik_mm / k["kalinlik_mm"]
        m &= d.kalinlik_mm.isna() | oran.between(1 / NASA_KOSUL["kalinlik_oran"], NASA_KOSUL["kalinlik_oran"])
    x = d[m]
    if not len(x):
        return None
    yanan = int(x.yanar.sum())
    ters = (len(x) - yanan) if k["sonuc"] == "yandi" else yanan
    return {"n": int(len(x)), "yanan": yanan, "celiski": ters / len(x) >= CELISKI_PAYI,
            "makaleler": sorted(x.makale_id.astype(str).unique().tolist())[:10]}


# ------------------------------------------------------------------ ekleme
def ekle(kayit, _ek_etiketler=(), _durum="onaysiz"):
    """Tek kayıt ekler. -> {"id", "durum", "etiketler", "kontrol_notlari", "mukerrer": bool}.
    Kabul edilemezse ToplulukHatasi (sebep metinde)."""
    _kalibrasyon_engeli()
    k, etiketler, notlar = dogrula(kayit)
    etiketler += [e for e in _ek_etiketler if e not in etiketler]
    anahtar = _anahtar(k)
    with _baglan() as c:
        r = c.execute("SELECT * FROM kayitlar WHERE anahtar = ?", (anahtar,)).fetchone()
        if r is not None:
            return {"id": r["id"], "durum": r["durum"], "etiketler": json.loads(r["etiketler"]),
                    "kontrol_notlari": ["mükerrer kayıt: aynı koşul, sonuç ve kaynak zaten var; eklenmedi"],
                    "mukerrer": True}
        nc = nasa_celiski(k)
        if nc is not None:
            if nc["celiski"]:
                etiketler.append("celiski")
                notlar.append(f"aynı koşulda NASA: {nc['yanan']}/{nc['n']} nokta yandı; bu kayıt "
                              f"'{k['sonuc']}' diyor ({', '.join(nc['makaleler'][:3])})")
            else:
                notlar.append(f"aynı koşulda {nc['n']} NASA noktası var, sonuçla uyumlu")
        cur = c.execute("INSERT INTO kayitlar (veri, anahtar, durum, etiketler, notlar, eklenme) VALUES (?,?,?,?,?,?)",
                        (json.dumps(k, ensure_ascii=False), anahtar, _durum, json.dumps(etiketler, ensure_ascii=False),
                         json.dumps(notlar, ensure_ascii=False), _simdi()))
        return {"id": cur.lastrowid, "durum": _durum, "etiketler": etiketler, "kontrol_notlari": notlar,
                "mukerrer": False}


def sablon_yaz(dosya=SABLON):
    """Boş CSV şablonu + bir ÖRNEK satır (ekleyen = ORNEK olan satırlar yüklenmez)."""
    with open(dosya, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=ALANLAR)
        w.writeheader()
        w.writerow({"malzeme": "pmma", "yakit_turu": "kati", "numune_tipi": "thin_sheet", "kalinlik_mm": "0.2",
                    "g": "0.0001", "oksijen_yuzde": "21", "basinc_kpa": "101.3", "akis_cm_s": "10",
                    "seyreltici": "n2", "sonuc": "yandi", "yayilma_hizi_mm_s": "1.2", "K_mm2_s": "",
                    "sonme_capi_mm": "", "kaynak_turu": "doi", "kaynak": "10.xxxx/ornek",
                    "yontem": "ISS, karşı akışlı kanal", "ekleyen": "ORNEK", "tarih": "2026-11-12"})
    return dosya


def csv_yukle(dosya, ekleyen=None):
    """CSV'deki her satırı ekle()'den geçirir. -> {"eklenen", "mukerrer", "reddedilen": [{satir, sebep}], "sonuclar"}"""
    _kalibrasyon_engeli()
    out = {"eklenen": 0, "mukerrer": 0, "reddedilen": [], "sonuclar": []}
    with open(dosya, newline="", encoding="utf-8-sig") as f:
        for i, s in enumerate(csv.DictReader(f), 2):
            if (s.get("ekleyen") or "").strip().upper() == "ORNEK":
                continue
            if ekleyen and not (s.get("ekleyen") or "").strip():
                s["ekleyen"] = ekleyen
            try:
                r = ekle(s)
            except ToplulukHatasi as e:
                out["reddedilen"].append({"satir": i, "sebep": str(e)})
                continue
            out["mukerrer" if r["mukerrer"] else "eklenen"] += 1
            out["sonuclar"].append({"satir": i, **r})
    return out


# ------------------------------------------------------------------ durum
def _karar(id_, durum, moderator, gerekce=None):
    _kalibrasyon_engeli()
    if not moderator:
        raise ToplulukHatasi("moderatör adı zorunlu")
    with _baglan() as c:
        r = c.execute("SELECT * FROM kayitlar WHERE id = ?", (int(id_),)).fetchone()
        if r is None:
            raise ToplulukHatasi(f"kayıt yok: {id_}")
        c.execute("UPDATE kayitlar SET durum=?, moderator=?, karar_tarihi=?, gerekce=? WHERE id=?",
                  (durum, moderator, _simdi(), gerekce, int(id_)))
        return _satir(c.execute("SELECT * FROM kayitlar WHERE id = ?", (int(id_),)).fetchone())


def onayla(id_, moderator):
    return _karar(id_, "onayli", moderator)


def reddet(id_, moderator, gerekce=""):
    return _karar(id_, "reddedildi", moderator, gerekce)


def listele(filtre=None):
    """filtre: {"durum", "malzeme" (ana malzeme), "ekleyen", "etiket", "kaynak_turu"}; boş = hepsi."""
    _kalibrasyon_engeli()
    filtre = filtre or {}
    with _baglan() as c:
        rows = [_satir(r) for r in c.execute("SELECT * FROM kayitlar ORDER BY id")]
    if filtre.get("durum"):
        rows = [r for r in rows if r["durum"] == filtre["durum"]]
    if filtre.get("malzeme"):
        a = _ana(filtre["malzeme"])
        rows = [r for r in rows if _ana(r["malzeme"]) == a]
    if filtre.get("ekleyen"):
        rows = [r for r in rows if r.get("ekleyen") == filtre["ekleyen"]]
    if filtre.get("etiket"):
        rows = [r for r in rows if filtre["etiket"] in r["etiketler"]]
    if filtre.get("kaynak_turu"):
        rows = [r for r in rows if r.get("kaynak_turu") == filtre["kaynak_turu"]]
    return rows


def yakin_kayitlar(malzeme, g, oksijen, basinc, pencere=None):
    """tahmin.py güven skoru v2 için: aynı ana malzeme + aynı g bandı + motor_kontrol.PENCERE içindeki
    reddedilmemiş kayıtlar. -> {"onayli": n, "onaysiz": n, "yanan": n} (yalnız sayım; modele girmez)."""
    _kalibrasyon_engeli()
    if not DEPO.exists():
        return {"onayli": 0, "onaysiz": 0, "yanan": 0, "yanan_onayli": 0}
    if pencere is None:
        import motor_kontrol
        pencere = motor_kontrol.PENCERE
    a, bant, lp = _ana(malzeme), _g_bandi(g), math.log10(max(basinc, 1))
    out = {"onayli": 0, "onaysiz": 0, "yanan": 0, "yanan_onayli": 0}
    for r in listele():
        if r["durum"] == "reddedildi" or _ana(r["malzeme"]) != a or _g_bandi(r["g"]) != bant:
            continue
        if abs(r["oksijen_yuzde"] - oksijen) > pencere["oksijen"]:
            continue
        if abs(math.log10(max(r["basinc_kpa"], 1)) - lp) > pencere["log_basinc"]:
            continue
        out[r["durum"]] += 1
        if r["sonuc"] == "yandi":
            out["yanan"] += 1
            out["yanan_onayli"] += r["durum"] == "onayli"
    return out


# ------------------------------------------------------------------ paylaşım paketi
def disa_aktar(dosya, filtre=None):
    """Paylaşım paketi (JSON): kayıtlar kaynak, durum, etiket ve kontrol notlarıyla birlikte."""
    rows = listele(filtre)
    paket = {"bicim": "topluluk_paketi", "surum": SURUM, "olusturma": _simdi(), "kayit_sayisi": len(rows),
             "not": "Topluluk verisi model ve motor kalibrasyonuna girmez. İçe aktarılan kayıtlar 'onaysiz' girer.",
             "kayitlar": rows}
    Path(dosya).write_text(json.dumps(paket, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"dosya": str(dosya), "kayit_sayisi": len(rows)}


def ice_aktar(dosya):
    """Paketteki kayıtları ekle()'den geçirir; her zaman 'onaysiz' girer. Önceki durum / moderatör / kaynak
    bilgisi kontrol notuna yazılır, etiket "ice_aktarildi"."""
    _kalibrasyon_engeli()
    p = json.loads(Path(dosya).read_text(encoding="utf-8"))
    if p.get("bicim") != "topluluk_paketi":
        raise ToplulukHatasi("dosya bir topluluk paketi değil")
    out = {"eklenen": 0, "mukerrer": 0, "reddedilen": [], "sonuclar": []}
    for i, r in enumerate(p.get("kayitlar", [])):
        ek = [e for e in r.get("etiketler", []) if e == "llm_cikardi"] + ["ice_aktarildi"]
        try:
            s = ekle(r, _ek_etiketler=ek)
        except ToplulukHatasi as e:
            out["reddedilen"].append({"sira": i, "sebep": str(e)})
            continue
        if not s["mukerrer"]:
            with _baglan() as c:
                n = json.loads(c.execute("SELECT notlar FROM kayitlar WHERE id=?", (s["id"],)).fetchone()[0])
                n.append(f"içe aktarıldı ({Path(dosya).name}); paketteki durum: {r.get('durum')}, "
                         f"moderatör: {r.get('moderator')}")
                c.execute("UPDATE kayitlar SET notlar=? WHERE id=?", (json.dumps(n, ensure_ascii=False), s["id"]))
        out["mukerrer" if s["mukerrer"] else "eklenen"] += 1
        out["sonuclar"].append(s)
    return out


# ------------------------------------------------------------------ PDF'ten aday kayıt (isteğe bağlı, EVREN)
class InternetYokHatasi(RuntimeError):
    pass


def _evren_erisilebilir(zaman_asimi=5.0):
    if os.environ.get("TOPLULUK_EVREN_KAPALI") == "1":
        return False, "EVREN kapalı (TOPLULUK_EVREN_KAPALI=1)"
    import socket
    import urllib.parse
    for adres in ("https://evren-llmapi.ssyz.org.tr/v1",):
        h = urllib.parse.urlparse(adres).hostname
        try:
            socket.create_connection((h, 443), timeout=zaman_asimi).close()
            return True, adres
        except OSError as e:
            sebep = f"{h}: {type(e).__name__}"
    return False, sebep


def pdf_ekle(dosya, ekleyen, makale_id=None):
    """veri_cikar3.py boru hattıyla (EVREN LLM) PDF'ten aday kayıtlar çıkarır. Hepsi "onaysiz" ve etiket
    "llm_cikardi". İnternet / anahtar yoksa InternetYokHatasi (net mesaj). Anahtar hiçbir yere yazılmaz."""
    _kalibrasyon_engeli()
    if not Path(dosya).is_file():
        raise ToplulukHatasi(f"PDF bulunamadı: {dosya}")
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        try:
            import fitz  # noqa: F401
        except ImportError:
            raise ToplulukHatasi("PDF okumak için PyMuPDF gerekli: pip install pymupdf") from None
    ok, bilgi = _evren_erisilebilir()
    if not ok:
        raise InternetYokHatasi(f"PDF'ten veri çıkarmak için internet ve EVREN gerekir; ulaşılamadı ({bilgi}). "
                                "Kayıtları elle ya da CSV ile ekleyebilirsiniz.")
    if not ANAHTAR.exists() and not os.environ.get("API_ANAHTAR"):
        raise InternetYokHatasi("EVREN anahtarı yok (evren_anahtar.txt). Örnek: evren_anahtar_ORNEK.txt")
    import contextlib
    import io
    os.environ.setdefault("API_URL", bilgi)
    # veri_cikar.py klasör ayarı Windows yolunu varsayıyor (D:\nasaspaceapp): ara dosyalar topluluk/pdf_isleri/'ne
    is_klasoru = DEPO.parent / "pdf_isleri"
    for alt in ("pdfler", "metinler", "ciktilar", "ciktilar3"):
        (is_klasoru / alt).mkdir(parents=True, exist_ok=True)
    os.environ["ANA_KLASOR"] = str(is_klasoru)
    if not os.environ.get("API_ANAHTAR"):      # anahtar yalnız bu sürecin ortamına; yazdırılmaz / loglanmaz
        os.environ["API_ANAHTAR"] = ANAHTAR.read_text(encoding="utf-8-sig").strip().strip('"')
    with contextlib.redirect_stdout(io.StringIO()):
        import veri_cikar3 as vc3
        try:
            vc3.api_kontrol()
        except SystemExit as e:
            raise InternetYokHatasi(f"EVREN cevap vermedi: {e}") from None
        sonuc = vc3.makale_isle(Path(dosya), makale_id or Path(dosya).stem)
    out = {"aday": 0, "eklenen": 0, "mukerrer": 0, "reddedilen": [], "hatalar": sonuc.get("hatalar", [])}
    for s in sonuc.get("satirlar", []):
        if s.get("tur") != "test" or s.get("yanar") is None:
            continue
        out["aday"] += 1
        k = {"malzeme": s.get("malzeme_sade"), "yakit_turu": s.get("yakit_turu"), "numune_tipi": s.get("numune_tipi"),
             "kalinlik_mm": s.get("kalinlik_mm"), "g": s.get("g_seviyesi"), "oksijen_yuzde": s.get("oksijen_yuzde"),
             "basinc_kpa": s.get("basinc_kpa"), "akis_cm_s": s.get("akis_hizi_cm_s"), "seyreltici": s.get("seyreltici"),
             "sonuc": "yandi" if s["yanar"] == 1 else "sondu", "yayilma_hizi_mm_s": s.get("alev_yayilma_hizi_mm_s"),
             "kaynak_turu": "makale_pdf", "kaynak": f"{Path(dosya).name} s. {s.get('sayfa')}",
             "yontem": f"LLM çıkardı ({vc3.MODEL}); kanıt: {str(s.get('kanit') or '')[:200]}", "ekleyen": ekleyen}
        try:
            r = ekle(k, _ek_etiketler=["llm_cikardi"] + (["supheli"] if s.get("supheli") == "evet" else []))
        except ToplulukHatasi as e:
            out["reddedilen"].append(str(e))
            continue
        out["mukerrer" if r["mukerrer"] else "eklenen"] += 1
    return out


# ------------------------------------------------------------------ komut satırı
def main():
    a = argparse.ArgumentParser(description="Topluluk verisi (modele girmez)")
    s = a.add_subparsers(dest="komut", required=True)
    s.add_parser("sablon")
    x = s.add_parser("listele"); x.add_argument("--durum"); x.add_argument("--malzeme")
    x = s.add_parser("yukle"); x.add_argument("dosya"); x.add_argument("--ekleyen")
    x = s.add_parser("onayla"); x.add_argument("id", type=int); x.add_argument("--moderator", required=True)
    x = s.add_parser("reddet"); x.add_argument("id", type=int); x.add_argument("--moderator", required=True)
    x.add_argument("--gerekce", default="")
    x = s.add_parser("disa"); x.add_argument("dosya")
    x = s.add_parser("ice"); x.add_argument("dosya")
    x = s.add_parser("pdf"); x.add_argument("dosya"); x.add_argument("--ekleyen", required=True)
    k = a.parse_args()
    f = {"sablon": lambda: str(sablon_yaz()),
         "listele": lambda: listele({"durum": k.durum, "malzeme": k.malzeme}),
         "yukle": lambda: csv_yukle(k.dosya, k.ekleyen), "onayla": lambda: onayla(k.id, k.moderator),
         "reddet": lambda: reddet(k.id, k.moderator, k.gerekce), "disa": lambda: disa_aktar(k.dosya),
         "ice": lambda: ice_aktar(k.dosya), "pdf": lambda: pdf_ekle(k.dosya, k.ekleyen)}[k.komut]
    print(json.dumps(f(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
