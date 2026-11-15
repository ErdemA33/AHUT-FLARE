"""Sistem ölçümleri ve render klasörü izleme.

İşlemci yüzdesi gerçekten ölçülür; ölçülemeyen değer None olur, uydurulmaz.
psutil kuruluysa çekirdek başına, değilse işletim sisteminin kendi sayaçlarından
toplam yüzde okunur.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import re
from pathlib import Path

VIDEO_TURLERI = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime"}
GORUNTU_TURLERI = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif"}

_kilit = threading.Lock()
_onceki = {"t": 0.0, "sayac": None, "sonuc": None}


def _sayaclar():
    """{ad: (meşgul, toplam)} döndürür; psutil yoksa /proc/stat ya da GetSystemTimes."""
    if sys.platform.startswith("linux"):
        sat = {}
        with open("/proc/stat") as f:
            for satir in f:
                if satir.startswith("cpu") and satir[3:4].isdigit():
                    p = satir.split()
                    v = list(map(int, p[1:]))
                    bos = v[3] + (v[4] if len(v) > 4 else 0)
                    sat[p[0]] = (sum(v) - bos, sum(v))
        return sat, "proc"
    if sys.platform == "win32":
        import ctypes

        class FT(ctypes.Structure):
            _fields_ = [("lo", ctypes.c_uint32), ("hi", ctypes.c_uint32)]

        bos, ker, kul = FT(), FT(), FT()
        ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(bos), ctypes.byref(ker), ctypes.byref(kul))
        deger = lambda f: (f.hi << 32) | f.lo
        toplam = deger(ker) + deger(kul)  # çekirdek süresi boşta süresini de içerir
        return {"toplam": (toplam - deger(bos), toplam)}, "windows"
    return None, None


def _psutil_ek(sonuc: dict, psutil) -> None:
    """Bellek, takas, süreç sayısı ve çalışma süresi — htop'taki gibi."""
    try:
        m = psutil.virtual_memory()
        sonuc["bellek"] = {"kullanilan": m.used, "toplam": m.total, "yuzde": m.percent}
    except Exception:
        pass
    try:
        s = psutil.swap_memory()
        if s.total:
            sonuc["takas"] = {"kullanilan": s.used, "toplam": s.total, "yuzde": s.percent}
    except Exception:
        pass
    try:
        sonuc["surec"] = len(psutil.pids())
    except Exception:
        pass
    try:
        sonuc["calisma_sn"] = max(0, time.time() - psutil.boot_time())
    except Exception:
        pass
    try:
        yuk = list(psutil.getloadavg())
        # Windows'ta psutil bunu taklit eder ve ilk dakikalarda 0 verir; sıfırsa gösterme.
        if any(y > 0 for y in yuk):
            sonuc["yuk"] = yuk
    except Exception:
        pass


