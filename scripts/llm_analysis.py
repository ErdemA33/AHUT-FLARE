#!/usr/bin/env python3
"""
scripts/llm_analysis.py — tahmin() sonucunu EVREN LLM'i ile kısa Türkçe bir yoruma çevirir.

    from llm_analysis import yorumla
    metin = yorumla(sonuc)          # sonuc: tahmin.tahmin(...) çıktısı

- KARAR satırını kod üretir (risk seviyesi, güvenlik katsayısı 1'in altında/üstünde, güven); LLM'e
  "değiştirme, gerekçelendir" diye verilir ve çıktının başına aynen eklenir.
- LLM çıktısındaki sayılar giriş JSON'undaki sayılarla karşılaştırılır; eşleşmeyenler sona
  "⚠️ Doğrulanamayan sayılar: ..." olarak eklenir.
- HTTP 429/503 ya da zaman aşımında 5 sn bekleyip bir kez daha dener.
- Hata olursa çökmez: "LLM yorumu alınamadı (sebep)" döner.
- Model: LLM_MODEL ortam değişkeni (varsayılan gemma-4-31b). Anahtar: evren_anahtar.txt
  (asla yazdırılmaz / loglanmaz).
- KARAR satırının altına kodun ürettiği MOTOR satırı eklenir (hangi fizik motoru, neden, ağırlıklar).

    from llm_analysis import malzeme_siniflandir
    malzeme_siniflandir("kevlar")   # listede olmayan malzemeyi EVREN'e sınıflandırtır (temperature 0)
- Listede olan malzeme LLM'e gitmez. Cevap kodla denetlenir (izin verilen değerler, uydurma malzeme yok,
  yakıt türü-numune tipi tutarlılığı). Sonuç data/material_cache.json'a yazılır; aynı ad tekrar LLM'e gitmez
  (çevrimdışı da çalışır). İnternet yoksa durum "baglanti_yok" döner (önbelleğe yazılmaz).
"""
import json
import math
import os
import re
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://evren-llmapi.ssyz.org.tr/v1/chat/completions"
# EVREN_ANAHTAR_DOSYASI: anahtar dosyasının yolu (dashboard yerel denemede ana klasördekini gösterir; dosya kopyalanmaz)
ANAHTAR_DOSYASI = Path(os.environ.get("EVREN_ANAHTAR_DOSYASI") or Path(__file__).resolve().parent / "evren_anahtar.txt")
VARSAYILAN_MODEL = "gemma-4-31b"
ZAMAN_ASIMI = 120          # sn
TEKRAR_BEKLEME = 5         # sn; HTTP 429/503 ya da zaman aşımında bir kez daha denenir
GUVEN_DUSUK = 60
# sistem mesajındaki tanımlarda geçen sayılar; LLM bunları kullanırsa uydurma sayılmaz
TANIM_SAYILARI = [0, 1, 50, 60, 100]

SISTEM = (
    "Sen bir uzay yangın güvenliği analistisin. Sana bir yangın riski tahmininin JSON çıktısı ve kod "
    "tarafından üretilmiş bir KARAR satırı verilecek.\n"
    "Kurallar:\n"
    "- SADECE verilen JSON'daki sayıları kullan. Yeni sayı hesaplama, tahmin etme ya da uydurma.\n"
    "- KARAR satırını değiştirme, tekrar yazma; sadece gerekçelendir.\n"
    "Tanımlar:\n"
    "- Güvenlik katsayısı = sönme sınırı / ortam oksijeni. 1'den büyükse güvenli, 1'den küçükse tehlikeli.\n"
    "- Yanma ihtimali %50'nin üstündeyse alev yanar kabul edilir.\n"
    "- Güven 0-100 arasıdır; 60'ın altı düşük güvendir.\n"
    "- Kısmi yerçekiminde (Ay/Mars) uzay, gerçek g ve Dünya sonuçlarının en kötüsü alınmıştır.\n"
    "Türkçe yaz, en fazla 150 kelime. Biçim tam olarak şöyle olsun:\n"
    "Gerekçe:\n- (2-3 madde)\nÖneri: (tek paragraf)\nGüvenilirlik: (tek paragraf)"
)


# ------------------------------------------------------------------ KARAR
def karar_satiri(sonuc):
    risk = sonuc.get("risk_seviyesi") or "bilinmiyor"
    gk = sonuc.get("guvenlik_katsayisi")
    if gk is None:
        gk_yazi = "güvenlik katsayısı hesaplanamadı (sönme sınırı bulunamadı)"
    elif gk < 1:
        gk_yazi = f"güvenlik katsayısı {gk} < 1 (tehlikeli)"
    elif gk > 1:
        gk_yazi = f"güvenlik katsayısı {gk} > 1 (güvenli)"
    else:
        gk_yazi = f"güvenlik katsayısı {gk} = 1 (tam sınırda)"
    v2 = sonuc.get("guven_v2") or {}
    skor = v2.get("skor") if v2.get("skor") is not None else (sonuc.get("guven") or {}).get("skor")   # v2 varsa o
    guven_yazi = ("güven bilinmiyor" if skor is None else
                  f"güven {skor}/100 ({'düşük' if skor < GUVEN_DUSUK else 'yeterli'})")
    return f"KARAR: Risk {risk} | {gk_yazi} | {guven_yazi}"


# ------------------------------------------------------------------ sayı kontrolü
_SAYI = re.compile(r"(?<![\w.,])[-−]?\d+(?:[.,]\d+)?(?:[eE][-−+]?\d+)?")


def _json_sayilari(x, out):
    """JSON'daki bütün sayılar (metin alanlarının içindekiler dahil)."""
    if isinstance(x, dict):
        for v in x.values():
            _json_sayilari(v, out)
    elif isinstance(x, list):
        for v in x:
            _json_sayilari(v, out)
    elif isinstance(x, bool) or x is None:
        pass
    elif isinstance(x, (int, float)):
        out.append(float(x))
    elif isinstance(x, str):
        out += [s[0] for s in _metin_sayilari(x)]
    return out


