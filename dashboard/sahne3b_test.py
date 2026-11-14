#!/usr/bin/env python3
"""sahne3b_test.py — 3B görüntüleyici denemesi (Xephyr): PMMA ISS (levha), metanol ISS (damla), metan (sızıntı / gözenekli küre),
SIBAL (OpenFOAM vakası, gerçek boyut + ağ), sizinti3d_ince/mars 3B sonucu (izo + kesit + zaman), ParaView'da aç (açılır, sonra PID ile kapatılır).
    DISPLAY=:77 GDK_BACKEND=x11 .venv/bin/python sahne3b_test.py
"""
import argparse, json, os, signal, sys, threading, time
from pathlib import Path

BURASI = Path(__file__).resolve().parent
ANA = BURASI.parent
sys.path.insert(0, str(BURASI))
import ahut_flare as A  # noqa: E402


def _ascii(k):
    return "".join(c if ord(c) < 128 else "\\u%04x" % ord(c) for c in k)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--cikti", default=str(ANA / "of_gorsel" / "ekran" / "sahne3b"))
    k = a.parse_args()
    cikti = Path(k.cikti); cikti.mkdir(parents=True, exist_ok=True)
    import webview, gi
    gi.require_version("Gtk", "3.0"); gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, GLib
    from webview.platforms import gtk as wg
    from cekirdek.kopru import Kopru
    gui = A.pencere_motoru()
    adres, oneki = A.pencere_adresi(gui)
    api = Kopru(surum=A.SURUM, arayuz=A.ARAYUZ, motor_yolu=A.MOTOR, veri=A.VERI, render=A.RENDER,
                anahtar=A.ANAHTAR, mock=False, ornekler=A.ORNEKLER, site=A.SITE, render_oneki=oneki)
    pen = webview.create_window("3b", url=adres, js_api=api, width=1600, height=980, min_size=(1180, 740))
    api.pencere_bagla(pen)
    kayit = {"hatalar": []}

    def js(kod, bekle=0.0):
        pen.run_js(_ascii(kod)); time.sleep(bekle)

    def oku(i):
        r = pen.run_js(_ascii(f"JSON.stringify(({i}))"))
        try: return json.loads(r) if isinstance(r, str) else r
        except ValueError: return r

    def bekle(kod, sure=60):
        t0 = time.time()
        while time.time() - t0 < sure:
            try:
                if oku(kod): return True
            except Exception: pass
            time.sleep(0.4)
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

    def girdi(alanlar, dugum):
        js("Kabuk.sekmeAc('calisma'); Kabuk.agacSec('ortam');", 0.6)
        for alan in ("numune_tipi", "kalinlik", "yakit_turu"): js(f"alanDegisti('{alan}', '');", 0.1)
        for alan, deger in alanlar: js(f"alanDegisti({json.dumps(alan)}, {json.dumps(deger)});", 0.3)
        js(f"Kabuk.agacSec('{dugum}');", 2.5)

    def sahne_ozet():
        return oku("({tuval: !!document.querySelector('#gorsel canvas.s3-tuval'), nesne: S3.g.geo.children.length, ok: S3.g.ok.children.length,"
                   " etiketler: S3.etiketler.map((e) => e.metin), not: (document.querySelector('.s3-not') || {}).textContent, vurgu: S3.vurgu})")

    def surucu():
        try:
            pen.events.loaded.wait(60); api.motoru_yukle()
            bekle("typeof S !== 'undefined' && S.motor && S.motor.durum === 'hazir'", 120); time.sleep(2)
            if oku("DIL") != "tr": js("dilSec('tr'); yenidenCiz();", 1)
            kayit["three"] = oku("window.THREE ? THREE.REVISION : null")
            girdi([("onayar", "ISS"), ("malzeme", "pmma")], "malzeme")
            kayit["pmma"] = sahne_ozet(); goruntu("01_pmma_iss_levha")
            js("alanDegisti('kalinlik', '3');", 1.5)
            kayit["pmma_kalinlik_3mm"] = oku("S3.etiketler.map((e) => e.metin).filter((t) => /kalınlık/.test(t))")
            js("Kabuk.agacSec('akis');", 1.5); kayit["akis_vurgu"] = oku("S3.vurgu")
            girdi([("onayar", "ISS"), ("malzeme", "methanol")], "numune")
            kayit["metanol"] = sahne_ozet(); goruntu("02_metanol_iss_damla")
            girdi([("onayar", "ISS"), ("malzeme", "methane"), ("numune_tipi", "porous_sphere")], "numune")
            kayit["metan"] = sahne_ozet(); goruntu("03_metan_sizinti")
            girdi([("onayar", "ISS"), ("malzeme", "sibal"), ("akisBilinmiyor", False), ("akis", "25")], "malzeme")
            js("document.querySelector('[data-s3=izgara]').click();", 3)
            kayit["sibal"] = sahne_ozet(); kayit["sibal_izgara_kenar"] = oku("S3.g.izgara.children.length ? S3.g.izgara.children[0].geometry.attributes.position.count / 2 : 0")
            goruntu("04_sibal_vaka_ag")
            js("document.querySelector('[data-s3=izgara]').click();", 0.5)
            # 3B sonuç: n-heptan Mars (sizinti3d_ince/mars)
            girdi([("onayar", "Mars üssü"), ("malzeme", "n-heptane")], "malzeme")
            js("window.__h = 0; cozHizli().then(() => { window.__h = 1; });", 0.3); bekle("window.__h === 1", 90)
            js("S3.son.liste = null; Kabuk.agacSec('r-3b');", 4)
            bekle("S3.son.meta && S3.son.kareler.size > 0", 60); time.sleep(1.5)
            kayit["sonuc"] = oku("({sec: S3.son.sec, ad: S3.son.meta && S3.son.meta.ad, kare: S3.son.i, izo: S3.g.sonuc.children.filter((o) => o.userData.tur === 'izo').map((o) => o.geometry.attributes.position.count),"
                                 " kesit: S3.g.sonuc.children.some((o) => o.userData.tur === 'kesit'), damla: S3.son.kareler.get(S3.son.i).damla_sayisi, olcek: !document.querySelector('.s3-olcek').hidden,"
                                 " bant: (document.querySelector('.s3-bant') || {}).textContent})")
            js("s3KareGoster(9);", 2.5)
            kayit["zaman_9"] = oku("({i: S3.son.i, t: S3.son.meta.zamanlar[S3.son.i], izo: S3.g.sonuc.children.filter((o) => o.userData.tur === 'izo').length, damla: S3.son.kareler.get(9).damla_sayisi})")
            js("var s = document.getElementById('s3Kesit'); s.value = '0.62'; s.dispatchEvent(new Event('input'));", 1)
            goruntu("05_sonuc_mars_izo_kesit")
            t0 = time.time(); js("s3IzoCiz();", 0.1); kayit["izo_sure_ms"] = oku("(function(){ var a = performance.now(); s3IzoCiz(); return Math.round(performance.now() - a); })()")
            js("var a = document.getElementById('s3Alan'); a.value = 'O2'; a.dispatchEvent(new Event('change'));", 2)
            kayit["alan_O2"] = oku("({alan: S3.son.alan, izo: S3.g.sonuc.children.filter((o) => o.userData.tur === 'izo').length, olcek: document.querySelector('.s3-olcek b').textContent})")
            js("document.getElementById('s3Oynat').click();", 2.2); kayit["oynat_ilerledi"] = oku("S3.son.i"); js("document.getElementById('s3Oynat').click();", 0.3)
            # hızlı çözüm, 3B sonuç yok: PMMA ISS
            girdi([("onayar", "ISS"), ("malzeme", "pmma")], "malzeme")
            js("window.__h = 0; cozHizli().then(() => { window.__h = 1; });", 0.3); bekle("window.__h === 1", 90)
            js("S3.son.sec = null; S3.son.otomatik = true; Kabuk.agacSec('r-3b');", 2.5)
            kayit["sonucsuz_bant"] = oku("(document.querySelector('.s3-bant') || {}).textContent")
            kayit["sonucsuz_geo"] = oku("S3.g.geo.visible && S3.g.geo.children.length > 0")
            # ParaView'da aç (sizinti3d_ince/mars: pv_3b.py ile) -> açılır, PID ile kapatılır
            r = api.paraview_ac(str(ANA / "of_kosular" / "sizinti3d_ince" / "mars"))
            kayit["paraview"] = {x: r.get(x) for x in ("tamam", "aciklama", "komut", "hata")}
            if r.get("pid"):
                time.sleep(8)
                try:
                    os.kill(r["pid"], 0); kayit["paraview_calisti"] = True
                    os.killpg(os.getpgid(r["pid"]), signal.SIGTERM)
                except ProcessLookupError:
                    kayit["paraview_calisti"] = False
        except Exception as e:  # noqa: BLE001
            kayit["hatalar"].append(repr(e))
        finally:
            (cikti / "sahne3b_sonuc.json").write_text(json.dumps(kayit, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            pen.destroy()

    A.pywebview_hazirla(gui)
    webview.start(surucu, gui=gui)
    return 0 if not kayit["hatalar"] else 1


if __name__ == "__main__":
    sys.exit(main())
