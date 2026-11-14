#!/usr/bin/env python3
"""
entegrasyon_test.py — dashboard ekibinin çalıştıracağı TEK test betiği.

    python3 entegrasyon_test.py                 # normal + internetsiz mod, topluluk akışı
    python3 entegrasyon_test.py --internetsiz   # yalnız internetsiz mod (EVREN kapalı)
    python3 entegrasyon_test.py --json sonuc.json

Denetlenenler:
  1) 10 vaka (PMMA Ay / Mars / ISS, SIBAL, metanol ISS, heptan Mars, etilen, metan, kevlar, saçma ad):
     tüm JSON alanları var mı, json.dumps ile yazılabiliyor mu (NaN yok), süre (ms),
     guven_v2 ve adimlar (12 adım) biçimi.
  2) Aynı vakalar internetsiz modda (EVREN kapalı: anahtar dosyası yok sayılır, ağ çağrıları hata verir):
     çökme yok; saçma ad "tanınmadı"; llm=True ise "LLM yorumu alınamadı".
  3) topluluk_veri: ekle -> listele -> onayla -> dışa aktar -> içe aktar (geçici depo; asıl depoya dokunmaz),
     kalibrasyon engeli (risk_modeli.py adlı bir betikten okuma reddedilir).
Testin kendisi hiçbir proje dosyasını kalıcı değiştirmez (malzeme_onbellek.json yedeklenip geri yüklenir).
Çıkış kodu: hepsi GEÇTİ ise 0, değilse 1.
"""
import argparse
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

KOK = Path(__file__).resolve().parent
os.chdir(KOK)
sys.path.insert(0, str(KOK))
GECICI = Path(tempfile.mkdtemp(prefix="entegrasyon_"))
os.environ["TOPLULUK_DB"] = str(GECICI / "topluluk.sqlite")    # asıl topluluk deposuna dokunma

VAKALAR = [
    ("PMMA Ay", ("pmma", 30, 70, 0.165), {}),
    ("PMMA Mars", ("pmma", 21, 101.3, 0.38), {}),
    ("PMMA ISS", ("pmma", 21, 101.3, 1e-4), {"akis": 0}),
    ("SIBAL ISS", ("sibal", 21, 101.3, 1e-4), {"akis": 25}),
    ("metanol ISS", ("methanol", 21, 101.3, 1e-4), {}),
    ("heptan Mars", ("n-heptane", 21, 101.3, 0.38), {}),
    ("etilen BRE", ("ethylene", 34, 57, 1e-4), {"numune_tipi": "flat_burner"}),
    ("metan 1 g", ("methane", 21, 101.3, 1.0), {"numune_tipi": "gas_jet"}),
    ("kevlar ISS", ("kevlar", 21, 101.3, 1e-4), {}),
    ("saçma ad", ("zxqv-blorpium 9000", 21, 101.3, 1e-4), {}),
]
ALANLAR = ["girdi", "yanma_ihtimali", "yanma_birlesik", "agirliklar", "belirsizlik", "risk_seviyesi", "sonme_siniri",
           "guvenlik_katsayisi", "sinirlama", "motor", "motor_turu", "motor_kaynagi", "motor_akis", "guven",
           "guven_v1", "guven_v2", "kullanilan_varsayilanlar", "uyarilar", "adimlar", "sure_sn"]
SAYI_ALANLARI = ["yanma_ihtimali", "yanma_birlesik", "belirsizlik", "risk_seviyesi"]
V2_ALANLAR = ["skor", "bant", "bilesenler", "cezalar", "yakin_deney_kaynaklari"]
V2_BILESEN = ["veri", "uyum", "motor", "kesinlik"]
ADIM_ALANLAR = ["no", "ad", "sure_ms", "karar", "ayrinti"]

sonuclar = []


def kaydet(grup, ad, gecti, ayrinti="", sure_ms=None):
    sonuclar.append({"grup": grup, "test": ad, "sonuc": "GEÇTİ" if gecti else "KALDI", "ayrinti": ayrinti,
                     "sure_ms": None if sure_ms is None else round(sure_ms, 1)})


