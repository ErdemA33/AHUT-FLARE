#!/usr/bin/env python3
"""screenshot.py — uygulamayı (Linux, GTK) açar, sekmeleri gezer, örnek vakaları ARAYÜZ ÜZERİNDEN çözer ve
her ekranın görüntüsünü alır. Arayüze dokunmaz; yalnız var olan JS fonksiyonlarını çağırır.

    .venv/bin/python screenshot.py [--cikti ../of_visual/ekran]

Görüntüler GTK penceresinin kendi tamponundan alınır (Wayland'da ekran yakalama izni gerekmez).
Çözülen vakaların özeti <cikti>/dashboard_cases.json'a yazılır.
"""
import argparse
import json
import sys
import threading
import time
from pathlib import Path

BURASI = Path(__file__).resolve().parent
sys.path.insert(0, str(BURASI))
import ahut_flare as A  # noqa: E402  (ortam değişkenlerini ve yolları ayarlar)

VAKALAR = [
    ("pmma_mars", "PMMA · Mars %30 O2 · 70 kPa",
     [("onayar", "Mars üssü"), ("malzeme", "pmma"), ("oksijen", "30"), ("basinc", "70")]),
    ("metanol_iss", "metanol · ISS", [("onayar", "ISS"), ("malzeme", "methanol")]),
    ("etilen_iss", "etilen · ISS (numune tipi seçilmeden)", [("onayar", "ISS"), ("malzeme", "ethylene")]),
    ("etilen_iss_gaz", "etilen · ISS · yakıt türü gaz", [("onayar", "ISS"), ("malzeme", "ethylene"),
                                                        ("yakit_turu", "gaz")]),
    ("lexan_iss", "Lexan · ISS (kütüphane eşlemesi)", [("onayar", "ISS"), ("malzeme", "__diger"), ("malzemeAd", "Lexan")]),
]
SONUC_DUGUMLERI = ["r-ozet", "r-motor", "r-guven", "r-oksijen", "r-harita", "r-akis", "r-deney", "r-adimlar", "r-sinirlama",
                   "r-llm", "r-render", "r-dunya"]