def _metin_sayilari(metin):
    """(değer, yazıldığı haliyle, ondalık basamak sayısı) listesi. Türkçe ondalık virgül desteklenir."""
    sonuc = []
    for m in _SAYI.finditer(metin):
        yazi = m.group(0)
        s = yazi.replace("−", "-").replace(",", ".")
        try:
            v = float(s)
        except ValueError:
            continue
        govde = s.lower().split("e")[0]
        ondalik = len(govde.split(".")[1]) if "." in govde else 0
        if "e" in s.lower():
            ondalik = None          # bilimsel gösterim: göreli tolerans
        sonuc.append((v, yazi, ondalik))
    return sonuc


def dogrulanamayan_sayilar(metin, sonuc):
    """LLM metnindeki, giriş JSON'unda karşılığı olmayan sayılar.
    Eşleşme: aynı değer, ya da oran<->yüzde dönüşümü (×100 / ÷100), yazılan son basamakta ±1 payıyla."""
    adaylar = []
    for v in _json_sayilari(sonuc, []) + TANIM_SAYILARI:
        adaylar += [v, v * 100, v / 100]
    supheli = []
    for v, yazi, ondalik in _metin_sayilari(metin):
        tol = abs(v) * 0.05 if ondalik is None else 10 ** (-ondalik)
        if not any(math.isclose(v, a, abs_tol=tol + 1e-9) or math.isclose(-v, a, abs_tol=tol + 1e-9)
                   for a in adaylar):
            if yazi not in supheli:
                supheli.append(yazi)
    return supheli


# ------------------------------------------------------------------ EVREN
def _anahtar():
    if not ANAHTAR_DOSYASI.exists():
        raise RuntimeError("anahtar dosyası yok")
    a = ANAHTAR_DOSYASI.read_text(encoding="utf-8-sig").strip()
    if not a:
        raise RuntimeError("anahtar dosyası boş")
    return a


def _gizle(metin, anahtar):
    return metin.replace(anahtar, "***") if anahtar else metin


def _llm_cagir(mesajlar, model, anahtar, temperature=0.2, max_tokens=1500):
    govde = {"model": model, "messages": mesajlar, "temperature": temperature, "max_tokens": max_tokens,
             "stream": False,
             "chat_template_kwargs": {"enable_thinking": False}}
    istek = urllib.request.Request(API_URL, data=json.dumps(govde).encode("utf-8"), method="POST",
                                   headers={"Content-Type": "application/json", "X-API-Key": anahtar})
    with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as c:
        yanit = json.loads(c.read().decode("utf-8"))
    mesaj = (yanit.get("choices") or [{}])[0].get("message") or {}
    icerik = mesaj.get("content") or ""
    icerik = re.sub(r"<think>.*?</think>", "", icerik, flags=re.S).strip()
    if not icerik:
        raise RuntimeError("boş cevap")
    return icerik


def _gecici_hata(e):
    if isinstance(e, urllib.error.HTTPError):
        return e.code in (429, 503)
    if isinstance(e, (socket.timeout, TimeoutError)):
        return True
    return isinstance(e, urllib.error.URLError) and isinstance(e.reason, (socket.timeout, TimeoutError))


def _llm_cagir_tekrarli(mesajlar, model, anahtar, **kw):
    """HTTP 429/503 ya da zaman aşımında TEKRAR_BEKLEME sn bekleyip bir kez daha dener."""
    try:
        return _llm_cagir(mesajlar, model, anahtar, **kw)
    except Exception as e:
        if not _gecici_hata(e):
            raise
        time.sleep(TEKRAR_BEKLEME)
        return _llm_cagir(mesajlar, model, anahtar, **kw)


# ------------------------------------------------------------------ motor seçimi cümlesi (koddan)
YAKIT_ADI = {"kati": "katı", "sivi": "sıvı", "gaz": "gaz"}


def motor_satiri(sonuc):
    """Hangi fizik motorunun neden seçildiğini anlatan cümle. LLM'den değil, koddan gelir."""
    m = sonuc.get("motor") or {}
    kaynak = sonuc.get("motor_kaynagi") or m.get("motor_kaynagi")
    tur = YAKIT_ADI.get(m.get("yakit_turu"), m.get("yakit_turu") or "?")
    auc = m.get("motor_auc")
    auc_y = f"dürüst test AUC {auc:.2f}" if isinstance(auc, (int, float)) else "dürüst testi yok"
    if not kaynak:
        return "MOTOR: fizik motoru bu koşulu bilmiyor; sonuç yalnızca risk modelinden."
    if kaynak == "damla":
        neden = "sıvı yakıt → FLEX (NASA PSI-69) ile doğrulanmış damla motoru"
    elif kaynak == "hafif" and m.get("yakit_turu") == "gaz":
        neden = "gaz yakıt → hafif motor (gaz grubu kalibre edilmedi, doğrulama verisi yok; ağırlığı 0)"
    elif kaynak == "hafif":
        neden = f"{tur} yakıt → NASA PSI verisiyle kalibre yarı-ampirik hafif motor"
    elif kaynak == "ofm_tablo":
        neden = f"{tur} yakıt → OpenFOAM motorunun tablosu (yakın koşu var)"
    elif kaynak == "ofm+hafif":
        neden = f"{tur} yakıt → OpenFOAM motorunun tablosu + hafif motor (mesafeye göre karışım)"
    else:
        neden = f"{tur} yakıt → {kaynak} motoru"
    a = sonuc.get("agirliklar") or {}
    ag = (f"; birleşik ihtimal = %{100 * a['model']:.0f} model + %{100 * a['motor']:.0f} motor"
          if "model" in a and "motor" in a else "")
    return f"MOTOR: {neden} ({auc_y}){ag}."


# ------------------------------------------------------------------ malzeme sınıflandırma
KOK = Path(__file__).resolve().parent.parent
ONBELLEK_PAKET = KOK / "data/material_cache.json"       # paketle gelen (salt okunur olabilir)
# YANGIN_VERI_KLASORU verilmişse yeni sınıflandırmalar oraya yazılır; okurken önce oraya, yoksa pakettekine bakılır
ONBELLEK = (Path(os.environ["YANGIN_VERI_KLASORU"]) / "data/material_cache.json"
            if os.environ.get("YANGIN_VERI_KLASORU") else ONBELLEK_PAKET)
KARSILASTIRMA = KOK / "engine_comparison.csv"
YAKIT_TURLERI = ("kati", "sivi", "gaz")
NUMUNE_TIPLERI = ("thin_sheet", "thick_sheet", "fabric", "rod", "wire", "sphere", "particle_cloud",
                  "droplet", "pool", "gas_jet")
