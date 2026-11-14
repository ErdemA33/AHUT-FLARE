#!/usr/bin/env python3
"""ofm_arayuz_test.py — OpenFOAM motoru arayüzü uçtan uca (Xephyr): sahte koşular içe aktarılır → vaka çözülür →
"Ayrıntılı Motor (OpenFOAM)" düğümü, Motor Ayrıntıları yan yana tablo, Kütüphane > Ayrıntılı koşular, "OpenFOAM motoruyla koş"
(kuyruk: hazırlık + kısa başlatma, sonra İPTAL; en çok 2 çekirdek). Tek ekran görüntüsü: düğüm.
    DISPLAY=:77 GDK_BACKEND=x11 .venv/bin/python ofm_arayuz_test.py
"""
import argparse, json, os, sys, tempfile, threading, time
from pathlib import Path

BURASI = Path(__file__).resolve().parent
ANA = BURASI.parent
sys.path.insert(0, str(BURASI)); sys.path.insert(0, str(ANA))
TMP = Path(tempfile.mkdtemp(prefix="ofm_ui_"))
os.environ["AHUT_OFM_KOK"] = str(TMP / "ofm")          # Kopru bunu setdefault ile korur
os.environ["AHUT_RENDER"] = str(TMP / "render"); (TMP / "render").mkdir()
import ahut_flare as A  # noqa: E402
import ofm_test as bt  # noqa: E402


