#!/usr/bin/env python3
"""screenshot_chat.py — Yapay Zeka Yorumu düğümündeki SOHBET'i arayüz üzerinden dener ve görüntüsünü alır.

    DISPLAY=:77 GDK_BACKEND=x11 .venv/bin/python screenshot_chat.py [--cikti ../of_visual/screen/workbench]

Vaka: PMMA · Mars · %30 O2 · 70 kPa. Dört soru sorulur; cevaplar ve ek hesaplar <cikti>/chat.json'a,
görüntü <cikti>/chat.png'ye yazılır. Ardından girdi değişimi ("eski vaka") ve çevrimdışı durumu sınanır
(--ek klasörü verilirse görüntüleri oraya). Uygulamanın veri klasörünün geçici kopyasıyla çalışır.
"""
import argparse
import json
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

BURASI = Path(__file__).resolve().parent
sys.path.insert(0, str(BURASI))
import ahut_flare as A  # noqa: E402

SORULAR = ["neden riskli?", "güven neden düşük?", "oksijen %25 olsa?", "basınç 101 kPa olsa?"]


def _ascii(kod):
    return "".join(c if ord(c) < 128 else "\\u%04x" % ord(c) for c in kod)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--cikti", default=str(BURASI.parent / "of_visual" / "screen" / "workbench"))
    a.add_argument("--ek", default=None, help="ek durum görüntüleri (eski vaka, çevrimdışı) için klasör")
    k = a.parse_args()
    cikti = Path(k.cikti)
    cikti.mkdir(parents=True, exist_ok=True)
    gecici = Path(tempfile.mkdtemp(prefix="sohbet_veri_"))
    shutil.copytree(A.VERI, gecici / "data")

    import webview
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, GLib
    from webview.platforms import gtk as wg
    from core.bridge import Kopru

    gui = A.pencere_motoru()
    adres, render_oneki = A.pencere_adresi(gui)
    api = Kopru(surum=A.SURUM, arayuz=A.ARAYUZ, motor_yolu=A.MOTOR, veri=gecici / "data", render=A.RENDER,
                anahtar=A.ANAHTAR, mock=False, ornekler=A.ORNEKLER, site=A.SITE, render_oneki=render_oneki)
    pencere = webview.create_window(f"{A.UYGULAMA_ADI} — sohbet", url=adres, js_api=api, width=1600, height=1040,
                                    min_size=(1180, 740), background_color="#f0f0f0")
    api.pencere_bagla(pencere)
    kayit = {"zaman": time.strftime("%Y-%m-%d %H:%M:%S"), "hatalar": []}

    def js(kod, bekle=0.0):
        pencere.run_js(_ascii(kod))
        if bekle:
            time.sleep(bekle)

    def oku(ifade):
        r = pencere.run_js(_ascii(f"JSON.stringify(({ifade}))"))
        try:
            return json.loads(r) if isinstance(r, str) else r
        except ValueError:
            return r

    def goruntu(yol):
        olay, hata = threading.Event(), []

        def basla():
            try:
                wv = wg.BrowserView.instances[pencere.uid].webview
                al = wv.get_allocation()
                pb = Gdk.pixbuf_get_from_window(wv.get_window(), al.x, al.y, al.width, al.height)
                pb.savev(str(yol), "png", [], [])
            except Exception as e:  # noqa: BLE001
                hata.append(repr(e))
            olay.set()
            return False

        GLib.idle_add(basla)
        olay.wait(30)
        if hata:
            kayit["hatalar"].append(f"{yol.name}: {hata}")
        print("görüntü", yol, flush=True)

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
            js("window.__hata = []; window.addEventListener('error', (e) => window.__hata.push(String(e.message)));")
            api.motoru_yukle()
            bekle_kosul("typeof S !== 'undefined' && S.motor && S.motor.durum === 'hazir'", 120)
            time.sleep(2)
            js("Kabuk.sekmeAc('calisma'); Kabuk.agacSec('ortam');", 1)
            for alan, deger in (("onayar", "Mars üssü"), ("malzeme", "pmma"), ("oksijen", "30"), ("basinc", "70")):
                js(f"alanDegisti({json.dumps(alan)}, {json.dumps(deger)});", 0.4)
            js("window.__coz = 0; cozHizli().then(() => { window.__coz = 1; });", 0.3)
            bekle_kosul("window.__coz === 1", 300)
            js("Kabuk.sekmeAc('calisma'); Kabuk.agacSec('r-llm');", 1.5)
            bekle_kosul("S.sohbet.erisim !== null", 20)
            kayit["erisim"] = oku("S.sohbet.erisim")
            kayit["kosul"] = oku("S.sonuc.kosul")
            for soru in SORULAR:
                # soruyu kutuya yaz, Enter ile gönder (kullanıcının yolu)
                js(f"(function(){{ var g = document.getElementById('sohbetGiris'); g.value = {json.dumps(soru)}; "
                   "g.dispatchEvent(new Event('input', {bubbles: true})); "
                   "g.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})); })();", 1.0)
                if soru == SORULAR[2] and k.ek:
                    goruntu(Path(k.ek) / "sohbet_bekliyor.png")
                    kayit["bekle_kutu_kapali"] = oku("document.getElementById('sohbetGiris').disabled")
                bekle_kosul("!S.sohbet.bekle", 300)
                time.sleep(0.8)
            kayit["mesajlar"] = oku("S.sohbet.mesajlar")
            js("document.getElementById('sohbetGiris').scrollIntoView({block: 'end'});", 1.0)
            goruntu(cikti / "chat.png")
            # girdi değişince: eski vaka + kutu kapalı
            js("alanDegisti('oksijen', '25');", 1.0)
            kayit["girdi_degisti"] = oku("{kapali: document.getElementById('sohbetGiris').disabled, "
                                         "eski: document.querySelectorAll('.sohbet-satir.eski').length}")
            if k.ek:
                js("document.getElementById('sohbetGiris').scrollIntoView({block: 'end'});", 0.6)
                goruntu(Path(k.ek) / "sohbet_girdi_degisti.png")
            js("alanDegisti('oksijen', '30');", 0.6)
            # internetsiz: erişim sınaması başarısız -> kutu kapalı, mesaj
            js("S.sohbet.erisim = false; S.sohbet.erisimSebep = 'bağlantı yok (sınama)'; llmGorseli();", 0.8)
            kayit["cevrimdisi"] = oku("{kapali: document.getElementById('sohbetGiris').disabled, "
                                      "mesaj: (document.querySelector('.sohbet .uyari-satir') || {}).textContent}")
            if k.ek:
                js("document.getElementById('sohbetGiris').scrollIntoView({block: 'end'});", 0.6)
                goruntu(Path(k.ek) / "sohbet_cevrimdisi.png")
            kayit["js_hatalari"] = oku("window.__hata")
        except Exception as e:  # noqa: BLE001
            kayit["hatalar"].append(repr(e))
        finally:
            (cikti / "chat.json").write_text(json.dumps(kayit, ensure_ascii=False, indent=1), encoding="utf-8")
            shutil.rmtree(gecici, ignore_errors=True)
            pencere.destroy()

    A.pywebview_hazirla(gui)
    webview.start(surucu, gui=gui)
    print("hatalar:", kayit["hatalar"])


if __name__ == "__main__":
    main()