def denetle_cikti(r, tanimsiz_beklenir):
    sorun = [f"eksik alan: {a}" for a in ALANLAR if a not in r]
    try:
        json.dumps(r, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as e:
        sorun.append(f"JSON'a çevrilemiyor: {e}")
    if tanimsiz_beklenir:
        if r.get("yanma_ihtimali") is not None:
            sorun.append("tanınmayan malzemede sayı üretildi")
    else:
        sorun += [f"{a} boş" for a in SAYI_ALANLARI if r.get(a) is None]
        v2 = r.get("guven_v2") or {}
        sorun += [f"guven_v2.{a} yok" for a in V2_ALANLAR if a not in v2]
        sorun += [f"guven_v2.bilesenler.{a} yok" for a in V2_BILESEN if a not in (v2.get("bilesenler") or {})]
        if v2 and not (0 <= v2.get("skor", -1) <= 100):
            sorun.append(f"guven_v2.skor aralık dışı: {v2.get('skor')}")
        if v2 and v2.get("bant") not in ("yüksek", "orta", "düşük"):
            sorun.append(f"guven_v2.bant: {v2.get('bant')}")
        if r.get("guven_v1") != r.get("guven"):
            sorun.append("guven_v1, guven ile aynı değil")
    ad = r.get("adimlar") or []
    if [a.get("no") for a in ad] != list(range(1, 13)):
        sorun.append(f"adimlar 1-12 değil: {[a.get('no') for a in ad]}")
    for a in ad:
        eks = [k for k in ADIM_ALANLAR if k not in a]
        if eks:
            sorun.append(f"adım {a.get('no')} eksik: {eks}")
            break
    return sorun


def vakalari_kos(grup, llm_ornek=False):
    import tahmin
    for ad, (m, o, b, g), kw in VAKALAR:
        t0 = time.perf_counter()
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                r = tahmin.tahmin(m, o, b, g, **kw)
        except Exception as e:
            kaydet(grup, ad, False, f"istisna: {type(e).__name__}: {str(e)[:150]}", 1000 * (time.perf_counter() - t0))
            continue
        ms = 1000 * (time.perf_counter() - t0)
        tanimsiz = ad == "saçma ad" or r.get("yanma_ihtimali") is None and ad == "kevlar ISS" and grup == "internetsiz"
        sorun = denetle_cikti(r, tanimsiz)
        if ad == "saçma ad" and r.get("yanma_ihtimali") is not None:
            sorun.append("saçma ad için sayı üretildi")
        bilgi = (f"v1 {r['guven']['skor']}, v2 {r['guven_v2']['skor']} ({r['guven_v2']['bant']}), motor "
                 f"{r.get('motor_kaynagi')}" if r.get("guven_v2") else (r.get("uyarilar") or [""])[0][:90])
        kaydet(grup, ad, not sorun, "; ".join(sorun) or bilgi, ms)
    if llm_ornek:
        t0 = time.perf_counter()
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                r = tahmin.tahmin("pmma", 21, 101.3, 1e-4, akis=0, llm=True)
            y = r.get("llm_yorum", "")
            ok = isinstance(y, str) and y.startswith("LLM yorumu alınamadı") and not denetle_cikti(r, False)
            kaydet(grup, "llm=True (EVREN kapalı)", ok, y[:90], 1000 * (time.perf_counter() - t0))
        except Exception as e:
            kaydet(grup, "llm=True (EVREN kapalı)", False, f"istisna: {type(e).__name__}: {e}")


@contextlib.contextmanager
def internetsiz():
    """EVREN kapalı: anahtar dosyası yok sayılır, ağ çağrısı hata verir."""
    import urllib.error
    import urllib.request
    import llm_analiz
    eski_dosya, eski_ac = llm_analiz.ANAHTAR_DOSYASI, urllib.request.urlopen

    def kapali(*a, **k):
        raise urllib.error.URLError("internetsiz test modu")
    llm_analiz.ANAHTAR_DOSYASI = GECICI / "anahtar_yok.txt"
    urllib.request.urlopen = kapali
    os.environ["TOPLULUK_EVREN_KAPALI"] = "1"
    try:
        yield
    finally:
        llm_analiz.ANAHTAR_DOSYASI, urllib.request.urlopen = eski_dosya, eski_ac
        os.environ.pop("TOPLULUK_EVREN_KAPALI", None)


def topluluk_akisi():
    import topluluk_veri as tv
    g = "topluluk"
    t0 = time.perf_counter()
    try:
        k = {"malzeme": "pmma", "yakit_turu": "kati", "numune_tipi": "thin_sheet", "kalinlik_mm": 0.2, "g": 0.0001,
             "oksijen_yuzde": 19.5, "basinc_kpa": 101.3, "akis_cm_s": 5, "seyreltici": "n2", "sonuc": "yandi",
             "yayilma_hizi_mm_s": 0.8, "kaynak_turu": "kendi_deney", "kaynak": "entegrasyon testi",
             "yontem": "test", "ekleyen": "test"}
        r = tv.ekle(k)
        kaydet(g, "ekle", r["durum"] == "onaysiz" and not r["mukerrer"], f"id {r['id']}, etiket {r['etiketler']}")
        r2 = tv.ekle(k)
        kaydet(g, "mükerrer kayıt tanınıyor", r2["mukerrer"] and r2["id"] == r["id"])
        try:
            tv.ekle({**k, "oksijen_yuzde": 150})
            kaydet(g, "fiziksel aralık reddi", False, "aralık dışı kayıt kabul edildi")
        except tv.ToplulukHatasi as e:
            kaydet(g, "fiziksel aralık reddi", True, str(e)[:80])
        r3 = tv.ekle({**k, "oksijen_yuzde": 0.21, "kaynak": "birim testi"})
        kaydet(g, "birim şüphesi etiketi", "birim_supheli" in r3["etiketler"], "; ".join(r3["kontrol_notlari"])[:80])
        r4 = tv.ekle({**k, "oksijen_yuzde": 21, "akis_cm_s": 5, "sonuc": "sondu", "kaynak": "çelişki testi"})
        kaydet(g, "NASA çelişki etiketi", "celiski" in r4["etiketler"], "; ".join(r4["kontrol_notlari"])[:90])
        liste = tv.listele({"durum": "onaysiz"})
        kaydet(g, "listele", len(liste) == 3, f"{len(liste)} onaysız kayıt")
        o = tv.onayla(r["id"], moderator="test_moderator")
        kaydet(g, "onayla", o["durum"] == "onayli" and o["moderator"] == "test_moderator")
        paket = GECICI / "paket.json"
        d = tv.disa_aktar(paket)
        kaydet(g, "dışa aktar", d["kayit_sayisi"] == 3 and paket.exists(), f"{d['kayit_sayisi']} kayıt")
        os.environ["TOPLULUK_DB"] = str(GECICI / "ikinci.sqlite")      # başka bir kullanıcının deposu
        import importlib
        tv = importlib.reload(tv)
        i = tv.ice_aktar(paket)
        hepsi_onaysiz = all(x["durum"] == "onaysiz" for x in tv.listele())
        kaydet(g, "içe aktar (hepsi onaysız)", i["eklenen"] == 3 and hepsi_onaysiz,
               f"{i['eklenen']} eklendi, durumlar {sorted({x['durum'] for x in tv.listele()})}")
        y = tv.yakin_kayitlar("pmma", 1e-4, 20, 101.3)
        kaydet(g, "yakın kayıt sayımı (güven v2)", y["onaysiz"] >= 1, json.dumps(y))
        pdf = GECICI / "bos.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
        with internetsiz():
            try:
                tv.pdf_ekle(pdf, "test")
                kaydet(g, "pdf_ekle internetsiz: net hata", False, "hata vermedi")
            except (tv.InternetYokHatasi, tv.ToplulukHatasi) as e:
                kaydet(g, "pdf_ekle internetsiz: net hata", True, f"{type(e).__name__}: {str(e)[:70]}")
    except Exception as e:
        kaydet(g, "topluluk akışı", False, f"istisna: {type(e).__name__}: {str(e)[:150]}")
    # kalibrasyon engeli: risk_modeli.py adlı bir betik topluluk verisini okuyamamalı
    b = GECICI / "risk_modeli.py"
    b.write_text("import sys; sys.path.insert(0, %r)\nimport topluluk_veri as tv\n"
                 "try:\n    tv.listele(); print('OKUDU')\nexcept tv.ToplulukKalibrasyonHatasi:\n    print('ENGEL')\n"
                 % str(KOK), encoding="utf-8")
    c = subprocess.run([sys.executable, str(b)], capture_output=True, text=True, env=os.environ, timeout=120)
    kaydet(g, "kalibrasyon engeli", c.stdout.strip().endswith("ENGEL"), c.stdout.strip()[-40:] or c.stderr[-120:])
    kaynaklar = {f: "topluluk" in (KOK / f).read_text(encoding="utf-8") for f in
                 ("risk_modeli.py", "hafif_motor.py", "damla_motoru.py", "gaz_motoru.py", "motor_dogrulama_uret.py")
                 if (KOK / f).exists()}
    kaydet(g, "model/kalibrasyon betikleri topluluk okumuyor", not any(kaynaklar.values()),
           ", ".join(f for f, v in kaynaklar.items() if v) or "hiçbiri 'topluluk' içermiyor")
    kaydet(g, "süre", True, "", 1000 * (time.perf_counter() - t0))


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--internetsiz", action="store_true", help="yalnız internetsiz mod")
    a.add_argument("--json", help="sonuç tablosunu JSON olarak da yaz")
    k = a.parse_args()
    onbellek = KOK / "malzeme_onbellek.json"
    yedek = GECICI / "malzeme_onbellek.json"
    if onbellek.exists():
        shutil.copy2(onbellek, yedek)
    bas = time.perf_counter()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            import tahmin  # noqa: F401  (ilk yükleme: model + karşılaştırma tablosu)
        if not k.internetsiz:
            vakalari_kos("normal")
        with internetsiz():
            vakalari_kos("internetsiz", llm_ornek=True)
        topluluk_akisi()
    finally:
        if yedek.exists():
            shutil.copy2(yedek, onbellek)
        shutil.rmtree(GECICI, ignore_errors=True)
    gen = max(len(s["test"]) for s in sonuclar)
    print(f"{'grup':12s} {'test':{gen}s}  sonuç   süre ms   ayrıntı")
    for s in sonuclar:
        ms = "" if s["sure_ms"] is None else f"{s['sure_ms']:8.0f}"
        print(f"{s['grup']:12s} {s['test']:{gen}s}  {s['sonuc']:6s} {ms:>8s}   {s['ayrinti']}")
    kalan = [s for s in sonuclar if s["sonuc"] != "GEÇTİ"]
    print(f"\n{len(sonuclar) - len(kalan)}/{len(sonuclar)} GEÇTİ, {len(kalan)} KALDI "
          f"({time.perf_counter() - bas:.1f} s)")
    if k.json:
        Path(k.json).write_text(json.dumps(sonuclar, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.exit(1 if kalan else 0)


if __name__ == "__main__":
    main()