def _ascii(kod):
    """pywebview GTK evaluate_js uzunluğu karakter sayısıyla verir (WebKit bayt bekler): ASCII dışı karakter içeren
    betik sondan kesilir. \\uXXXX kaçışı JS dizgilerinde ve adlarda geçerlidir."""
    return "".join(c if ord(c) < 128 else "\\u%04x" % ord(c) for c in kod)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--cikti", default=str(BURASI.parent / "of_visual" / "screen"))
    a.add_argument("--llmsiz", action="store_true", help="yapay zeka yorumu isteme")
    a.add_argument("--dil", choices=("tr", "en"), default="tr", help="arayüz dili (görüntü adlarına _en eklenir)")
    a.add_argument("--videosuz", action="store_true",
                   help="video oynatma adımını atla (GPU'suz Xephyr'de oynayan video WebKit'i kilitliyor)")
    k = a.parse_args()
    main.llmsiz = k.llmsiz
    dil = k.dil
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

    for klasor in (A.VERI, A.VERI / "vakalar", A.RENDER):
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
        yol = cikti / f"dashboard_{ad}{'' if dil == 'tr' else '_en'}.png"
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
            if not bekle_kosul("typeof S !== 'undefined' && S.motor && S.motor.durum === 'hazir'", 120):
                kayit["hatalar"].append("motor ekranda 'hazir' olmadı")
            time.sleep(2)
            if oku("DIL") != dil:                    # görüntü dili --dil ile seçilir
                js(f"dilSec('{dil}'); yenidenCiz();", 1)
            js("Kabuk.sekmeAc('baslangic'); baslangicCiz();", 2)
            goruntu("01_baslangic")
            for i, (ad, baslik, alanlar) in enumerate(VAKALAR):
                js("Kabuk.sekmeAc('calisma'); Kabuk.agacSec('ortam');", 1)
                for alan in ("numune_tipi", "kalinlik", "yakit_turu"):     # önceki vakadan kalan elle girdiler
                    js(f"alanDegisti('{alan}', '');", 0.1)
                for alan, deger in alanlar:
                    js(f"alanDegisti({json.dumps(alan)}, {json.dumps(deger)});", 0.4)
                js("Kabuk.agacSec('malzeme');", 1)
                goruntu(f"02_kurulum_{ad}")
                if i == 0:
                    for dg in ("ortam", "numune"):
                        js(f"Kabuk.agacSec('{dg}');", 1)
                        goruntu(f"02_girdi_{ad}_{dg}")
                js("window.__cozBitti = 0; cozHizli().then(() => { window.__cozBitti = 1; })"
                   ".catch((e) => { window.__cozBitti = 'hata: ' + e; });", 0.3)
                if i == 0:
                    goruntu("03_cozum_suruyor")
                bekle_kosul("window.__cozBitti !== 0", 300)
                durum = oku("window.__cozBitti")
                time.sleep(1.5)
                ozet = oku("S.sonuc ? {kosul: S.sonuc.kosul, sure_sn: S.sonuc.sure_sn, tahmin: S.sonuc.tahmin} : null")
                kayit["vakalar"][ad] = {"baslik": baslik, "coz": durum, "sonuc": ozet}
                dugumler = SONUC_DUGUMLERI if i == 0 else ["r-ozet", "r-guven", "r-motor"]
                for d in dugumler:
                    var = oku(f"agacDugumVar('{d}')")
                    if not var:
                        continue
                    js(f"Kabuk.agacSec('{d}');", 1.5 if d != "r-render" else 3)
                    goruntu(f"04_sonuc_{ad}_{d[2:]}")
                    if d == "r-render" and not getattr(main, "videosuz", False):   # bir de video seç (liste bir GIF'le açılıyor)
                        js("S.renderSecili = 'n-heptane_g0_o21_p101.3_sizinti-3b-4g_dogrulanmadi.mp4'; "
                           "renderGorseli();", 4)
                        goruntu(f"04_sonuc_{ad}_render_video")
                        kayit["render_video"] = oku("(function(){ var v = document.querySelector('video'); "
                                                    "return v ? {src: v.currentSrc, hazir: v.readyState, "
                                                    "sure: v.duration, hata: v.error && v.error.code} : null; })()")
                        # videoyu durdur ve bırak: GPU'suz X sunucusunda (Xephyr) oynayan video WebKit içerik sürecini kilitliyor
                        js("document.querySelectorAll('video').forEach((v) => { v.pause(); v.removeAttribute('src'); v.load(); }); "
                           "S.renderSecili = (S.render.find((x) => x.tur !== 'video') || {}).ad || null;", 1)
            if not getattr(main, "llmsiz", False):
                # yapay zeka yorumu (EVREN, ~25 s): son vaka için; sonra girdiyi değiştirip eski yorumun gizlendiğini göster
                js("Kabuk.sekmeAc('calisma'); Kabuk.agacSec('r-llm'); llmIste();", 2)
                bekle_kosul("S.llm.durum === 'geldi' || S.llm.durum === 'hata'", 180)
                js("Kabuk.agacSec('r-llm'); llmGorseli();", 1.5)
                goruntu("04b_llm_yorum")
                kayit["llm"] = oku("{durum: S.llm.durum, uzunluk: (S.llm.metin || '').length}")
                js("alanDegisti('oksijen', '25'); Kabuk.sekmeAc('calisma'); Kabuk.agacSec('r-llm'); llmGorseli();", 1.5)
                goruntu("04c_llm_girdi_degisti")
                js("alanDegisti('oksijen', '21');", 0.5)
            js("Kabuk.sekmeAc('calisma'); Kabuk.agacSec('cozum');", 1)
            goruntu("05_cozum_son")
            js("Kabuk.sekmeAc('calisma'); Kabuk.agacSec('r-ozet'); Kabuk.altSec('gunluk');", 1.5)
            goruntu("05b_gunluk_adimlar")
            js("Kabuk.altSec('mesaj');", 0.5)
            js("Kabuk.sekmeAc('kutuphane'); kutuphaneCiz();", 2)
            goruntu("06_kutuphane")
            js("ktpGorunum = 'malzemeler'; mlzTur = ''; kutuphaneCiz();", 2.5)
            goruntu("06b_kutuphane_malzemeler")
            kayit["malzeme_sayisi"] = oku("MLZ && MLZ.malzemeler ? MLZ.malzemeler.length : null")
            js("mlzAyrinti('pmma');", 1.5)
            goruntu("06c_malzeme_pmma")
            js("Kabuk.pencereKapat(); mlzTur = 'sivi'; kutuphaneCiz();", 1.5)
            goruntu("06d_kutuphane_sivilar")
            js("mlzAyrinti('ethanol');", 1.5)
            goruntu("06e_malzeme_etanol")
            js("Kabuk.pencereKapat(); mlzTur = 'gaz'; ktpAra = ''; kutuphaneCiz();", 1.5)
            goruntu("06f_kutuphane_gazlar")
            # 9) kullanıcı malzemesi: LLM önerisiyle form -> onayla -> listede -> tahminde tanınır
            js("Kabuk.pencereKapat(); mlzTur = ''; kutuphaneCiz(); kullaniciMalzemeFormu('aerogel', null, null);", 1)
            if not getattr(main, "llmsiz", False):
                js("document.querySelector('#kmOner').click();", 2)
                bekle_kosul("!!document.querySelector('#kmOner') && !document.querySelector('#kmOner').disabled", 150)
                time.sleep(1)
            goruntu("06g_kullanici_malzeme_form")
            kayit["kullanici_form"] = oku("{ad: (document.querySelector('#kmAd')||{}).value, yakit: (document.querySelector('#kmYakit')||{}).value, "
                                          "benzer: (document.querySelector('#kmBenzer')||{}).value}")
            js("document.querySelector('#kmYakit').value = document.querySelector('#kmYakit').value || 'kati'; "
               "document.querySelector('#pencereIc [data-pd=\"2\"]').click();", 2.5)
            kayit["kullanici_kayit_hata"] = oku("(document.querySelector('#kmHata')||{}).textContent || null")
            js("Kabuk.pencereKapat(); ktpGorunum = 'malzemeler'; ktpAra = 'aerogel'; kutuphaneCiz();", 2)
            goruntu("06h_kullanici_malzeme_listede")
            js("kullaniciMalzemeFormu('blorpium', {durum: 'baglanti_yok', sebep: 'URLError: ağ yok'}, null);", 1)
            goruntu("06i_form_internetsiz")
            js("kullaniciMalzemeFormu('asdfgh', {durum: 'reddedildi', sebep: 'LLM bunu gerçek bir malzeme olarak tanımadı'}, null);", 1)
            goruntu("06j_form_reddedildi")
            js("Kabuk.pencereKapat(); ktpAra = ''; ktpGorunum = 'vakalar'; mlzTur = ''; kutuphaneCiz();", 1)
            # onaylı kullanıcı malzemesiyle çözüm
            js("Kabuk.sekmeAc('calisma'); Kabuk.agacSec('ortam'); alanDegisti('onayar', 'ISS'); "
               "alanDegisti('malzeme', '__diger'); alanDegisti('malzemeAd', 'aerogel');", 1)
            js("window.__cozBitti = 0; cozHizli().then(() => { window.__cozBitti = 1; });", 0.5)
            bekle_kosul("window.__cozBitti !== 0", 300)
            time.sleep(1.5)
            js("Kabuk.sekmeAc('calisma'); Kabuk.agacSec('r-ozet');", 1.5)
            goruntu("06k_kullanici_malzeme_cozum")
            kayit["vakalar"]["aerogel_iss"] = {"sonuc": oku("S.sonuc ? {tahmin: S.sonuc.tahmin} : null")}
            js("Kabuk.sekmeAc('topluluk');", 1)
            bekle_kosul("S.toplulukBilgi !== null", 40)
            time.sleep(1)
            goruntu("07_topluluk")
            kayit["topluluk_bilgi"] = oku("S.toplulukBilgi")
            kayit["mesajlar"] = oku("S.mesajlar.slice(-20)")
        except Exception as e:  # noqa: BLE001
            kayit["hatalar"].append(f"sürücü: {type(e).__name__}: {e}")
        finally:
            (cikti / "dashboard_cases.json").write_text(json.dumps(kayit, ensure_ascii=False, indent=1),
                                                          encoding="utf-8")
            time.sleep(1)
            pencere.destroy()

    A.pywebview_hazirla(gui)
    webview.start(surucu, gui=gui)
    print(json.dumps({"goruntu": len(kayit["goruntuler"]), "hatalar": kayit["hatalar"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
