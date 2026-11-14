#!/usr/bin/env python3
"""
Makalelerden veri çıkarma hattı (pipeline) - sürüm 2.

Her makale için sırayla:
  1. Sayfa sayfa metin al (yazı varsa direkt, taranmışsa OCR)
  2. Kaynakçayı at, anahtar kelime elemesi yap
  3. Gemma: makalenin türü ne? (deney / simulasyon / derleme / teori / alakasiz)
  4. Metnin en çok veri içeren parçalarını seç
  5. Gemma: türe göre veri çıkar (sayılar ve birimler yazıldığı gibi)
  6. Kod: birimleri çevirir, kanıt / sayı / mantık kontrolü yapar, tekrarları siler
  7. Sonucu ciktilar/<makale_id>.json olarak kaydet -> sonraki makale

Kullanım:
  python veri_cikar.py --sec         # önce: hızlı seçim, secim.csv yazar
  python veri_cikar.py --limit 5     # sadece ilk 5 makale (deneme)
  python veri_cikar.py               # hepsi (kaldığı yerden devam eder)
  python veri_cikar.py --birlestir   # bütün json'ları CSV'lere birleştir

Kurulum:
  pip install pymupdf pytesseract pillow
  Taranmış PDF'ler için Tesseract da kurulu olmalı (yoksa o sayfalar sonra tekrar denenir).
"""

import argparse
import csv
import io
import json
import multiprocessing
import os
import queue
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None      # sadece --birlestir / temizleme için gerekmez

# ============================== AYARLAR ==============================
# Colab gibi başka bir yerde çalışırken ANA_KLASOR, MODEL ve NUM_CTX ortam değişkeniyle verilebilir
ANA_KLASOR = Path(os.environ.get("ANA_KLASOR", r"D:\nasaspaceapp"))   # çalışma klasörü
PDF_KLASORU = ANA_KLASOR / "pdfler"          # bütün PDF'ler burada (alt klasörler de taranır)
METIN_KLASORU = ANA_KLASOR / "metinler"      # .txt dosyaları buraya
CIKTI_KLASORU = ANA_KLASOR / "ciktilar"      # her makalenin json sonucu buraya
# CSV'ler de ANA_KLASOR içine yazılır

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("MODEL", "gemma3:4b")       # 'ollama list' ile tam adına bak
NUM_CTX = int(os.environ.get("NUM_CTX", 16384))    # modelin bir seferde okuyabileceği uzunluk
NUM_PREDICT = 3000                      # modelin bir cevapta yazabileceği en fazla uzunluk
MAKS_KARAKTER = 12000                   # Gemma'ya bir seferde verilen metin
MAKS_PARCA = 6                          # bir makaleden en fazla kaç parça okunsun
CEVAP_SURESI = 300                      # bir Gemma cevabı için en fazla bekleme (sn)
MAKALE_SURESI = 20 * 60                 # bir makale bundan uzun sürerse atlanır (sn)

MIN_KARAKTER_SAYFA = 200                # bundan az yazı varsa sayfa taranmış sayılır
OCR_DPI = 300
OCR_MIN_GUVEN = 60                      # bunun altındaki OCR sayıları şüpheli
OCR_SAYFA_SURESI = 60                   # bir sayfanın OCR'ı bundan uzun sürerse o sayfa atlanır
MAKS_OCR_SAYFA = 40                     # bir makalede en fazla kaç sayfa OCR'lansın

# Arkadaşının ayıkladığı liste (CSV). Doluysa sadece bu listedeki makaleler işlenir.
# Örn: ANA_KLASOR / "secilenler.csv"   |   None = klasördeki bütün PDF'ler
SECILI_CSV = None
SECILI_SUTUN = "doi"                    # listedeki DOI sütununun adı

# Gemma'ya sormadan önce hızlı anahtar kelime elemesi
ANAHTAR_ELEME = True
MIN_YANMA_KELIMESI = 5                  # metinde en az kaç yanma kelimesi geçmeli
YERCEKIMI_ZORUNLU = True                # yerçekimi kelimesi hiç yoksa ele
# ======================================================================

SURUM = 2

YANMA_KELIMELERI = ["flame", "combust", "ignit", "flammab", "extinction", "burning rate",
                    "spread rate", "fire"]
YERCEKIMI_KELIMELERI = ["microgravity", "micro-gravity", "reduced gravity", "low gravity",
                        "low-gravity", "zero gravity", "zero-gravity", "partial gravity",
                        "weightless", "drop tower", "parabolic flight", "space station",
                        "lunar", "martian", "mars gravity", "buoyan", "μg", "narrow channel"]

TUR_ESLE = {"experiment": "deney", "simulation": "simulasyon", "review": "derleme",
            "theory": "teori", "irrelevant": "alakasiz"}

# Mikro yerçekimi platformları: g sayısı yazılmamışsa bu değer kullanılır
PLATFORM_G = {"drop_tower": 1e-4, "ISS": 1e-4, "sounding_rocket": 1e-4, "space_shuttle": 1e-4,
              "normal_g": 1.0, "narrow_channel": 1.0}
MIKRO_G_PLATFORMLAR = ("drop_tower", "ISS", "sounding_rocket", "space_shuttle")

SAYAC_ADIMI = 10                        # kalan süre tahmini için son kaç makaleye bakılsın


# =========================================================== birim çevirme
def _b(u):
    """Birim yazısını sadeleştirir: 'cm s^-1' -> 'cm/s', '$\\mu$m' -> 'µm', 'kPa' -> 'kpa'."""
    u = (u or "").strip().lower()
    for a, b in (("\\textmu", "µ"), ("\\mu", "µ"), ("μ", "µ"), ("\\text", ""), ("$", ""),
                 ("{", ""), ("}", ""), ("\\", ""), ("²", "2"), ("^", ""), ("−", "-"),
                 ("–", "-"), ("—", "-"), ("◦", "°"), ("º", "°"), ("с", "c"), ("℃", "°c")):
        u = u.replace(a, b)
    u = re.sub(r"\s+", "", u).rstrip(".")
    u = re.sub(r"^([a-zµ]+)=s$", r"\1/s", u)            # cm=s (OCR) -> cm/s
    u = re.sub(r"^([a-zµ]+)s-1$", r"\1/s", u)          # cms-1 -> cm/s
    u = re.sub(r"^([a-zµ]+)min-1$", r"\1/min", u)
    u = u.replace("persecond", "/s").replace("/sec", "/s")
    return u


def us_ayir(v, u):
    """Birimin başına yazılmış 10'un kuvvetini sayıya katar.
    '2' + 'x10^-2 m' -> 0.02 + 'm';  '10' + '^-4 g' -> 0.0001 + 'g';  '1' + 'e-5 g' -> 1e-5 + 'g'"""
    b = _b(u)
    m = re.match(r"^(\d+(?:\.\d+)?)[x×*]10([-+]?\d+)(.*)$", b)   # birimde sayı da yazılmış: 1×10-3g
    if m:
        return float(m.group(1)) * 10 ** int(m.group(2)), m.group(3)
    m = re.match(r"^[x×*]?10([-+]?\d+)(.*)$", b) or re.match(r"^e([-+]?\d+)(.*)$", b)
    if m:
        return v * 10 ** int(m.group(1)), m.group(2)
    m = re.match(r"^([-]\d+)(.*)$", b)                 # '10' + '-2 g' -> 10^-2
    if m:
        us = int(m.group(1))
        return (10 ** us if v == 10 else v * 10 ** us), m.group(2)
    return v, b