SIVI_NUMUNE, GAZ_NUMUNE = ("droplet", "pool"), ("gas_jet",)
EN_AZ_NOKTA = 5          # veri setinde en az bu kadar noktası olan malzeme "listede" sayılır
# malzeme olmayan / belirsiz / kısaltma adlar (veri setindeki çıkarım artıkları) listeye alınmaz
GENEL_ADLAR = {"nan", "none", "", "solid", "flat materials", "solid beds", "wire", "awg28", "liquid",
               "double thickness of", "single thickness of", "mg", "pe", "laboratory wipe"}
_bilinen = None

SINIF_SISTEM = (
    "Sen bir yanma bilimi uzmanısın. Verilen malzeme adını sınıflandır. SADECE şu JSON'u döndür, başka hiçbir "
    "şey yazma:\n"
    '{"yakit_turu": "...", "benzer_malzeme": "...", "numune_tipi": "...", "gerekce": "tek cümle"}\n'
    "Kurallar:\n"
    "- yakit_turu şunlardan biri: kati, sivi, gaz\n"
    "- benzer_malzeme SADECE şu listeden, yanma davranışı en benzer olan: {liste}\n"
    "- numune_tipi SADECE şunlardan biri: {numune}\n"
    "- sıvı yakıt -> droplet ya da pool; gaz -> gas_jet; katı -> diğerleri\n"
    "- Ad gerçek, bilinen bir malzeme değilse (anlamsız harf dizisi vb.) benzer_malzeme alanına null yaz.\n"
    "- gerekce Türkçe, tek cümle."
)


def bilinen_malzemeler():
    """MALZEME_VARSAYILAN anahtarları + veri setinde >= EN_AZ_NOKTA noktası olan malzemeler (malzeme_ana)."""
    global _bilinen
    if _bilinen is None:
        from risk_model import malzeme_ana
        from predict import MALZEME_VARSAYILAN
        s = set(MALZEME_VARSAYILAN)
        if KARSILASTIRMA.exists():
            import pandas as pd
            ad = pd.read_csv(KARSILASTIRMA, usecols=["malzeme_sade"], low_memory=False).malzeme_sade.dropna()
            ana = ad.astype(str).map(malzeme_ana).value_counts()
            s |= set(ana[ana >= EN_AZ_NOKTA].index)
        _bilinen = sorted(x for x in s if str(x).strip().lower() not in GENEL_ADLAR)
    return _bilinen


def _norm(ad):
    return re.sub(r"\s+", " ", str(ad or "")).strip().lower()


def malzeme_biliniyor(ad):
    from risk_model import malzeme_ana
    return malzeme_ana(_norm(ad)) in set(bilinen_malzemeler())


def _onbellek_oku():
    try:
        kaynak = ONBELLEK if ONBELLEK.exists() else ONBELLEK_PAKET
        return json.loads(kaynak.read_text(encoding="utf-8")) if kaynak.exists() else {}
    except (OSError, ValueError):
        return {}


def onbellekten(ad):
    return _onbellek_oku().get(_norm(ad))


def _onbellege_yaz(ad, kayit):
    d = _onbellek_oku()
    d[_norm(ad)] = kayit
    ONBELLEK.parent.mkdir(parents=True, exist_ok=True)
    ONBELLEK.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def siniflandirma_denetle(metin):
    """LLM cevabını denetler -> (kabul mü, sözlük ya da red sebebi)."""
    m = re.search(r"\{.*\}", metin or "", flags=re.S)
    if not m:
        return False, "JSON yok"
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return False, "JSON okunamadı"
    if not isinstance(d, dict):
        return False, "JSON nesne değil"
    tur, benzer, numune = d.get("yakit_turu"), d.get("benzer_malzeme"), d.get("numune_tipi")
    gerekce = str(d.get("gerekce") or "").strip()
    if tur not in YAKIT_TURLERI:
        return False, f"yakit_turu izin verilen değerlerden değil: {tur!r}"
    if benzer is None:
        return False, "LLM bunu gerçek bir malzeme olarak tanımadı (benzer_malzeme null)"
    benzer = _norm(benzer)
    if benzer not in set(bilinen_malzemeler()):
        return False, f"benzer_malzeme listede yok (uydurma kabul edilmez): {benzer!r}"
    if numune not in NUMUNE_TIPLERI:
        return False, f"numune_tipi izin verilen değerlerden değil: {numune!r}"
    if (tur == "sivi") != (numune in SIVI_NUMUNE) or (tur == "gaz") != (numune in GAZ_NUMUNE):
        return False, f"yakit_turu '{tur}' ile numune_tipi '{numune}' tutarsız"
    from engine import yakit_turu_bul
    if yakit_turu_bul(benzer) != tur:
        return False, f"benzer_malzeme '{benzer}' bir {YAKIT_ADI[yakit_turu_bul(benzer)]} yakıt; yakit_turu '{tur}' ile tutarsız"
    if not gerekce:
        return False, "gerekce boş"
    return True, {"yakit_turu": tur, "benzer_malzeme": benzer, "numune_tipi": numune, "gerekce": gerekce[:300]}


def malzeme_siniflandir(ad, model=None):
    """Dönüş: {"durum": "listede"|"kabul"|"reddedildi"|"baglanti_yok", "girilen", "yakit_turu",
    "benzer_malzeme", "numune_tipi", "gerekce", "sebep", "kaynak": "liste"|"onbellek"|"llm"}.
    Hiçbir durumda istisna fırlatmaz."""
    from risk_model import malzeme_ana
    bos = {"girilen": ad, "yakit_turu": None, "benzer_malzeme": None, "numune_tipi": None,
           "gerekce": None, "sebep": None}
    if malzeme_biliniyor(ad):
        return {**bos, "durum": "listede", "benzer_malzeme": malzeme_ana(_norm(ad)), "kaynak": "liste"}
    k = onbellekten(ad)
    if k:
        return {**bos, **k, "girilen": ad, "kaynak": "onbellek"}
    anahtar = None
    try:
        model = model or os.environ.get("LLM_MODEL", VARSAYILAN_MODEL)
        anahtar = _anahtar()
        sistem = SINIF_SISTEM.replace("{liste}", ", ".join(bilinen_malzemeler())).replace(
            "{numune}", ", ".join(NUMUNE_TIPLERI))
        metin = _llm_cagir_tekrarli([{"role": "system", "content": sistem},
                                     {"role": "user", "content": f"Malzeme: {str(ad)[:100]}"}],
                                    model, anahtar, temperature=0, max_tokens=300)
    except urllib.error.HTTPError as e:
        return {**bos, "durum": "baglanti_yok", "sebep": f"HTTP {e.code}", "kaynak": "llm"}
    except Exception as e:
        return {**bos, "durum": "baglanti_yok",
                "sebep": _gizle(f"{type(e).__name__}: {str(e)[:120]}", anahtar), "kaynak": "llm"}
    ok, sonuc = siniflandirma_denetle(metin)
    kayit = ({**bos, **sonuc, "durum": "kabul"} if ok else
             {**bos, "durum": "reddedildi", "sebep": sonuc, "ham_cevap": (metin or "")[:300]})
    kayit.pop("girilen", None)
    kayit.update({"model": model, "tarih": time.strftime("%Y-%m-%d %H:%M")})
    _onbellege_yaz(ad, kayit)
    return {**kayit, "girilen": ad, "kaynak": "llm"}


