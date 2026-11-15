#!/usr/bin/env python3
"""detailed_test.py — Çözüm türü (Ayrıntılı/Hızlı) arayüz denemesi (Xephyr; ~5 dk):
 1) varsayılan Ayrıntılı  2) PMMA Mars → desteklenmiyor penceresi → "Hızlı çözümle devam"
 3) SIBAL Saffire: başlatma penceresi (çekirdek varsayılanı nproc−2), koşu başlar, ön tahmin bandı, 1 dk sonra İPTAL
 4) SIBAL Mars (g>0): ilk dakikada kaldırma denetimi (p_rgh), sonra İPTAL
 5) sahte biten koşu: otomatik analiz → Risk Özeti'nde ana sonuç OpenFOAM motorundan (+ doğrulama etiketi)
En çok 2 çekirdek (gerçek koşular), nice 19. Ekran görüntüleri: ayrintili_on_tahmin.png, ayrintili_sonuc.png
    DISPLAY=:77 GDK_BACKEND=x11 .venv/bin/python detailed_test.py
"""
import argparse, json, os, sys, tempfile, threading, time
from pathlib import Path

BURASI = Path(__file__).resolve().parent
ANA = BURASI.parent
sys.path.insert(0, str(BURASI)); sys.path.insert(0, str(ANA))
TMP = Path(tempfile.mkdtemp(prefix="ayr_ui_"))
os.environ["AHUT_OFM_KOK"] = str(TMP / "ofm")
os.environ["AHUT_RENDER"] = str(TMP / "render"); (TMP / "render").mkdir()
import ahut_flare as A  # noqa: E402
import ofm_test as bt  # noqa: E402