def islemci() -> dict:
    """Çekirdek başına ve toplam işlemci yüzdesi, bellek, takas, süreç, çalışma süresi.

    Ölçülemeyen değer None olur ya da hiç konmaz; hiçbir şey uydurulmaz.
    """
    with _kilit:
        simdi = time.time()
        if _onceki["sonuc"] is not None and simdi - _onceki["t"] < 0.4:
            return _onceki["sonuc"]
        sonuc = {"cekirdek": None, "toplam": None, "cekirdek_sayisi": os.cpu_count(), "kaynak": None}
        try:
            try:
                import psutil

                # psutil.cpu_percent() yüzdeyi "bir önceki çağrıdan bu yana" hesaplar;
                # kim ne zaman çağırdıysa ona bağımlıdır ve art arda çağrılarda 0 döner.
                # Bu yüzden ham sayaçları alıp farkı kendimiz tutuyoruz: ölçüm, çağrı
                # aralığından bağımsız ve tekrarlanabilir olur.
                simdiki = psutil.cpu_times(percpu=True)
                onceki_t = _onceki.get("cpu_times")
                if onceki_t and len(onceki_t) == len(simdiki):
                    yuzdeler = []
                    for a, b in zip(onceki_t, simdiki):
                        t0, t1 = sum(a), sum(b)
                        bos0 = a.idle + getattr(a, "iowait", 0.0)
                        bos1 = b.idle + getattr(b, "iowait", 0.0)
                        d = t1 - t0
                        yuzdeler.append(max(0.0, min(100.0, 100.0 * ((t1 - bos1) - (t0 - bos0)) / d)) if d > 0 else 0.0)
                    sonuc["cekirdek"] = yuzdeler
                    sonuc["toplam"] = sum(yuzdeler) / max(1, len(yuzdeler))
                _onceki["cpu_times"] = simdiki
                sonuc["kaynak"] = "psutil"
                _psutil_ek(sonuc, psutil)
            except ImportError:
                sayac, kaynak = _sayaclar()
                onceki = _onceki["sayac"]
                if sayac is not None and onceki is not None:
                    yuzde = {}
                    for ad, (m, t) in sayac.items():
                        m0, t0 = onceki.get(ad, (m, t))
                        yuzde[ad] = 100.0 * (m - m0) / (t - t0) if t > t0 else 0.0
                    toplam = yuzde.pop("toplam", None) if "toplam" in yuzde else None
                    if yuzde:
                        sonuc["cekirdek"] = [yuzde[k] for k in sorted(yuzde, key=lambda x: int(x[3:]))]
                        toplam = sum(sonuc["cekirdek"]) / len(sonuc["cekirdek"])
                    sonuc["toplam"] = toplam
                    sonuc["kaynak"] = kaynak
                _onceki["sayac"] = sayac
        except Exception:
            pass
        _onceki["t"], _onceki["sonuc"] = simdi, sonuc
        return sonuc


# ---------------------------------------------------------------- render klasörü
def _vaka_eslesmesi(ad: str) -> dict | None:
    """Dosya adı sözleşmesi:  <malzeme>_g<g>_o<oksijen>_p<basinc>[_a<akis>].<uzanti>
    Örnek: pmma_g1e-4_o21_p101.3_a10.mp4 — eşleşmezse None döner (dosya yine listelenir).
    """
    govde = Path(ad).stem
    parca = govde.split("_")
    if len(parca) < 4:
        return None
    k = {"malzeme": parca[0]}
    try:
        for p in parca[1:]:
            if p.startswith("g"):
                k["g"] = float(p[1:])
            elif p.startswith("o"):
                k["oksijen"] = float(p[1:])
            elif p.startswith("p"):
                k["basinc"] = float(p[1:])
            elif p.startswith("a"):
                k["akis"] = float(p[1:])
    except ValueError:
        return None
    return k if {"g", "oksijen", "basinc"} <= set(k) else None


def render_listesi(klasor: Path) -> list[dict]:
    """render/ klasöründeki video ve görüntüler, en yeni başta."""
    try:
        liste = []
        for p in sorted(klasor.iterdir()):
            uzanti = p.suffix.lower()
            if not p.is_file() or uzanti not in (VIDEO_TURLERI | GORUNTU_TURLERI):
                continue
            st = p.stat()
            liste.append(
                {
                    "ad": p.name,
                    "yol": p.resolve().as_uri(),
                    "tur": "video" if uzanti in VIDEO_TURLERI else "goruntu",
                    "mime": (VIDEO_TURLERI | GORUNTU_TURLERI)[uzanti],
                    "zaman": st.st_mtime,
                    "boyut": st.st_size,
                    "vaka": _vaka_eslesmesi(p.name),
                    **_render_ek(p.name),
                }
            )
        return sorted(liste, key=lambda x: x["zaman"], reverse=True)
    except Exception:
        return []


