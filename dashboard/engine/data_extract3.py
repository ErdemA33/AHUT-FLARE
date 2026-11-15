#!/usr/bin/env python3
"""
data_extract3.py  —  makalelerden "YANDI / SÖNDÜ" verisi çıkarır (sürüm 3)

Neden yeni sürüm?
  Eski sürüm 30 alan soruyordu; Gemma sönme sınırının yarısında ortamdaki oksijeni yazmıştı.
  Bu sürüm sadece risk modelinin ihtiyacını sorar:
    1) TESTLER  : her test koşulu (oksijen, basınç, g, gaz, akış, malzeme) -> yandı / söndü / ateşlenmedi
    2) SINIRLAR : makalede açıkça yazan "en düşük oksijen" (LOI, MOC, sönme sınırı)

Her makale için:
  1. Metin (metinler/ klasöründeki eski kayıttan; yoksa PDF'ten / OCR)
  2. PDF'teki TABLOLAR ayrıca okunur ve sayfasının altına eklenir
  3. Sonuç içeren parçalar seçilir -> Gemma: testler + sınırlar
  4. Kod kontrolü: kanıt cümlesi metinde var mı, sayılar sayfada geçiyor mu,
     sınırın kanıtında "limit/LOI/extinction..." kelimesi ve sınır sayısı var mı
  5. Gemma ikinci tur: "bu satırı metin gerçekten söylüyor mu?" -> hayır denenler atılır
  6. ciktilar3/<makale_id>.json

Kullanım:
  python data_extract3.py --altin        # önce: doğru cevabını bildiğimiz makalelerde test + puan
  python data_extract3.py --limit 5      # ilk 5 makale (deneme)
  python data_extract3.py --saat 10      # en fazla 10 saat çalış (kaldığı yerden devam eder)
  python data_extract3.py --birlestir    # json'lar -> labeled_gemma3.csv (risk_model.py okur)

Model:
  - EVREN (önerilen, GPU gerekmez, kendi bilgisayarında çalışır):
      evren_anahtar.txt dosyasına API anahtarını yapıştır, aşağıdaki API_URL'yi doldur
      (ya da: set API_URL=https://.../v1). MODEL: gemma-4-31b ya da glm-5.3
  - Ollama (Colab): API_URL boş bırak.

Gerekenler: data_extract.py ve clean.py aynı klasörde; pip install pymupdf pytesseract pillow pandas
"""

import argparse
import json
import math
import multiprocessing
import os
import queue
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

import data_extract as vc
from clean import malzeme_sade, YAKIT_TURU

fitz = vc.fitz

# ============================== AYARLAR ==============================
ANA_KLASOR = vc.ANA_KLASOR
PDF_KLASORU = vc.PDF_KLASORU
METIN_KLASORU = vc.METIN_KLASORU
CIKTI_KLASORU = ANA_KLASOR / "ciktilar3"
SINIFLANDIRMA = ANA_KLASOR / "classification.csv"   # eski çalışmanın türleri (tekrar sormayalım)
ISLENECEK_TURLER = ("deney", "derleme")             # simülasyon/teori/alakasız makaleler atlanır
ALTIN_DOSYA = ANA_KLASOR / "psi_labeled_flex2.csv" # elle çıkarılmış doğru cevaplar

# --- EVREN (ya da OpenAI uyumlu başka bir API) ---
# API_URL boşsa Ollama kullanılır. EVREN için: API_URL = "https://<evren adresi>/v1"
API_URL = os.environ.get("API_URL", "").rstrip("/")   # "evren" yazılırsa adres otomatik bulunur
EVREN_ADAYLARI = ["https://evren-llmapi.ssyz.org.tr/v1", "https://evren.ssyz.org.tr/v1", "https://api.evren.ssyz.org.tr/v1",
                  "https://evren.ssyz.org.tr/api/v1", "https://evren.ssyz.org.tr/llm/v1",
                  "https://llm.evren.ssyz.org.tr/v1"]
ANAHTAR_DOSYASI = ANA_KLASOR / "evren_anahtar.txt"     # API anahtarını bu dosyaya yapıştır (kimseyle paylaşma)
API_ANAHTAR = os.environ.get("API_ANAHTAR") or (
    ANAHTAR_DOSYASI.read_text(encoding="utf-8-sig").strip().strip('"').strip()
    if ANAHTAR_DOSYASI.exists() else "")
PARALEL = int(os.environ.get("PARALEL", 4 if API_URL else 1))   # aynı anda kaç makale
PARCA_PARALEL = int(os.environ.get("PARCA_PARALEL", 1))   # EVREN: hesap başına en fazla 4 eşzamanlı istek (4 makale x 1 parça)   # bir makalenin kaç parçası aynı anda

MODEL = os.environ.get("MODEL", "gemma-4-31b" if API_URL else vc.MODEL)
OLLAMA_URL = vc.OLLAMA_URL
NUM_CTX = vc.NUM_CTX
NUM_PREDICT = 4000             # Ollama
API_MAKS_TOKEN = 12000         # EVREN: modeller önce "düşünüyor" (reasoning), cevaba yer kalsın
MAKS_KARAKTER = 12000          # Gemma'ya bir seferde verilen metin
MAKS_PARCA = int(os.environ.get("MAKS_PARCA", 4 if os.environ.get("API_URL") else 6))   # makale başına en fazla parça
MAKS_TEST = 30                 # bir parçadan en fazla kaç test
MAKS_TABLO_SAYFA = 40          # tablo aranacak en fazla sayfa
CEVAP_SURESI = 300
MAKALE_SURESI = (45 if os.environ.get("API_URL") else 25) * 60   # EVREN modelleri düşünerek cevaplıyor, yavaş
DOGRULA = os.environ.get("DOGRULA", "1") == "1"   # ikinci tur Gemma kontrolü (yavaşlatır, temizler)

O2_HAVA = 20.95
SINIR_PAYLARI = (1.0, 3.0)     # sınırın bu kadar üstü "yanar", altı "söner" (risk_model ile aynı)
SINIR_ARALIGI = (5, 50)
SURUM = 3

SINIR_KELIMESI = re.compile(
    r"limit|\bloi\b|\bmoc\b|oxygen index|minimum oxygen|lowest oxygen|critical oxygen|"
    r"extinction|extinguish|flammab|threshold|below which|cannot (be )?sustain|"
    r"could not (be )?(sustain|ignit)|quench|blow-?off|boundary", re.IGNORECASE)

SONUC_IPUCU = re.compile(
    r"extinc|extinguish|ignit|flammab|limit|\bloi\b|\bmoc\b|oxygen index|did not|failed|"
    r"self-sustain|sustained|blow-?off|quench|burn(ed|t)? out|spread rate|spread velocity|"
    r"no flame|went out|=== TABLE", re.IGNORECASE)