def _ascii(k):
    return "".join(c if ord(c) < 128 else "\\u%04x" % ord(c) for c in k)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--cikti", default=str(ANA / "of_visual" / "screen" / "detailed"))
    k = a.parse_args()
    cikti = Path(k.cikti); cikti.mkdir(parents=True, exist_ok=True)
    import webview, gi
    gi.require_version("Gtk", "3.0"); gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, GLib
    from webview.platforms import gtk as wg
    from core.bridge import Kopru

    gui = A.pencere_motoru()
    adres, oneki = A.pencere_adresi(gui)
    api = Kopru(surum=A.SURUM, arayuz=A.ARAYUZ, motor_yolu=A.MOTOR, veri=TMP / "data", render=TMP / "render",
                anahtar=A.ANAHTAR, mock=False, ornekler=A.ORNEKLER, site=A.SITE, render_oneki=oneki)
    pen = webview.create_window("ayrintili", url=adres, js_api=api, width=1600, height=980, min_size=(1180, 740))
    api.pencere_bagla(pen)
    kayit = {"hatalar": []}

    def js(kod, bekle=0.0):
        pen.run_js(_ascii(kod)); time.sleep(bekle)

    def oku(i):
        r = pen.run_js(_ascii(f"JSON.stringify(({i}))"))
        try: return json.loads(r) if isinstance(r, str) else r
        except ValueError: return r

    def bekle(kod, sure=120):
        t0 = time.time()
        while time.time() - t0 < sure:
            try:
                if oku(kod): return True
            except Exception: pass
            time.sleep(0.5)
        return False

    def goruntu(ad):
        yol = cikti / f"{ad}.png"; ev = threading.Event()
        def f():
            try:
                wv = wg.BrowserView.instances[pen.uid].webview; al = wv.get_allocation()
                Gdk.pixbuf_get_from_window(wv.get_window(), al.x, al.y, al.width, al.height).savev(str(yol), "png", [], [])
            except Exception as e: kayit["hatalar"].append(f"{ad}: {e!r}")
            ev.set(); return False
        GLib.idle_add(f); ev.wait(30)

    def girdiler(alanlar):
        js("Kabuk.sekmeAc('calisma'); Kabuk.agacSec('ortam');", 1)
        for alan in ("numune_tipi", "kalinlik", "yakit_turu"): js(f"alanDegisti('{alan}', '');", 0.1)
        for alan, deger in alanlar: js(f"alanDegisti({json.dumps(alan)}, {json.dumps(deger)});", 0.4)

    def dialog_bekle(secici, sure=60):
        return bekle(f"!document.getElementById('ortu').hidden && !!document.querySelector({json.dumps(secici)})", sure)

    def surucu():
        try:
            pen.events.loaded.wait(60); api.motoru_yukle()
            bekle("typeof S !== 'undefined' && S.motor && S.motor.durum === 'hazir'", 120); time.sleep(2)
            if oku("DIL") != "tr": js("dilSec('tr'); yenidenCiz();", 1)
            # 1) varsayılan
            kayit["varsayilan_tur"] = oku("S.cozumTuru"); kayit["arac_secici"] = oku("document.getElementById('cozumTuru').value")
            kayit["ayar_alani"] = oku("(function(){ Kabuk.agacSec('cozumAyar'); return null; })()")
            time.sleep(1); kayit["ayar_secenekleri"] = oku("Array.from(document.querySelectorAll('#ayrintilar select')).map((s) => Array.from(s.options).map((o) => o.textContent))")
            # 2) PMMA Mars -> desteklenmiyor
            girdiler([("onayar", "Mars üssü"), ("malzeme", "pmma")])
            js("window.__c = 0; coz().then(() => { window.__c = 1; });", 0.5)
            kayit["pmma_dialog"] = dialog_bekle("#pencereIc .pencere-ic") and oku("document.querySelector('#pencereIc').innerText")
            js("document.querySelector('#pencereIc [data-pd]').click();", 0.5)   # Hızlı çözümle devam
            bekle("S.sonuc && S.sonuc.tahmin && !S.cozuluyor", 60); time.sleep(1)
            kayit["pmma_hizli_sonuc"] = oku("S.sonuc && S.sonuc.tahmin.girdi.malzeme"); kayit["pmma_ayrintili_durum"] = oku("S.ayrintili && S.ayrintili.durum")
            # 3) SIBAL Saffire (g=0): başlat, 60 s, iptal
            girdiler([("onayar", "ISS"), ("malzeme", "sibal"), ("akisBilinmiyor", False), ("akis", "25")])
            js("window.__c = 0; coz().then(() => { window.__c = 1; });", 0.5)
            kayit["sibal_dialog_acik"] = dialog_bekle("#ayCek", 60)
            kayit["cekirdek_varsayilan"] = oku("Number(document.getElementById('ayCek').value)"); kayit["nproc"] = os.cpu_count()
            kayit["uyarilar_dialog"] = oku("Array.from(document.querySelectorAll('#pencereIc .uyari-satir')).map((e) => e.textContent)")
            js("document.getElementById('ayCek').value = '2'; document.getElementById('ayCek').dispatchEvent(new Event('input'));", 1.5)
            kayit["sure_metni"] = oku("document.getElementById('aySure').textContent")
            js("document.querySelector('#pencereIc [data-pd]').click();", 1)          # Başlat
            bekle("S.ayrintili && S.ayrintili.durum === 'calisiyor'", 60)
            t0 = time.time(); kid = oku("S.ayrintili.id"); kayit["kosu_id"] = kid
            time.sleep(25)
            js("Kabuk.agacSec('r-ozet');", 2)
            kayit["banner"] = oku("(document.getElementById('ayrBanner') || {}).textContent || null")
            kayit["on_tahmin_var"] = oku("!!S.sonuc")
            goruntu("ayrintili_on_tahmin")
            time.sleep(max(0, 62 - (time.time() - t0)))
            d = api.ofm_ayrintili_durum(kid)
            kayit["kosu_60s"] = {"durum": d["durum"], "t": (d.get("ilerleme") or {}).get("t"), "yuzde": (d.get("ilerleme") or {}).get("yuzde")}
            kayit["iptal1"] = api.kosu_iptal(kid); time.sleep(4)
            js("izPoll(true);", 4)
            kayit["durum_iptal1"] = oku("S.ayrintili && S.ayrintili.durum")
            # 4) SIBAL Mars (g>0): ilk dakikada kaldırma denetimi
            girdiler([("onayar", "Mars üssü"), ("malzeme", "sibal"), ("akisBilinmiyor", False), ("akis", "25")])
            js("window.__c = 0; coz().then(() => { window.__c = 1; });", 0.5)
            dialog_bekle("#ayCek", 60)
            js("document.getElementById('ayCek').value = '2'; document.getElementById('ayOn').checked = false;", 0.5)
            js("document.querySelector('#pencereIc [data-pd]').click();", 1)
            bekle("S.ayrintili && S.ayrintili.durum === 'calisiyor'", 60)
            kid2 = oku("S.ayrintili.id"); kayit["kosu_id_g"] = kid2
            bekle("S.ayrintili && S.ayrintili.kontrol", 110)
            kayit["kaldirma_kontrol"] = oku("S.ayrintili && S.ayrintili.kontrol")
            kayit["kaldirma_mesaj"] = oku("S.mesajlar.filter((m) => /Kaldırma denetimi/.test(m.metin)).map((m) => m.metin)")
            kayit["g_dosyasi"] = (Path(api.izleyici.kosu(kid2)["dizin"]) / "constant/fluid/g").read_text() if api.izleyici.kosu(kid2) else None
            kayit["on_tahmin_kapali_bekleme"] = oku("(function(){ Kabuk.agacSec('r-ozet'); return null; })()"); time.sleep(1.5)
            kayit["bekleme_metni"] = oku("(document.querySelector('#gorsel .bos b') || {}).textContent || null")
            kayit["iptal2"] = api.kosu_iptal(kid2); time.sleep(4); js("izPoll(true);", 4)
            # 5) sahte biten koşu: otomatik analiz + ana sonuç OpenFOAM motorundan
            ham = TMP / "ham"; ham.mkdir()
            c = bt.sahte_kati(ham, "sahte_ayr_saffire")
            (c / "fake.sh").write_text("#!/bin/bash\nfor i in 1 2 3 4 5 6; do echo \"Courant Number mean: 0.001 max: 0.05\"; echo \"deltaT = 2e-05\"; echo \"Time = 0.0$i s\"; "
                                       "echo \"ExecutionTime = $i s  ClockTime = $i s\"; sleep 0.5; done\n")
            r = api.izleyici.kosu_ekle("sahte ayrıntılı koşu", str(c), ["bash", "fake.sh"], "log.run", 1, ice_aktar=True, bitis_s=12.0)
            girdiler([("onayar", "ISS"), ("malzeme", "sibal"), ("akisBilinmiyor", False), ("akis", "25")])
            js("window.__h = 0; cozHizli().then(() => { window.__h = 1; });", 0.5); bekle("window.__h === 1", 60)
            js(f"S.ayrintili = {{ id: {json.dumps(r['id'])}, kosu: 'sahte_ayr_saffire', durum: 'calisiyor', kosul: kosul(), cekirdek: 1, bitis_s: 12, ilerleme: null, kontrol: null, kayit: null, ofm: null }}; "
               "Kabuk.agacSec('r-ozet'); agacYenile();", 1)
            ok = bekle("S.ayrintili && S.ayrintili.durum === 'bitti'", 60); kayit["sahte_bitti"] = ok; time.sleep(2)
            js("Kabuk.agacSec('r-ozet');", 2)
            kayit["ana_sonuc_var"] = oku("!!document.querySelector('#gorsel .ayr-ana')")
            kayit["ana_sonuc_metin"] = oku("(document.querySelector('#gorsel .ayr-ana') || {}).innerText")
            kayit["kaynak_etiketi"] = oku("Array.from(document.querySelectorAll('.sonuc-blok span')).map((e) => e.textContent).filter((t) => /Ayrıntılı|Detailed/.test(t))")
            kayit["karsilastirma_baslik"] = oku("Array.from(document.querySelectorAll('#gorsel h3')).map((h) => h.textContent).filter((t) => /Karşılaştırma/.test(t))")
            kayit["ofm_node"] = (js("Kabuk.agacSec('r-ofm');", 1.5), oku("(document.querySelector('#gorsel .kart h3') || {}).textContent"))[1]
            js("Kabuk.agacSec('r-ozet');", 1.5)
            goruntu("ayrintili_sonuc")
        except Exception as e:  # noqa: BLE001
            kayit["hatalar"].append(repr(e))
        finally:
            (cikti / "ayrintili_sonuc.json").write_text(json.dumps(kayit, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            pen.destroy()

    A.pywebview_hazirla(gui)
    webview.start(surucu, gui=gui)
    return 0 if not kayit["hatalar"] else 1


if __name__ == "__main__":
    sys.exit(main())