UZUNLUK_MM = {"mm": 1, "cm": 10, "m": 1000, "µm": 1e-3, "um": 1e-3, "micron": 1e-3,
              "microns": 1e-3, "micrometer": 1e-3, "micrometers": 1e-3, "lm": 1e-3,
              "mkm": 1e-3, "in": 25.4, "inch": 25.4, "inches": 25.4,
              "mil": 0.0254, "mils": 0.0254, "nm": 1e-6}
HIZ_MM_S = {"mm/s": 1, "cm/s": 10, "m/s": 1000, "µm/s": 1e-3, "um/s": 1e-3,
            "mm/min": 1 / 60, "cm/min": 10 / 60, "m/min": 1000 / 60,
            "in/s": 25.4, "ft/s": 304.8, "ft/min": 304.8 / 60}
BASINC_KPA = {"kpa": 1, "pa": 1e-3, "mpa": 1000, "atm": 101.325, "bar": 100, "bars": 100,
              "mbar": 0.1, "psi": 6.89476, "psia": 6.89476, "torr": 0.133322,
              "mmhg": 0.133322, "hpa": 0.1, "atmosphere": 101.325, "atmospheres": 101.325,
              "atmospheric": 101.325, "atmosphericpressure": 101.325,
              "standardatmosphere": 101.325, "arm": 101.325, "atms": 101.325}


def tablo_cevir(tablo, carpan=1):
    def f(v, u):
        v, u = us_ayir(v, u)
        k = tablo.get(u)
        return None if k is None else v * k * carpan
    return f


def basinc_cevir(v, u):
    if _b(u) == "psig":                      # gösterge basıncı: atmosfer eklenir
        return (v + 14.696) * 6.89476
    return tablo_cevir(BASINC_KPA)(v, u)


def oksijen_cevir(v, u):
    v, u = us_ayir(v, u)
    u = u.replace("oxygen", "").replace("o2", "").replace("byvolume", "").replace("by", "")
    u = u.replace("volume", "").replace("vol", "").replace("mole", "").replace("molar", "")
    u = u.replace(".", "")
    if u in ("%", "percent", "pct", "%(v/v)", "v/v%", "%v/v"):
        return v
    if u in ("", "fraction", "massfraction", "molfraction", "x", "y", "x(o2)"):
        return v * 100 if v <= 1 else (v if v <= 100 else None)
    return v if u.endswith("%") and "c3h8" not in u and "ch4" not in u else None


def sicaklik_cevir(v, u):
    u = _b(u).replace("°", "").replace("deg", "")
    if u in ("k", "kelvin", "kelvins", "ok"):
        return v
    if u in ("c", "celsius", "oc", ""):
        return v + 273.15 if u else None
    if u in ("f", "fahrenheit"):
        return (v - 32) * 5 / 9 + 273.15
    return None


def g_cevir(v, u):
    v, u = us_ayir(v, u)
    u = u.replace("'", "")
    if u in ("g", "g0", "ge", "go", "gs", "earthg", "xg", "", "gravity", "gn", "g/ge", "g/g0",
             "ofearthsnormalgravity", "ofearthsgravity", "normalgravity", "earthgravity",
             "timesearthgravity", "ofnormalgravity", "g-level", "glevel"):
        return v
    if u in ("m/s2", "ms-2", "m/s/s"):
        return v / 9.81
    if u in ("cm/s2", "cms-2"):
        return v / 981
    if u in ("µg", "ug", "micro-g", "microg"):
        return v * 1e-6
    if u in ("mg", "milli-g"):
        return v * 1e-3
    return None


CEVIRICILER = {
    # Gemma alanı        : (çevrilmiş sütun,            ham sütun,          çevirici)
    "g_level":           ("g_seviyesi",              "g_ham",             g_cevir),
    "thickness":         ("kalinlik_mm",             "kalinlik_ham",      tablo_cevir(UZUNLUK_MM)),
    "oxygen":            ("oksijen_yuzde",           "oksijen_ham",       oksijen_cevir),
    "pressure":          ("basinc_kpa",              "basinc_ham",        basinc_cevir),
    "flow_velocity":     ("akis_hizi_cm_s",          "akis_hizi_ham",     tablo_cevir(HIZ_MM_S, 0.1)),
    "flame_spread_rate": ("alev_yayilma_hizi_mm_s",  "yayilma_hizi_ham",  tablo_cevir(HIZ_MM_S)),
    "min_oxygen":        ("min_oksijen_yuzde",       "min_oksijen_ham",   oksijen_cevir),
    "flame_temperature": ("alev_sicakligi_k",        "sicaklik_ham",      sicaklik_cevir),
}
SONUC_ALANLARI = ["alev_yayilma_hizi_mm_s", "min_oksijen_yuzde", "alev_sicakligi_k"]


# ----------------------------------------------------------------- OCR
def tesseract_bul():
    yol = shutil.which("tesseract")
    if not yol:
        win = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        yol = str(win) if win.exists() else None
    if yol:
        try:
            import pytesseract
        except ImportError:
            return None
        pytesseract.pytesseract.tesseract_cmd = yol
    return yol


TESSERACT = tesseract_bul()


def rakam_duzelt(metin):
    """Sayıların içine karışmış harfleri düzeltir: 1O.5 -> 10.5, 2l% -> 21%.
    'O2' (oksijen) gibi ifadelere dokunmaz: harf iki tarafta da rakam/nokta ister."""
    metin = re.sub(r"(?<=[\d.,])[Oo](?=[\d.,%])", "0", metin)
    metin = re.sub(r"(?<=[\d.,])[lI|](?=[\d.,%])", "1", metin)
    return metin


def ocr_sayfa(sayfa, sayfa_no):
    """Taranmış sayfayı OCR'lar. (metin, düşük güvenli sayılar) döndürür."""
    import pytesseract
    from PIL import Image

    resim = Image.open(io.BytesIO(sayfa.get_pixmap(dpi=OCR_DPI).tobytes("png")))
    veri = pytesseract.image_to_data(resim, lang="eng", output_type=pytesseract.Output.DICT,
                                     timeout=OCR_SAYFA_SURESI)

    satirlar, supheli = {}, []
    for i, kelime in enumerate(veri["text"]):
        kelime = kelime.strip()
        if not kelime:
            continue
        anahtar = (veri["block_num"][i], veri["par_num"][i], veri["line_num"][i])
        satirlar.setdefault(anahtar, []).append(kelime)
        guven = float(veri["conf"][i])
        if any(c.isdigit() for c in kelime) and 0 <= guven < OCR_MIN_GUVEN:
            supheli.append({"sayfa": sayfa_no, "kelime": rakam_duzelt(kelime), "guven": round(guven)})

    metin = "\n".join(" ".join(k) for k in satirlar.values())
    return rakam_duzelt(metin), supheli


