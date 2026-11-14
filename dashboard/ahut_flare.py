#!/usr/bin/env python3
"""AHUT FLARE — mikro yerçekiminde yangın güvenliği analiz uygulaması.

Masaüstü uygulamasıdır: kendi penceresinde açılır, tarayıcı ya da yerel sunucu
kullanmaz. Ekran ile Python arasındaki bağ doğrudan fonksiyon çağrısıdır
(pywebview js_api); HTTP yoktur, port açılmaz.

Çalıştırma (geliştirme):
    python ahut_flare.py              gerçek model
    python ahut_flare.py --mock       sahte veri (model yüklemeden arayüz denemesi)
    python ahut_flare.py --ayikla     geliştirici araçları açık

Exe olarak paketlenince: veri ve arayüz paketin içinde, yazılabilir dosyalar
(veri/, render/, evren_anahtar.txt) exe'nin yanında durur.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
from pathlib import Path

SURUM = "1.0.0"
UYGULAMA_ADI = "AHUT FLARE"

# ---------------------------------------------------------------- yollar
# VERI_KOK : salt okunur kaynaklar (arayüz, model, veri dosyaları)
# KOK      : yazılabilir kök (kayıtlı vakalar, ayarlar, render klasörü)
# Program Files'a kurulduğunda exe'nin yanına yazılamaz; bu yüzden paketli sürümde
# yazılabilir kök %LOCALAPPDATA%\AHUT FLARE olur. Exe'nin yanında "tasinabilir.txt"
# varsa (USB / zip kullanımı) her şey exe'nin yanında tutulur.
PAKETLI = getattr(sys, "frozen", False)
if PAKETLI:
    VERI_KOK = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    EXE_YANI = Path(sys.executable).resolve().parent
    if (EXE_YANI / "tasinabilir.txt").exists():
        KOK = EXE_YANI
    else:
        KOK = Path(os.environ.get("LOCALAPPDATA") or EXE_YANI) / "AHUT FLARE"
else:
    VERI_KOK = KOK = EXE_YANI = Path(__file__).resolve().parent

ARAYUZ = VERI_KOK / "arayuz"
MOTOR = VERI_KOK / "motor"
VERI = KOK / "veri"
ORNEKLER = VERI_KOK / "veri" / "ornekler"   # uygulamayla gelen örnek vakalar (salt okunur)
SITE = VERI_KOK / "site"                    # GitHub Pages sitesinin kaynak dosyaları
RENDER = KOK / "render"

# EVREN anahtarı (dosya yolu; içerik burada okunmaz, yazdırılmaz). Sıra:
#   1) EVREN_ANAHTAR_DOSYASI ortam değişkeni   2) yazılabilir kök   3) exe'nin yanı
#   4) yalnız geliştirmede: bir üst klasör (~/nasaspaceapp/evren_anahtar.txt; kopyalanmaz, yerinden okunur)
_adaylar = [Path(os.environ["EVREN_ANAHTAR_DOSYASI"])] if os.environ.get("EVREN_ANAHTAR_DOSYASI") else []
_adaylar += [KOK / "evren_anahtar.txt", EXE_YANI / "evren_anahtar.txt"]
if not PAKETLI:
    _adaylar.append(KOK.parent / "evren_anahtar.txt")
ANAHTAR = next((a for a in _adaylar if a.exists()), _adaylar[0])

# Backend'in yazılabilir dosyaları (malzeme_onbellek.json, topluluk/topluluk.sqlite, tahmin kaydı) veri/ altına gider.
# Backend import edilmeden ÖNCE ayarlanmalı (modüller yolu import anında okur).
os.environ.setdefault("YANGIN_VERI_KLASORU", str(VERI))
os.environ.setdefault("TAHMIN_KAYIT", str(VERI / "loglar" / "tahmin_kayit.jsonl"))
os.environ["EVREN_ANAHTAR_DOSYASI"] = str(ANAHTAR)

sys.path.insert(0, str(VERI_KOK))  # cekirdek paketi


def pencere_motoru() -> str | None:
    """pywebview arka ucu: Windows'ta Edge WebView2, Linux'ta GTK (WebKit2GTK), macOS'ta Cocoa.
    AHUT_GUI ortam değişkeniyle değiştirilebilir (ör. qt)."""
    if os.environ.get("AHUT_GUI"):
        return os.environ["AHUT_GUI"]
    if sys.platform == "win32":
        return "edgechromium"
    if sys.platform.startswith("linux"):
        return "gtk"
    return None   # macOS: pywebview kendisi seçer (cocoa)


def pencere_adresi(gui: str | None):
    """(pencere adresi, render adres öneki).

    pywebview 5+ yerel dosyaları 127.0.0.1 üzerindeki kendi HTTP sunucusundan açar; sayfa http:// kökenli olunca
    render/ klasöründeki file:// videolar yüklenmez (CSP media-src 'self' ve tarayıcının yerel dosya engeli).
    Windows dışında arayüz ve render/ aynı kökenden, küçük bir WSGI uygulamasıyla sunulur (yalnız 127.0.0.1;
    arayuz/ ve render/ dışında dosya verilmez). Windows (Edge WebView2) eskisi gibi dosya yoluyla açılır.
    """
    if gui == "edgechromium":
        return str(ARAYUZ / "index.html"), None
    import bottle

    uygulama = bottle.Bottle()

    def _ver(yol, kok):
        yanit = bottle.static_file(yol, root=str(kok))
        yanit.set_header("Cache-Control", "no-cache, no-store, must-revalidate")
        return yanit

    @uygulama.route("/render/<ad:path>")
    def _render(ad):
        return _ver(ad, RENDER)

    @uygulama.route("/")
    def _kok():
        return _ver("index.html", ARAYUZ)

    @uygulama.route("/<yol:path>")
    def _arayuz(yol):
        return _ver(yol, ARAYUZ)

    return uygulama, "/render/"


def pywebview_hazirla(gui: str | None) -> None:
    """Windows dışında pywebview'in evaluate_js'ini eval'siz çalıştırır.

    pywebview 5+ evaluate_js betiği eval() içine sarar ve Python -> ekran dönüşlerini (js_api sonuçları,
    olaylar) da bununla yapar; js_api fonksiyonlarını da `new Function` ile kurar. index.html'deki CSP
    'unsafe-eval' içermez ve WebKitGTK bunu uygular: Linux'ta ekran Python'a hiç ulaşamaz ("Uygulama
    çekirdeğine ulaşılamadı"). CSP gevşetilmez; pywebview eval'siz çalışacak şekilde yamanır.
    Windows (Edge WebView2) olduğu gibi bırakılır.
    """
    if gui == "edgechromium":
        return
    import re
    import webview.util as wu
    import webview.window as ww
    if getattr(ww.Window, "_ahut_evalsiz", False):
        return

    # 1) js_api fonksiyonları api.js'te `new Function(params, body)` ile kuruluyor; CSP bunu da engelliyor.
    #    Aynı davranışı veren bir kapanışla (closure) değiştirilir. Desen bulunmazsa (pywebview sürümü
    #    değiştiyse) dokunulmaz.
    _yukle = wu.load_js_files
    desen = re.compile(r"new Function\(\s*sanitize_params\(params\),\s*funcBody\s*\)")
    kapanis = ("(function (fn) { return function () {"
               " var __id = (Math.random() + '').substring(2);"
               " var promise = new Promise(function (resolve, reject) {"
               " window.pywebview._checkValue(fn, resolve, reject, __id); });"
               " window.pywebview._jsApiCallback(fn, Array.prototype.slice.call(arguments), __id);"
               " return promise; }; })(funcName)")

    def load_js_files(window, platform):
        kod, bitis = _yukle(window, platform)
        return desen.sub(lambda _: kapanis, kod), bitis

    wu.load_js_files = load_js_files

    # 2) evaluate_js betiği eval() ile sarar; Python -> ekran dönüşleri (js_api sonuçları, olaylar) bununla
    #    yapılır. run_js betiği olduğu gibi çalıştırır (pywebview'in iç çağrıları tek deyimdir).
    # 3) pywebview GTK, betik uzunluğunu karakter sayısıyla verir (WebKit bayt bekler): ASCII dışı karakterli betik
    #    sondan kesilir. \\uXXXX kaçışıyla ASCII'ye çevrilir (JS dizgi ve adlarında geçerli).
    def evaluate_js(self, script, callback=None):
        script = "".join(c if ord(c) < 128 else "\\u%04x" % ord(c) for c in script)
        sonuc = self.run_js(script)
        if callback is not None:
            callback(sonuc)
        return sonuc

    ww.Window.evaluate_js = evaluate_js
    ww.Window._ahut_evalsiz = True


def kendini_sina(Kopru, mock: bool) -> int:
    """Pencere açmadan paketin sağlamlığını sınar.

    Paketlenmiş exe'de en kırılgan yer modelin (joblib + scikit-learn) açılmasıdır;
    bu mod onu pencere açmadan doğrular. Rapor hem ekrana hem dosyaya yazılır,
    çünkü exe penceresiz derlenir ve konsol çıktısı görünmeyebilir.
    """
    import time

    satirlar, hata_var = [], False

    def yaz(satir, basarili=True):
        nonlocal hata_var
        if not basarili:
            hata_var = True
        satirlar.append(("[OK]   " if basarili else "[HATA] ") + satir)
        print(satirlar[-1], flush=True)

    rapor = VERI / "sinama_raporu.txt"
    yaz(f"{UYGULAMA_ADI} {SURUM} · paketli={PAKETLI} · python={sys.version.split()[0]}")
    yaz(f"kaynak kök : {VERI_KOK}")
    yaz(f"veri kök   : {KOK}")
    try:
        api = Kopru(surum=SURUM, arayuz=ARAYUZ, motor_yolu=MOTOR, veri=VERI,
                    render=RENDER, anahtar=ANAHTAR, mock=mock, ornekler=ORNEKLER, site=SITE)
        for ad, yol in (("arayüz", ARAYUZ / "index.html"), ("motor", MOTOR / "tahmin.py"),
                        ("model", MOTOR / "modeller" / "risk.joblib")):
            yaz(f"{ad} dosyası bulundu: {yol.name}", yol.exists())

        bas = time.perf_counter()
        d = api.motoru_yukle()
        yaz(f"model yüklendi ({d.get('sure_sn')} sn)" if d["durum"] == "hazir"
            else f"model yüklenemedi: {d.get('mesaj')}", d["durum"] == "hazir")
        if d["durum"] != "hazir":
            raise RuntimeError(d.get("mesaj") or "model hazır değil")

        s = api.coz({"malzeme": "pmma", "oksijen": 21, "basinc": 101.3, "g": 1e-4, "akis": None})
        t = s["tahmin"].get("veri")
        yaz("tahmin çalıştı" if t else f"tahmin hata verdi: {s['tahmin'].get('hata')}", bool(t))
        if t:
            yaz(f"risk={t['risk_seviyesi']} · ihtimal={t['yanma_ihtimali']} · "
                f"sönme={t['sonme_siniri']} · güven={t['guven']['skor']}")
            for ad in ("oksijen_egrisi", "harita", "akis_egrisi", "yakin"):
                yaz(f"{ad}: tamam" if "hata" not in s[ad] else f"{ad}: {s[ad]['hata']}", "hata" not in s[ad])

        ozet = api.vaka_kaydet({"girdi": s["kosul"], "sonuc": {"tahmin": t}, "onayar": "ISS",
                                "baslik": "sınama vakası"})
        yaz(f"vaka yazıldı ve okundu: {ozet['id']}", api.vaka_oku(ozet["id"]) is not None)
        api.vaka_sil(ozet["id"])
        yaz(f"örnek vaka sayısı (topluluk): {len(api.topluluk())}")
        yaz(f"EVREN anahtarı: {'bulundu' if ANAHTAR.exists() else 'yok (yapay zeka yorumu çalışmaz)'}")
        yaz(f"toplam süre: {round(time.perf_counter() - bas, 2)} sn")
    except Exception as e:
        yaz(f"{type(e).__name__}: {e}", False)

    satirlar.append("")
    satirlar.append("SONUÇ: " + ("BAŞARISIZ — yukarıdaki [HATA] satırlarını ekibe iletin." if hata_var else "BAŞARILI"))
    print(satirlar[-1], flush=True)
    try:
        rapor.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
        print(f"Rapor: {rapor}", flush=True)
    except Exception:
        pass
    return 1 if hata_var else 0


def main() -> int:
    a = argparse.ArgumentParser(prog="ahut_flare", description=f"{UYGULAMA_ADI} {SURUM}")
    a.add_argument("--mock", action="store_true", help="gerçek model yerine sahte veri")
    a.add_argument("--ayikla", action="store_true", help="geliştirici araçlarını aç")
    a.add_argument("--sinama", action="store_true",
                   help="pencere açmadan kendini sına (model yüklenir, bir vaka çözülür); rapor dosyaya yazılır")
    a.add_argument("dosya", nargs="?", help="açılacak .ahut vaka dosyası")
    arg = a.parse_args()
    if arg.dosya:   # göreli yol verildiyse çalışma klasörü değişmeden önce mutlak yola çevir
        arg.dosya = str(Path(arg.dosya).resolve())

    if PAKETLI:
        import multiprocessing
        multiprocessing.freeze_support()

    from cekirdek.kopru import Kopru

    for klasor in (VERI, VERI / "vakalar", RENDER):
        klasor.mkdir(parents=True, exist_ok=True)

    if arg.sinama:
        return kendini_sina(Kopru, arg.mock)

    import webview

    gui = pencere_motoru()
    adres, render_oneki = pencere_adresi(gui)
    api = Kopru(
        surum=SURUM,
        arayuz=ARAYUZ,
        motor_yolu=MOTOR,
        veri=VERI,
        render=RENDER,
        anahtar=ANAHTAR,
        mock=arg.mock,
        acilis_dosyasi=arg.dosya,
        ornekler=ORNEKLER,
        site=SITE,
        render_oneki=render_oneki,
    )

    pencere = webview.create_window(
        f"{UYGULAMA_ADI} — Fire Learning, Analysis & Research Engine",
        url=adres,
        js_api=api,
        width=1600,
        height=980,
        min_size=(1180, 740),
        background_color="#f0f0f0",
        zoomable=True,
    )
    api.pencere_bagla(pencere)

    # Model yüklemesi birkaç saniye sürer; pencere hemen açılsın, yükleme arkada sürsün.
    threading.Thread(target=api.motoru_yukle, daemon=True).start()

    # Pencere kapanınca / terminal kapanınca / öldürülünce: kendi başlattığımız koşular da sonlansın (sahipsiz mpirun kalmasın)
    import atexit
    import signal as _sg
    atexit.register(api._kapat)

    def _sinyalle_kapat(no, _cerceve):
        api._kapat()
        os._exit(128 + no)
    for _no in (_sg.SIGTERM, _sg.SIGHUP):
        try:
            _sg.signal(_no, _sinyalle_kapat)
        except (ValueError, OSError):
            pass

    pywebview_hazirla(gui)
    webview.start(gui=gui, debug=arg.ayikla)
    api._kapat()
    return 0


if __name__ == "__main__":
    sys.exit(main())