SEYRELTICI = {"air": "n2", "nitrogen": "n2", "n2": "n2", "helium": "he", "he": "he",
              "argon": "ar", "ar": "ar", "carbon dioxide": "co2", "co2": "co2",
              "xenon": "xe", "xe": "xe", "sf6": "sf6", "krypton": "kr"}


# ============================== GEMMA ==============================
SISTEM = (
    "You extract experimental results from combustion papers for a spacecraft fire-safety "
    "database. Only report what is explicitly stated in the given text or tables. Never guess. "
    "Copy numbers and units exactly as written; never convert units. "
    "Evidence must be copied word for word from the text (for a table: copy the table row). "
    "Page numbers come from the '=== PAGE n ===' markers."
)

SAYI = {"type": ["number", "null"]}
YAZI = {"type": ["string", "null"]}
DEGER = {"type": "object", "properties": {"value": SAYI, "unit": YAZI}, "required": ["value", "unit"]}
PLATFORM = {"type": ["string", "null"], "enum": [
    "drop_tower", "parabolic", "ISS", "sounding_rocket", "space_shuttle", "centrifuge",
    "normal_g", "other", None]}
NUMUNE = {"type": ["string", "null"], "enum": [
    "thin_sheet", "thick_sheet", "rod", "droplet", "gas_jet", "wire", "fabric", "pool",
    "particle_cloud", "other", None]}
AKIS_YONU = {"type": ["string", "null"], "enum": ["concurrent", "opposed", "none", None]}
KAYNAK = {"type": "string", "enum": ["experiment", "simulation", "cited"]}

ORTAK = {
    "material": YAZI, "sample_type": NUMUNE, "thickness": DEGER,
    "pressure": DEGER, "g_level": DEGER, "platform": PLATFORM,
    "gravity": {"type": "string", "enum": ["microgravity", "normal_gravity", "partial_gravity", "unknown"]},
    "diluent": YAZI, "flow_velocity": DEGER, "flow_direction": AKIS_YONU,
    "source": KAYNAK, "evidence": {"type": "string"}, "page": {"type": ["integer", "null"]},
}
SEMA = {
    "type": "object",
    "properties": {
        "tests": {"type": "array", "items": {
            "type": "object",
            "properties": {**ORTAK,
                           "oxygen": DEGER,
                           "base_gas": {"type": ["string", "null"],
                                        "enum": ["air", "oxygen_inert", "other", None]},
                           "diluent_fraction": DEGER,
                           "outcome": {"type": "string", "enum": [
                               "sustained", "not_sustained", "no_ignition", "unclear"]},
                           "spread_rate": DEGER},
            "required": list(ORTAK) + ["oxygen", "base_gas", "diluent_fraction", "outcome",
                                       "spread_rate"],
        }},
        "limits": {"type": "array", "items": {
            "type": "object",
            "properties": {**ORTAK, "minimum_oxygen": DEGER},
            "required": list(ORTAK) + ["minimum_oxygen"],
        }},
    },
    "required": ["tests", "limits"],
}

SORU = """TEXT:
{metin}

=== TASK ===
From the text above (part of a combustion paper), extract (A) TESTS with their outcome and
(B) stated oxygen LIMITS.

(A) tests: one item per test condition whose OUTCOME is stated (a table row is usually one test).
  - oxygen = the AMBIENT oxygen of THAT test, as written. Never put a limit value here.
  - If the gas is air diluted with an added gas (e.g. "Xd = 0.3 of CO2 added to air"):
    base_gas = "air", diluent = that gas, diluent_fraction = the added fraction, oxygen = null
    unless the oxygen is written. Plain air: base_gas = "air", oxygen = null if not written.
  - outcome:
      "sustained"      = flame kept burning / spread / droplet burned (also if it went out only
                         late, e.g. near burnout or after a long burn)
      "not_sustained"  = ignited but the flame could not sustain itself and went out soon
                         (e.g. went out right after the igniter was removed, flame retreated)
      "no_ignition"    = the sample could not be ignited
      "unclear"        = outcome not stated
    A vaporization / gasification rate alone does NOT mean the droplet burned; use it as
    "sustained" only if the text says the droplet was burning in that test.
  - spread_rate: the flame spread rate if stated.
(B) limits: ONLY when the text explicitly states a minimum / limiting oxygen concentration
  (LOI, MOC, oxygen index, extinction limit, flammability limit). minimum_oxygen = that value.
  The evidence MUST be the sentence or table row that states the limit.

Common rules:
  - Copy numbers and units exactly. If not stated: {{"value": null, "unit": null}}.
  - g_level only if gravity is written as a number; otherwise null (platform is enough).
    platform: "normal_g" for ordinary laboratory (1 g) tests; for reduced-gravity tests the
    facility used in the paper (drop_tower, parabolic, ISS ...).
  - gravity: the gravity condition of THIS test: "microgravity" (drop tower, ISS, parabolic
    flight, sounding rocket, "reduced gravity", "µg", "0g"), "normal_gravity" (1 g, laboratory),
    "partial_gravity" (Moon, Mars, centrifuge, partial-g parabola), or "unknown".
  - Many tables have SEPARATE columns for microgravity and normal gravity (e.g. "Case 1 µg" vs
    "Case 1 1-g"). Give each column its own platform. In extracted text "µg" often appears as
    "mg", "lg" or "ug" - these mean microgravity, not milligrams.
  - source: "experiment" = this paper's own tests; "simulation" = this paper's own model;
    "cited" = results of other studies.
  - At most {maks} tests. If nothing, return empty lists."""

SEMA_KONTROL = {
    "type": "object",
    "properties": {"checks": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "integer"}, "supported": {"type": "boolean"}},
        "required": ["id", "supported"]}}},
    "required": ["checks"],
}

SORU_KONTROL = """TEXT:
{metin}

=== TASK ===
Above is a text from a combustion paper. Below are claims extracted from it.
For each claim decide if it is consistent with the text.

supported = true when the numbers in the claim belong to that test in the text and the outcome
agrees with the text. Outcomes can be implicit: a measured burning rate, flame spread rate,
flame size or burn time means the flame was sustained (but a vaporization / gasification rate
without a flame does not). Values stated once for all tests
(e.g. "oxygen fixed at 21%", "all tests at 1 atm") apply to every test.

supported = false only when a number in the claim is NOT given for that test in the text,
the outcome contradicts the text, or the claim mixes up values (e.g. the ambient oxygen
given as a minimum oxygen limit).

CLAIMS:
{iddialar}"""

DUSUNME_KAPALI = True


JSON_SEMA_DESTEK = True