def metin_al(pdf, makale_id):
    """PDF'i sayfa sayfa metne çevirir. Daha önce yapıldıysa kayıttan okur."""
    txt = METIN_KLASORU / f"{makale_id}.txt"
    meta = METIN_KLASORU / f"{makale_id}.meta.json"
    if txt.exists() and meta.exists():
        try:
            bilgi = json.loads(meta.read_text(encoding="utf-8"))
            # Önceden Tesseract yokken atlanan sayfalar varsa ve artık Tesseract varsa yeniden yap
            if not (bilgi.get("ocr_atlanan") and TESSERACT):
                return txt.read_text(encoding="utf-8"), bilgi
        except Exception:
            pass

    sayfalar, ocr_sayfalar, supheli, atlanan, basarisiz, sinir_disi = [], [], [], [], [], []
    with fitz.open(pdf) as doc:
        toplam = len(doc)
        for no, sayfa in enumerate(doc, 1):
            metin = sayfa.get_text()
            if len(metin.strip()) < MIN_KARAKTER_SAYFA:
                if not TESSERACT:
                    atlanan.append(no)             # Tesseract kurulunca tekrar denenecek
                elif len(ocr_sayfalar) + len(basarisiz) >= MAKS_OCR_SAYFA:
                    sinir_disi.append(no)          # çok uzun taranmış belge, gerisi atlandı
                else:
                    print(f"   OCR sayfa {no}/{toplam}", flush=True)
                    try:
                        metin, s = ocr_sayfa(sayfa, no)
                        ocr_sayfalar.append(no)
                        supheli.extend(s)
                    except Exception:
                        basarisiz.append(no)       # takıldı ya da bozuk: atla
            sayfalar.append(f"\n=== PAGE {no} ===\n{metin}")

    tam = "".join(sayfalar)
    bilgi = {"sayfa_sayisi": len(sayfalar), "ocr_sayfalar": ocr_sayfalar,
             "ocr_dusuk_guven": supheli, "ocr_atlanan": atlanan,
             "ocr_basarisiz": basarisiz, "ocr_sinir_disi": sinir_disi}
    guvenli_yaz(txt, tam)
    guvenli_yaz(meta, json.dumps(bilgi, ensure_ascii=False))
    return tam, bilgi


def guvenli_yaz(yol, icerik):
    """Önce geçici dosyaya yazar, sonra adını değiştirir. Bağlantı koparsa yarım dosya kalmaz."""
    gecici = Path(str(yol) + ".tmp")
    gecici.write_text(icerik, encoding="utf-8")
    os.replace(gecici, yol)


# --------------------------------------------------------- metin hazırlama
def kaynakcayi_at(metin):
    """Metnin ikinci yarısındaki son 'References' başlığından sonrasını atar."""
    eslesmeler = list(re.finditer(
        r"\n\s*(\d+\.?\s*)?(references|bibliography|literature cited|references and notes|"
        r"works cited)\s*:?\s*\n", metin, re.IGNORECASE))
    if eslesmeler and eslesmeler[-1].start() > len(metin) * 0.5:
        return metin[:eslesmeler[-1].start()]
    return metin


VERI_IPUCU = re.compile(
    r"\d+(\.\d+)?\s*(mm/s|cm/s|m/s|mm\s*s|cm\s*s|kpa|atm|torr|psi|%|µm|μm|mm\b|k\b|°c)"
    r"|spread rate|spread velocity|extinction|flammability limit|blow-?off|quench"
    r"|\btable\s+\d|\bfig(ure)?\.?\s*\d", re.IGNORECASE)


def parcala(metin):
    """Metni sayfa sınırlarından parçalara böler; en çok veri içeren MAKS_PARCA parçayı
    (makaledeki sırasını bozmadan) seçer."""
    sayfalar = re.split(r"(?=\n=== PAGE \d+ ===\n)", metin)
    parcalar, simdiki = [], ""
    for s in sayfalar:
        while len(s) > MAKS_KARAKTER:                 # tek sayfa çok uzunsa böl
            if simdiki:
                parcalar.append(simdiki)
                simdiki = ""
            parcalar.append(s[:MAKS_KARAKTER])
            s = s[MAKS_KARAKTER:]
        if len(simdiki) + len(s) > MAKS_KARAKTER and simdiki:
            parcalar.append(simdiki)
            simdiki = ""
        simdiki += s
    if simdiki.strip():
        parcalar.append(simdiki)
    if len(parcalar) <= MAKS_PARCA:
        return parcalar
    puan = [len(VERI_IPUCU.findall(p)) for p in parcalar]
    secilen = sorted(sorted(range(len(parcalar)), key=lambda i: -puan[i])[:MAKS_PARCA])
    return [parcalar[i] for i in secilen]


# -------------------------------------------------------- belge (kontrol için)
def sadelestir(s):
    """Küçük harf, sadece harf/rakam; nokta sadece ondalık sayılarda kalır."""
    s = (s or "").lower()
    s = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", s)
    return re.sub(r"[^a-z0-9.]+", " ", s).strip()


def ikililer(kelimeler):
    return {(a, b) for a, b in zip(kelimeler, kelimeler[1:])}


class Belge:
    """Kontroller için makalenin sayfalarını hazır tutar."""

    def __init__(self, metin, bilgi):
        self.metin = metin
        self.sayfalar = {}
        for parca in re.split(r"(?=\n=== PAGE \d+ ===\n)", metin):
            m = re.search(r"=== PAGE (\d+) ===", parca)
            if m:
                self.sayfalar[int(m.group(1))] = parca
        self.sade = {n: sadelestir(t) for n, t in self.sayfalar.items()}
        self.ikili = {n: ikililer(t.split()) for n, t in self.sade.items()}
        self.tum_sade = " ".join(self.sade.values())
        self.ocr_sayfalar = set(bilgi.get("ocr_sayfalar", []))
        self.dusuk_guven = {}
        for d in bilgi.get("ocr_dusuk_guven", []):
            self.dusuk_guven.setdefault(d["sayfa"], []).append(d["kelime"])

    def kanit_bul(self, kanit):
        """Kanıt cümlesi metinde var mı? (birebir ya da çok küçük farkla)
        (var_mi, sayfa) döndürür."""
        k = sadelestir(kanit)
        kelimeler = k.split()
        if len(kelimeler) < 4:
            return False, None
        aranan = " ".join(kelimeler[:14])
        for n, t in self.sade.items():
            if aranan in t:
                return True, n
        # birebir yoksa: kelime ikililerinin en az %75'i aynı sayfada geçiyor mu?
        k_ikili = ikililer(kelimeler)
        en_iyi, sayfa = 0, None
        for n, iki in self.ikili.items():
            oran = len(k_ikili & iki) / max(len(k_ikili), 1)
            if oran > en_iyi:
                en_iyi, sayfa = oran, n
        return (en_iyi >= 0.75), (sayfa if en_iyi >= 0.75 else None)

    def sayi_var_mi(self, deger, sayfa=None):
        """Sayı (yazıldığı biçimiyle) ilgili sayfada ya da yanındaki sayfalarda geçiyor mu?"""
        if sayfa and sayfa in self.sayfalar:
            alan = " ".join(self.sayfalar.get(n, "") for n in (sayfa - 1, sayfa, sayfa + 1))
        else:
            alan = self.metin
        return any(re.search(r"(?<![\d.])" + re.escape(b) + r"(?![\d])", alan)
                   for b in sayi_bicimleri(deger))

    def dusuk_guvenli_mi(self, deger, sayfa):
        if sayfa not in self.dusuk_guven:
            return False
        bicimler = sayi_bicimleri(deger)
        return any(re.sub(r"[^\d.]", "", k).strip(".") in bicimler for k in self.dusuk_guven[sayfa])


