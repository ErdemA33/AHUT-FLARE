#!/usr/bin/env python3
"""end_to_end.py — uçtan uca deneme: uygulamayı açar, senaryoları ARAYÜZ ÜZERİNDEN çalıştırır, her biri için
ekran görüntüsü alır ve sonuçların özetini yazar.

    DISPLAY=:77 GDK_BACKEND=x11 .venv/bin/python end_to_end.py [--cikti ../of_visual/screen/end_to_end]

Ekran kilitliyken GTK penceresi çizilmez; bu yüzden iç içe X sunucusu (Xephyr :77) içinde çalıştırılır:
    Xephyr :77 -screen 1700x1060 -nolisten tcp -br &
Senaryolar: PMMA Mars %30 70 kPa, metanol ISS, heptan Mars, etilen, metan, Lexan, IPA, kevlar, hidrazin, asdfgh,
internetsiz PMMA (EVREN'e ulaşılamaz), parametre süpürmesi, vaka kaydet/aç, topluluk kaydı ekle-onayla-dışa aktar,
videolar.
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

COZUMLER = [  # (ad, alanlar, gösterilecek düğümler)
    ("pmma_mars_30_70", [("onayar", "Mars üssü"), ("malzeme", "pmma"), ("oksijen", "30"), ("basinc", "70")], ["r-ozet", "r-motor", "r-guven"]),
    ("metanol_iss", [("onayar", "ISS"), ("malzeme", "methanol")], ["r-ozet", "r-motor"]),
    ("heptan_mars", [("onayar", "Mars üssü"), ("malzeme", "n-heptane")], ["r-ozet", "r-motor"]),
    ("etilen_iss", [("onayar", "ISS"), ("malzeme", "ethylene")], ["r-ozet", "r-motor"]),
    ("metan_iss", [("onayar", "ISS"), ("malzeme", "methane")], ["r-ozet", "r-motor"]),
    ("lexan_iss", [("onayar", "ISS"), ("malzeme", "__diger"), ("malzemeAd", "Lexan")], ["r-ozet"]),
    ("ipa_iss", [("onayar", "ISS"), ("malzeme", "__diger"), ("malzemeAd", "IPA")], ["r-ozet"]),
    ("kevlar_iss", [("onayar", "ISS"), ("malzeme", "__diger"), ("malzemeAd", "kevlar")], ["r-ozet"]),
    ("hidrazin_iss", [("onayar", "ISS"), ("malzeme", "__diger"), ("malzemeAd", "hidrazin")], ["r-ozet", "r-motor"]),
    ("asdfgh", [("onayar", "ISS"), ("malzeme", "__diger"), ("malzemeAd", "asdfgh")], ["r-ozet"]),
]


def _ascii(kod):
    """pywebview GTK evaluate_js uzunluğu karakter sayısıyla verir (WebKit bayt bekler): ASCII dışı karakter içeren
    betik sondan kesilir. \\uXXXX kaçışı JS dizgilerinde ve adlarda geçerlidir."""
    return "".join(c if ord(c) < 128 else "\\u%04x" % ord(c) for c in kod)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--cikti", default=str(BURASI.parent / "of_visual" / "screen" / "end_to_end"))
    a.add_argument("--videosuz", action="store_true", help="video oynatmayı atla (Xephyr)")
    k = a.parse_args()
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

    gui = A.pencere_motoru()
    adres, render_oneki = A.pencere_adresi(gui)
    api = Kopru(surum=A.SURUM, arayuz=A.ARAYUZ, motor_yolu=A.MOTOR, veri=A.VERI, render=A.RENDER, anahtar=A.ANAHTAR,
                mock=False, ornekler=A.ORNEKLER, site=A.SITE, render_oneki=render_oneki)
    pencere = webview.create_window(f"{A.UYGULAMA_ADI} — uçtan uca", url=adres, js_api=api, width=1600, height=980,
                                    min_size=(1180, 740), background_color="#f0f0f0")
    api.pencere_bagla(pencere)
    kayit = {"zaman": time.strftime("%Y-%m-%d %H:%M:%S"), "goruntuler": [], "senaryolar": {}, "hatalar": []}

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

    def bekle(kod, sure=180):
        t0 = time.time()
        while time.time() - t0 < sure:
            try:
                if oku(kod):
                    return True
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.5)
        return False

    def goruntu(ad):
        yol = cikti / f"{ad}.png"
        olay, hata = threading.Event(), []

        def basla():
            try:
                wv = wg.BrowserView.instances[pencere.uid].webview
                al = wv.get_allocation()
                pb = Gdk.pixbuf_get_from_window(wv.get_window(), al.x, al.y, al.width, al.height)
                pb.savev(str(yol), "png", [], []) if pb else hata.append("pixbuf boş")
            except Exception as e:  # noqa: BLE001
                hata.append(repr(e))
            olay.set()
            return False
        GLib.idle_add(basla)
        olay.wait(30)
        (kayit["hatalar"].append(f"{ad}: {hata}") if hata else kayit["goruntuler"].append(yol.name))
        print("görüntü", yol.name, flush=True)

    def coz(alanlar):
        js("Kabuk.sekmeAc('calisma'); Kabuk.agacSec('ortam');", 0.8)
        for alan in ("numune_tipi", "kalinlik", "yakit_turu"):
            js(f"alanDegisti('{alan}', '');", 0.05)
        for alan, deger in alanlar:
            js(f"alanDegisti({json.dumps(alan)}, {json.dumps(deger)});", 0.3)
        js("window.__b = 0; cozHizli().then(() => { window.__b = 1; }).catch((e) => { window.__b = 'hata: ' + e; });", 0.3)
        bekle("window.__b !== 0", 300)
        time.sleep(1.2)
        return oku("S.sonuc ? {kosul: S.sonuc.kosul, t: S.sonuc.tahmin} : null")

    def ozet(s):
        t = (s or {}).get("t") or {}
        a2 = next((x for x in t.get("adimlar") or [] if x.get("no") == 2), {})
        return {"risk_model": t.get("risk_seviyesi"), "p_model": t.get("yanma_ihtimali"), "p_birlesik": t.get("yanma_birlesik"),
                "agirliklar": t.get("agirliklar"), "motor": t.get("motor_kaynagi"),
                "motor_yanma": (t.get("motor") or {}).get("yanma"), "guven_v2": (t.get("guven_v2") or {}).get("skor"),
                "bant": (t.get("guven_v2") or {}).get("bant"), "tanima": a2.get("karar"),
                "tanima_kaynagi": (a2.get("ayrinti") or {}).get("kaynak"), "girdi": t.get("girdi"),
                "uyarilar": t.get("uyarilar")}

    def surucu():
        try:
            pencere.events.loaded.wait(60)
            api.motoru_yukle()
            bekle("typeof S !== 'undefined' && S.motor && S.motor.durum === 'hazir'", 120)
            time.sleep(2)
            dil0 = oku("DIL")
            if dil0 != "tr":                         # görüntüler Türkçe
                js("dilSec('tr'); yenidenCiz();", 1)
            for i, (ad, alanlar, dugumler) in enumerate(COZUMLER, 1):
                s = coz(alanlar)
                kayit["senaryolar"][ad] = ozet(s)
                for d in dugumler:
                    js(f"Kabuk.sekmeAc('calisma'); Kabuk.agacSec('{d}');", 1.5)
                    goruntu(f"{i:02d}_{ad}_{d[2:]}")
            # 11) internetsiz PMMA: EVREN adresi süreç içinde ulaşılamaz yapılır (çözüm yereldir, yorum alınamaz)
            import llm_analysis as llm_analysis
            eski_url = llm_analysis.API_URL
            llm_analysis.API_URL = "http://127.0.0.1:9/v1/chat/completions"
            try:
                s = coz([("onayar", "ISS"), ("malzeme", "pmma")])
                js("Kabuk.sekmeAc('calisma'); Kabuk.agacSec('r-ozet');", 1.2)
                goruntu("11_offline_pmma_summary")
                js("Kabuk.agacSec('r-llm'); llmIste();", 1)
                bekle("S.llm.durum === 'geldi' || S.llm.durum === 'hata'", 200)
                js("Kabuk.agacSec('r-llm'); llmGorseli();", 1.2)
                goruntu("11_offline_pmma_llm")
                kayit["senaryolar"]["internetsiz_pmma"] = dict(ozet(s), llm=oku("{durum: S.llm.durum, metin: S.llm.metin}"))
            finally:
                llm_analysis.API_URL = eski_url
            # 12) parametre süpürmesi (oksijen 14–30, PMMA ISS)
            js("Kabuk.sekmeAc('calisma'); Kabuk.agacSec('supurme'); alanDegisti('sup_parametre', 'oksijen');", 1)
            js("supur();", 1)
            bekle("S.supurme && !S.supurme.calisiyor && !!S.supurme.sonuc", 400)
            js("Kabuk.agacSec('supurme');", 1.5)
            goruntu("12_parameter_sweep")
            kayit["senaryolar"]["supurme"] = oku("S.supurme.sonuc ? {n: S.supurme.sonuc.noktalar.length, hata: S.supurme.sonuc.hata_sayisi, "
                                                "sure: S.supurme.sonuc.sure_sn} : null")
            # 13) vaka kaydet / aç
            js("S.baslik = 'uçtan uca deneme · PMMA ISS'; S.baslikOto = false; window.__k = 0; "
               "vakaKaydet().then(() => { window.__k = 1; }).catch((e) => { window.__k = 'hata: ' + e; });", 0.5)
            bekle("window.__k !== 0 && S.vakaId", 60)
            vid = oku("S.vakaId")
            kayit["kaydet_mesaj"] = oku("{k: window.__k, mesajlar: S.mesajlar.slice(0, 3)}")
            js("yeniVaka();", 1)
            js("Kabuk.sekmeAc('kutuphane'); ktpGorunum = 'vakalar'; kutuphaneCiz();", 1.5)
            goruntu("13_case_saved_library")
            js(f"vakaYukle({json.dumps(vid)});", 2.5)
            goruntu("13_case_opened")
            kayit["senaryolar"]["vaka"] = {"id": vid, "acilan": oku("S.vakaId"), "baslik": oku("S.baslik")}
            # 14) topluluk deney kaydı: ekle -> moderatör onayı -> dışa aktar
            js("Kabuk.sekmeAc('topluluk'); topGorunum = 'deney'; TV.liste = null; toplulukCiz();", 2)
            js("tvFormu();", 1)
            for alan, deger in (("malzeme", "pmma"), ("g", "0.0001"), ("oksijen_yuzde", "17"), ("basinc_kpa", "101.3"),
                                ("sonuc", "sondu"), ("kaynak_turu", "kendi_deney"), ("kaynak", "uçtan uca deneme defteri s. 1"),
                                ("ekleyen", "deneme")):
                js(f"document.querySelector('[data-tv=\"{alan}\"]').value = {json.dumps(deger)};", 0.05)
            goruntu("14_community_form")
            js("document.querySelector('#pencereIc [data-pd=\"1\"]').click();", 2.5)
            js("TV.moderator = true; TV.moderatorAd = 'moderatör (deneme)'; toplulukCiz();", 1.5)
            son = oku("(TV.liste || []).length ? TV.liste[0].id : null")
            if son is not None:
                js(f"API.tvOnayla({json.dumps(son)}, 'moderatör (deneme)').then(() => tvTazele());", 2)
            paket = str(BURASI.parent / "of_visual" / "screen" / "end_to_end" / "community_package.json")
            js(f"API.tvDisaAktar({json.dumps(paket)}).then((r) => {{ TV.ozet = 'Paket yazıldı: ' + (r.yol || r.hata); tvTazele(); }});", 2.5)
            goruntu("14_community_approved_export_imported")
            kayit["senaryolar"]["topluluk"] = {"son_id": son, "liste": oku("(TV.liste || []).slice(0, 5).map((x) => ({id: x.id, malzeme: x.malzeme, durum: x.durum, etiketler: x.etiketler}))"),
                                               "paket": paket}
            # 15) videolar (GPU'suz Xephyr'de oynayan video WebKit'i kilitliyor: --videosuz ile yalnız liste)
            if getattr(main, "videosuz", False):
                js("Kabuk.sekmeAc('calisma'); Kabuk.agacSec('r-render');", 2)
                goruntu("15_video_list")
                kayit["senaryolar"]["video"] = oku("{dosya: S.render.length, video: S.render.filter((x) => x.tur === 'video').length}")
                raise StopIteration
            js("Kabuk.sekmeAc('calisma'); Kabuk.agacSec('r-render'); S.renderSecili = 'methane_g0_o21_p101.3_metan-3b-4g_dogrulanmadi.mp4'; renderGorseli();", 4)
            goruntu("15_video")
            kayit["senaryolar"]["video"] = oku("(function(){ var v = document.querySelector('video'); return v ? {src: v.currentSrc, hazir: v.readyState, sure: v.duration, hata: v.error && v.error.code} : null; })()")
        except StopIteration:
            pass
        except Exception as e:  # noqa: BLE001
            kayit["hatalar"].append(f"sürücü: {type(e).__name__}: {e}")
        finally:
            (cikti / "end_to_end.json").write_text(json.dumps(kayit, ensure_ascii=False, indent=1), encoding="utf-8")
            time.sleep(1)
            pencere.destroy()

    A.pywebview_hazirla(gui)
    webview.start(surucu, gui=gui)
    print(json.dumps({"goruntu": len(kayit["goruntuler"]), "hatalar": kayit["hatalar"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