# ------------------------------------------------------------------ kullanıcı malzemesi önerisi (arayüz formu)
# LLM'in önerdiği sayılar YALNIZ formu doldurur: "LLM önerisi, doğrulanmadı" diye işaretlenir, onaysız hiçbir
# hesaba girmez; onaylı kullanıcı malzemesinde de yalnız yakıt türü / numune / kalınlık / benzer malzeme kullanılır.
OZELLIK_SISTEM = (
    "Sen bir malzeme özellikleri asistanısın. Verilen malzeme için yalnız emin olduğun değerleri yaz; "
    "emin değilsen null yaz, ASLA tahmin uydurma. Yalnız şu JSON'u döndür, başka metin yazma:\n"
    '{"ad_tr": str, "ad_en": str, "es_anlamlilar": [str], "yogunluk_kg_m3": sayı|null, '
    '"isil_deger_MJ_kg": sayı|null, "kaynama_K": sayı|null, "LOI_yuzde": sayı|null, '
    '"parlama_noktasi_K": sayı|null, "LFL_yuzde": sayı|null, "UFL_yuzde": sayı|null, '
    '"uzayda_kullanim": str|null}')
OZELLIK_ARALIK = {"yogunluk_kg_m3": (0.05, 25000), "isil_deger_MJ_kg": (0, 150), "kaynama_K": (1, 6000),
                  "LOI_yuzde": (0, 100), "parlama_noktasi_K": (50, 1500), "LFL_yuzde": (0, 100), "UFL_yuzde": (0, 100)}


def malzeme_oner(ad, model=None):
    """Kullanıcı malzemesi formu için öneri. Dönüş: {"durum": kabul|reddedildi|baglanti_yok, "siniflandirma": {...},
    "ozellikler": {alan: sayı}, "ad_tr", "ad_en", "es_anlamlilar", "uzayda_kullanim", "sebep"}. İstisna fırlatmaz."""
    sinif = malzeme_siniflandir(ad, model=model)
    sonuc = {"girilen": ad, "durum": sinif.get("durum"), "siniflandirma": sinif, "ozellikler": {},
             "sebep": sinif.get("sebep"), "kaynak": sinif.get("kaynak")}
    if sinif.get("durum") == "listede":
        sonuc["durum"] = "kabul"
    if sonuc["durum"] != "kabul":
        return sonuc
    anahtar = None
    try:
        model = model or os.environ.get("LLM_MODEL", VARSAYILAN_MODEL)
        anahtar = _anahtar()
        metin = _llm_cagir_tekrarli([{"role": "system", "content": OZELLIK_SISTEM},
                                     {"role": "user", "content": f"Malzeme: {str(ad)[:100]}"}],
                                    model, anahtar, temperature=0, max_tokens=400)
        m = re.search(r"\{.*\}", metin or "", re.S)
        d = json.loads(m.group(0)) if m else {}
    except urllib.error.HTTPError as e:
        sonuc["ozellik_sebep"] = f"HTTP {e.code}"
        return sonuc
    except Exception as e:  # noqa: BLE001  (bağlantı yok ya da JSON bozuk: sınıflandırma yine de döner)
        sonuc["ozellik_sebep"] = _gizle(f"{type(e).__name__}: {str(e)[:120]}", anahtar)
        return sonuc
    for alan, (lo, hi) in OZELLIK_ARALIK.items():
        v = d.get(alan)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi:
            sonuc["ozellikler"][alan] = float(v)
    for alan in ("ad_tr", "ad_en", "uzayda_kullanim"):
        if isinstance(d.get(alan), str):
            sonuc[alan] = d[alan][:200]
    if isinstance(d.get("es_anlamlilar"), list):
        sonuc["es_anlamlilar"] = [str(x)[:60] for x in d["es_anlamlilar"][:10]]
    return sonuc


SISTEM_GIRDI = (
    "Sen bir uzay yangın güvenliği analistisin. Sana yalnızca bir senaryonun GİRDİLERİ verilecek "
    "(malzeme, oksijen, basınç, yerçekimi, akış...). Model çözümü ÇALIŞTIRILMADI; sayısal risk tahmini yoktur.\n"
    "Kurallar:\n"
    "- Risk yüzdesi, yayılma hızı, sönme sınırı gibi SAYISAL tahmin verme; bunları uydurma.\n"
    "- Sayı yazacaksan yalnızca verilen girdilerdeki sayıları kullan.\n"
    "- Nitel ve genel bilgiyle konuş (oksijen zenginliği, mikro yerçekimi, akış, malzeme türü etkisi).\n"
    "- Girdi eksik ya da şüpheliyse bunu söyle.\n"
    "Türkçe yaz, en fazla 150 kelime, düz metin (markdown, ** ya da # kullanma). Biçim tam olarak şöyle olsun:\n"
    "Gerekçe:\n- (2-3 madde)\nÖneri: (tek paragraf)"
)