def sayi_bicimleri(deger):
    d = float(deger)
    b = {f"{d:g}", repr(d)}
    if d.is_integer():
        b.add(str(int(d)))
    if 0 < abs(d) < 1:
        b |= {x[1:] for x in list(b) if x.startswith("0.")}     # 0.25 -> .25
    for basamak in (1, 2, 3):
        b.add(f"{d:.{basamak}f}")          # 21 -> 21.0, 1.5 -> 1.50
    return {x for x in b if x and float(x) == d and float(x) != 0}


# ----------------------------------------------------------------- Gemma
SISTEM = (
    "You extract data from scientific papers about combustion, flames and fire, "
    "especially in reduced gravity. Only report information that is explicitly stated "
    "in the given text. Never guess or use outside knowledge. If something is not "
    "stated, use null. Copy numbers and units exactly as written; never convert units. "
    "Evidence must be copied word for word from the text. "
    "Page numbers come from the '=== PAGE n ===' markers."
)

SAYI = {"type": ["number", "null"]}
YAZI = {"type": ["string", "null"]}
DEGER = {"type": "object", "properties": {"value": SAYI, "unit": YAZI},
         "required": ["value", "unit"]}

SEMA_TUR = {
    "type": "object",
    "properties": {
        "types": {"type": "array", "items": {"type": "string", "enum": list(TUR_ESLE)}},
        "reason": {"type": "string"},
    },
    "required": ["types", "reason"],
}

SEMA_DENEY = {
    "type": "object",
    "properties": {
        "conditions": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "enum": ["experiment", "simulation", "cited"]},
                "platform": {"type": ["string", "null"], "enum": [
                    "drop_tower", "parabolic", "ISS", "sounding_rocket", "space_shuttle",
                    "centrifuge", "narrow_channel", "normal_g", "other", None]},
                "g_level": DEGER,
                "material": YAZI,
                "sample_type": {"type": ["string", "null"], "enum": [
                    "thin_sheet", "thick_sheet", "rod", "droplet", "gas_jet", "wire",
                    "fabric", "pool", "particle_cloud", "other", None]},
                "thickness": DEGER,
                "oxygen": DEGER,
                "diluent": YAZI,
                "pressure": DEGER,
                "flow_velocity": DEGER,
                "flow_direction": {"type": ["string", "null"],
                                   "enum": ["concurrent", "opposed", "none", None]},
                "spread_direction": {"type": ["string", "null"],
                                     "enum": ["upward", "downward", "horizontal", None]},
                "flame_spread_rate": DEGER,
                "extinguished": {"type": ["string", "null"], "enum": ["yes", "no", None]},
                "min_oxygen": DEGER,
                "flame_temperature": DEGER,
                "note": YAZI,
                "evidence": {"type": "string"},
                "page": {"type": ["integer", "null"]},
            },
            "required": ["source", "platform", "g_level", "material", "sample_type",
                         "thickness", "oxygen", "diluent", "pressure", "flow_velocity",
                         "flow_direction", "spread_direction", "flame_spread_rate",
                         "extinguished", "min_oxygen", "flame_temperature", "note",
                         "evidence", "page"],
        }},
        "result_tables_figures": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "page": {"type": ["integer", "null"]},
                "kind": {"type": "string", "enum": ["table", "figure"]},
                "label": YAZI,
                "shows": {"type": "string"},
            },
            "required": ["page", "kind", "label", "shows"],
        }},
    },
    "required": ["conditions", "result_tables_figures"],
}

SEMA_DERLEME = {
    "type": "object",
    "properties": {"data_tables": {"type": "array", "items": {
        "type": "object",
        "properties": {"page": {"type": ["integer", "null"]}, "label": YAZI,
                       "shows": {"type": "string"}},
        "required": ["page", "label", "shows"],
    }}},
    "required": ["data_tables"],
}

SEMA_TEORI = {
    "type": "object",
    "properties": {"formulas": {"type": "array", "items": {
        "type": "object",
        "properties": {"formula": {"type": "string"}, "predicts": {"type": "string"},
                       "valid_when": YAZI, "evidence": {"type": "string"},
                       "page": {"type": ["integer", "null"]}},
        "required": ["formula", "predicts", "valid_when", "evidence", "page"],
    }}},
    "required": ["formulas"],
}

SORU_TUR = """Classify this paper. We only want papers about the PHYSICS of combustion:
flame spread, ignition, extinction, flammability of materials, droplet or gas flames,
especially in microgravity or reduced gravity.

Possible types (a paper can have more than one):
- experiment: new physical measurements of flames or combustion were made
- simulation: numerical / computational results of flames or combustion
- review: summarizes or compiles combustion results of other studies
- theory: develops formulas or analytical models of flames or combustion
- irrelevant: anything else. Examples: medical papers (burn injuries, patients,
  treatment), engines or industry without flame physics, papers that only mention
  fire in passing. If unsure, choose irrelevant.

TEXT:
{metin}"""

SORU_DENEY = """From this part of a combustion paper, extract the test conditions and results.

Rules:
- One item per distinct test condition (different material, oxygen, pressure, gravity,
  flow, thickness ...). Do not repeat the same condition.
- Copy every number and unit EXACTLY as written. Do NOT convert units.
  Examples: "1 atm" -> {{"value": 1, "unit": "atm"}}; "21% O2" -> {{"value": 21, "unit": "%"}};
  "0.38 g" -> {{"value": 0.38, "unit": "g"}}; "2.5 cm/s" -> {{"value": 2.5, "unit": "cm/s"}}.
- If a quantity is not stated, use {{"value": null, "unit": null}}.
- If only a range is given (e.g. "15-21%"), use null and write the range in "note".
- source: "experiment" = measured in this paper's own tests, "simulation" = computed by this
  paper's own model, "cited" = value from another study mentioned in the text.
- g_level: only if gravity is given as a number. Otherwise null; the platform is enough.
- evidence: copy ONE sentence exactly from the text, the one with the most important values.
- At most 20 items. If this part has no conditions or results, return empty lists.
- Also list tables and figures that show numerical results (spread rate, extinction limits ...).

TEXT:
{metin}"""

SORU_DERLEME = """This is a review paper. List the tables that compile numerical data from
experiments (flame spread rates, extinction / flammability limits, conditions).
If there are none, return an empty list.

TEXT:
{metin}"""

SORU_TEORI = """List the formulas or correlations in this text that predict flame behaviour
(spread rate, extinction limit, flame temperature, etc.). Write each formula in plain text,
say what it predicts and when it is valid. Copy one evidence sentence exactly from the text.
At most 10 items. If there are none, return an empty list.

TEXT:
{metin}"""


DUSUNME_KAPALI = True   # Gemma 4 gibi "düşünen" modellerde düşünmeyi kapat (hız + tam JSON)


