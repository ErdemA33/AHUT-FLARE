#!/usr/bin/env python3
"""monitor_test.py — Çözüm İzleyici'yi ARAYÜZ ÜZERİNDEN sınar (Xephyr gerekir; render düğümüne girmez, video yok).

    Xephyr :77 -screen 1700x1060 -nolisten tcp -br &
    DISPLAY=:77 GDK_BACKEND=x11 .venv/bin/python monitor_test.py [--cikti ../of_visual/screen/izleyici]

1) hızlı çözümde günlük akıyor mu  2) sahte OpenFOAM logu (kısa betik) kuyruğa girer: günlük satırları, grafik serisi,
ilerleme, bitince TAMAM + bildirim  3) sistem paneli değerleri `sensors`/df/meminfo ile yan yana. Tek ekran görüntüsü.
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile, threading, time
from pathlib import Path

BURASI = Path(__file__).resolve().parent
sys.path.insert(0, str(BURASI))
import ahut_flare as A  # noqa: E402

SAHTE = r'''#!/bin/bash
# sahte foam günlüğü: 400 adım, her adım 0.06 s gerçek, 0.25 s "ClockTime"
mkdir -p postProcessing/cellMax\(T\)/0
echo "# Time	max(T)" > "postProcessing/cellMax(T)/0/volFieldValue.dat"
t=0; ck=0
for i in $(seq 1 400); do
  t=$(awk -v t=$t 'BEGIN{printf "%.7g", t+0.0025}'); ck=$(awk -v c=$ck 'BEGIN{printf "%.3f", c+0.25}')
  co=$(awk -v i=$i 'BEGIN{printf "%.5g", 0.05+0.002*i}')
  echo "Courant Number mean: 0.001 max: $co"
  echo "deltaT = 0.0025"
  echo "Time = ${t}s"
  echo "DILUPBiCGStab:  Solving for Ux, Initial residual = 1e-5, Final residual = 1e-9, No Iterations 1"
  [ $i = 150 ] && echo "--> FOAM Warning : sahte uyarı: bounding h"
  [ $((i % 20)) = 0 ] && awk -v t=$t -v i=$i 'BEGIN{printf "%s\t%.1f\n", t, 300+i*5}' >> "postProcessing/cellMax(T)/0/volFieldValue.dat"
  echo "ExecutionTime = $ck s  ClockTime = $ck s"
  echo
  sleep 0.06
done
echo "End"
'''


def _ascii(k):
    return "".join(c if ord(c) < 128 else "\\u%04x" % ord(c) for c in k)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--cikti", default=str(BURASI.parent / "of_visual" / "screen" / "monitor"))
    k = a.parse_args()
    cikti = Path(k.cikti); cikti.mkdir(parents=True, exist_ok=True)
    import webview, gi
    gi.require_version("Gtk", "3.0"); gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, GLib
    from webview.platforms import gtk as wg
    from core.bridge import Kopru

    gui = A.pencere_motoru()
    adres, oneki = A.pencere_adresi(gui)
    api = Kopru(surum=A.SURUM, arayuz=A.ARAYUZ, motor_yolu=A.MOTOR, veri=A.VERI, render=A.RENDER,
                anahtar=A.ANAHTAR, mock=False, ornekler=A.ORNEKLER, site=A.SITE, render_oneki=oneki)
    pen = webview.create_window("izleyici", url=adres, js_api=api, width=1600, height=980, min_size=(1180, 740))
    api.pencere_bagla(pen)
    kayit = {"hatalar": []}
    tmp = Path(tempfile.mkdtemp(prefix="sahte_kosu_"))
    (tmp / "system").mkdir(); (tmp / "system" / "controlDict").write_text("endTime 1.0;\n")
    (tmp / "sahte.sh").write_text(SAHTE)

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

    def surucu():
        try:
            pen.events.loaded.wait(60); api.motoru_yukle()
            bekle("typeof S !== 'undefined' && S.motor && S.motor.durum === 'hazir'", 120); time.sleep(2)
            if oku("DIL") != "tr": js("dilSec('tr'); yenidenCiz();", 1)
            # ---- 1) hızlı çözüm: günlük akıyor mu
            js("Kabuk.sekmeAc('calisma'); Kabuk.agacSec('ortam');", 1)
            for alan, deger in [("onayar", "Mars üssü"), ("malzeme", "pmma")]: js(f"alanDegisti({json.dumps(alan)}, {json.dumps(deger)});", 0.4)
            js("IZ.elle = true; IZ.kaynak = 'hizli'; Kabuk.agacSec('cozum');", 1.5)
            js("window.__b = 0; cozHizli().then(() => { window.__b = 1; }).catch(() => { window.__b = 'hata'; });", 0.2)
            js("Kabuk.agacSec('cozum');", 0.3)                      # çözüm bitince ağaç r-ozet'e geçiyor: izleyiciye dön
            bekle("window.__b !== 0", 120); time.sleep(0.3)
            js("Kabuk.agacSec('cozum');", 1.0)
            kayit["hizli_satir_sayisi"] = oku("IZ.log.hizli.length")
            kayit["hizli_ilk"] = oku("IZ.log.hizli.slice(0, 3).map((r) => r.metin)")
            kayit["hizli_dom"] = oku("document.querySelectorAll('#izLog .izs').length")
            kayit["bos_metin"] = oku("T('sonuc.yokHenuzAlt')")
            # ---- 2) sahte foam koşusu kuyruğa
            r = api.kosu_ekle("sahte-foam-kosusu", str(tmp), ["bash", "sahte.sh"], "log.foamRun", 1)
            kid = r["id"]; kayit["kosu_id"] = kid
            time.sleep(7)
            js(f"IZ.kaynak = {json.dumps(kid)}; IZ.elle = true; izKaynakDegisti(); izPoll(true, true);", 8)
            kayit["foam_dom"] = oku("document.querySelectorAll('#izLog .izs').length")
            kayit["foam_son"] = oku("(IZ.log[IZ.kaynak] || []).slice(-2).map((r) => r.metin)")
            kayit["foam_uyari"] = oku("(IZ.log[IZ.kaynak] || []).filter((r) => r.seviye === 'uyari').map((r) => r.metin)")
            kayit["seri_n"] = oku("(IZ.seri[IZ.kaynak] || []).length")
            kayit["seri_son"] = oku("(IZ.seri[IZ.kaynak] || []).slice(-1)[0]")
            kayit["ozet"] = oku("IZ.ozet[IZ.kaynak]")
            kayit["grafik_svg"] = oku("document.querySelectorAll('#izGraf svg').length")
            # ---- 3) sistem paneli: arayüz değerleri ve sensors/df/meminfo
            js("Kabuk.altSec('sistem');", 2.5)
            kayit["arayuz_sistem"] = oku("{ek: S.sisEk, cpu: S.sisSon && {toplam: S.sisSon.toplam, n: (S.sisSon.cekirdek || []).length, bellek: S.sisSon.bellek, takas: S.sisSon.takas, yuk: S.sisSon.yuk}}")
            so = subprocess.run(["sensors"], capture_output=True, text=True).stdout
            kayit["sensors_package"] = re.findall(r"Package id 0:\s+\+?([\d.]+)", so)
            kayit["sensors_fan"] = re.findall(r"(cpu_fan|gpu_fan):\s+(\d+) RPM", so)
            kayit["df_bos_GB"] = round(shutil.disk_usage(A.VERI).free / 1073741824, 2)
            mem = dict(re.findall(r"(\w+):\s+(\d+) kB", open("/proc/meminfo").read()))
            kayit["meminfo"] = {"toplam_GB": round(int(mem["MemTotal"]) / 1048576, 2), "kullanilan_GB": round((int(mem["MemTotal"]) - int(mem["MemAvailable"])) / 1048576, 2)}
            kayit["load"] = os.getloadavg()
            kayit["profil"] = open("/sys/firmware/acpi/platform_profile").read().strip()
            time.sleep(1)
            goruntu("monitor_fake_run")
            # ---- düzen: sağ şerit yok, Mesajlar durum çubuğundan, Grafik|Tablo geçişi
            kayit["serit_var"] = oku("!!document.getElementById('altSekme')")
            js("document.getElementById('dMesaj').click();", 0.8)
            kayit["mesaj_popup_acik"] = oku("!document.getElementById('mesajPopup').hidden && document.querySelectorAll('#mesajPopup .alt-satir').length")
            goruntu("layout_message_popup")
            js("document.getElementById('dMesaj').click();", 0.3)
            js("document.querySelector('[data-gt=tablo]').click();", 0.8)
            kayit["tablo_satir"] = oku("document.querySelectorAll('#gorsel table.veri tbody tr').length")
            js("document.querySelector('[data-gt=grafik]').click();", 0.8)
            kayit["grafik_svg_gt"] = oku("document.querySelectorAll('#gorsel svg').length")
            js("document.querySelector('[data-gt=gorunum]').click();", 0.8)
            kayit["gorunume_donus"] = oku("!!document.getElementById('izKok')")
            # ---- 4) bitince TAMAM + bildirim
            bekle(f"(IZ.kosular.find((x) => x.id === {json.dumps(kid)}) || {{}}).durum === 'TAMAM'", 40)
            kayit["durum"] = oku(f"(IZ.kosular.find((x) => x.id === {json.dumps(kid)}) || {{}}).durum")
            kayit["mesaj_kosu"] = oku("S.mesajlar.filter((m) => /Koşu|Run/.test(m.metin)).map((m) => m.metin)")
            kayit["gecmis_satir"] = oku("S.gunluk.filter((x) => x.tur === 'Çöz' || x.tur === 'Koşu').length")
        except Exception as e:  # noqa: BLE001
            kayit["hatalar"].append(repr(e))
        finally:
            (cikti / "monitor_result.json").write_text(json.dumps(kayit, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            pen.destroy()

    A.pywebview_hazirla(gui)
    webview.start(surucu, gui=gui)
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if not kayit["hatalar"] else 1


if __name__ == "__main__":
    sys.exit(main())