def yorumla_girdi(girdi, model=None):
    """Çözüm olmadan, yalnız girdilerden nitel yorum. Hiçbir durumda istisna fırlatmaz."""
    anahtar = None
    try:
        model = model or os.environ.get("LLM_MODEL", VARSAYILAN_MODEL)
        anahtar = _anahtar()
        kullanici = "Girdiler (JSON):\n" + json.dumps(girdi, ensure_ascii=False, indent=1)
        metin = _llm_cagir_tekrarli([{"role": "system", "content": SISTEM_GIRDI}, {"role": "user", "content": kullanici}],
                                    model, anahtar, max_tokens=700).strip()
        cikti = metin
        supheli = dogrulanamayan_sayilar(metin, {"girdi": girdi})
        if supheli:
            cikti += f"\n\n⚠️ Doğrulanamayan sayılar: {', '.join(supheli)}"
        return cikti
    except urllib.error.HTTPError as e:
        return _gizle(f"LLM yorumu alınamadı (HTTP {e.code})", anahtar)
    except (socket.timeout, TimeoutError):
        return f"LLM yorumu alınamadı (zaman aşımı, {ZAMAN_ASIMI} sn)"
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            return f"LLM yorumu alınamadı (zaman aşımı, {ZAMAN_ASIMI} sn)"
        return _gizle(f"LLM yorumu alınamadı (bağlantı hatası: {e.reason})", anahtar)
    except Exception as e:
        return _gizle(f"LLM yorumu alınamadı ({type(e).__name__}: {str(e)[:150]})", anahtar)


def yorumla(sonuc, model=None):
    """tahmin() sonucunu yorumlar. Hiçbir durumda istisna fırlatmaz."""
    anahtar = None
    try:
        model = model or os.environ.get("LLM_MODEL", VARSAYILAN_MODEL)
        karar = karar_satiri(sonuc)
        veri = {k: v for k, v in sonuc.items() if k not in ("llm_yorum", "sure_sn")}
        kullanici = (f"{karar}\n\nBu KARAR satırı kod tarafından üretildi. Bunu değiştirme ve tekrar yazma; "
                     f"sadece gerekçelendir.\n\nVeri (JSON):\n{json.dumps(veri, ensure_ascii=False, indent=1)}")
        anahtar = _anahtar()
        metin = _llm_cagir_tekrarli([{"role": "system", "content": SISTEM}, {"role": "user", "content": kullanici}],
                           model, anahtar)
        # LLM KARAR satırını yine de tekrar ettiyse at (başa kod ekliyor)
        metin = "\n".join(l for l in metin.splitlines() if not l.strip().lstrip("*#").strip().startswith("KARAR"))
        metin = metin.strip()
        cikti = f"{karar}\n{motor_satiri(sonuc)}\n\n{metin}"
        supheli = dogrulanamayan_sayilar(metin, sonuc)
        if supheli:
            cikti += f"\n\n⚠️ Doğrulanamayan sayılar: {', '.join(supheli)}"
        return cikti
    except urllib.error.HTTPError as e:
        try:
            govde = e.read().decode("utf-8", "replace")[:150]
        except Exception:
            govde = ""
        return _gizle(f"LLM yorumu alınamadı (HTTP {e.code}{': ' + govde if govde else ''})", anahtar)
    except (socket.timeout, TimeoutError):
        return f"LLM yorumu alınamadı (zaman aşımı, {ZAMAN_ASIMI} sn)"
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            return f"LLM yorumu alınamadı (zaman aşımı, {ZAMAN_ASIMI} sn)"
        return _gizle(f"LLM yorumu alınamadı (bağlantı hatası: {e.reason})", anahtar)
    except Exception as e:
        return _gizle(f"LLM yorumu alınamadı ({type(e).__name__}: {str(e)[:150]})", anahtar)


# ------------------------------------------------------------------ sohbet (Yapay Zeka Yorumu düğümü)
# LLM sayı tahmin etmez: "ne olur eğer" sorusunda {"hesapla": {...}} isteği döndürür; isteği kod doğrular,
# tahmin()'i çalıştırır ve sonucu LLM'e açıklatır. Cevaptaki sayılar yorumla() ile aynı denetimden geçer.
SOHBET_EN_FAZLA_HESAP = 3
SOHBET_GECMIS = 6            # LLM'e giden son mesaj sayısı
SOHBET_SORU_UZUNLUK = 400
SOHBET_SEYRELTICI = ("n2", "co2", "he", "ar", "xe")
SOHBET_ALANLAR = ("oksijen", "basinc", "g", "akis", "kalinlik", "seyreltici", "malzeme")
SOHBET_ARALIK = {"oksijen": (0.0, 100.0, False), "basinc": (0.0, 1000.0, False), "g": (0.0, 10.0, False),
                 "akis": (0.0, 500.0, True), "kalinlik": (0.0, 1000.0, False)}     # (alt, üst, alt sınır dahil mi)

SOHBET_SISTEM = (
    "Sen bir uzay yangın güvenliği analistisin. Kullanıcı, kodun hesapladığı bir yangın riski tahmini hakkında "
    "soru soruyor. Sana tahminin özeti (JSON) verilecek.\n"
    "Kurallar:\n"
    "- Önce sorunun cevabının verilen JSON'da ya da 'Ek hesap' sonuçlarında olup olmadığına bak. Varsa cevabı "
    "oradan ver ve o sayıları aynen kullan; bu vakanın sayılarını yeniden hesaplama, değiştirme, uydurma.\n"
    "- Cevap JSON'da yoksa (genel kavram, malzeme, yanma fiziği, uzay ortamı, yöntem gibi) kendi bilginle cevap ver. "
    "Böyle cevabın başına 'Genel bilgi:' yaz; bu vakanın sonucuymuş gibi sunma.\n"
    "- Kullanıcı bir girdinin değişmesini sorarsa ('... olsa?', 'ne olur eğer') cevabı SEN tahmin etme. "
    "O zaman SADECE şu JSON'u yaz, başka hiçbir şey yazma:\n"
    '  {"hesapla": {"oksijen": 25}}\n'
    "  İzinli alanlar: oksijen (% hacim), basinc (kPa), g (Dünya g'si; Ay 0.16, Mars 0.38, ISS 0.0001), "
    "akis (cm/s), kalinlik (mm), seyreltici (n2, co2, he, ar, xe), malzeme (ad). Yalnız değişen alanları yaz. "
    f"Birden çok durum gerekiyorsa liste ver; en fazla {SOHBET_EN_FAZLA_HESAP} hesap: "
    '{"hesapla": [{"oksijen": 25}, {"oksijen": 21}]}\n'
    "- 'Ek hesap' sonuçları verildiyse yeni hesap isteme; o sonuçları mevcut durumla karşılaştırarak açıkla.\n"

    "Tanımlar:\n"
    "- yanma_birlesik: risk modeli ile fizik motorunun ağırlıklı birleşik yanma ihtimali (ana sonuç).\n"
    "- Güvenlik katsayısı = sönme sınırı / ortam oksijeni. 1'den büyükse güvenli, 1'den küçükse tehlikeli.\n"
    "- Yanma ihtimali %50'nin üstündeyse alev yanar kabul edilir.\n"
    "- Güven (guven_v2) 0-100 arasıdır; 60'ın altı düşük güvendir. 'cezalar' güveni düşüren sebeplerdir.\n"
    "- Kısmi yerçekiminde (Ay/Mars) uzay, gerçek g ve Dünya sonuçlarının en kötüsü alınmıştır.\n"
    "Alan adlarını (yanma_birlesik, guven_v2 gibi) yazma; Türkçe karşılığını kullan (birleşik yanma ihtimali, "
    "güven skoru). Türkçe, düz metin, en fazla 120 kelime yaz."
)