# ---------------------------------------------------------------- render süzme (çözülen vakaya göre)
# Render dosyalarının malzemesi -> yakıt türü (tahmin.MALZEME_VARSAYILAN ile aynı sözleşme).
_RENDER_YAKIT = {"n-heptane": "sivi", "methanol": "sivi", "ethanol": "sivi", "n-decane": "sivi",
                 "methane": "gaz", "ethylene": "gaz", "propane": "gaz", "pmma": "kati", "sibal": "kati",
                 "cotton": "kati", "nomex": "kati", "silicone": "kati"}
_G_SIRA = ("uzay", "ay", "mars", "dunya")
_G_BANT_G = {"uzay": 0.0, "ay": 0.165, "mars": 0.38, "dunya": 1.0}


def g_bandi(g) -> str:
    """Yerçekimi bandı: uzay (<0,05 g) | ay (<0,27) | mars (<0,6) | dunya."""
    g = float(g)
    return "uzay" if g < 0.05 else "ay" if g < 0.27 else "mars" if g < 0.6 else "dunya"


def _render_ek(ad: str) -> dict:
    """Dosya adından: yakıt türü, panel bantları, dil. Çok panelli videolarda dosya adındaki g yalnız sol panelin g'sidir;
    paneller etiketten okunur (…-4g: uzay|ay|mars|dünya, …uzay-mars…: uzay|mars)."""
    govde = Path(ad).stem
    k = _vaka_eslesmesi(ad)
    if not k:
        return {"yakit": None, "paneller": [], "dil": "tr"}
    etiket = govde.lower()
    if re.search(r"(^|[-_])4g($|[-_])", etiket):
        paneller = list(_G_SIRA)
    elif "uzay-mars" in etiket:
        paneller = ["uzay", "mars"]
    else:
        paneller = [g_bandi(k["g"])]
    dil = "en" if re.search(r"[-_]en($|[-_])", etiket) else "tr"
    return {"yakit": _RENDER_YAKIT.get(str(k["malzeme"]).lower()), "paneller": paneller, "dil": dil}


def render_uygun(liste: list[dict], malzeme: str, yakit: str | None, g, dil: str = "tr") -> dict:
    """Çözülen vakaya uygun renderlar.
      tam   : aynı malzeme + aynı yerçekimi bandı (çok panelde paneller arasında)
      benzer: aynı yakıt türünden, yerçekimi bandı en yakın olanlar
      yok   : uygun render yok
    Dil: tr ise "-en" sürümleri gizlenir; en ise "-en" sürümü olan dosyanın tr'si gizlenir."""
    def dil_suz(l):
        en_adlar = {re.sub(r"[-_]en(?=\.|$)", "", Path(x["ad"]).stem) for x in l if x.get("dil") == "en"}
        if dil == "en":
            return [x for x in l if x.get("dil") == "en" or Path(x["ad"]).stem not in en_adlar]
        return [x for x in l if x.get("dil") != "en"]

    aday = dil_suz([x for x in liste if x.get("vaka") and x.get("paneller")])
    m = str(malzeme or "").strip().lower()
    bant = g_bandi(g)
    tam = [x for x in aday if str(x["vaka"]["malzeme"]).lower() == m and bant in x["paneller"]]
    if tam:
        return {"mod": "tam", "adlar": [x["ad"] for x in sorted(tam, key=lambda x: x["ad"])]}
    if yakit:
        def uzak(x):   # bant sırası farkı (panellerin en yakını)
            return min(abs(_G_SIRA.index(b) - _G_SIRA.index(bant)) for b in x["paneller"])
        ben = [x for x in aday if x.get("yakit") == yakit]
        if ben:
            en_yakin = min(uzak(x) for x in ben)
            ben = [x for x in ben if uzak(x) == en_yakin]
            return {"mod": "benzer", "adlar": [x["ad"] for x in sorted(ben, key=lambda x: x["ad"])]}
    return {"mod": "yok", "adlar": []}