def _ascii(k):
    return "".join(c if ord(c) < 128 else "\\u%04x" % ord(c) for c in k)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--cikti", default=str(ANA / "of_gorsel" / "ekran" / "ofm"))
    k = a.parse_args()
    cikti = Path(k.cikti); cikti.mkdir(parents=True, exist_ok=True)
    import webview, gi
    gi.require_version("Gtk", "3.0"); gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, GLib
    from webview.platforms import gtk as wg
    from cekirdek.kopru import Kopru
    import ofm_ice_aktar as ia, ofm_motor as bm

    ham = TMP / "ham"; ham.mkdir()
    bt.sahte_kati(ham); bt.sahte_sivi(ham); bt.sahte_gaz(ham)
    for ad in ("sahte_saffire_2b", "sahte_heptan_damla", "sahte_metan_alev"):
        ia.ice_aktar(ham / ad, bm.kok() / "ofm_gelen", bm.kok() / "ofm_sonuclar", TMP / "render")

    gui = A.pencere_motoru()
    adres, oneki = A.pencere_adresi(gui)
    api = Kopru(surum=A.SURUM, arayuz=A.ARAYUZ, motor_yolu=A.MOTOR, veri=TMP / "veri", render=TMP / "render",
                anahtar=A.ANAHTAR, mock=False, ornekler=A.ORNEKLER, site=A.SITE, render_oneki=oneki)
    pen = webview.create_window("ofm", url=adres, js_api=api, width=1600, height=980, min_size=(1180, 740))
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

    def coz(alanlar):
        js("Kabuk.sekmeAc('calisma'); Kabuk.agacSec('ortam');", 1)
        for alan in ("numune_tipi", "kalinlik", "yakit_turu"): js(f"alanDegisti('{alan}', '');", 0.1)
        for alan, deger in alanlar: js(f"alanDegisti({json.dumps(alan)}, {json.dumps(deger)});", 0.4)
        js("window.__b = 0; cozHizli().then(() => { window.__b = 1; }).catch(() => { window.__b = 'hata'; });", 0.3)
        bekle("window.__b !== 0", 180); time.sleep(1.5)

    def surucu():
        try:
            pen.events.loaded.wait(60); api.motoru_yukle()
            bekle("typeof S !== 'undefined' && S.motor && S.motor.durum === 'hazir'", 120); time.sleep(2)
            if oku("DIL") != "tr": js("dilSec('tr'); yenidenCiz();", 1)
            # 1) sahte katı koşuya yakın vaka: ISS, sibal, akış 25 cm/s
            js("alanDegisti('akisBilinmiyor', false);", 0.2)
            coz([("onayar", "ISS"), ("malzeme", "sibal"), ("akisBilinmiyor", False), ("akis", "25")])
            kayit["tahmin_ofm"] = oku("(S.sonuc.tahmin.ofm ? {kosu: S.sonuc.tahmin.ofm.kosu, mesafe: S.sonuc.tahmin.ofm.mesafe, agirlik: S.sonuc.tahmin.ofm.agirlik} : null)")
            kayit["agirliklar"] = oku("S.sonuc.tahmin.agirliklar")
            kayit["dugum_var"] = oku("agacDugumVar('r-ofm')")
            js("Kabuk.agacSec('r-ofm');", 1.5)
            kayit["ofm_kartlar"] = oku("document.querySelectorAll('#gorsel .kart').length")
            kayit["ofm_metin"] = oku("(document.querySelector('#gorsel .kart') || {}).innerText")
            kayit["karsilastirma_satir"] = oku("document.querySelectorAll('#gorsel table.veri')[2] ? document.querySelectorAll('#gorsel table.veri')[2].querySelectorAll('tbody tr').length : 0")
            kayit["egri_svg"] = oku("document.querySelectorAll('#gorsel svg polyline').length")
            time.sleep(0.5); goruntu("ofm_dugum")
            # 2) Motor Ayrıntıları: yan yana tablo
            js("Kabuk.agacSec('r-motor');", 2)
            kayit["yan_yana"] = oku("Array.from(document.querySelectorAll('#gorsel h3')).map((h) => h.textContent).filter((t) => /OpenFOAM/.test(t))")
            # 3) Kütüphane > Ayrıntılı koşular
            js("ktpGorunum = 'ofm'; Kabuk.sekmeAc('kutuphane'); kutuphaneCiz();", 2.5)
            kayit["ktp_satir"] = oku("document.querySelectorAll('#ek-kutuphane table.veri tbody tr').length")
            # 4) vaka yok: heptan yerçekimi Dünya -> OpenFOAM yok
            coz([("onayar", "Dünya"), ("malzeme", "pmma")])
            js("Kabuk.agacSec('r-ofm');", 1.5)
            kayit["yok_metin"] = oku("(document.querySelector('#gorsel .bos b') || {}).textContent")
            # 5) OpenFOAM motoruyla koş: iletişim kutusu
            js("ofmKosDialog();", 2)
            kayit["dialog"] = oku("(document.querySelector('#pencereIc .pencere-ic') || {}).innerText")
            js("document.querySelector('#pencereIc [data-pkapat]').click();", 0.5)
            # 6) kuyruğa gerçekten ekle (Python tarafı), kısa bekle, iptal
            kon = api.ofm_kos_kontrol("kati"); kayit["kos_kontrol"] = {x: kon.get(x) for x in ("hazir", "foam_calisiyor", "uyarilar", "neden")}
            if kon.get("hazir"):
                r = api.ofm_kos_baslat("kati"); kayit["kos_baslat"] = {x: r.get(x) for x in ("id", "hata")}
                time.sleep(25)
                l = [x for x in api.kosular()["kosular"] if x["id"] == r.get("id")]
                kayit["kos_durum_25s"] = l[0]["durum"] if l else None
                iz = api.izle(r["id"], None, False); kayit["kos_log_satir"] = len(iz.get("satirlar", [])); kayit["kos_log_ofset"] = iz.get("ofset")
                kayit["iptal"] = api.kosu_iptal(r["id"])
                time.sleep(4)
                l = [x for x in api.kosular()["kosular"] if x["id"] == r.get("id")]
                kayit["kos_durum_iptal_sonrasi"] = l[0]["durum"] if l else None
                bd = (Path(r["dizin"]) / "system" / "decomposeParDict").read_text()
                kayit["alt_alan"] = [ln for ln in bd.splitlines() if "numberOfSubdomains" in ln]
        except Exception as e:  # noqa: BLE001
            kayit["hatalar"].append(repr(e))
        finally:
            (cikti / "ofm_ui_sonuc.json").write_text(json.dumps(kayit, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            pen.destroy()

    A.pywebview_hazirla(gui)
    webview.start(surucu, gui=gui)
    return 0 if not kayit["hatalar"] else 1


if __name__ == "__main__":
    sys.exit(main())