def _sohbet_ozeti(sonuc):
    """Bir tahmin() çıktısının kısa özeti (ek hesaplar ve tablo için)."""
    m = sonuc.get("motor") or {}
    v2 = sonuc.get("guven_v2") or {}
    return {"yanma_birlesik": sonuc.get("yanma_birlesik"), "yanma_ihtimali_model": sonuc.get("yanma_ihtimali"),
            "motor_yanma": m.get("yanma"), "motor_kaynagi": sonuc.get("motor_kaynagi"),
            "risk_seviyesi": sonuc.get("risk_seviyesi"), "sonme_siniri": sonuc.get("sonme_siniri"),
            "guvenlik_katsayisi": sonuc.get("guvenlik_katsayisi"),
            "guven": v2.get("skor") if v2.get("skor") is not None else (sonuc.get("guven") or {}).get("skor"),
            "guven_bant": v2.get("bant")}


def sohbet_baglami(sonuc):
    """LLM'e giden bağlam: tahmin() çıktısının kısa hali (birleşik ihtimal, ağırlıklar, motor, güven v2,
    uyarılar, adımlar)."""
    m = sonuc.get("motor") or {}
    v2 = sonuc.get("guven_v2") or {}
    b = {"girdi": sonuc.get("girdi"), **_sohbet_ozeti(sonuc),
         "belirsizlik_model": sonuc.get("belirsizlik"), "agirliklar": sonuc.get("agirliklar"),
         "motor": {k: m.get(k) for k in ("motor_kaynagi", "yanma", "min_oksijen", "yayilma_hizi", "sicaklik",
                                         "motor_auc", "sonme_turu") if m.get(k) is not None},
         "motor_belirsizlik": sonuc.get("motor_belirsizlik"),
         "guven_v2": {"skor": v2.get("skor"), "bant": v2.get("bant"), "bilesenler": v2.get("bilesenler"),
                      "agirliklar": v2.get("agirliklar"), "ham_skor": v2.get("ham_skor"),
                      "cezalar": [{k: c.get(k) for k in ("ad", "carpan", "mesafe")} for c in v2.get("cezalar") or []],
                      "kalibrasyon_mesafesi": v2.get("kalibrasyon_mesafesi"),
                      "agirlikli_yakin_deney": v2.get("agirlikli_yakin_deney")},
         "kullanilan_varsayilanlar": sonuc.get("kullanilan_varsayilanlar"),
         "uyarilar": sonuc.get("uyarilar"),
         "adimlar": [{"no": a.get("no"), "ad": a.get("ad"), "karar": a.get("karar")}
                     for a in sonuc.get("adimlar") or []]}
    s = sonuc.get("sinirlama")
    if isinstance(s, dict):
        b["sinirlama"] = {ad: {k: v.get(k) for k in ("g", "yanma_ihtimali", "sonme_siniri")}
                          for ad, v in s.items() if isinstance(v, dict)}
    return {k: v for k, v in b.items() if v is not None}


def _malzeme_taniniyor(ad):
    """LLM sınıflandırması GEREKTİRMEDEN tanınan malzeme mi (liste, kütüphane ya da önbellek)."""
    try:
        if malzeme_biliniyor(ad) or onbellekten(ad):
            return True
        import predict as T
        return bool(T.kutuphanede_bul(ad))
    except Exception:
        return False


def sohbet_istek_dogrula(istek):
    """Tek bir hesap isteğini denetler -> (kabul mü, temiz sözlük ya da red sebebi)."""
    if not isinstance(istek, dict) or not istek:
        return False, "istek boş ya da nesne değil"
    temiz = {}
    for alan, v in istek.items():
        if alan not in SOHBET_ALANLAR:
            return False, f"izinli olmayan alan: {str(alan)[:30]!r}"
        if alan in SOHBET_ARALIK:
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                return False, f"{alan} sayı olmalı"
            lo, hi, dahil = SOHBET_ARALIK[alan]
            if not (lo <= v <= hi if dahil else lo < v <= hi):
                return False, f"{alan} aralık dışı ({lo}–{hi})"
            temiz[alan] = float(v)
        elif alan == "seyreltici":
            v = _norm(v)
            if v not in SOHBET_SEYRELTICI:
                return False, f"seyreltici şunlardan biri olmalı: {', '.join(SOHBET_SEYRELTICI)}"
            temiz[alan] = v
        else:
            v = _norm(v)[:60]
            if not v or not _malzeme_taniniyor(v):
                return False, f"malzeme listede / kütüphanede yok: {v!r}"
            temiz[alan] = v
    return True, temiz