def gemma(soru, sema):
    """Gemma'ya sorar. Bozuk cevapta bir kez daha, biraz farklı ayarla dener."""
    global DUSUNME_KAPALI
    son_hata = None
    for sicaklik in (0, 0.3):
        istek_verisi = {
            "model": MODEL, "stream": False, "format": sema,
            "options": {"temperature": sicaklik, "num_ctx": NUM_CTX, "num_predict": NUM_PREDICT},
            "messages": [{"role": "system", "content": SISTEM},
                         {"role": "user", "content": soru}],
        }
        if DUSUNME_KAPALI:
            istek_verisi["think"] = False
        try:
            istek = urllib.request.Request(f"{OLLAMA_URL}/api/chat",
                                           data=json.dumps(istek_verisi).encode("utf-8"),
                                           headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(istek, timeout=CEVAP_SURESI) as cevap:
                icerik = json.loads(cevap.read())["message"]["content"]
            return json.loads(icerik)
        except urllib.error.HTTPError as e:
            mesaj = e.read().decode("utf-8", "replace")
            # model "think" ayarını desteklemiyorsa ayarı bırakıp aynı soruyu tekrar sor
            if DUSUNME_KAPALI and "think" in mesaj.lower():
                DUSUNME_KAPALI = False
                return gemma(soru, sema)
            son_hata = f"HTTP {e.code}: {mesaj[:200]}"
            time.sleep(2)
        except Exception as e:
            son_hata = e
            time.sleep(2)
    raise RuntimeError(f"Gemma cevap vermedi / bozuk JSON: {son_hata}")


def ollama_kontrol():
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=10) as c:
            modeller = [m["name"] for m in json.loads(c.read())["models"]]
    except Exception as e:
        sys.exit(f"Ollama'ya bağlanılamadı ({OLLAMA_URL}): {e}\n'ollama serve' çalışıyor mu?")
    if MODEL not in modeller and f"{MODEL}:latest" not in modeller:
        sys.exit(f"'{MODEL}' modeli yok. Yüklü modeller: {modeller}\n"
                 f"Koddaki MODEL ayarını bunlardan biriyle değiştir.")


# --------------------------------------------------------------- kontroller
def mantik_kontrol(s):
    sorun = []

    def ara(alan, alt, ust):
        v = s.get(alan)
        if v is not None and not (alt <= v <= ust):
            sorun.append(f"{alan}={v:g} mantıksız")

    ara("oksijen_yuzde", 0.1, 100)
    ara("min_oksijen_yuzde", 0.1, 100)
    ara("basinc_kpa", 0.1, 10000)
    ara("g_seviyesi", 0, 3)
    ara("kalinlik_mm", 0.0005, 100)
    ara("alev_yayilma_hizi_mm_s", 0.0001, 500)
    ara("alev_sicakligi_k", 300, 3500)
    ara("akis_hizi_cm_s", 0, 1000)

    g, p = s.get("g_seviyesi"), s.get("platform")
    if g is not None and p in MIKRO_G_PLATFORMLAR and g > 0.05:
        sorun.append(f"platform {p} ama g={g:g}")
    if g is not None and p in ("normal_g", "narrow_channel") and not (0.5 <= g <= 1.5):
        sorun.append(f"platform {p} ama g={g:g}")
    o, mo = s.get("oksijen_yuzde"), s.get("min_oksijen_yuzde")
    if o is not None and mo is not None and mo > o and s.get("sondu_mu") == "hayir":
        sorun.append("sönme sınırı ortam oksijeninden büyük ama alev sönmemiş")
    return sorun


def deney_satiri(ham, belge):
    """Gemma'nın verdiği bir deney koşulunu çevirir ve kontrol eder."""
    kaynak = ham.get("source")
    s = {
        "veri_turu": {"experiment": "deney", "simulation": "simulasyon",
                      "cited": "alinti"}.get(kaynak, "deney"),
        "platform": ham.get("platform"),
        "malzeme": ham.get("material"), "numune_tipi": ham.get("sample_type"),
        "seyreltici": ham.get("diluent"),
        "akis_yonu": {"concurrent": "ayni", "opposed": "ters", "none": "yok"}.get(
            ham.get("flow_direction")),
        "yayilma_yonu": {"upward": "yukari", "downward": "asagi",
                         "horizontal": "yatay"}.get(ham.get("spread_direction")),
        "sondu_mu": {"yes": "evet", "no": "hayir"}.get(ham.get("extinguished")),
    }
    sorun, sayfa = [], ham.get("page")

    var, bulunan = belge.kanit_bul(ham.get("evidence", ""))
    if var:
        sayfa = bulunan or sayfa
    else:
        sorun.append("kanıt cümlesi metinde yok")

    # sayıları yazıldığı birimle al, kodla çevir, metinde geçiyor mu bak
    for alan, (sutun, ham_sutun, cevir) in CEVIRICILER.items():
        d = ham.get(alan) or {}
        if not isinstance(d, dict):
            d = {}
        v, u = d.get("value"), d.get("unit")
        s[sutun], s[ham_sutun] = None, None
        if v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        s[ham_sutun] = f"{v:g} {u or ''}".strip()
        cevrilen = cevir(v, u)
        if cevrilen is None:
            sorun.append(f"{alan}: birim tanınmadı ({v:g} {u})")
        else:
            s[sutun] = round(cevrilen, 6)
        if v != 0 and not belge.sayi_var_mi(v, sayfa):
            sorun.append(f"{alan}={v:g} metinde geçmiyor")
        if belge.dusuk_guvenli_mi(v, sayfa):
            sorun.append(f"{alan}={v:g} OCR'da düşük güvenle okunmuş")

    # model bilmediği platformları "narrow_channel"a atabiliyor: makalede geçmiyorsa sil
    if s["platform"] == "narrow_channel" and "narrow channel" not in belge.tum_sade:
        s["platform"] = None
    # 280-320 K arası "alev sıcaklığı" aslında ortam/başlangıç sıcaklığıdır
    if s["alev_sicakligi_k"] is not None and 280 <= s["alev_sicakligi_k"] <= 320:
        s["alev_sicakligi_k"] = None

    # g yazılmamışsa platformdan tahmin et
    s["g_kaynagi"] = "metin" if s["g_seviyesi"] is not None else None
    if s["g_seviyesi"] is None and s["platform"] in PLATFORM_G:
        s["g_seviyesi"] = PLATFORM_G[s["platform"]]
        s["g_kaynagi"] = "platformdan"

    # malzeme adı gerçekten metinde geçiyor mu?
    if s["malzeme"]:
        kelimeler = [k for k in sadelestir(s["malzeme"]).split() if len(k) >= 3]
        if kelimeler and not any(k in belge.tum_sade for k in kelimeler):
            sorun.append(f"malzeme '{s['malzeme']}' metinde geçmiyor")

    sorun += mantik_kontrol(s)
    s["sonuc_var"] = "evet" if (any(s[a] is not None for a in SONUC_ALANLARI)
                                or s["sondu_mu"]) else "hayir"
    s["not"] = ham.get("note")
    s["kanit"] = ham.get("evidence", "")
    s["sayfa"] = sayfa
    s["ocr"] = ("evet" if sayfa in belge.ocr_sayfalar else "hayir") if sayfa else \
               ("belirsiz" if belge.ocr_sayfalar else "hayir")
    s["supheli"] = "evet" if sorun else "hayir"
    s["supheli_nedenleri"] = "; ".join(sorun)
    return s


