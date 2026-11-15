#!/usr/bin/env python3
"""screenshot_library.py — malzeme kütüphanesinin 2. genişletmesini (kategori süzgeci, özel durumlar) arayüz üzerinden
gezer ve görüntü alır. screenshot.py'nin kurulumunu kullanır; arayüze dokunmaz.

    DISPLAY=:77 GDK_BACKEND=x11 .venv/bin/python screenshot_library.py   # -> ../of_visual/screen/library2/
"""
import argparse
import json
import sys
import threading
import time
from pathlib import Path

BURASI = Path(__file__).resolve().parent
sys.path.insert(0, str(BURASI))
import ahut_flare as A  # noqa: E402
from screenshot import _ascii  # noqa: E402

COZ = [("oksijen", "oksijen · ISS (oksitleyici)"), ("Krytox", "Krytox · ISS (yanmaz)"),
       ("Li-ion", "Li-ion · ISS (pil)"), ("bütan", "bütan · ISS (kütüphane, gaz)"), ("koli bandı", "koli bandı · ISS")]


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--cikti", default=str(BURASI.parent / "of_visual" / "screen" / "library2"))
    a.add_argument("--llmsiz", action="store_true", help="yapay zeka yorumu isteme")
    a.add_argument("--videosuz", action="store_true",
                   help="video oynatma adımını atla (GPU'suz Xephyr'de oynayan video WebKit'i kilitliyor)")
    k = a.parse_args()
    main.llmsiz = k.llmsiz
    main.videosuz = k.videosuz
    cikti = Path(k.cikti)
    cikti.mkdir(parents=True, exist_ok=True)

    import webview
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, GLib
    from webview.platforms import gtk as wg
    from core.bridge import Kopru

    for klasor in (A.VERI, A.VERI / "cases", A.RENDER):
        klasor.mkdir(parents=True, exist_ok=True)
    gui = A.pencere_motoru()
    adres, render_oneki = A.pencere_adresi(gui)
    api = Kopru(surum=A.SURUM, arayuz=A.ARAYUZ, motor_yolu=A.MOTOR, veri=A.VERI, render=A.RENDER,
                anahtar=A.ANAHTAR, mock=False, ornekler=A.ORNEKLER, site=A.SITE, render_oneki=render_oneki)
    pencere = webview.create_window(f"{A.UYGULAMA_ADI} — ekran görüntüsü", url=adres,
                                    js_api=api, width=1600, height=980, min_size=(1180, 740),
                                    background_color="#f0f0f0")
    api.pencere_bagla(pencere)
    kayit = {"zaman": time.strftime("%Y-%m-%d %H:%M:%S"), "goruntuler": [], "vakalar": {}, "hatalar": []}

    def js(kod, bekle=0.0):
        """Deyim çalıştırır. run_js eval'siz çalışır (sayfanın CSP'si eval'e izin vermiyor)."""
        pencere.run_js(_ascii(kod))
        if bekle:
            time.sleep(bekle)

    def oku(ifade):
        """Bir JS ifadesinin değerini JSON üzerinden okur."""
        r = pencere.run_js(_ascii(f"JSON.stringify(({ifade}))"))
        try:
            return json.loads(r) if isinstance(r, str) else r
        except ValueError:
            return r

    def goruntu(ad):
        yol = cikti / f"dashboard_{ad}.png"
        olay, hata = threading.Event(), []

        def basla():
            # Görüntü GTK penceresinin kendi tamponundan alınır (GdkPixbuf); WebKit anlık görüntüsü cairo köprüsü
            # (python3-gi-cairo) istediği için kullanılmaz. Wayland'da ekran yakalama izni gerekmez.
            try:
                wv = wg.BrowserView.instances[pencere.uid].webview
                a = wv.get_allocation()
                pb = Gdk.pixbuf_get_from_window(wv.get_window(), a.x, a.y, a.width, a.height)
                if pb is None:
                    hata.append("pixbuf boş")
                else:
                    pb.savev(str(yol), "png", [], [])
            except Exception as e:  # noqa: BLE001
                hata.append(repr(e))
            olay.set()
            return False

        GLib.idle_add(basla)
        olay.wait(30)
        if hata or not yol.exists():
            kayit["hatalar"].append(f"{ad}: görüntü alınamadı {hata}")
        else:
            kayit["goruntuler"].append(yol.name)
            print("görüntü", yol.name, flush=True)

    def bekle_kosul(kod, sure=180):
        t0 = time.time()
        while time.time() - t0 < sure:
            try:
                if oku(kod):
                    return True
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.5)
        return False

    def surucu():
        try:
            pencere.events.loaded.wait(60)
            api.motoru_yukle()
            bekle_kosul("typeof S !== 'undefined' && S.motor && S.motor.durum === 'hazir'", 120)
            time.sleep(2)
            if oku("DIL") != "tr":
                js("dilSec('tr'); yenidenCiz();", 1)
            js("Kabuk.sekmeAc('kutuphane'); ktpGorunum = 'malzemeler'; mlzTur = ''; mlzKat = ''; ktpAra = ''; kutuphaneCiz();", 3)
            goruntu("k1_tumu")
            kayit["sayim"] = oku("{toplam: MLZ.malzemeler.length, secenek: Array.from(document.querySelectorAll('#mlzKatSec option')).map(o => o.textContent)}")
            for i, kat in enumerate(("kıyafet/kumaş", "pil", "yiyecek")):
                js(f"mlzKat = {json.dumps(kat)}; kutuphaneCiz();", 2)
                kayit[f"kat_{kat}"] = oku("document.querySelectorAll('.vaka-kart[data-malzeme]').length")
                goruntu(f"k2_kategori_{i}")
            js("mlzKat = 'gaz'; mlzTur = 'gaz'; kutuphaneCiz();", 2)
            goruntu("k3_kategori_gaz")
            js("mlzKat = ''; mlzTur = ''; kutuphaneCiz(); mlzAyrinti('pfpe');", 2)
            goruntu("k4_ayrinti_pfpe")
            js("Kabuk.pencereKapat(); mlzAyrinti('polyester_fabric');", 2)
            goruntu("k5_ayrinti_polyester")
            js("Kabuk.pencereKapat();", 0.5)
            for i, (ad, baslik) in enumerate(COZ):
                js("Kabuk.sekmeAc('calisma'); Kabuk.agacSec('ortam');", 1)
                for alan in ("numune_tipi", "kalinlik", "yakit_turu"):
                    js(f"alanDegisti('{alan}', '');", 0.1)
                for alan, deger in (("onayar", "ISS"), ("malzeme", "__diger"), ("malzemeAd", ad)):
                    js(f"alanDegisti({json.dumps(alan)}, {json.dumps(deger)});", 0.4)
                js("window.__cozBitti = 0; cozHizli().then(() => { window.__cozBitti = 1; })"
                   ".catch((e) => { window.__cozBitti = 'hata: ' + e; });", 0.5)
                bekle_kosul("window.__cozBitti !== 0", 300)
                time.sleep(1.5)
                kayit["vakalar"][ad] = oku("{coz: window.__cozBitti, ozel: S.sonuc && S.sonuc.tahmin.ozel_durum, "
                                           "birlesik: S.sonuc && S.sonuc.tahmin.yanma_birlesik, "
                                           "kutup: S.sonuc && S.sonuc.tahmin.kutuphane_eslesme && S.sonuc.tahmin.kutuphane_eslesme.id}")
                js("Kabuk.sekmeAc('calisma'); Kabuk.agacSec('r-ozet');", 1.5)
                goruntu(f"k6_coz_{i}")
        except Exception as e:  # noqa: BLE001
            kayit["hatalar"].append(repr(e))
        finally:
            (cikti / "library2.json").write_text(json.dumps(kayit, ensure_ascii=False, indent=1), encoding="utf-8")
            time.sleep(1)
            pencere.destroy()

    A.pywebview_hazirla(gui)
    webview.start(surucu, gui=gui)
    print(json.dumps({"goruntu": len(kayit["goruntuler"]), "hatalar": kayit["hatalar"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