def _sohbet_istek_ayikla(metin):
    """LLM cevabında {"hesapla": ...} varsa istek listesini, yoksa None döndürür."""
    if '"hesapla"' not in (metin or ""):
        return None
    m = re.search(r"\{.*\}", metin, flags=re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return None
    h = d.get("hesapla") if isinstance(d, dict) else None
    if isinstance(h, dict):
        h = [h]
    return h if isinstance(h, list) and h else None


def _sohbet_hesapla(istekler, sonuc, kosul, hesapla):
    """İstekleri doğrular, tahmin()'i çalıştırır. Dönüş: [{"istek", "durum": tamam|reddedildi|hata, "sebep",
    "girdi", "ozet", "uyarilar"}]; en fazla SOHBET_EN_FAZLA_HESAP hesap."""
    if hesapla is None:
        from predict import tahmin as hesapla
    taban = dict(kosul or sonuc.get("girdi") or {})
    cikti = []
    for istek in istekler[:SOHBET_EN_FAZLA_HESAP]:
        ok, temiz = sohbet_istek_dogrula(istek)
        if not ok:
            cikti.append({"istek": istek if isinstance(istek, dict) else str(istek)[:80], "durum": "reddedildi",
                          "sebep": temiz})
            continue
        k = {a: taban.get(a) for a in ("malzeme", "oksijen", "basinc", "g", "akis", "kalinlik", "numune_tipi",
                                       "yakit_turu", "akis_yonu", "seyreltici")}
        if "malzeme" in temiz and temiz["malzeme"] != _norm(k.get("malzeme")):
            # başka malzeme: numune tipi / yakıt türü / kalınlık o malzemenin varsayılanından gelsin
            k.update({"numune_tipi": None, "yakit_turu": None, "kalinlik": None})
        k.update(temiz)
        k["seyreltici"] = k.get("seyreltici") or "n2"
        try:
            r = hesapla(**k)
        except Exception as e:  # noqa: BLE001
            cikti.append({"istek": temiz, "durum": "hata", "sebep": f"{type(e).__name__}: {str(e)[:120]}"})
            continue
        if r.get("ozel_durum") or r.get("yanma_ihtimali") is None:
            cikti.append({"istek": temiz, "durum": "hata", "sebep": "bu koşul yakıt olarak çözülemedi",
                          "uyarilar": (r.get("uyarilar") or [])[:2]})
            continue
        cikti.append({"istek": temiz, "durum": "tamam", "girdi": r.get("girdi"), "ozet": _sohbet_ozeti(r),
                      "agirliklar": r.get("agirliklar"), "uyarilar": (r.get("uyarilar") or [])[:4]})
    return cikti


def _sohbet_hata(e, anahtar):
    if isinstance(e, urllib.error.HTTPError):
        return "hata", f"HTTP {e.code}"
    if isinstance(e, (socket.timeout, TimeoutError)) or (
            isinstance(e, urllib.error.URLError) and isinstance(e.reason, (socket.timeout, TimeoutError))):
        return "baglanti_yok", f"zaman aşımı, {ZAMAN_ASIMI} sn"
    if isinstance(e, urllib.error.URLError):
        return "baglanti_yok", _gizle(f"bağlantı hatası: {e.reason}", anahtar)
    if isinstance(e, RuntimeError) and "anahtar" in str(e):
        return "baglanti_yok", str(e)
    return "hata", _gizle(f"{type(e).__name__}: {str(e)[:150]}", anahtar)


def ulasilabilir(zaman_asimi=3.0):
    """LLM'e ulaşılabiliyor mu (anahtar var + sunucuya bağlanılıyor)? -> (bool, sebep). İstek göndermez."""
    try:
        _anahtar()
    except Exception as e:  # noqa: BLE001
        return False, str(e)
    if any(os.environ.get(x) for x in ("https_proxy", "HTTPS_PROXY")):
        return True, None            # vekil sunucu arkasında doğrudan bağlantı denenemez
    import urllib.parse
    u = urllib.parse.urlparse(API_URL)
    try:
        socket.create_connection((u.hostname, u.port or 443), timeout=zaman_asimi).close()
        return True, None
    except OSError as e:
        return False, f"bağlantı yok ({type(e).__name__})"


SOHBET_GENEL_SISTEM = (
    "Sen AHUT FLARE uygulamasının yardımcısısın. AHUT FLARE: uzayda yangın güvenliği için masaüstü analiz ortamı. "
    "ISS, Ay ve Mars koşullarında (yerçekimi, basınç, oksijen, seyreltici gaz, hava akışı) bir malzemenin yanıp "
    "yanmayacağını tahmin eder ve tahmini NASA mikro yerçekimi yanma deneyleriyle (Saffire, BASS, FLEX, BRE) karşılaştırır.\n"
    "Uygulamanın bölümleri: Başlangıç, Model (girdi düğümleri: ortam, malzeme, numune, akış, çözüm ayarları; sonuç "
    "düğümleri: risk özeti, oksijen eğrisi, yanabilirlik haritası, akış eğrisi, yakın deneyler, güven, motor, 3B, adımlar, "
    "sınırlamalar, yapay zeka yorumu, render), Kütüphane (malzemeler), Topluluk, parametre süpürmesi, Çözüm İzleyici. "
    "İki çözüm türü var: hızlı (risk modeli + yarı-ampirik motorlar, saniyenin altında) ve ayrıntılı (OpenFOAM CFD, kuyruğa eklenir). "
    "Çıktılar: risk seviyesi, yanma ihtimali, sönme sınırı (oksijen %), güvenlik katsayısı (sönme sınırı / ortam oksijeni; "
    "1'in altı yanabilir), güven skoru (0-100), uyarılar.\n"
    "Kurallar:\n"
    "- Şu an ekranda bir çözüm sonucu YOK ya da güncel değil. Bu vakanın risk yüzdesi, yayılma hızı, sönme sınırı gibi "
    "sayılarını tahmin etme, uydurma. Kullanıcı sayı isterse 'Çöz (F8)' ile çözmesini söyle.\n"
    "- Sayı yazacaksan yalnızca kullanıcının girdilerindeki sayıları kullan.\n"
    "- Uygulamanın nasıl kullanıldığı, ne yaptığı, sınırları, uzay yangın fiziği ve malzemeler hakkında kısa, doğru, "
    "Türkçe cevap ver (en fazla 120 kelime). Emin olmadığın uygulama ayrıntısını 'emin değilim' diye belirt.\n"
    "- Düz metin yaz (markdown, ** ya da # kullanma); yalnızca sorulanı cevapla, ek açıklama ya da uyarı ekleme."
)


def sohbet_genel(gecmis, soru, girdiler=None, model=None):
    """Çözümden ve motordan bağımsız, uygulama hakkında genel sohbet. Hiçbir durumda istisna fırlatmaz.
    Dönüş: {"durum": "tamam"|"baglanti_yok"|"hata", "cevap", "hesaplar": [], "dogrulanamayan": [], "sebep"}"""
    anahtar = None
    try:
        soru = str(soru or "").strip()[:SOHBET_SORU_UZUNLUK]
        if not soru:
            return {"durum": "hata", "sebep": "soru boş", "hesaplar": []}
        model = model or os.environ.get("LLM_MODEL", VARSAYILAN_MODEL)
        gecmis = [g for g in (gecmis or []) if isinstance(g, dict) and g.get("metin")][-SOHBET_GECMIS:]
        mesajlar = [{"role": "system", "content": SOHBET_GENEL_SISTEM}]
        if isinstance(girdiler, dict) and girdiler:
            mesajlar += [{"role": "user", "content": "Kullanıcının ekrandaki girdileri (çözüm yok):\n"
                          + json.dumps(girdiler, ensure_ascii=False)},
                         {"role": "assistant", "content": "Anlaşıldı."}]
        for g in gecmis:
            mesajlar.append({"role": "assistant" if g.get("rol") == "asistan" else "user", "content": str(g["metin"])[:800]})
        mesajlar.append({"role": "user", "content": soru})
        anahtar = _anahtar()
        cevap = _llm_cagir_tekrarli(mesajlar, model, anahtar, max_tokens=500).replace("**", "").strip()
        kaynak = {"girdiler": girdiler, "soru": soru, "gecmis": [g.get("metin") for g in gecmis]}
        return {"durum": "tamam", "cevap": cevap, "hesaplar": [], "dogrulanamayan": dogrulanamayan_sayilar(cevap, kaynak),
                "model": model, "sonuclu": False}
    except Exception as e:  # noqa: BLE001
        durum, sebep = _sohbet_hata(e, anahtar)
        return {"durum": durum, "sebep": sebep, "hesaplar": []}


def sohbet(sonuc, gecmis, soru, model=None, kosul=None, hesapla=None):
    """Bir tahmin() sonucu hakkında soru-cevap. Hiçbir durumda istisna fırlatmaz.

    sonuc  : tahmin.tahmin(...) çıktısı (mevcut vaka)
    gecmis : [{"rol": "kullanici"|"asistan", "metin": str, "hesaplar": [...]}] (eski mesajlar; son SOHBET_GECMIS'i gider)
    soru   : kullanıcının yeni sorusu
    kosul  : kullanıcının verdiği ham girdiler (yoksa sonuc["girdi"]); ek hesapların tabanı
    hesapla: tahmin fonksiyonu (verilmezse tahmin.tahmin)
    Dönüş: {"durum": "tamam"|"baglanti_yok"|"hata", "cevap", "hesaplar": [...], "dogrulanamayan": [...], "sebep"}"""
    anahtar = None
    hesaplar = []
    try:
        soru = str(soru or "").strip()[:SOHBET_SORU_UZUNLUK]
        if not soru:
            return {"durum": "hata", "sebep": "soru boş", "hesaplar": []}
        if not isinstance(sonuc, dict) or sonuc.get("yanma_ihtimali") is None:
            return {"durum": "hata", "sebep": "önce bir çözüm gerekli (bu vakada sayı yok)", "hesaplar": []}
        model = model or os.environ.get("LLM_MODEL", VARSAYILAN_MODEL)
        baglam = sohbet_baglami(sonuc)
        gecmis = [g for g in (gecmis or []) if isinstance(g, dict) and g.get("metin")][-SOHBET_GECMIS:]
        mesajlar = [{"role": "system", "content": SOHBET_SISTEM},
                    {"role": "user", "content": "Mevcut tahmin (JSON):\n" + json.dumps(baglam, ensure_ascii=False)},
                    {"role": "assistant", "content": "Anlaşıldı. Cevap bu veride varsa oradan vereceğim; yoksa 'Genel bilgi:' diye kendi bilgimle cevaplayacağım."}]
        for g in gecmis:
            asistan = g.get("rol") == "asistan"
            metin = str(g["metin"])[:800]
            if asistan and g.get("hesaplar"):
                metin = "Ek hesap (kod çalıştırdı): " + json.dumps(g["hesaplar"], ensure_ascii=False)[:1500] + "\n" + metin
            mesajlar.append({"role": "assistant" if asistan else "user", "content": metin})
        mesajlar.append({"role": "user", "content": soru})
        anahtar = _anahtar()
        cevap = _llm_cagir_tekrarli(mesajlar, model, anahtar, max_tokens=600)
        istekler = _sohbet_istek_ayikla(cevap)
        if istekler:
            hesaplar = _sohbet_hesapla(istekler, sonuc, kosul, hesapla)
            mesajlar.append({"role": "assistant", "content": json.dumps({"hesapla": istekler[:SOHBET_EN_FAZLA_HESAP]},
                                                                        ensure_ascii=False)})
            mesajlar.append({"role": "user", "content": (
                "Ek hesap sonuçları (kod çalıştırdı; 'reddedildi' / 'hata' olanların sayısı yoktur):\n"
                + json.dumps(hesaplar, ensure_ascii=False)
                + "\n\nŞimdi soruyu bu sonuçlarla cevapla: mevcut durumla karşılaştır. Yeni hesap isteme, JSON yazma, "
                  "yalnız yukarıdaki sayıları kullan.")})
            cevap = _llm_cagir_tekrarli(mesajlar, model, anahtar, max_tokens=600)
            if _sohbet_istek_ayikla(cevap):          # yine istek yazdıysa: sayıları kod tablosu gösterir
                cevap = "Ek hesap yapıldı; sonuçlar tabloda. (Dil modeli açıklama yazmadı.)"
        # sayı denetimi: bağlam + ek hesaplar + kullanıcının yazdığı sayılar + önceki ek hesaplar
        kaynak = {"baglam": baglam, "hesaplar": hesaplar, "soru": soru,
                  "gecmis": [g.get("metin") for g in gecmis if g.get("rol") != "asistan"],
                  "gecmis_hesap": [g.get("hesaplar") for g in gecmis if g.get("hesaplar")],
                  "sinir": SOHBET_EN_FAZLA_HESAP}
        return {"durum": "tamam", "cevap": cevap.strip(), "hesaplar": hesaplar,
                "dogrulanamayan": dogrulanamayan_sayilar(cevap, kaynak), "model": model}
    except Exception as e:  # noqa: BLE001
        durum, sebep = _sohbet_hata(e, anahtar)
        return {"durum": durum, "sebep": sebep, "hesaplar": hesaplar}