KOSUL_ALANLARI = ["platform", "g_seviyesi", "malzeme", "numune_tipi", "kalinlik_mm",
                  "oksijen_yuzde", "seyreltici", "basinc_kpa", "akis_hizi_cm_s", "akis_yonu",
                  "yayilma_yonu"]


def bos_mu(s):
    """Hiçbir koşul ve sonuç yoksa satır işe yaramaz."""
    kosul = any(s.get(a) is not None for a in KOSUL_ALANLARI if a not in ("g_seviyesi",))
    return not kosul and s["sonuc_var"] == "hayir"


def tekrarlari_sil(satirlar):
    """Aynı deney birkaç parçada tekrar çıktıysa bir tane bırak (şüphesiz olanı tercih et)."""
    def anahtar(s):
        return tuple(str(s.get(a)).lower() for a in KOSUL_ALANLARI + SONUC_ALANLARI + ["sondu_mu"])
    secilen = {}
    for s in satirlar:
        k = anahtar(s)
        if k not in secilen or (secilen[k]["supheli"] == "evet" and s["supheli"] == "hayir"):
            secilen[k] = s
    return list(secilen.values())


# ------------------------------------------------------------ tek makale
def anahtar_skor(metin):
    kucuk = metin.lower()
    yanma = sum(kucuk.count(k) for k in YANMA_KELIMELERI)
    yercekimi = sum(kucuk.count(k) for k in YERCEKIMI_KELIMELERI)
    gecti = yanma >= MIN_YANMA_KELIMESI and (yercekimi > 0 or not YERCEKIMI_ZORUNLU)
    return yanma, yercekimi, gecti


def kaynak_bul(pdf):
    """NTRS'ten inen dosyaların adı sadece rakamdır (örn. 20205004657.pdf)."""
    if pdf.stem.isdigit() or pdf.parent.name.lower() in ("nasa", "nasa_pdfler"):
        return "nasa"
    return "diger"


def makale_isle(pdf, makale_id):
    metin, bilgi = metin_al(pdf, makale_id)
    temiz = kaynakcayi_at(metin)
    sonuc = {"makale_id": makale_id, "dosya": str(pdf), "kaynak": kaynak_bul(pdf),
             "model": MODEL, "surum": SURUM,
             "sayfa_sayisi": bilgi["sayfa_sayisi"], "ocr_sayfalar": bilgi["ocr_sayfalar"],
             "ocr_dusuk_guven": bilgi["ocr_dusuk_guven"], "ocr_atlanan": bilgi["ocr_atlanan"],
             "turler": [], "tur_gerekce": "", "deneyler": [], "tablo_grafik": [],
             "derleme_tablolar": [], "formuller": [], "hatalar": []}

    if len(temiz.strip()) < 500:
        sonuc["hatalar"].append("metin çok kısa ya da okunamadı")
        return sonuc

    # 0) hızlı anahtar kelime elemesi (Gemma'ya hiç sormadan)
    if ANAHTAR_ELEME:
        yanma, yercekimi, gecti = anahtar_skor(temiz)
        sonuc["anahtar_kelime"] = {"yanma": yanma, "yercekimi": yercekimi}
        if not gecti:
            sonuc["turler"] = ["alakasiz"]
            sonuc["tur_gerekce"] = f"anahtar kelime elemesi (yanma={yanma}, yerçekimi={yercekimi})"
            return sonuc

    # 1) tür
    t = gemma(SORU_TUR.format(metin=temiz[:6000]), SEMA_TUR)
    sonuc["turler"] = sorted({TUR_ESLE[x] for x in t.get("types", []) if x in TUR_ESLE})
    sonuc["tur_gerekce"] = t.get("reason", "")
    turler = set(sonuc["turler"]) - {"alakasiz"}
    if not turler:
        sonuc["turler"] = ["alakasiz"]
        return sonuc

    # 2) türe göre çıkarım, en çok veri içeren parçalarda
    belge = Belge(temiz, bilgi)
    satirlar = []
    parcalar = parcala(temiz)
    for i, parca in enumerate(parcalar, 1):
        print(f"   Gemma parça {i}/{len(parcalar)}", flush=True)
        if turler & {"deney", "simulasyon"}:
            try:
                c = gemma(SORU_DENEY.format(metin=parca), SEMA_DENEY)
                for d in c.get("conditions", [])[:20]:
                    satir = deney_satiri(d, belge)
                    if not bos_mu(satir):
                        satirlar.append(satir)
                for tg in c.get("result_tables_figures", []):
                    sonuc["tablo_grafik"].append({
                        "sayfa": tg.get("page"),
                        "tur": "tablo" if tg.get("kind") == "table" else "grafik",
                        "etiket": tg.get("label"), "gosterdigi": tg.get("shows"),
                        "ocr_sayfasi": "evet" if tg.get("page") in belge.ocr_sayfalar else "hayir"})
            except Exception as e:
                sonuc["hatalar"].append(f"parça {i} deney: {e}")

        if "derleme" in turler:
            try:
                c = gemma(SORU_DERLEME.format(metin=parca), SEMA_DERLEME)
                for tb in c.get("data_tables", []):
                    sonuc["derleme_tablolar"].append({
                        "sayfa": tb.get("page"), "etiket": tb.get("label"),
                        "gosterdigi": tb.get("shows")})
            except Exception as e:
                sonuc["hatalar"].append(f"parça {i} derleme: {e}")

        if "teori" in turler:
            try:
                c = gemma(SORU_TEORI.format(metin=parca), SEMA_TEORI)
                for f in c.get("formulas", [])[:10]:
                    var, sayfa = belge.kanit_bul(f.get("evidence", ""))
                    sonuc["formuller"].append({
                        "formul": f.get("formula"), "hesapladigi": f.get("predicts"),
                        "gecerlilik": f.get("valid_when"), "kanit": f.get("evidence"),
                        "sayfa": sayfa or f.get("page"),
                        "supheli": "hayir" if var else "evet"})
            except Exception as e:
                sonuc["hatalar"].append(f"parça {i} teori: {e}")

    sonuc["deneyler"] = tekrarlari_sil(satirlar)
    sonuc["tablo_grafik"] = tekil(sonuc["tablo_grafik"], ("sayfa", "tur", "etiket"))
    sonuc["derleme_tablolar"] = tekil(sonuc["derleme_tablolar"], ("sayfa", "etiket"))
    sonuc["formuller"] = tekil(sonuc["formuller"], ("formul",), sadelestir)
    return sonuc


def tekil(liste, alanlar, donustur=lambda x: x):
    gorulen, sonuc = set(), []
    for x in liste:
        k = tuple(donustur(str(x.get(a))) for a in alanlar)
        if k not in gorulen:
            gorulen.add(k)
            sonuc.append(x)
    return sonuc