def json_ayikla(metin):
    metin = re.sub(r"^```(json)?|```$", "", (metin or "").strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(metin)
    except json.JSONDecodeError:
        bas, son = metin.find("{"), metin.rfind("}")
        return json.loads(metin[bas:son + 1])


AKIS = os.environ.get("AKIS", "1") == "1"   # cevabı parça parça al: uzun düşünmede bağlantı kopmaz
AKIS_BEKLEME = 180                          # akışta bu kadar saniye hiç veri gelmezse kopmuş say
AKIS_TOPLAM = 20 * 60                       # bir cevap en fazla bu kadar sürebilir


TOKEN = {"girdi": 0, "onbellek": 0, "cikti": 0, "istek": 0}
TOKEN_KILIT = threading.Lock()
KULLANIM_ISTE = True          # akışın sonunda token kullanımını da iste
DUSUNME_EK = json.loads(os.environ.get("DUSUNME_EK", "{}"))   # düşünmeyi kapatan ek ayar (api_kontrol bulur)


def token_say(kullanim):
    if not kullanim:
        return
    with TOKEN_KILIT:
        TOKEN["istek"] += 1
        TOKEN["girdi"] += kullanim.get("prompt_tokens") or 0
        TOKEN["cikti"] += kullanim.get("completion_tokens") or 0
        TOKEN["onbellek"] += ((kullanim.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)


def akisi_oku(c):
    """Server-sent events (data: {...}) satırlarından cevap metnini toplar."""
    parcalar, bitis, bas = [], None, time.time()
    for satir in c:
        if time.time() - bas > AKIS_TOPLAM:
            raise TimeoutError(f"cevap {AKIS_TOPLAM // 60} dakikada bitmedi")
        satir = satir.decode("utf-8", "replace").strip()
        if not satir.startswith("data:"):
            continue
        veri = satir[5:].strip()
        if veri == "[DONE]":
            break
        try:
            olay = json.loads(veri)
        except json.JSONDecodeError:
            continue
        if olay.get("error"):
            raise RuntimeError(f"akış hatası: {str(olay['error'])[:200]}")
        token_say(olay.get("usage"))
        for secim in olay.get("choices") or []:
            parca = (secim.get("delta") or secim.get("message") or {}).get("content")
            if parca:
                parcalar.append(parca)
            bitis = secim.get("finish_reason") or bitis
    return "".join(parcalar), bitis


def api_sor(soru, sema):
    """OpenAI uyumlu /chat/completions (EVREN). Yoğunlukta (429/5xx) bekleyip tekrar dener."""
    global JSON_SEMA_DESTEK, KULLANIM_ISTE
    son_hata = None
    for deneme in range(6):
        icerik = soru if JSON_SEMA_DESTEK else (
            soru + "\n\nReturn ONLY a JSON object that matches this JSON schema:\n" + json.dumps(sema))
        govde = {"model": MODEL, "temperature": 0 if deneme < 3 else 0.3, "max_tokens": API_MAKS_TOKEN,
                 "stream": AKIS, **DUSUNME_EK,
                 **({"stream_options": {"include_usage": True}} if AKIS and KULLANIM_ISTE else {}),
                 "messages": [{"role": "system", "content": SISTEM}, {"role": "user", "content": icerik}],
                 "response_format": ({"type": "json_schema", "json_schema": {"name": "cevap", "schema": sema}}
                                     if JSON_SEMA_DESTEK else {"type": "json_object"})}
        try:
            istek = urllib.request.Request(f"{API_URL}/chat/completions", data=json.dumps(govde).encode(),
                                           headers={"Content-Type": "application/json", **api_basliklari()})
            with urllib.request.urlopen(istek, timeout=AKIS_BEKLEME if AKIS else CEVAP_SURESI) as c:
                if AKIS:
                    icerik, bitis = akisi_oku(c)
                else:
                    yanit = json.loads(c.read())
                    token_say(yanit.get("usage"))
                    secim = yanit["choices"][0]
                    icerik, bitis = (secim.get("message") or {}).get("content") or "", secim.get("finish_reason")
            if not icerik.strip():
                raise ValueError(f"boş cevap (finish_reason={bitis})")
            return json_ayikla(icerik)
        except urllib.error.HTTPError as e:
            mesaj = e.read().decode("utf-8", "replace")
            son_hata = f"HTTP {e.code}: {mesaj[:300]}"
            if "terms_not_accepted" in mesaj:
                raise RuntimeError("EVREN kullanım şartları onaylanmamış: EVREN sitesinde Test Alanı'ndaki "
                                   "anahtar kutusundan şartları onayla, sonra tekrar çalıştır.")
            if e.code in (401, 403):
                raise RuntimeError(f"API anahtarı reddedildi: {son_hata}")
            if e.code in (400, 422) and KULLANIM_ISTE and "stream_options" in mesaj:
                KULLANIM_ISTE = False
                continue
            if re.search(r"quota|kota", mesaj, re.I) and re.search(r"daily|günlük|day", mesaj, re.I):
                raise RuntimeError(f"GÜNLÜK KOTA DOLDU: {mesaj[:200]}")
            if e.code in (400, 422) and JSON_SEMA_DESTEK and re.search(r"response_format|schema", mesaj, re.I):
                JSON_SEMA_DESTEK = False            # şema desteklenmiyorsa şemayı soruya yazarak sor
                continue
            if e.code in (408, 429, 500, 502, 503, 504):
                bekle = min(90, 5 * 2 ** deneme)
                print(f"   (EVREN HTTP {e.code}, {bekle} sn bekleyip tekrar deniyor: {mesaj[:120]})", flush=True)
                time.sleep(bekle)
                continue
            time.sleep(2)
        except Exception as e:
            son_hata = e
            print(f"   (EVREN bağlantı sorunu, tekrar deniyor: {type(e).__name__}: {str(e)[:120]})", flush=True)
            time.sleep(3)
    raise RuntimeError(f"API cevap vermedi / bozuk JSON: {son_hata}")


def api_basliklari():
    # EVREN anahtarı X-API-Key başlığıyla ister; başka OpenAI uyumlu servisler için Bearer de eklenir
    return {"X-API-Key": API_ANAHTAR, "Authorization": f"Bearer {API_ANAHTAR}"}


def adres_bul():
    """API_URL 'evren' ise olası adresleri dener; JSON cevap veren ilk adresi seçer."""
    global API_URL
    deneme = json.dumps({"model": MODEL, "max_tokens": 5, "stream": False,
                         "messages": [{"role": "user", "content": "hi"}]}).encode()
    for aday in EVREN_ADAYLARI:
        try:
            istek = urllib.request.Request(f"{aday}/chat/completions", data=deneme,
                                           headers={"Content-Type": "application/json", **api_basliklari()})
            with urllib.request.urlopen(istek, timeout=60) as c:
                json.loads(c.read())["choices"]
        except urllib.error.HTTPError as e:
            govde = e.read().decode("utf-8", "replace")
            print(f"  {aday}: HTTP {e.code} {govde[:200]}")
            if govde.strip().startswith("{"):       # JSON hata = doğru adres, sorun başka yerde
                API_URL = aday
                return
            continue
        except Exception as e:
            print(f"  {aday}: {type(e).__name__}: {e}")
            continue
        API_URL = aday
        return
    sys.exit("EVREN API adresi bulunamadı. Kod örneklerindeki adresi API_URL olarak ver:\n"
             '  $env:API_URL="https://.../v1"')


DUSUNME_ADAYLARI = [{"reasoning_effort": "none"}, {"chat_template_kwargs": {"enable_thinking": False}},
                    {"reasoning": {"enabled": False}}, {"think": False}]


def dusunme_olc(ek):
    """Küçük bir soru sorar; (çalıştı_mı, düşünme_uzunluğu, çıktı_token) döndürür."""
    govde = {"model": MODEL, "max_tokens": 400, "stream": False, "temperature": 0, **ek,
             "messages": [{"role": "user", "content": "What is 17 + 25? Answer with the number only."}]}
    istek = urllib.request.Request(f"{API_URL}/chat/completions", data=json.dumps(govde).encode(),
                                   headers={"Content-Type": "application/json", **api_basliklari()})
    try:
        with urllib.request.urlopen(istek, timeout=180) as c:
            y = json.loads(c.read())
    except Exception:
        return False, None, None
    m = y["choices"][0].get("message") or {}
    dusunce = m.get("reasoning") or m.get("reasoning_content") or ""
    return bool(m.get("content")), len(dusunce), (y.get("usage") or {}).get("completion_tokens")


def dusunmeyi_kapat():
    global DUSUNME_EK
    if os.environ.get("DUSUNME", "kapali") != "kapali":
        print("Düşünme açık bırakıldı (DUSUNME ayarı).")
        return
    _, temel, temel_tok = dusunme_olc({})
    print(f"Düşünme ölçümü: normal cevapta {temel} karakter düşünme, {temel_tok} çıktı token")
    if not temel:
        return
    for ek in DUSUNME_ADAYLARI:
        tamam, uzunluk, tok = dusunme_olc(ek)
        if tamam and uzunluk is not None and uzunluk < temel * 0.2:
            DUSUNME_EK = ek
            os.environ["DUSUNME_EK"] = json.dumps(ek)      # paralel süreçler de kullansın
            print(f"Düşünme KAPATILDI: {ek} -> {uzunluk} karakter, {tok} çıktı token")
            return
    print("Düşünmeyi kapatan bir ayar bulunamadı; açık devam ediliyor.")


def api_kontrol():
    if not API_ANAHTAR:
        sys.exit(f"API anahtarı yok. Anahtarı {ANAHTAR_DOSYASI} dosyasına yapıştır.")
    if API_URL.lower() == "evren":
        adres_bul()
        os.environ["API_URL"] = API_URL          # paralel süreçler de bu adresi kullansın
        print(f"API adresi: {API_URL}")
    try:
        istek = urllib.request.Request(f"{API_URL}/models", headers=api_basliklari())
        with urllib.request.urlopen(istek, timeout=30) as c:
            modeller = [m.get("id") for m in json.loads(c.read()).get("data", [])]
        print(f"API bağlantısı tamam. Modeller: {', '.join(map(str, modeller))}")
        if modeller and MODEL not in modeller:
            print(f"UYARI: '{MODEL}' listede görünmüyor; yine de denenecek.")
    except Exception as e:
        print(f"UYARI: model listesi alınamadı ({e}); yine de denenecek.")
    try:
        api_sor('Return {"ok": true}', {"type": "object", "properties": {"ok": {"type": "boolean"}},
                                        "required": ["ok"]})
        print(f"'{MODEL}' cevap veriyor. JSON şeması desteği: {'var' if JSON_SEMA_DESTEK else 'yok (yedek yol)'}")
    except Exception as e:
        sys.exit(f"'{MODEL}' cevap vermedi: {e}")
    dusunmeyi_kapat()
    print()


def gemma(soru, sema):
    global DUSUNME_KAPALI
    if API_URL:
        return api_sor(soru, sema)
    son_hata = None
    for sicaklik in (0, 0.3):
        veri = {"model": MODEL, "stream": False, "format": sema,
                "options": {"temperature": sicaklik, "num_ctx": NUM_CTX, "num_predict": NUM_PREDICT},
                "messages": [{"role": "system", "content": SISTEM},
                             {"role": "user", "content": soru}]}
        if DUSUNME_KAPALI:
            veri["think"] = False
        try:
            istek = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=json.dumps(veri).encode(),
                                           headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(istek, timeout=CEVAP_SURESI) as c:
                return json.loads(json.loads(c.read())["message"]["content"])
        except urllib.error.HTTPError as e:
            mesaj = e.read().decode("utf-8", "replace")
            if DUSUNME_KAPALI and "think" in mesaj.lower():
                DUSUNME_KAPALI = False
                return gemma(soru, sema)
            son_hata = f"HTTP {e.code}: {mesaj[:200]}"
        except Exception as e:
            son_hata = e
        time.sleep(2)
    raise RuntimeError(f"Gemma cevap vermedi / bozuk JSON: {son_hata}")


# ============================== METİN + TABLO ==============================
def tablolari_al(pdf, makale_id, bilgi):
    """PDF'teki tabloları markdown olarak çıkarır (bir kez; sonra kayıttan okur)."""
    kayit = METIN_KLASORU / f"{makale_id}.tablolar.json"
    if kayit.exists():
        try:
            return json.loads(kayit.read_text(encoding="utf-8"))
        except Exception:
            pass
    tablolar = []
    ocr = set(bilgi.get("ocr_sayfalar", []))
    try:
        with fitz.open(pdf) as doc:
            for no, sayfa in enumerate(doc, 1):
                if no > MAKS_TABLO_SAYFA:
                    break
                if no in ocr:                      # taranmış sayfada tablo bulunamaz
                    continue
                try:
                    bulunan = sayfa.find_tables().tables
                except Exception:
                    continue
                for t in bulunan:
                    try:
                        md = t.to_markdown(clean=False)
                    except Exception:
                        continue
                    bas = md.split("\n", 1)[0].lower()
                    if "nomenclature" in bas or "symbol" in bas:
                        continue
                    if md.count("\n") >= 3 and len(md) < 8000 and re.search(r"\d", md):
                        tablolar.append({"sayfa": no, "md": md})
    except Exception:
        pass
    vc.guvenli_yaz(kayit, json.dumps(tablolar, ensure_ascii=False))
    return tablolar


def tablolari_ekle(metin, tablolar):
    """Her tabloyu kendi sayfasının sonuna ekler (kanıt kontrolü de tabloyu görsün)."""
    if not tablolar:
        return metin
    sayfalar = re.split(r"(?=\n=== PAGE \d+ ===\n)", metin)
    for t in tablolar:
        for i, s in enumerate(sayfalar):
            if s.startswith(f"\n=== PAGE {t['sayfa']} ===\n"):
                sayfalar[i] = s + f"\n=== TABLE (page {t['sayfa']}) ===\n{t['md']}\n"
                break
    return "".join(sayfalar)


def parcala(metin):
    sayfalar = re.split(r"(?=\n=== PAGE \d+ ===\n)", metin)
    parcalar, simdiki = [], ""
    for s in sayfalar:
        while len(s) > MAKS_KARAKTER:
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
    puan = [len(SONUC_IPUCU.findall(p)) for p in parcalar]
    secilen = [i for i in sorted(range(len(parcalar)), key=lambda i: -puan[i])[:MAKS_PARCA]
               if puan[i] > 0]
    return [parcalar[i] for i in sorted(secilen)]


# ============================== ÇEVİRME + KONTROL ==============================
def deger(d, cevir):
    """{'value','unit'} -> (çevrilmiş, ham_yazı). Çevrilemezse (None, ham)."""
    if not isinstance(d, dict) or d.get("value") is None:
        return None, None
    try:
        v = float(d["value"])
    except (TypeError, ValueError):
        return None, None
    ham = f"{v:g} {d.get('unit') or ''}".strip()
    try:
        c = cevir(v, d.get("unit"))
    except Exception:
        c = None
    return (None if c is None or (isinstance(c, float) and math.isnan(c)) else c), ham


def seyreltici_sade(s):
    if not isinstance(s, str):
        return None
    s = s.lower().strip()
    for ad, kod in SEYRELTICI.items():
        if re.search(rf"\b{re.escape(ad)}\b", s):
            return kod
    return s or None


def ortak_alanlar(h, belge, sorun):
    """Testlerde ve sınırlarda ortak alanları çevirir, sayıları kontrol eder."""
    sayfa = h.get("page")
    var, bulunan = belge.kanit_bul(h.get("evidence", ""))
    if var:
        sayfa = bulunan or sayfa
    else:
        sorun.append("kanıt metinde yok")
    s = {"veri_turu": {"experiment": "deney", "simulation": "simulasyon", "cited": "alinti"}
         .get(h.get("source"), "deney"),
         "platform": h.get("platform"), "malzeme": h.get("material"),
         "malzeme_sade": malzeme_sade(h.get("material")),
         "numune_tipi": h.get("sample_type"),
         "yakit_turu": YAKIT_TURU.get(h.get("sample_type")),
         "seyreltici": seyreltici_sade(h.get("diluent")),
         "akis_yonu": {"concurrent": "ayni", "opposed": "ters", "none": "yok"}.get(h.get("flow_direction")),
         "kanit": h.get("evidence", ""), "sayfa": sayfa}
    for alan, sutun, cevir in (("thickness", "kalinlik_mm", vc.tablo_cevir(vc.UZUNLUK_MM)),
                               ("pressure", "basinc_kpa", vc.basinc_cevir),
                               ("g_level", "g_seviyesi", vc.g_cevir),
                               ("flow_velocity", "akis_hizi_cm_s", vc.tablo_cevir(vc.HIZ_MM_S, 0.1))):
        c, ham = deger(h.get(alan), cevir)
        s[sutun] = c
        if ham and c is None and alan != "g_level":      # g yazılışı tuhafsa yerçekimi durumu yeter
            sorun.append(f"{alan} birimi tanınmadı ({ham})")
        if ham and c is not None and alan != "g_level" and float(h[alan]["value"]) != 0 \
                and not belge.sayi_var_mi(float(h[alan]["value"])):      # koşullar makalede bir kez yazılabilir
            sorun.append(f"{alan}={ham} sayfada yok")
    s["yercekimi_durumu"] = h.get("gravity")
    if s["g_seviyesi"] is None:            # sayı yoksa: önce testin kendi yerçekimi durumu, sonra platform
        s["g_seviyesi"] = {"microgravity": 1e-4, "normal_gravity": 1.0}.get(h.get("gravity"))
    if s["g_seviyesi"] is None:
        s["g_seviyesi"] = {**vc.PLATFORM_G, "normal_g": 1.0}.get(s["platform"])
    if s["malzeme"]:
        kel = [k for k in vc.sadelestir(s["malzeme"]).split() if len(k) >= 3]
        if kel and not any(k in belge.tum_sade for k in kel):
            sorun.append("malzeme metinde yok")
    return s


def test_satiri(h, belge):
    sorun = []
    s = ortak_alanlar(h, belge, sorun)
    s["tur"] = "test"
    o2, o2_ham = deger(h.get("oxygen"), vc.oksijen_cevir)
    xd, xd_ham = deger(h.get("diluent_fraction"), vc.oksijen_cevir)   # % ya da oran -> %
    s["oksijen_kaynagi"] = "metin"
    if o2 is None and h.get("base_gas") == "air":
        if xd is not None and 0 <= xd < 100:
            o2, s["oksijen_kaynagi"] = O2_HAVA * (1 - xd / 100), "havaya_seyreltici"
        elif xd is None:
            o2, s["oksijen_kaynagi"] = O2_HAVA, "hava"
    if o2_ham and o2 is not None and not belge.sayi_var_mi(float(h["oxygen"]["value"])):
        sorun.append(f"oksijen={o2_ham} sayfada yok")
    s["oksijen_yuzde"] = round(o2, 2) if o2 is not None else None
    s["seyreltici_yuzde"] = xd
    hiz, _ = deger(h.get("spread_rate"), vc.tablo_cevir(vc.HIZ_MM_S))
    s["alev_yayilma_hizi_mm_s"] = hiz
    sonuc = h.get("outcome")
    if sonuc == "unclear" and hiz:
        sonuc = "sustained"
    s["sonuc"] = sonuc
    s["yanar"] = {"sustained": 1, "not_sustained": 0, "no_ignition": 0}.get(sonuc)
    if s["yanar"] is None:
        sorun.append("sonuç belirsiz")
    if s["oksijen_yuzde"] is None or not (0 < s["oksijen_yuzde"] <= 100):
        sorun.append("oksijen yok")
    s["supheli"] = "evet" if sorun else "hayir"
    s["supheli_nedenleri"] = "; ".join(sorun)
    return s


def sinir_satiri(h, belge):
    sorun = []
    s = ortak_alanlar(h, belge, sorun)
    s["tur"] = "sinir"
    m, ham = deger(h.get("minimum_oxygen"), vc.oksijen_cevir)
    s["min_oksijen_yuzde"] = m
    kanit = h.get("evidence", "") or ""
    if m is None:
        sorun.append("sınır değeri yok")
    else:
        if not (SINIR_ARALIGI[0] <= m <= SINIR_ARALIGI[1]):
            sorun.append("sınır makul aralıkta değil")
        v = float(h["minimum_oxygen"]["value"])
        if not any(re.search(r"(?<![\d.])" + re.escape(b) + r"(?!\d)", kanit)
                   for b in vc.sayi_bicimleri(v)):
            sorun.append("sınır sayısı kanıt cümlesinde yok")
    if not SINIR_KELIMESI.search(kanit):
        sorun.append("kanıtta sınır kelimesi yok")
    s["supheli"] = "evet" if sorun else "hayir"
    s["supheli_nedenleri"] = "; ".join(sorun)
    return s


def iddia_yaz(i, s):
    kos = []
    if s.get("malzeme"):
        kos.append(str(s["malzeme"]))
    if s["tur"] == "test":
        if s.get("oksijen_kaynagi") == "havaya_seyreltici":
            kos.append(f"air diluted with {s['seyreltici']} (diluent fraction {s['seyreltici_yuzde'] / 100:g})")
        else:
            if s.get("oksijen_yuzde") is not None:
                kos.append(f"{s['oksijen_yuzde']:g}% O2")
            if s.get("seyreltici_yuzde") is not None:
                kos.append(f"{s['seyreltici_yuzde']:g}% {s.get('seyreltici')}")
    if s.get("basinc_kpa") is not None:
        kos.append(f"{s['basinc_kpa']:g} kPa")
    if s.get("yercekimi_durumu") in ("microgravity", "normal_gravity", "partial_gravity"):
        kos.append(s["yercekimi_durumu"].replace("_", " "))
    elif s.get("g_seviyesi") is not None:
        kos.append(f"gravity {s['g_seviyesi']:g} g")
    if s.get("akis_hizi_cm_s") is not None:
        kos.append(f"flow {s['akis_hizi_cm_s']:g} cm/s")
    if s["tur"] == "test":
        sonuc = {"sustained": "flame was sustained", "not_sustained": "flame was NOT sustained",
                 "no_ignition": "did NOT ignite"}[s["sonuc"]]
        return f"{i}. Test: {', '.join(kos)} -> {sonuc}."
    return f"{i}. Limit: {', '.join(kos)} -> minimum oxygen for burning = {s['min_oksijen_yuzde']:.3g}%."


def dogrula(satirlar, parca):
    """Gemma'ya ikinci kez sorar; desteklenmeyen satırları işaretler."""
    adaylar = [s for s in satirlar if s["supheli"] == "hayir"]
    if not adaylar:
        return
    iddialar = "\n".join(iddia_yaz(i, s) for i, s in enumerate(adaylar, 1))
    c = gemma(SORU_KONTROL.format(iddialar=iddialar, metin=parca), SEMA_KONTROL)
    cevap = {x.get("id"): x.get("supported") for x in c.get("checks", [])}
    for i, s in enumerate(adaylar, 1):
        s["dogrulandi"] = "evet" if cevap.get(i) is True else "hayir"
        if cevap.get(i) is not True:
            s["supheli"] = "evet"
            s["supheli_nedenleri"] = "ikinci kontrol: metin desteklemiyor"


def tekrarlari_sil(satirlar):
    gorulen, sonuc = set(), []
    for s in satirlar:
        k = tuple(str(s.get(a)) for a in ("tur", "malzeme_sade", "oksijen_yuzde", "min_oksijen_yuzde",
                                          "basinc_kpa", "g_seviyesi", "seyreltici", "akis_hizi_cm_s",
                                          "kalinlik_mm", "yanar"))
        if k not in gorulen:
            gorulen.add(k)
            sonuc.append(s)
    return sonuc


# ============================== MAKALE ==============================
def makale_isle(pdf, makale_id):
    TOKEN.update(girdi=0, onbellek=0, cikti=0, istek=0)
    metin, bilgi = vc.metin_al(pdf, makale_id)
    temiz = vc.kaynakcayi_at(metin)
    sonuc = {"makale_id": makale_id, "dosya": str(pdf), "kaynak": vc.kaynak_bul(pdf),
             "model": MODEL, "surum": SURUM, "tablo_sayisi": 0, "satirlar": [], "hatalar": [],
             "token": TOKEN}
    if len(temiz.strip()) < 500:
        sonuc["hatalar"].append("metin çok kısa")
        return sonuc
    tablolar = tablolari_al(pdf, makale_id, bilgi)
    sonuc["tablo_sayisi"] = len(tablolar)
    tam = tablolari_ekle(temiz, tablolar)
    belge = vc.Belge(tam, bilgi)

    parcalar = parcala(tam)
    kisa = makale_id[:28]

    def parca_isle(sira_parca):
        i, parca = sira_parca
        hatalar = []
        t0 = time.time()
        print(f"   {kisa} | parça {i}/{len(parcalar)}: Gemma okuyor...", flush=True)
        try:
            c = gemma(SORU.format(metin=parca, maks=MAKS_TEST), SEMA)
        except Exception as e:
            print(f"   {kisa} | parça {i}: HATA {str(e)[:100]}", flush=True)
            return [], [f"parça: {e}"]
        bu = [test_satiri(h, belge) for h in c.get("tests", [])[:MAKS_TEST]]
        bu += [sinir_satiri(h, belge) for h in c.get("limits", [])[:10]]
        print(f"   {kisa} | parça {i}: {len(bu)} satır çıktı ({time.time() - t0:.0f} sn)"
              + (", kontrol ediliyor..." if DOGRULA and bu else ""), flush=True)
        if DOGRULA and bu:
            t1 = time.time()
            try:
                dogrula(bu, parca)
                print(f"   {kisa} | parça {i}: kontrol bitti, {sum(x['supheli'] == 'hayir' for x in bu)} "
                      f"sağlam ({time.time() - t1:.0f} sn)", flush=True)
            except Exception as e:
                hatalar.append(f"kontrol: {e}")
        return bu, hatalar

    satirlar = []
    with ThreadPoolExecutor(PARCA_PARALEL) as havuz:
        for bu, hatalar in havuz.map(parca_isle, enumerate(parcalar, 1)):
            satirlar += bu
            sonuc["hatalar"] += hatalar

    # oksijeni yazılmamış testler: makalede tek bir ortam oksijeni varsa onu kullan
    o2ler = {round(x["oksijen_yuzde"], 1) for x in satirlar
             if x["tur"] == "test" and x.get("oksijen_yuzde") is not None and x.get("oksijen_kaynagi") == "metin"}
    if len(o2ler) == 1:
        for x in satirlar:
            if x["tur"] == "test" and x.get("oksijen_yuzde") is None:
                x["oksijen_yuzde"], x["oksijen_kaynagi"] = next(iter(o2ler)), "makaleden"
                kalan = [n for n in x["supheli_nedenleri"].split("; ") if n and n != "oksijen yok"]
                x["supheli_nedenleri"] = "; ".join(kalan)
                x["supheli"] = "evet" if kalan else "hayir"
    sonuc["satirlar"] = tekrarlari_sil(satirlar)
    return sonuc


def _isci(pdf, kuyruk):
    try:
        kuyruk.put(("tamam", makale_isle(pdf, pdf.stem)))
    except Exception as e:
        kuyruk.put(("hata", f"{type(e).__name__}: {e}"))


AKTIF_SURECLER = set()


def sureli_isle(pdf):
    kuyruk = multiprocessing.Queue()
    surec = multiprocessing.Process(target=_isci, args=(pdf, kuyruk), daemon=True)
    surec.start()
    AKTIF_SURECLER.add(surec)
    try:
        durum, veri = kuyruk.get(timeout=MAKALE_SURESI)
    except queue.Empty:
        surec.terminate()
        surec.join(10)
        if surec.is_alive():
            surec.kill()
        AKTIF_SURECLER.discard(surec)
        return "zaman_asimi", f"{MAKALE_SURESI // 60} dakikada bitmedi"
    surec.join(10)
    AKTIF_SURECLER.discard(surec)
    return durum, veri


# ============================== BİRLEŞTİR ==============================
ETIKET_SUTUNLARI = ["makale_id", "kaynak", "link", "veri_turu", "platform", "g_seviyesi",
                    "malzeme_sade", "numune_tipi", "yakit_turu", "kalinlik_mm", "oksijen_yuzde",
                    "seyreltici", "basinc_kpa", "akis_hizi_cm_s", "akis_yonu",
                    "alev_yayilma_hizi_mm_s", "yanar", "etiket_kaynagi", "kanit", "sayfa"]


def etiketli_noktalar(makale):
    """Bir makalenin sağlam satırlarını risk modelinin okuyacağı noktalara çevirir."""
    noktalar = []
    for s in makale["satirlar"]:
        if s["supheli"] != "hayir" or s["veri_turu"] == "alinti" or s.get("g_seviyesi") is None:
            continue                      # yerçekimi bilinmeyen nokta bizim için işe yaramaz
        ortak = {k: s.get(k) for k in ETIKET_SUTUNLARI}
        ortak.update(makale_id=makale["makale_id"], kaynak=makale["kaynak"],
                     link=vc.kaynak_link(makale["makale_id"], makale["kaynak"]))
        if s["tur"] == "test":
            noktalar.append({**ortak, "etiket_kaynagi": "gemma3_test"})
        else:
            for pay in SINIR_PAYLARI:
                for yon, yanar in ((+1, 1), (-1, 0)):
                    noktalar.append({**ortak, "oksijen_yuzde": round(s["min_oksijen_yuzde"] + yon * pay, 2),
                                     "yanar": yanar, "alev_yayilma_hizi_mm_s": None,
                                     "etiket_kaynagi": "gemma3_sinir"})
    return noktalar


def jsonlari_oku(adlar=None):
    for f in sorted(CIKTI_KLASORU.glob("*.json")):
        if adlar is None or f.stem in adlar:
            try:
                yield json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass


def birlestir():
    import pandas as pd
    hepsi, noktalar = [], []
    for m in jsonlari_oku():
        for s in m["satirlar"]:
            hepsi.append({"makale_id": m["makale_id"], **s})
        noktalar += etiketli_noktalar(m)
    pd.DataFrame(hepsi).to_csv(ANA_KLASOR / "raw_gemma3.csv", index=False, encoding="utf-8-sig")
    df = pd.DataFrame(noktalar, columns=ETIKET_SUTUNLARI)
    df.to_csv(ANA_KLASOR / "labeled_gemma3.csv", index=False, encoding="utf-8-sig")
    h = pd.DataFrame(hepsi)
    print(f"raw_gemma3.csv: {len(h)} satır | sağlam: {(h.supheli == 'hayir').sum() if len(h) else 0}")
    if len(h):
        print("  şüphe nedenleri:", h.supheli_nedenleri.str.split("; ").explode()
              .value_counts().head(8).to_dict())
    print(f"labeled_gemma3.csv: {len(df)} nokta, {df.makale_id.nunique()} makale "
          f"(yandı {int(df.yanar.sum())}, söndü {int((1 - df.yanar).sum())})")
    print("risk_model.py artık bu dosyayı kullanır.")


# ============================== ALTIN TEST ==============================
def altin_puan(adlar):
    """Elle çıkarılmış noktalarla karşılaştırır."""
    import pandas as pd
    altin = pd.read_csv(ALTIN_DOSYA)
    altin = altin[altin.makale_id.isin(adlar)]
    bulunan = pd.DataFrame([n for m in jsonlari_oku(adlar) for n in etiketli_noktalar(m)])
    if bulunan.empty:
        print("Hiç nokta çıkmadı.")
        return
    bulunan["seyreltici"] = bulunan.seyreltici.map(seyreltici_sade)
    eslesen = dogru = 0
    for _, a in altin.iterrows():
        b = bulunan[(bulunan.makale_id == a.makale_id)
                    & ((bulunan.g_seviyesi.fillna(1) < 0.01) == (a.g_seviyesi < 0.01))
                    & ((bulunan.oksijen_yuzde - a.oksijen_yuzde).abs() <= 1.0)]
        b = b[b.seyreltici.isna() | (b.seyreltici == a.seyreltici)]
        b = b[b.basinc_kpa.isna() | ((b.basinc_kpa / a.basinc_kpa).between(0.8, 1.25))]
        if len(b):
            eslesen += 1
            en_yakin = b.iloc[(b.oksijen_yuzde - a.oksijen_yuzde).abs().argsort()[:1]]
            dogru += int(en_yakin.yanar.iloc[0] == a.yanar)
    print(f"\n=== ALTIN TEST ({altin.makale_id.nunique()} makale, {len(altin)} doğru nokta) ===")
    print(f"Bulunan    : {eslesen}/{len(altin)}  (%{100 * eslesen / max(len(altin), 1):.0f})")
    print(f"Etiket doğru: {dogru}/{eslesen}  (%{100 * dogru / max(eslesen, 1):.0f})")
    print(f"Gemma'nın bu makalelerden çıkardığı toplam nokta: {len(bulunan)}")
    for m in jsonlari_oku(adlar):
        s = m["satirlar"]
        print(f"  {m['makale_id']}: tablo {m['tablo_sayisi']}, satır {len(s)}, "
              f"sağlam {sum(x['supheli'] == 'hayir' for x in s)}, hata {len(m['hatalar'])}")


# ============================== ANA ==============================
def secili_adlar():
    """classification.csv'den deney/derleme makaleleri; eski çalışmada en çok veri
    çıkan makaleler önce (süre yetmezse en değerlileri bitmiş olur). {ad: sıra}"""
    if not SINIFLANDIRMA.exists():
        return None
    import pandas as pd
    s = pd.read_csv(SINIFLANDIRMA, low_memory=False)
    s = s[s.turler.astype(str).str.contains("|".join(ISLENECEK_TURLER))]
    if "deney_satiri" in s:
        s = s.sort_values("deney_satiri", ascending=False, kind="stable")
    return {ad: i for i, ad in enumerate(s.makale_id.astype(str).str.lower())}


def main():
    p = argparse.ArgumentParser(description="Makalelerden yandı/söndü verisi (sürüm 3)")
    p.add_argument("--altin", action="store_true", help="sadece doğru cevabı bilinen makaleler + puan")
    p.add_argument("--limit", type=int)
    p.add_argument("--saat", type=float, help="en fazla kaç saat çalışsın")
    p.add_argument("--birlestir", action="store_true")
    p.add_argument("--sonra-birlestir", action="store_true")
    p.add_argument("--yeniden", action="store_true", help="bitmiş makaleleri de tekrar işle")
    p.add_argument("--nasa", action="store_true", help="sadece NASA raporları (adı rakam olan PDF'ler, ör. 20150023456.pdf)")
    arg = p.parse_args()

    CIKTI_KLASORU.mkdir(exist_ok=True)
    METIN_KLASORU.mkdir(exist_ok=True)
    if arg.birlestir:
        birlestir()
        return
    api_kontrol() if API_URL else vc.ollama_kontrol()

    pdfler = sorted(PDF_KLASORU.rglob("*.pdf"))
    if arg.altin:
        import pandas as pd
        if not ALTIN_DOSYA.exists():
            sys.exit(f"{ALTIN_DOSYA} yok.")
        adlar = set(pd.read_csv(ALTIN_DOSYA).makale_id.astype(str))
        pdfler = [p for p in pdfler if p.stem in adlar]
        print(f"Altın test: {len(pdfler)} makale bulundu ({len(adlar)} makaleden).")
    elif arg.nasa:
        pdfler = [p for p in pdfler if p.stem.isdigit()]
        var = {p.stem for p in pdfler}
        # PDF'i olmayan ama metni (metinler/<rakam>.txt) önceden çıkarılmış raporlar: metinden çalış
        sadece_metin = [PDF_KLASORU / "nasa" / f"{t.stem}.pdf" for t in METIN_KLASORU.glob("*.txt")
                        if t.stem.isdigit() and t.stem not in var
                        and (METIN_KLASORU / f"{t.stem}.meta.json").exists()]
        pdfler = sorted(pdfler + sadece_metin)
        print(f"NASA raporları: {len(pdfler) - len(sadece_metin)} PDF + {len(sadece_metin)} sadece metni olan rapor.")
    else:
        secili = secili_adlar()
        if secili is not None:
            once = len(pdfler)
            pdfler = sorted((p for p in pdfler if p.stem.lower() in secili),
                            key=lambda p: secili[p.stem.lower()])
            print(f"classification.csv: {once} PDF'ten {len(pdfler)} deney/derleme makalesi işlenecek.")

    bitmis = {f[:-5] for f in os.listdir(CIKTI_KLASORU) if f.endswith(".json")}
    bekleyen = pdfler if (arg.yeniden or arg.altin) else [p for p in pdfler if p.stem not in bitmis]
    if arg.limit:
        bekleyen = bekleyen[:arg.limit]
    print(f"İşlenecek: {len(bekleyen)} | Model: {MODEL} | aynı anda: {PARALEL} | "
          f"ikinci kontrol: {'açık' if DOGRULA else 'kapalı'}\n")

    bas, biten, durdur = time.time(), 0, False
    toplam_token = [0, 0.0, 0]     # ham token, kotaya yansıyan, makale sayısı

    def kaydet(pdf, durum, sonuc, gecen):
        nonlocal biten, durdur
        biten += 1
        if durum != "tamam":
            print(f"[{biten}/{len(bekleyen)}] {pdf.name}  {durum.upper()}: {sonuc}", flush=True)
            with open(ANA_KLASOR / "hatalar3.txt", "a", encoding="utf-8") as f:
                f.write(f"{pdf}\t{durum}\t{sonuc}\n")
            if "anahtarı reddedildi" in str(sonuc) or "şartları" in str(sonuc) or "KOTA" in str(sonuc) or (not API_URL and not vc.ollama_saglikli()):
                print("\nModel/API cevap vermiyor, duruluyor.")
                durdur = True
            if durum == "zaman_asimi":
                vc.guvenli_yaz(CIKTI_KLASORU / f"{pdf.stem}.json", json.dumps(
                    {"makale_id": pdf.stem, "dosya": str(pdf), "kaynak": vc.kaynak_bul(pdf),
                     "model": MODEL, "surum": SURUM, "tablo_sayisi": 0, "satirlar": [],
                     "hatalar": [sonuc]}, ensure_ascii=False))
            return
        vc.guvenli_yaz(CIKTI_KLASORU / f"{pdf.stem}.json", json.dumps(sonuc, ensure_ascii=False, indent=1))
        hiz = biten / (time.time() - bas)
        s = sonuc["satirlar"]
        t = sonuc.get("token") or {}
        if t.get("istek"):
            toplam_token[0] += t["girdi"] + t["cikti"]
            toplam_token[1] += t["girdi"] - t["onbellek"] + t["cikti"] + 0.03 * t["onbellek"]
            toplam_token[2] += 1
        print(f"[{biten}/{len(bekleyen)}] {pdf.name} | tablo {sonuc['tablo_sayisi']} | "
              f"test {sum(x['tur'] == 'test' for x in s)} | sınır {sum(x['tur'] == 'sinir' for x in s)} | "
              f"sağlam {sum(x['supheli'] == 'hayir' for x in s)} | {gecen:.0f} sn | "
              f"kalan ~{vc.sure_yaz((len(bekleyen) - biten) / hiz)}"
              + (f" | token {t['girdi'] + t['cikti']:,} (önbellek {t['onbellek']:,}) | "
                 f"kotaya göre günde ~{int(15e6 / (toplam_token[1] / toplam_token[2]))} makale"
                 if t.get("istek") else ""), flush=True)

    def tek(pdf):
        print(f"   başladı: {pdf.name}", flush=True)
        t0 = time.time()
        durum, sonuc = sureli_isle(pdf)
        return durum, sonuc, time.time() - t0

    sira = iter(bekleyen)
    havuz = ThreadPoolExecutor(PARALEL)
    try:
        calisan = {}

        def doldur():
            while not durdur and len(calisan) < PARALEL:
                if arg.saat and time.time() - bas > arg.saat * 3600:
                    return
                pdf = next(sira, None)
                if pdf is None:
                    return
                calisan[havuz.submit(tek, pdf)] = pdf

        doldur()
        while calisan:
            bitenler, _ = wait(calisan, timeout=1, return_when=FIRST_COMPLETED)   # Ctrl+C çalışsın
            for f in bitenler:
                kaydet(calisan.pop(f), *f.result())
            doldur()
    except KeyboardInterrupt:
        print("\nDurduruldu (Ctrl+C). Bitmiş makaleler kayıtlı; tekrar çalıştırınca kaldığı yerden devam eder.")
        for p in list(AKTIF_SURECLER):
            p.kill()
        os._exit(1)
    havuz.shutdown()
    if arg.saat and time.time() - bas > arg.saat * 3600:
        print(f"\n{arg.saat} saat doldu. Tekrar çalıştırınca kaldığı yerden devam eder.")

    if arg.altin:
        altin_puan({p.stem for p in pdfler})
    elif arg.sonra_birlestir:
        birlestir()


if __name__ == "__main__":
    main()