# ------------------------------------------------------------- birleştir
def csv_yaz(dosya, satirlar):
    if not satirlar:
        print(f"  {dosya}: boş, yazılmadı")
        return
    alanlar = list(dict.fromkeys(k for s in satirlar for k in s))
    with open(dosya, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=alanlar)
        w.writeheader()
        w.writerows(satirlar)
    print(f"  {dosya}: {len(satirlar)} satır")


def kaynak_link(makale_id, kaynak):
    if kaynak == "nasa":
        return "", f"https://ntrs.nasa.gov/citations/{makale_id}"
    if re.match(r"^W\d+$", makale_id):
        return "", f"https://openalex.org/{makale_id}"
    if makale_id.startswith("10."):
        doi = re.sub(r"^(10\.\d{4,9})_", r"\1/", makale_id)   # ilk '_' büyük ihtimalle '/'
        return doi, f"https://doi.org/{doi}"
    return "", ""


def birlestir():
    veri, formul, tablo, sinif, bozuk = [], [], [], [], []
    for js in sorted(CIKTI_KLASORU.glob("*.json")):
        try:
            r = json.loads(js.read_text(encoding="utf-8"))
        except Exception:
            bozuk.append(js.name)
            continue
        doi, link = kaynak_link(r["makale_id"], r.get("kaynak", "diger"))
        ortak = {"makale_id": r["makale_id"], "kaynak": r.get("kaynak", "diger"),
                 "doi_tahmini": doi, "link": link, "model": r.get("model", "")}
        sinif.append({**ortak, "turler": ", ".join(r["turler"]), "gerekce": r["tur_gerekce"],
                      "deney_satiri": len(r["deneyler"]),
                      "ocr_sayfa_sayisi": len(r["ocr_sayfalar"]),
                      "ocr_atlanan": len(r.get("ocr_atlanan", [])),
                      "hatalar": " | ".join(r["hatalar"])})
        for d in r["deneyler"]:
            veri.append({**ortak, **d})
        for f in r["formuller"]:
            formul.append({**ortak, **f})
        for t in r["tablo_grafik"]:
            tablo.append({**ortak, "nereden": "sonuc", **t})
        for t in r["derleme_tablolar"]:
            tablo.append({**ortak, "nereden": "derleme", "tur": "tablo", **t})

    print("Birleştiriliyor:")
    csv_yaz(ANA_KLASOR / "veri_seti.csv", veri)
    csv_yaz(ANA_KLASOR / "elle_bakilacak.csv", [v for v in veri if v["supheli"] == "evet"])
    csv_yaz(ANA_KLASOR / "formuller.csv", formul)
    csv_yaz(ANA_KLASOR / "tablo_grafik_sayfalari.csv", tablo)
    csv_yaz(ANA_KLASOR / "siniflandirma.csv", sinif)
    if veri:
        say = lambda k, v: sum(1 for x in veri if x.get(k) == v)
        print(f"\n  Deney satırı: {say('veri_turu', 'deney')} | simülasyon: "
              f"{say('veri_turu', 'simulasyon')} | alıntı: {say('veri_turu', 'alinti')} | "
              f"şüpheli: {say('supheli', 'evet')} | sonucu olan: {say('sonuc_var', 'evet')}")
    if bozuk:
        print(f"  UYARI: {len(bozuk)} bozuk json atlandı (bu makaleler tekrar işlenecek).")


# ------------------------------------------------------------------ seçim
SECIM_CSV = ANA_KLASOR / "secim.csv"


def secim_yap(pdfler):
    """Bütün PDF'leri hızlıca tarar (OCR yok, Gemma yok) ve secim.csv yazar."""
    satirlar = []
    for i, pdf in enumerate(pdfler, 1):
        try:
            with fitz.open(pdf) as doc:
                metin = "".join(s.get_text() for s in doc)
                sayfa = len(doc)
        except Exception as e:
            satirlar.append({"makale_id": pdf.stem, "karar": "bozuk_pdf", "yanma": 0,
                             "yercekimi": 0, "sayfa": 0, "not": str(e)[:80]})
            continue
        if len(metin.strip()) < MIN_KARAKTER_SAYFA * max(sayfa, 1) * 0.5:
            karar, yanma, yercekimi = "taranmis", 0, 0     # yazı yok, OCR'dan sonra bakılacak
        else:
            yanma, yercekimi, gecti = anahtar_skor(kaynakcayi_at(metin))
            karar = "gecti" if gecti else "elendi"
        satirlar.append({"makale_id": pdf.stem, "karar": karar, "yanma": yanma,
                         "yercekimi": yercekimi, "sayfa": sayfa, "not": ""})
        if i % 200 == 0 or i == len(pdfler):
            print(f"  {i}/{len(pdfler)}", flush=True)

    satirlar.sort(key=lambda r: (r["karar"] != "gecti", -r["yercekimi"], -r["yanma"]))
    csv_yaz(SECIM_CSV, satirlar)
    say = {}
    for r in satirlar:
        say[r["karar"]] = say.get(r["karar"], 0) + 1
    print("\nSonuç:", ", ".join(f"{k}: {v}" for k, v in say.items()))
    print(f"'{SECIM_CSV.name}' dosyasına bak. Sonra: python veri_cikar.py --limit 3")


def secim_oku():
    """secim.csv varsa, işlenecek makaleleri en alakalıdan başlayarak sıralı döndürür."""
    if not SECIM_CSV.exists():
        return None
    with open(SECIM_CSV, encoding="utf-8-sig", newline="") as f:
        return [r["makale_id"].lower() for r in csv.DictReader(f)
                if r["karar"] in ("gecti", "taranmis")]


def secili_liste():
    """Arkadaşının listesindeki DOI'leri, PDF dosya adı biçimine çevirir."""
    yol = Path(SECILI_CSV)
    if not yol.exists():
        sys.exit(f"Seçili liste bulunamadı: {yol}")
    with open(yol, encoding="utf-8-sig", newline="") as f:
        okuyucu = csv.DictReader(f)
        sutun = SECILI_SUTUN if SECILI_SUTUN in (okuyucu.fieldnames or []) else okuyucu.fieldnames[0]
        degerler = [(r.get(sutun) or "").strip() for r in okuyucu]
    adlar = set()
    for d in degerler:
        if not d:
            continue
        d = d.split("doi.org/")[-1]
        adlar.add(d.lower())
        adlar.add(re.sub(r"[^\w\.\-]", "_", d).lower())   # 10.1001/jama -> 10.1001_jama
    return adlar, sum(1 for d in degerler if d)


# ------------------------------------------------------------------ bekçi
def _isci(pdf, kuyruk):
    """Makaleyi ayrı bir süreçte işler; sonucu kuyruğa koyar."""
    try:
        kuyruk.put(("tamam", makale_isle(pdf, pdf.stem)))
    except Exception as e:
        kuyruk.put(("hata", f"{type(e).__name__}: {e}"))


def sureli_isle(pdf):
    """Makaleyi en fazla MAKALE_SURESI kadar işler. Takılırsa süreci öldürür.
    (durum, sonuç_ya_da_hata) döndürür; durum: tamam / hata / zaman_asimi"""
    kuyruk = multiprocessing.Queue()
    surec = multiprocessing.Process(target=_isci, args=(pdf, kuyruk), daemon=True)
    surec.start()
    try:
        durum, veri = kuyruk.get(timeout=MAKALE_SURESI)
    except queue.Empty:
        surec.terminate()
        surec.join(10)
        if surec.is_alive():
            surec.kill()
        return "zaman_asimi", f"{MAKALE_SURESI // 60} dakikada bitmedi"
    surec.join(10)
    return durum, veri


def ollama_saglikli():
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=15):
            return True
    except Exception:
        return False


def atlandi_kaydi(pdf, neden):
    """Takılan makale için boş bir sonuç yazar; bir dahaki sefere atlanır."""
    return {"makale_id": pdf.stem, "dosya": str(pdf), "kaynak": kaynak_bul(pdf),
            "model": MODEL, "surum": SURUM, "sayfa_sayisi": 0, "ocr_sayfalar": [],
            "ocr_dusuk_guven": [], "ocr_atlanan": [], "turler": ["zaman_asimi"],
            "tur_gerekce": neden, "deneyler": [], "tablo_grafik": [],
            "derleme_tablolar": [], "formuller": [], "hatalar": [neden]}


# ------------------------------------------------------------------ ana
def bitti_mi(pdf):
    """Makalenin sonucu kaydedilmiş ve sağlam mı? OCR atlanmışsa ve artık
    Tesseract varsa 'bitmedi' sayılır, tekrar işlenir."""
    js = CIKTI_KLASORU / f"{pdf.stem}.json"
    if not js.exists():
        return False
    try:
        r = json.loads(js.read_text(encoding="utf-8"))
    except Exception:
        return False
    return not (r.get("ocr_atlanan") and TESSERACT)


def sure_yaz(sn):
    sn = int(sn)
    if sn < 3600:
        return f"{sn // 60} dk"
    if sn < 86400:
        return f"{sn // 3600} sa {sn % 3600 // 60} dk"
    return f"{sn // 86400} gün {sn % 86400 // 3600} sa"


def main():
    p = argparse.ArgumentParser(description="Makalelerden veri çıkarma")
    p.add_argument("--limit", type=int, help="sadece ilk N makale")
    p.add_argument("--birlestir", action="store_true", help="json'ları CSV'lere birleştir")
    p.add_argument("--sec", action="store_true", help="hızlı anahtar kelime seçimi -> secim.csv")
    p.add_argument("--saat", type=float, help="en fazla kaç saat çalışsın (dolunca durur)")
    p.add_argument("--sonra-birlestir", action="store_true", help="bitince CSV'leri de oluştur")
    arg = p.parse_args()

    if not PDF_KLASORU.exists():
        sys.exit(f"PDF klasörü bulunamadı: {PDF_KLASORU}\n"
                 f"Kodun başındaki ANA_KLASOR ayarını kendi klasörünle değiştir.")
    METIN_KLASORU.mkdir(exist_ok=True)
    CIKTI_KLASORU.mkdir(exist_ok=True)

    if arg.birlestir:
        birlestir()
        return

    if arg.sec:
        pdfler = sorted(PDF_KLASORU.rglob("*.pdf"))
        print(f"{len(pdfler)} PDF taranıyor (OCR ve Gemma yok, hızlı)...")
        secim_yap(pdfler)
        return

    ollama_kontrol()
    if not TESSERACT:
        print("UYARI: Tesseract bulunamadı. Taranmış sayfalar atlanacak; Tesseract "
              "kurulunca o makaleler otomatik tekrar işlenir.\n")

    pdfler = sorted(PDF_KLASORU.rglob("*.pdf"))
    if SECILI_CSV:
        secili, adet = secili_liste()
        once = len(pdfler)
        pdfler = [p for p in pdfler if p.stem.lower() in secili]
        print(f"Seçili listede {adet} makale var; klasördeki {once} PDF'ten "
              f"{len(pdfler)} tanesi eşleşti.")
    secim = secim_oku()
    if secim is not None:
        once = len(pdfler)
        sira = {ad: i for i, ad in enumerate(secim)}   # secim.csv sırası: en alakalı önce
        pdfler = sorted((p for p in pdfler if p.stem.lower() in sira),
                        key=lambda p: sira[p.stem.lower()])
        print(f"secim.csv kullanılıyor: {once} PDF'ten {len(pdfler)} tanesi işlenecek "
              f"(gecti + taranmis).")
    bekleyen = [p for p in pdfler if not bitti_mi(p)]
    if arg.limit:
        bekleyen = bekleyen[:arg.limit]
    print(f"Toplam {len(pdfler)} PDF, işlenecek {len(bekleyen)}. Model: {MODEL} "
          f"(ctx {NUM_CTX})\n")

    sureler, genel_baslangic = [], time.time()
    for i, pdf in enumerate(bekleyen, 1):
        if arg.saat and time.time() - genel_baslangic > arg.saat * 3600:
            print(f"\n{arg.saat} saatlik süre doldu, duruluyor. Tekrar çalıştırınca kaldığı yerden devam eder.")
            break
        baslangic = time.time()
        print(f"[{i}/{len(bekleyen)}] {pdf.name}", flush=True)
        durum, sonuc = sureli_isle(pdf)
        if durum != "tamam":
            print(f"   {'ZAMAN AŞIMI' if durum == 'zaman_asimi' else 'HATA'}: {sonuc}")
            with open(ANA_KLASOR / "hatalar.txt", "a", encoding="utf-8") as f:
                f.write(f"{pdf}\t{durum}\t{sonuc}\n")
            if not ollama_saglikli():
                print("\nOllama cevap vermiyor; kredi boşa gitmesin diye duruluyor.\n"
                      "Colab'da 5. hücreyi (Ollama) tekrar çalıştır, sonra 8'i başlat.")
                break
            if durum == "zaman_asimi":
                # takılan makaleyi bir dahaki sefere tekrar deneme
                guvenli_yaz(CIKTI_KLASORU / f"{pdf.stem}.json",
                            json.dumps(atlandi_kaydi(pdf, sonuc), ensure_ascii=False, indent=1))
            continue
        guvenli_yaz(CIKTI_KLASORU / f"{pdf.stem}.json",
                    json.dumps(sonuc, ensure_ascii=False, indent=1))

        gecen = time.time() - baslangic
        sureler = (sureler + [gecen])[-SAYAC_ADIMI:]
        kalan = sum(sureler) / len(sureler) * (len(bekleyen) - i)
        d = sonuc["deneyler"]
        print(f"   tür: {', '.join(sonuc['turler']) or '-'} | deney satırı: {len(d)} "
              f"(şüpheli {sum(x['supheli'] == 'evet' for x in d)}, "
              f"sonucu olan {sum(x['sonuc_var'] == 'evet' for x in d)}) | "
              f"tablo/grafik: {len(sonuc['tablo_grafik'])} | formül: {len(sonuc['formuller'])} | "
              f"OCR sayfa: {len(sonuc['ocr_sayfalar'])} | {gecen:.0f} sn | "
              f"kalan ~{sure_yaz(kalan)}", flush=True)

    if arg.sonra_birlestir:
        print()
        birlestir()
    else:
        print("\nBitti. CSV'leri oluşturmak için: python veri_cikar.py --birlestir")


if __name__ == "__main__":
    main()
