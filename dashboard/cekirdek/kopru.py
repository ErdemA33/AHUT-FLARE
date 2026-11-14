"""Arayüz ile Python arasındaki köprü.

Buradaki her genel (alt çizgiyle başlamayan) metot, ekranda
`pywebview.api.<ad>(...)` olarak çağrılabilir ve bir Promise döndürür.
HTTP, port ya da yerel sunucu yoktur; çağrı doğrudan fonksiyon çağrısıdır.

Dönen her değer `temizle()` ile JSON'a yazılabilir hale getirilir:
numpy tipleri düz Python'a, NaN/inf None'a çevrilir.
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from .depo import Depo
from . import github as gh
from . import sistem
from .izleyici import Izleyici
from . import sahne

KOSUL_ANAHTARLARI = ("malzeme", "oksijen", "basinc", "g", "akis", "kalinlik",
                     "numune_tipi", "yakit_turu", "akis_yonu", "seyreltici")
SAYISAL = ("oksijen", "basinc", "g", "akis", "kalinlik")
SUPURULEBILIR = ("oksijen", "basinc", "g", "akis", "kalinlik")
SUPURME_EN_FAZLA = 120          # ölçüldü: nokta başına 0,7–1,2 sn (sönme sınırı taraması yüzünden)


def _simdi_metni() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def temizle(x):
    """NaN/inf -> None; numpy tiplerini düz Python'a çevirir."""
    if isinstance(x, dict):
        return {str(k): temizle(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [temizle(v) for v in x]
    if hasattr(x, "item") and not isinstance(x, (str, bytes)):
        try:
            x = x.item()
        except Exception:
            pass
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def kosul_hazirla(ham: dict) -> dict:
    """Ekrandan gelen değerleri tahmin() parametrelerine çevirir; boş -> None."""
    k = {}
    for ad in KOSUL_ANAHTARLARI:
        v = (ham or {}).get(ad)
        if isinstance(v, str):
            v = v.strip() or None
        if v is not None and ad in SAYISAL:
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise ValueError(f"'{ad}' sayı olmalı")
        k[ad] = v
    if k["seyreltici"] is None:
        k["seyreltici"] = "n2"
    for zorunlu in ("malzeme", "oksijen", "basinc", "g"):
        if k[zorunlu] is None:
            raise ValueError(f"'{zorunlu}' zorunlu")
    if k["g"] <= 0 or k["basinc"] <= 0 or not 0 < k["oksijen"] <= 100:
        raise ValueError("g > 0, basınç > 0 ve 0 < oksijen ≤ 100 olmalı")
    if k["kalinlik"] is not None and k["kalinlik"] <= 0:
        raise ValueError("kalınlık 0'dan büyük olmalı")
    if k["akis"] is not None and k["akis"] < 0:
        raise ValueError("akış negatif olamaz")
    return k


def _calistir(f, *a, **kw) -> dict:
    """Bir model çağrısını süresiyle birlikte sarar; hata uygulamayı düşürmez."""
    bas = time.perf_counter()
    try:
        return {"veri": temizle(f(*a, **kw)), "sure_sn": round(time.perf_counter() - bas, 3)}
    except Exception as e:
        return {"hata": f"{type(e).__name__}: {e}", "sure_sn": round(time.perf_counter() - bas, 3)}


class Kopru:
    def __init__(self, *, surum, arayuz: Path, motor_yolu: Path, veri: Path,
                 render: Path, anahtar: Path, mock=False, acilis_dosyasi=None,
                 ornekler: Path | None = None, site: Path | None = None, render_oneki: str | None = None):
        self.surum = surum
        self.arayuz = arayuz
        self.motor_yolu = motor_yolu
        self.render_klasoru = render
        # Pencere yerel HTTP üzerinden açıldıysa (Linux/macOS) render dosyaları file:// yerine bu önekle verilir
        self.render_oneki = render_oneki
        self.anahtar = anahtar
        self.mock = mock
        self.acilis_dosyasi = acilis_dosyasi
        self.depo = Depo(veri, ornekler_kaynak=ornekler)
        self.site_klasoru = site
        self.onbellek_dosyasi = veri / "topluluk_onbellek.json"
        self._gh_kilit = threading.Lock()
        sistem.islemci()   # psutil'in ilk ölçümü referanssız 0 döner; sayacı şimdi başlat
        self._pencere = None
        self._B = None
        self._motor_durumu = {"durum": "yukleniyor", "mesaj": None, "mock": mock, "sure_sn": None}
        self._llm_kilit = threading.Lock()
        self._ana_kok = veri.parent.parent                                  # depo kökü (of_*.py betikleri)
        self.izleyici = Izleyici(veri, self._ana_kok / "of_kosular")
        os.environ.setdefault("AHUT_OFM_KOK", str(veri / "ofm"))     # OpenFOAM motoru: içe aktarılan koşular veri/ofm altında
        os.environ.setdefault("AHUT_RENDER", str(render))
        self.izleyici.bitis_kancasi = self._ofm_bitti
        self.izleyici.kontrol_kancasi = self._ofm_kontrol
        self.izleyici.disa_aktar_kancasi = self._disa_aktar_kancasi     # koşu TAMAM bitince 3B dışa aktarma (arka planda)
        self.proje_kok = veri.parent.parent if (veri.parent.parent / "of_3b_disa_aktar.py").exists() else Path(__file__).resolve().parents[2]

    # ------------------------------------------------------------ kurulum
    def pencere_bagla(self, pencere) -> None:
        self._pencere = pencere

    def _olay(self, ad: str, veri=None) -> None:
        """Python tarafından ekrana haber gönderir (ilerleme, durum değişimi)."""
        if self._pencere is None:
            return
        betik = f"window.AHUT && window.AHUT.olay({json.dumps(ad)}, {json.dumps(temizle(veri))})"
        try:
            # pywebview 5+ evaluate_js betiği eval() ile sarar; index.html'deki CSP 'unsafe-eval' içermediği için
            # (ör. Linux/GTK'da) olaylar hiç ulaşmaz ve ekran "model yükleniyor"da kalır. run_js betiği olduğu gibi çalıştırır.
            if hasattr(self._pencere, "run_js"):
                self._pencere.run_js(betik)
            else:
                self._pencere.evaluate_js(betik)
        except Exception:
            pass

    def motoru_yukle(self) -> dict:
        """Modeli arka planda yükler ve ilk çağrıyı yaparak önbelleği ısıtır."""
        bas = time.perf_counter()
        try:
            # os.chdir YOK: backend dosya yollarını kendi klasörüne (__file__) bağlıyor; yazılabilir dosyalar
            # YANGIN_VERI_KLASORU'na gidiyor (ahut_flare.py ayarlar). Süreç genelinde klasör değiştirmek
            # göreli yollu açılış dosyalarını ve diğer iş parçacıklarını bozabilirdi.
            if str(self.motor_yolu) not in sys.path:
                sys.path.insert(0, str(self.motor_yolu))
            self._olay("motor", {"durum": "yukleniyor", "adim": "modüller"})
            if self.mock:
                import mock_backend as B
            else:
                import tahmin as B
                try:
                    import llm_analiz
                    llm_analiz.ANAHTAR_DOSYASI = self.anahtar
                except Exception:
                    pass
            self._B = B
            if not self.mock:
                self._olay("motor", {"durum": "yukleniyor", "adim": "ısınma"})
                B.tahmin("pmma", 21, 101.3, 1e-4)
            self._motor_durumu = {
                "durum": "hazir", "mesaj": None, "mock": self.mock,
                "sure_sn": round(time.perf_counter() - bas, 2),
            }
        except Exception as e:
            self._motor_durumu = {
                "durum": "hata", "mesaj": f"{type(e).__name__}: {e}", "mock": self.mock,
                "sure_sn": round(time.perf_counter() - bas, 2),
            }
        self._olay("motor", self._motor_durumu)
        return self._motor_durumu

    def _motor(self):
        if self._B is None:
            raise RuntimeError(
                "Model henüz hazır değil."
                if self._motor_durumu["durum"] == "yukleniyor"
                else f"Model yüklenemedi: {self._motor_durumu.get('mesaj')}"
            )
        return self._B

    # ------------------------------------------------------------ açılış
    def hazir(self) -> dict:
        """Ekran açılırken bir kez çağrılır."""
        return temizle({
            "surum": self.surum,
            "motor": self._motor_durumu,
            "ayarlar": self.depo.ayarlar(),
            "profil": self.depo.profil(),
            "vakalar": self.depo.listele(),
            "topluluk": self.depo.topluluk(),
            "render": self._render_listesi(),
            "sistem": {
                "python": sys.version.split()[0],
                "platform": sys.platform,
                "cekirdek_sayisi": os.cpu_count(),
                "anahtar_var": self.anahtar.exists(),
                "render_klasoru": str(self.render_klasoru),
                "veri_klasoru": str(self.depo.veri),
            },
            "acilis_dosyasi": self.acilis_dosyasi,
        })

    def motor_durumu(self) -> dict:
        return temizle(self._motor_durumu)

    def malzeme_tani(self, ad: str) -> dict:
        """LLM çağırmadan tanıma kaynağı: liste | kutuphane | kullanici_kutuphanesi | onbellek | llm_gerekli.
        Arayüz 'llm_gerekli' ise uzun bekleme mesajı ve (9. madde) kullanıcı malzemesi önerisi gösterir."""
        B = self._motor()
        import llm_analiz
        ad = (ad or "").strip()
        if not ad:
            return {"kaynak": "bos"}
        if llm_analiz.malzeme_biliniyor(ad):
            return {"kaynak": "liste", "ad": ad}
        k = B.kutuphanede_bul(ad) if hasattr(B, "kutuphanede_bul") else None
        if k is not None:
            return temizle({"kaynak": "kullanici_kutuphanesi" if k.get("_kaynak") == "kullanici" else "kutuphane",
                            "id": k.get("id"), "ad_tr": k.get("ad"), "durum": k.get("durum"),
                            "motor_benzeri": k.get("motor_benzeri")})
        o = llm_analiz.onbellekten(ad)
        if o:
            return temizle({"kaynak": "onbellek", "durum": o.get("durum"), "benzer_malzeme": o.get("benzer_malzeme")})
        return {"kaynak": "llm_gerekli", "ad": ad}

    def malzeme_kutuphanesi(self) -> dict:
        """Yerleşik malzeme kütüphanesi (motor/malzeme_kutuphanesi.json; malzeme_kutuphanesi_uret.py üretir) +
        kullanıcı malzemeleri (veri/malzemeler_kullanici.json; her kayıtta _kaynak = 'kullanici' ve onay).
        Model gerektirmez; dosya yoksa boş liste döner."""
        yol = self.motor_yolu / "malzeme_kutuphanesi.json"
        try:
            d = json.loads(yol.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            d = {"malzemeler": [], "hata": f"{yol.name} okunamadı: {e}"}
        for m in d.get("malzemeler", []):
            m["_kaynak"] = "kutuphane"
        d["malzemeler"] = d.get("malzemeler", []) + [dict(m, _kaynak="kullanici") for m in self._kullanici_oku()]
        return d

    # ------------------------------------------------------------ kullanıcı malzemeleri (9. madde)
    KULLANICI_DOSYA = "malzemeler_kullanici.json"
    MALZEME_ARALIK = {"yogunluk": (0.05, 25000), "isil_deger": (0, 150), "kaynama_K": (1, 6000), "LOI": (0, 100),
                      "parlama_noktasi_K": (50, 1500), "LFL": (0, 100), "UFL": (0, 100)}
    MALZEME_BIRIM = {"yogunluk": "kg/m3", "isil_deger": "MJ/kg", "kaynama_K": "K", "LOI": "%",
                     "parlama_noktasi_K": "K", "LFL": "% hacim", "UFL": "% hacim"}

    def _kullanici_yolu(self) -> Path:
        return self.depo.veri / self.KULLANICI_DOSYA

    def _kullanici_oku(self) -> list:
        try:
            return json.loads(self._kullanici_yolu().read_text(encoding="utf-8")).get("malzemeler", [])
        except (OSError, ValueError):
            return []

    def _kullanici_yaz(self, liste: list) -> None:
        yol = self._kullanici_yolu()
        gecici = yol.with_suffix(".tmp")
        gecici.write_text(json.dumps({"aciklama": "Kullanıcı malzemeleri (arayüzden). Onaysızlar hiçbir hesaba girmez; "
                                      "onaylılarda yalnız yakıt türü, numune, kalınlık ve benzer malzeme kullanılır, "
                                      "motor ağırlığı 0. Modele ve kalibrasyona girmez.", "malzemeler": liste},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
        gecici.replace(yol)

    def malzeme_oner(self, ad: str) -> dict:
        """LLM önerisi (yakıt türü, numune tipi, benzer malzeme, varsa özellikler). ~15–60 s; internet yoksa
        durum 'baglanti_yok'. Hepsi 'LLM önerisi, doğrulanmadı'; hiçbir hesaba girmez."""
        self._motor()
        import llm_analiz
        ad = (ad or "").strip()
        if not ad:
            return {"durum": "bos"}
        if not self._llm_kilit.acquire(blocking=False):
            return {"durum": "mesgul", "sebep": "Başka bir yapay zeka isteği sürüyor."}
        try:
            return temizle(llm_analiz.malzeme_oner(ad))
        finally:
            self._llm_kilit.release()

    def kullanici_malzeme_kaydet(self, kayit: dict, onay: str = "onaysiz") -> dict:
        """Formdan gelen kaydı doğrular ve yazar. onay: 'onaysiz' | 'onayli'. Hata varsa {'hatalar': [...]}."""
        import re as _re
        B = self._motor()
        k = dict(kayit or {})
        h = []
        ad = str(k.get("ad") or "").strip()
        if not ad:
            h.append("Ad zorunlu.")
        kid = str(k.get("id") or "").strip() or _re.sub(r"[^a-z0-9]+", "_", ad.lower()).strip("_")[:40] or "malzeme"
        es = [str(x).strip() for x in (k.get("es_anlamlilar") or []) if str(x).strip()]
        yerlesik = [x for x in [ad, kid] + es if (lambda r: r is not None and r.get("_kaynak") == "kutuphane")(
            B.kutuphanede_bul(x) if hasattr(B, "kutuphanede_bul") else None)]
        if yerlesik:
            h.append(f"'{yerlesik[0]}' yerleşik kütüphanede zaten var; kullanıcı kaydı onu değiştiremez.")
        if k.get("yakit_turu") not in ("kati", "sivi", "gaz"):
            h.append("Yakıt türü kati / sivi / gaz olmalı.")
        benzer = k.get("motor_benzeri") or None
        import llm_analiz
        if benzer is not None and benzer not in B.MALZEME_VARSAYILAN and not llm_analiz.malzeme_biliniyor(benzer) and not (
                hasattr(B, "kutuphanede_bul") and B.kutuphanede_bul(benzer) is not None):
            h.append(f"Benzer malzeme '{benzer}' bilinen bir malzeme değil.")
        kal = k.get("kalinlik_veya_cap_mm")
        if kal not in (None, ""):
            try:
                kal = float(kal)
                if not 0 < kal < 1000:
                    h.append("Kalınlık/çap 0–1000 mm olmalı.")
            except (TypeError, ValueError):
                h.append("Kalınlık/çap sayı olmalı.")
        else:
            kal = None
        oz = {}
        for alan, v in (k.get("ozellikler") or {}).items():
            if alan not in self.MALZEME_ARALIK or v in (None, "") or (isinstance(v, dict) and v.get("deger") in (None, "")):
                continue
            d = v if isinstance(v, dict) else {"deger": v}
            try:
                x = float(d["deger"])
            except (TypeError, ValueError):
                h.append(f"{alan} sayı olmalı.")
                continue
            lo, hi = self.MALZEME_ARALIK[alan]
            if not lo <= x <= hi:
                h.append(f"{alan} = {x:g} fiziksel aralık dışında ({lo:g}–{hi:g}).")
                continue
            kaynak = str(d.get("kaynak") or "").strip()
            if not kaynak:
                h.append(f"{alan} için kaynak yazın (ör. 'LLM önerisi, doğrulanmadı' ya da makale/veri sayfası).")
            oz[alan] = {"deger": x, "birim": self.MALZEME_BIRIM[alan], "kaynak": kaynak,
                        "llm_onerisi": bool(d.get("llm_onerisi"))}
        if h:
            return {"hatalar": h}
        liste = [m for m in self._kullanici_oku() if m.get("id") != kid]
        yeni = {
            "id": kid, "ad": ad, "ad_en": str(k.get("ad_en") or "").strip() or None, "es_anlamlilar": es,
            "yakit_turu": k["yakit_turu"],
            "varsayilan": {"numune_tipi": k.get("numune_tipi") or None, "kalinlik_veya_cap_mm": kal,
                           "kaynak": "kullanıcı girişi"},
            "motor_benzeri": benzer,
            "eslesme_gerekce": str(k.get("eslesme_gerekce") or "kullanıcı seçimi").strip()
                               + (" (LLM önerisi, doğrulanmadı)" if k.get("benzer_llm") else ""),
            "ozellikler": oz, "durum": "kullanıcı malzemesi", "onay": "onayli" if onay == "onayli" else "onaysiz",
            "uzayda_kullanim": str(k.get("uzayda_kullanim") or "").strip() or None,
            "ekleyen": self.depo.profil().get("ad") or "(isimsiz)", "zaman": _simdi_metni(),
            "llm_onerisi_kullanildi": bool(k.get("llm_onerisi_kullanildi")),
        }
        liste.append(yeni)
        self._kullanici_yaz(liste)
        return temizle({"tamam": True, "kayit": yeni})

    def kullanici_malzeme_disa_aktar(self, yol: str | None = None) -> dict:
        """Kullanıcı malzemelerini paylaşım paketine yazar (Topluluk > Deney verisi'nden de çağrılır)."""
        yol = yol or self._dialog("kaydet", "kullanici_malzemeleri.json", ("JSON (*.json)",))
        if not yol:
            return {"iptal": True}
        liste = self._kullanici_oku()
        Path(yol).write_text(json.dumps({"bicim": "ahut-kullanici-malzemeleri", "surum": 1, "zaman": _simdi_metni(),
                                         "malzemeler": liste}, ensure_ascii=False, indent=1), encoding="utf-8")
        return {"yol": str(yol), "sayi": len(liste)}

    def kullanici_malzeme_ice_aktar(self, yol: str | None = None) -> dict:
        """Paketteki malzemeler HER ZAMAN onaysız girer ve kaydet denetiminden geçer."""
        yol = yol or self._dialog("ac", None, ("JSON (*.json)",))
        if not yol:
            return {"iptal": True}
        try:
            d = json.loads(Path(yol).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            return {"hata": f"Okunamadı: {e}"}
        eklenen, reddedilen = 0, []
        for m in d.get("malzemeler", []):
            k = {"id": m.get("id"), "ad": m.get("ad"), "ad_en": m.get("ad_en"), "es_anlamlilar": m.get("es_anlamlilar"),
                 "yakit_turu": m.get("yakit_turu"), "numune_tipi": (m.get("varsayilan") or {}).get("numune_tipi"),
                 "kalinlik_veya_cap_mm": (m.get("varsayilan") or {}).get("kalinlik_veya_cap_mm"),
                 "motor_benzeri": m.get("motor_benzeri"), "eslesme_gerekce": (m.get("eslesme_gerekce") or "") + " (içe aktarıldı)",
                 "uzayda_kullanim": m.get("uzayda_kullanim"), "ozellikler": m.get("ozellikler") or {}}
            r = self.kullanici_malzeme_kaydet(k, "onaysiz")
            if r.get("hatalar"):
                reddedilen.append({"ad": m.get("ad"), "sebep": "; ".join(r["hatalar"])})
            else:
                eklenen += 1
        return {"eklenen": eklenen, "reddedilen": reddedilen}

    # ------------------------------------------------------------ topluluk deney verisi (11. madde)
    def _dialog(self, tur: str, onerilen: str | None, turler: tuple):
        import webview
        if self._pencere is None:
            return None
        if tur == "kaydet":
            h = self._pencere.create_file_dialog(webview.SAVE_DIALOG, save_filename=onerilen or "", file_types=turler + ("Tüm dosyalar (*.*)",))
        else:
            h = self._pencere.create_file_dialog(webview.OPEN_DIALOG, file_types=turler + ("Tüm dosyalar (*.*)",))
        if not h:
            return None
        return h if isinstance(h, str) else h[0]

    def _tv(self):
        self._motor()
        import topluluk_veri
        return topluluk_veri

    def tv_ekle(self, kayit: dict) -> dict:
        tv = self._tv()
        k = {a: (None if v in ("", None) else v) for a, v in (kayit or {}).items()}
        for a in ("g", "oksijen_yuzde", "basinc_kpa", "akis_cm_s", "kalinlik_mm", "yayilma_hizi_mm_s", "K_mm2_s", "sonme_capi_mm"):
            if k.get(a) is not None:
                try:
                    k[a] = float(k[a])
                except (TypeError, ValueError):
                    return {"hata": f"'{a}' sayı olmalı"}
        try:
            return temizle(tv.ekle(k))
        except Exception as e:  # ToplulukHatasi: mesaj aynen gösterilir
            return {"hata": str(e)}

    def tv_listele(self, filtre: dict | None = None) -> dict:
        tv = self._tv()
        try:
            f = {a: v for a, v in (filtre or {}).items() if v}
            return temizle({"liste": tv.listele(f or None), "depo": str(tv.DEPO)})
        except Exception as e:
            return {"hata": str(e), "liste": []}

    def tv_onayla(self, id_, moderator: str) -> dict:
        if not (moderator or "").strip():
            return {"hata": "Moderatör adı zorunlu."}
        try:
            return temizle(self._tv().onayla(int(id_), moderator.strip()) or {"tamam": True})
        except Exception as e:
            return {"hata": str(e)}

    def tv_reddet(self, id_, moderator: str, gerekce: str = "") -> dict:
        if not (moderator or "").strip():
            return {"hata": "Moderatör adı zorunlu."}
        try:
            return temizle(self._tv().reddet(int(id_), moderator.strip(), gerekce or "") or {"tamam": True})
        except Exception as e:
            return {"hata": str(e)}

    def tv_csv_yukle(self, yol: str | None = None, ekleyen: str | None = None) -> dict:
        yol = yol or self._dialog("ac", None, ("CSV (*.csv)",))
        if not yol:
            return {"iptal": True}
        try:
            return temizle(self._tv().csv_yukle(yol, ekleyen=ekleyen or None))
        except Exception as e:
            return {"hata": str(e)}

    def tv_sablon(self, yol: str | None = None) -> dict:
        tv = self._tv()
        yol = yol or self._dialog("kaydet", "topluluk_sablon.csv", ("CSV (*.csv)",))
        if not yol:
            return {"iptal": True}
        import shutil
        shutil.copy2(tv.SABLON, yol)
        return {"yol": str(yol)}

    def tv_disa_aktar(self, yol: str | None = None) -> dict:
        yol = yol or self._dialog("kaydet", "topluluk_paket.json", ("JSON (*.json)",))
        if not yol:
            return {"iptal": True}
        try:
            r = self._tv().disa_aktar(yol)
            return temizle({"yol": str(yol), "sonuc": r})
        except Exception as e:
            return {"hata": str(e)}

    def tv_ice_aktar(self, yol: str | None = None) -> dict:
        yol = yol or self._dialog("ac", None, ("JSON (*.json)",))
        if not yol:
            return {"iptal": True}
        try:
            return temizle(self._tv().ice_aktar(yol))
        except Exception as e:
            return {"hata": str(e)}

    def kullanici_malzeme_onayla(self, kid: str) -> dict:
        liste = self._kullanici_oku()
        for m in liste:
            if m.get("id") == kid:
                m["onay"] = "onayli"
                m["onay_zamani"] = _simdi_metni()
                self._kullanici_yaz(liste)
                return {"tamam": True}
        return {"hata": "Kayıt bulunamadı."}

    def kullanici_malzeme_sil(self, kid: str) -> dict:
        liste = self._kullanici_oku()
        kalan = [m for m in liste if m.get("id") != kid]
        if len(kalan) == len(liste):
            return {"hata": "Kayıt bulunamadı."}
        self._kullanici_yaz(kalan)
        return {"tamam": True}

    def malzeme_varsayilanlari(self) -> dict:
        """{malzeme: [numune_tipi, kalınlık mm, yakıt türü]} — önce tahmin.py MALZEME_VARSAYILAN, sonra yerleşik
        kütüphane (aynı varsayılanları tahmin() de kullanır)."""
        B = self._motor()
        v = {k: list(x) for k, x in B.MALZEME_VARSAYILAN.items()}
        for m in self.malzeme_kutuphanesi().get("malzemeler", []):
            if m.get("id") and m["id"] not in v:
                d = m.get("varsayilan") or {}
                v[m["id"]] = [d.get("numune_tipi"), d.get("kalinlik_veya_cap_mm"), m.get("yakit_turu")]
        return temizle(v)

    # ------------------------------------------------------------ çözüm
    def coz(self, ham: dict) -> dict:
        """Tam analiz: tahmin + üç grafik + yakın deneyler."""
        k = kosul_hazirla(ham)
        B = self._motor()
        bas = time.perf_counter()
        sonuc = {"kosul": k}

        self._olay("cozum", {"adim": "tahmin", "yuzde": 5})
        sonuc["tahmin"] = _calistir(B.tahmin, **k)
        if "hata" in sonuc["tahmin"] or (sonuc["tahmin"].get("veri") or {}).get("ozel_durum"):
            # ozel_durum (oksitleyici / yanmaz / pil): yakıt olarak çözülmez, grafik de üretilmez
            sonuc["sure_sn"] = round(time.perf_counter() - bas, 3)
            self._olay("cozum", {"adim": "bitti", "yuzde": 100})
            return temizle(sonuc)

        for ad, f, kw, yuzde in (
            ("oksijen_egrisi", B.oksijen_egrisi, {}, 35),
            ("harita", B.yanabilirlik_haritasi, {"n_g": 40, "n_o2": 40}, 60),
            ("akis_egrisi", B.akis_egrisi, {}, 80),
            ("yakin", B.yakin_deneyler, {"en_fazla": 200}, 95),
        ):
            self._olay("cozum", {"adim": ad, "yuzde": yuzde})
            sonuc[ad] = _calistir(f, **kw, **k)

        sonuc["sure_sn"] = round(time.perf_counter() - bas, 3)
        self._olay("cozum", {"adim": "bitti", "yuzde": 100})
        return temizle(sonuc)

    def llm(self, ham: dict) -> dict:
        """Yapay zeka yorumu (~25 sn). Aynı anda tek istek çalışır."""
        k = kosul_hazirla(ham)
        B = self._motor()
        if not self._llm_kilit.acquire(blocking=False):
            return {"hata": "Başka bir yapay zeka isteği sürüyor."}
        try:
            self._olay("cozum", {"adim": "llm", "yuzde": 10})
            return temizle({"kosul": k, "tahmin": _calistir(B.tahmin, llm=True, **k)})
        finally:
            self._llm_kilit.release()
            self._olay("cozum", {"adim": "bitti", "yuzde": 100})

    def llm_durumu(self) -> dict:
        """Sohbet kutusu için: LLM'e ulaşılabiliyor mu (anahtar + bağlantı; istek göndermez, en çok ~3 sn)."""
        if self.mock:
            return {"ulasilabilir": False, "sebep": "deneme (mock) kipinde yapay zeka yok"}
        try:
            self._motor()
            import llm_analiz
            ok, sebep = llm_analiz.ulasilabilir()
            return {"ulasilabilir": bool(ok), "sebep": sebep}
        except Exception as e:  # noqa: BLE001
            return {"ulasilabilir": False, "sebep": f"{type(e).__name__}: {str(e)[:120]}"}

    def sohbet(self, ham: dict, gecmis, soru: str) -> dict:
        """Çözülmüş vaka hakkında soru-cevap. Sayıları kod üretir: tahmin() burada yeniden çalışır, "ne olur eğer"
        soruları için LLM'in istediği ek hesapları (en fazla 3) yine tahmin() yapar. Aynı anda tek istek."""
        k = kosul_hazirla(ham)
        B = self._motor()
        if self.mock:
            return {"durum": "baglanti_yok", "sebep": "deneme (mock) kipinde yapay zeka yok", "hesaplar": []}
        import llm_analiz
        if not self._llm_kilit.acquire(blocking=False):
            return {"durum": "mesgul", "sebep": "Başka bir yapay zeka isteği sürüyor.", "hesaplar": []}
        try:
            bas = time.perf_counter()
            sonuc = B.tahmin(**k)
            r = llm_analiz.sohbet(sonuc, gecmis if isinstance(gecmis, list) else [], soru, kosul=k, hesapla=B.tahmin)
            r["kosul"] = k
            r["mevcut"] = llm_analiz._sohbet_ozeti(sonuc)
            r["sure_sn"] = round(time.perf_counter() - bas, 2)
            return temizle(r)
        except Exception as e:  # noqa: BLE001
            return {"durum": "hata", "sebep": f"{type(e).__name__}: {str(e)[:150]}", "hesaplar": []}
        finally:
            self._llm_kilit.release()

    # ------------------------------------------------------------ parametre süpürmesi
    def supur(self, ham: dict, parametre: str, bas_deger, son_deger, adim) -> dict:
        """Tek bir girdiyi aralık boyunca değiştirip her noktada tahmin() çağırır.

        Grafik fonksiyonları çağrılmaz (nokta başına ~0,05 sn), çünkü süpürmede
        yalnızca risk, sönme sınırı, güvenlik katsayısı ve güven gerekir.
        """
        if parametre not in SUPURULEBILIR:
            raise ValueError(f"'{parametre}' süpürülemez. Seçenekler: {', '.join(SUPURULEBILIR)}")
        try:
            bas_deger, son_deger, adim = float(bas_deger), float(son_deger), float(adim)
        except (TypeError, ValueError):
            raise ValueError("Başlangıç, bitiş ve adım sayı olmalı.")
        if adim <= 0:
            raise ValueError("Adım 0'dan büyük olmalı.")
        if son_deger < bas_deger:
            bas_deger, son_deger = son_deger, bas_deger
        n = int(math.floor((son_deger - bas_deger) / adim + 1e-9)) + 1
        if n < 2:
            raise ValueError("Aralık en az iki nokta vermeli.")
        if n > SUPURME_EN_FAZLA:
            raise ValueError(f"{n} nokta çok fazla (en fazla {SUPURME_EN_FAZLA}). Adımı büyütün.")

        k = kosul_hazirla(ham)
        B = self._motor()
        baslangic = time.perf_counter()
        noktalar, hatalar = [], 0

        for i in range(n):
            deger = round(bas_deger + i * adim, 10)
            kk = dict(k)
            kk[parametre] = deger
            try:
                kosul_hazirla(kk)          # aralık dışı değerleri atla, süpürmeyi durdurma
            except ValueError as e:
                noktalar.append({"deger": deger, "hata": str(e)})
                hatalar += 1
                continue
            try:
                t = B.tahmin(**kk)
                noktalar.append({
                    "deger": deger,
                    "yanma_ihtimali": t.get("yanma_ihtimali"),
                    "belirsizlik": t.get("belirsizlik"),
                    "sonme_siniri": t.get("sonme_siniri"),
                    "guvenlik_katsayisi": t.get("guvenlik_katsayisi"),
                    "risk_seviyesi": t.get("risk_seviyesi"),
                    "guven": (t.get("guven") or {}).get("skor"),
                    "motor_yanma": (t.get("motor") or {}).get("yanma"),
                })
            except Exception as e:
                noktalar.append({"deger": deger, "hata": f"{type(e).__name__}: {e}"})
                hatalar += 1
            if i % 3 == 0 or i == n - 1:
                self._olay("supurme", {"i": i + 1, "n": n, "yuzde": round(100 * (i + 1) / n)})

        return temizle({
            "parametre": parametre, "bas": bas_deger, "son": son_deger, "adim": adim,
            "taban_kosul": k, "noktalar": noktalar, "hata_sayisi": hatalar,
            "sure_sn": round(time.perf_counter() - baslangic, 3),
        })

    # ------------------------------------------------------------ sistem
    def islemci(self) -> dict:
        return temizle(sistem.islemci())

    def _render_listesi(self) -> list:
        liste = sistem.render_listesi(self.render_klasoru)
        if self.render_oneki:
            from urllib.parse import quote
            for x in liste:
                x["yol"] = self.render_oneki + quote(x["ad"])
        return liste

    def render_listesi(self) -> list:
        return temizle(self._render_listesi())

    # ------------------------------------------------------------ OpenFOAM motoru (ayrıntılı OpenFOAM koşuları; ayrı kaynak)
    def _ofm(self):
        if str(self.motor_yolu) not in sys.path:
            sys.path.insert(0, str(self.motor_yolu))
        import ofm_motor, ofm_ice_aktar
        return ofm_motor, ofm_ice_aktar

    def ofm_kosular(self) -> dict:
        """Kütüphane > Ayrıntılı koşular: içe aktarılmış OpenFOAM koşuları (özet; eğri verisi dahil değil)."""
        try:
            bm, _ = self._ofm()
            return temizle({"kosular": [{k: v for k, v in x.items() if k != "egri"} for x in bm.kosular()], "kok": str(bm.kok())})
        except Exception as e:  # noqa: BLE001
            return {"kosular": [], "hata": f"{type(e).__name__}: {e}"}

    def ofm_ice_aktar(self, yol: str) -> dict:
        try:
            bm, ia = self._ofm()
            r = ia.ice_aktar(yol, bm.kok() / "ofm_gelen", bm.kok() / "ofm_sonuclar", Path(os.environ["AHUT_RENDER"]))
            return temizle({k: v for k, v in r.items() if k != "egri"})
        except SystemExit as e:
            return {"hata": str(e)}
        except Exception as e:  # noqa: BLE001
            return {"hata": f"{type(e).__name__}: {e}"}

    OFM_PAKET = Path(os.environ.get("AHUT_MOTOR_C") or Path.home() / "Desktop" / "motor_c")
    OFM_SURE_4CEK_S10 = 6.5      # saat: 10 s benzetim, 4 çekirdek (yüklü makinede ölçüldü; ofm_motor_c_duman_sonuc.md)

    def _ofm_vaka(self):
        if str(self.motor_yolu) not in sys.path:
            sys.path.insert(0, str(self.motor_yolu))
        import ofm_vaka
        return ofm_vaka

    def _ofm_ad(self, ad: str) -> str | None:
        """Girilen malzeme adının kütüphane kimliği (sibal, pmma …); bilinmiyorsa None."""
        try:
            if self._B is None:
                self.motoru_yukle()
            k = self._B.kutuphanede_bul(ad)
            return k["id"] if k else None
        except Exception:  # noqa: BLE001
            return None

    def ofm_destek(self, kosul: dict) -> dict:
        """Ayrıntılı (OpenFOAM) çözüm bu vaka için desteklenir mi? (şimdilik katı / SIBAL, kalınlık OpenFOAM vaka ağına uygunsa)"""
        try:
            bv = self._ofm_vaka()
            ad = str(kosul.get("malzeme") or "")
            r = bv.destek(kosul, malzeme_kanonik=self._ofm_ad(ad) or ad)
            r["paket_var"] = (self.OFM_PAKET / "vaka").is_dir() and Path("/opt/openfoam14/etc/bashrc").exists()
            if r["destekli"] and not r["paket_var"]:
                r["destekli"], r["neden"] = False, (f"OpenFOAM paketi ({self.OFM_PAKET}) ya da OpenFOAM 14 bu bilgisayarda yok.")
            return temizle(r)
        except Exception as e:  # noqa: BLE001
            return {"destekli": False, "neden": f"{type(e).__name__}: {e}"}

    def ofm_sure_tahmini(self, cekirdek: int, bitis_s: float) -> dict:
        n = max(1, int(cekirdek))
        saat = self.OFM_SURE_4CEK_S10 * (float(bitis_s) / 10.0) * (4.0 / n) * (1.3 if n > 4 else 1.0)
        return {"saat": round(saat, 1), "aciklama": (f"Kaba tahmin: 10 s benzetim 4 çekirdekte {self.OFM_SURE_4CEK_S10:g} sa ölçüldü; "
                                                    f"{n} çekirdek, {float(bitis_s):g} s için ≈ {saat:.1f} sa (ölçeklenme yaklaşık, ≥5 çekirdekte %30 verim kaybı varsayıldı).")}

    def ofm_kos_kontrol(self, tur: str = "kati", cekirdek: int | None = None, bitis_s: float = 10.0) -> dict:
        """Başlatma penceresi için: hazır mı, çekirdek varsayılanı (nproc−2), başka foamRun uyarısı, süre tahmini."""
        nproc = os.cpu_count() or 4
        n = int(cekirdek) if cekirdek else max(1, nproc - 2)
        s = {"tur": tur, "hazir": False, "nproc": nproc, "cekirdek": n, "uyarilar": []}
        if tur != "kati":
            s["neden"] = "Sıvı ve gaz vakaları henüz pakette yok: OpenFOAM motorundan vaka gelince eklenecek."
            return s
        if not (self.OFM_PAKET / "vaka").is_dir():
            s["neden"] = f"OpenFOAM paketi bulunamadı: {self.OFM_PAKET}"
            return s
        if not Path("/opt/openfoam14/etc/bashrc").exists():
            s["neden"] = "OpenFOAM 14 (/opt/openfoam14) bu bilgisayarda yok."
            return s
        ek = self.izleyici.sistem_ek()
        f = ek.get("foam") or {}
        s["foam_calisiyor"] = int(f.get("cozucu") or 0)
        s["foam_cekirdek"] = f.get("cekirdek")
        s["disk_bos_gb"] = round(ek["disk"]["bos"] / 1073741824, 1) if ek.get("disk") else None
        s["hazir"] = True
        t = self.ofm_sure_tahmini(n, bitis_s)
        s["sure_saat"], s["sure_uyarisi"] = t["saat"], t["aciklama"]
        if s["foam_calisiyor"]:
            s["uyarilar"].append(f"Şu an {s['foam_calisiyor']} foamRun süreci çalışıyor ({f.get('cekirdek')} çekirdek): yeni koşu onlarla CPU paylaşır, ikisi de yavaşlar.")
        if n > nproc - 2:
            s["uyarilar"].append(f"{n} çekirdek seçildi ({nproc} var): arayüz ve diğer işler yavaşlayabilir.")
        if s["disk_bos_gb"] is not None and s["disk_bos_gb"] < 8:
            s["uyarilar"].append(f"Boş disk az ({s['disk_bos_gb']} GB): uzun koşu yazarken dolabilir.")
        if ek.get("pil") and not ek["pil"].get("prizde"):
            s["uyarilar"].append("Pilde çalışıyor: uzun koşuda prize takın.")
        return s

    def ofm_ayrintili_baslat(self, kosul: dict, cekirdek: int | None = None, bitis_s: float = 10.0, vekil: bool = False) -> dict:
        """Girdileri OpenFOAM vakasının bir KOPYASINA yazar (O2, basınç, akış; g > 0 ise constant/fluid/g + 0/fluid/p_rgh) ve
        Çözüm İzleyici kuyruğuna ekler. Bitince ofm_analiz otomatik çalışır (içe aktarma). Paketin kendisine dokunulmaz."""
        d0 = self.ofm_destek(kosul)
        vekil_notu = None
        if not d0.get("destekli"):
            # vekil=True: malzeme/kalınlık OpenFOAM vakasına uymuyorsa koşu yine SIBAL ağıyla yapılır (ortam koşulları vakadan)
            if not (vekil and d0.get("kod") in ("malzeme", "kalinlik")):
                return {"hata": d0.get("neden") or "desteklenmiyor", "kod": d0.get("kod")}
            vekil_notu = (f"Vekil koşu: OpenFOAM vakası yalnız SIBAL (katı, {self._ofm_vaka().KALINLIK_AG_MM:g} mm) içindir; "
                          f"'{kosul.get('malzeme')}' yerine SIBAL koşulur, ortam (O₂, basınç, akış, g) vakadan alınır.")
        k = self.ofm_kos_kontrol("kati", cekirdek, bitis_s)
        if not k.get("hazir"):
            return {"hata": k.get("neden") or "hazır değil"}
        bv = self._ofm_vaka()
        bm, _ = self._ofm()
        ad = "ofm_ayr_" + time.strftime("%Y%m%d_%H%M%S")
        d = bm.kok() / "ofm_kosu" / ad
        d.parent.mkdir(parents=True, exist_ok=True)
        g = kosul.get("g")
        h = bv.hazirla(d, self.OFM_PAKET, {"oksijen": kosul.get("oksijen"), "basinc": kosul.get("basinc"), "akis": kosul.get("akis"), "g": g},
                       k["cekirdek"], float(bitis_s))
        kilit = h["kilit"]
        # deney yalnız koşullar Saffire-III S1'e yakınsa (g≈0, O2, basınç, akış); değilse doğrulama yok
        o = kilit["ortam"]
        saffire = ((g or 0) < 0.01 and abs((kosul.get("oksijen") or 0) - 21.2) <= 1.5 and abs((kosul.get("basinc") or 0) - o["p"] / 1000) <= 5
                   and abs((kosul.get("akis") if kosul.get("akis") is not None else o["U_in"] * 100) - o["U_in"] * 100) <= 5)
        (d / "BILGI.json").write_text(json.dumps({
            "kosu": ad, "yakit_turu": "kati", "malzeme": "sibal", "deney": "saffire3" if saffire else "yok", "boyut": "2B",
            "motor": "MOTOR_KILIT 1", "numune_x0_m": 0.15, "numune_x1_m": 1.09, "endTime_s": float(bitis_s), "cekirdek": k["cekirdek"],
            "kosullar": {"g": g if g is not None else 0, "oksijen": kosul.get("oksijen"), "basinc": kosul.get("basinc"),
                         "akis": kosul.get("akis") if kosul.get("akis") is not None else round(o["U_in"] * 100, 2), "kalinlik_mm": bv.KALINLIK_AG_MM},
            "notlar": "Çözüm İzleyici kuyruğundan (Ayrıntılı çözüm): " + "; ".join(h["notlar"] + ([vekil_notu] if vekil_notu else [])),
            "vaka_malzemesi": kosul.get("malzeme"), "vekil": bool(vekil_notu)}, ensure_ascii=False, indent=1), encoding="utf-8")
        r = self.izleyici.kosu_ekle(f"Ayrıntılı (OpenFOAM): {kosul.get('malzeme')} g={g:g} %{kosul.get('oksijen'):g} O₂" if g is not None else "Ayrıntılı (OpenFOAM)",
                                    str(d), ["bash", "kos.sh"], "log.run", k["cekirdek"], ice_aktar=True,
                                    kaldirma=bool(g is not None and g > 0.01), bitis_s=float(bitis_s))
        return temizle({**r, "kosu": ad, "dizin": str(d), "notlar": h["notlar"], "uyarilar": ([vekil_notu] if vekil_notu else []) + k["uyarilar"],
                        "vekil": bool(vekil_notu), "sure_saat": k.get("sure_saat"), "sure_uyarisi": k.get("sure_uyarisi"),
                        "cekirdek": k["cekirdek"], "deney": "saffire3" if saffire else "yok"})

    def ofm_kos_baslat(self, tur: str = "kati") -> dict:
        """Eski kısa yol: Saffire-III S1 (kilitli motor, kilit koşulları) — Kütüphane / Çözüm İzleyici düğmesi."""
        k = self.ofm_kos_kontrol(tur)
        if not k.get("hazir"):
            return {"hata": k.get("neden") or "hazır değil"}
        import ofm_sonuc_donustur as bsd
        kos = bsd.kosullar(json.loads((self.OFM_PAKET / "MOTOR_KILIT.json").read_text(encoding="utf-8")))
        return self.ofm_ayrintili_baslat({"malzeme": "sibal", "oksijen": kos["oksijen"], "basinc": kos["basinc"], "akis": kos["akis"], "g": 0.0},
                                           k["cekirdek"], 10.0)

    def ofm_ayrintili_durum(self, kid: str) -> dict:
        """Ayrıntılı koşunun durumu: kuyruk durumu, ilerleme (t, kalan), içe aktarma, sonuç kaydı (bitince)."""
        k = self.izleyici.kosu(str(kid))
        if not k:
            return {"hata": "koşu yok"}
        r = {"id": kid, "durum": k["durum"], "ice_aktarma": k.get("ice_aktarma"), "kontrol": k.get("kontrol"),
             "ilerleme": self.izleyici.ilerleme(str(kid)) if k["durum"] in ("ÇALIŞIYOR", "BEKLİYOR", "DURAKLADI") else None}
        r.update(self._ofm_sonuc_kaydi(Path(k["dizin"]).name))
        return temizle(r)

    def _ofm_sonuc_kaydi(self, ad: str) -> dict:
        """İçe aktarılmış koşunun kaydı ve (en yakın koşu olarak) 'ofm' özeti; yoksa boş sözlük."""
        try:
            bm, _ = self._ofm()
            kayit = next((x for x in bm.kosular() if x.get("kosu") == ad), None)
            if not kayit:
                return {}
            kk = kayit["kosullar"]
            gm = bm.degerlendir(kk["g"], kk["oksijen"], kk["basinc"], kk.get("akis"), kk.get("kalinlik"), kayit["malzeme"], kayit["yakit_turu"])
            return {"kayit": dict(kayit), "ofm": gm if gm and gm.get("kosu") == ad else None}
        except Exception as e:  # noqa: BLE001
            return {"hata": f"{type(e).__name__}: {e}"}

    def ofm_kosu_sonuc(self, ad: str) -> dict:
        """Vaka açılırken: kayıtlı ayrıntılı koşunun sonucu (içe aktarılmışsa)."""
        return temizle(self._ofm_sonuc_kaydi(str(ad)))

    def _ofm_bitti(self, k: dict):
        """Kuyruk kancası: ayrıntılı koşu TAMAM bitince ofm_analiz'i çalıştırır (içe aktarma)."""
        bm, ia = self._ofm()
        r = ia.ice_aktar(k["dizin"], bm.kok() / "ofm_gelen", bm.kok() / "ofm_sonuclar", Path(os.environ["AHUT_RENDER"]))
        return {"hata": "; ".join(r.get("sorunlar") or [r.get("hata")])} if r.get("hata") else {"tamam": True}

    def _ofm_kontrol(self, k: dict, log_metni: str):
        bv = self._ofm_vaka()
        return bv.kaldirma_kontrol(log_metni, True)

    # ------------------------------------------------------------ 3B sahne (geometri, ağ, alan sonuçları, ParaView)
    def _ofm_kok_yolu(self):
        try:
            bm, _ = self._ofm()
            return bm.kok()
        except Exception:  # noqa: BLE001
            return None

    def sahne_vaka(self, kosul: dict | None = None) -> dict:
        """Vaka geometrisi: OpenFOAM (SIBAL) vakası destekleniyorsa gerçek boyutlar, yoksa {kaynak: temsili}."""
        k = kosul or {}
        try:
            ad = self._ofm_ad(str(k.get("malzeme") or "")) or str(k.get("malzeme") or "")
            bv = self._ofm_vaka()
            if bv.desteklenen_mi(ad, "kati"):
                g = sahne.ofm_geometri(self.OFM_PAKET)
                if g:
                    return temizle({**g, "izgara_var": True})
        except Exception as e:  # noqa: BLE001
            return {"kaynak": "temsili", "hata": f"{type(e).__name__}: {e}"}
        return {"kaynak": "temsili"}

    def sahne_izgara(self) -> dict:
        try:
            return temizle(sahne.ofm_izgara(self.OFM_PAKET) or {"hata": "ağ yok"})
        except Exception as e:  # noqa: BLE001
            return {"hata": f"{type(e).__name__}: {e}"}

    def sonuc3b_liste(self) -> list:
        return temizle(sahne.sonuc_listesi(self.proje_kok, self._ofm_kok_yolu()))

    def _sonuc3b_yol(self, yol: str) -> Path:
        izinli = {x["yol"] for x in sahne.sonuc_listesi(self.proje_kok, self._ofm_kok_yolu())}
        if str(yol) not in izinli:
            raise ValueError("bilinmeyen 3B sonuç dosyası")
        return Path(yol)

    def sonuc3b_meta(self, yol: str) -> dict:
        return temizle(sahne.sonuc_meta(self._sonuc3b_yol(yol)) or {"hata": "okunamadı"})

    def sonuc3b_kare(self, yol: str, i: int) -> dict:
        return sahne.sonuc_kare(self._sonuc3b_yol(yol), int(i))

    def sonuc3b_aktar(self, dizin: str) -> dict:
        return temizle(sahne.disa_aktar_baslat(self.proje_kok, dizin))

    def sonuc3b_durum(self) -> list:
        return temizle(sahne.disa_aktar_durumu())

    def paraview_ac(self, dizin: str) -> dict:
        try:
            return temizle(sahne.paraview_ac(self.proje_kok, dizin, self.depo.veri / "gecici"))
        except Exception as e:  # noqa: BLE001
            return {"hata": f"{type(e).__name__}: {e}"}

    def _disa_aktar_kancasi(self, k: dict):
        r = sahne.disa_aktar_baslat(self.proje_kok, k["dizin"])
        return r

    # ------------------------------------------------------------ Çözüm İzleyici
    def sistem_ek(self) -> dict:
        return temizle(self.izleyici.sistem_ek())

    def kosular(self) -> dict:
        return temizle(self.izleyici.kosular())

    def kosu_kaynaklari(self) -> list:
        return temizle(self.izleyici.kaynaklar())

    def izle(self, kaynak: str, ofset=None, sifirla: bool = False) -> dict:
        return temizle(self.izleyici.izle(str(kaynak), ofset, bool(sifirla)))

    def kosu_ekle(self, ad: str, dizin: str, komut, log: str = "log.kosu", cekirdek: int = 1) -> dict:
        return temizle(self.izleyici.kosu_ekle(ad, dizin, komut, log, int(cekirdek)))

    def kosu_iptal(self, kid: str) -> dict:
        return temizle(self.izleyici.kosu_iptal(str(kid)))

    def kosu_duraklat(self, kid: str) -> dict:
        return temizle(self.izleyici.kosu_duraklat(str(kid)))

    # ------------------------------------------------------------ motor doğrulama: sıvı (n-heptan damla, FLEX)
    def _dd(self):
        import importlib.util
        yol = self._ana_kok / "of_damla_dogrulama.py"
        if not yol.exists():
            raise RuntimeError(f"of_damla_dogrulama.py bulunamadı: {yol}")
        sp = importlib.util.spec_from_file_location("of_damla_dogrulama", yol)
        m = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(m)
        return m

    def dogrulama_sivi(self) -> dict:
        """Test listesi + her vakanın durumu (kurulmadı / kuruldu / bitti) + özet (AUC, doğruluk, K oranı)."""
        try:
            m = self._dd()
            if not m.LISTE.exists():
                m.liste_yaz()
            o = m.ozet()
            for v in o["vakalar"]:
                v["dizin"] = str(m.DD_KOK / v["ad"])
            o["nproc"] = os.cpu_count() or 4
            return temizle(o)
        except Exception as e:  # noqa: BLE001
            return {"hata": f"{type(e).__name__}: {e}"}

    def dogrulama_sivi_kur(self, adlar=None) -> dict:
        """Eksik vakaları kurar (OpenFOAM gerekir; vaka başına birkaç saniye)."""
        try:
            m = self._dd()
            l = __import__("json").loads(m.LISTE.read_text(encoding="utf-8"))["vakalar"]
            kurulan = []
            for v in l:
                if adlar and v["ad"] not in adlar:
                    continue
                if (m.DD_KOK / v["ad"] / "kos.sh").exists():
                    continue
                m.kur_vaka(v)
                kurulan.append(v["ad"])
            return {"kurulan": kurulan}
        except BaseException as e:  # noqa: BLE001  (kur_vaka hata durumunda SystemExit atar)
            return {"hata": f"{type(e).__name__}: {e}"}

    def _kapat(self) -> None:
        """Uygulama kapanırken çağrılır (JS'e açık değil): kendi başlattığımız koşuları sonlandırır."""
        try:
            self.izleyici.kapat()
        except Exception:  # noqa: BLE001
            pass

    def kosu_devam(self, kid: str) -> dict:
        return temizle(self.izleyici.kosu_devam(str(kid)))

    def kosu_log_ac(self, kaynak: str) -> dict:
        yol = self.izleyici.log_yolu(str(kaynak))
        if not yol:
            return {"hata": "günlük yok"}
        try:
            subprocess.Popen(["xdg-open", yol] if sys.platform.startswith("linux") else ["open", yol] if sys.platform == "darwin" else ["notepad", yol])
            return {"tamam": True, "yol": yol}
        except Exception as e:  # noqa: BLE001
            return {"hata": str(e)}

    def render_uygun(self, malzeme: str = "", yakit_turu: str | None = None, g: float = 0.0, dil: str = "tr") -> dict:
        """Çözülen vakaya uygun renderlar: {mod: tam|benzer|yok, adlar: [...]}."""
        return temizle(sistem.render_uygun(self._render_listesi(), malzeme, yakit_turu, g, dil))

    # ------------------------------------------------------------ ayarlar ve profil
    def ayarlar(self) -> dict:
        return self.depo.ayarlar()

    def ayar_yaz(self, yeni: dict) -> dict:
        return self.depo.ayar_yaz(yeni)

    def profil(self) -> dict:
        """Jeton ekrana gönderilmez; yerine yalnızca var/yok bilgisi gider."""
        p = dict(self.depo.profil())
        p["github_jeton_var"] = bool((p.get("github_jeton") or "").strip())
        p["github_jeton"] = ""
        return p

    def profil_yaz(self, yeni: dict) -> dict:
        yeni = dict(yeni or {})
        # Ekrandan boş jeton gelirse var olanı silmeyelim; silmek için "-" yazılır.
        j = yeni.get("github_jeton")
        if j is None or not str(j).strip():
            yeni.pop("github_jeton", None)
        elif str(j).strip() == "-":
            yeni["github_jeton"] = ""
        self.depo.profil_yaz(yeni)
        return self.profil()

    # ------------------------------------------------------------ vaka kütüphanesi
    def vaka_kaydet(self, alanlar: dict) -> dict:
        paket = self.depo.paket_yap(
            girdi=alanlar.get("girdi"),
            sonuc=alanlar.get("sonuc"),
            baslik=alanlar.get("baslik", ""),
            aciklama=alanlar.get("aciklama", ""),
            etiketler=alanlar.get("etiketler"),
            onayar=alanlar.get("onayar"),
            llm_yorum=alanlar.get("llm_yorum"),
            render=alanlar.get("render"),
            supurme=alanlar.get("supurme"),
            vaka_id=alanlar.get("id"),
            uygulama={"ad": "AHUT FLARE", "surum": self.surum},
        )
        if alanlar.get("id"):  # var olan vakanın üstüne yazılıyorsa eski üstveriyi koru
            eski = self.depo.oku(alanlar["id"])
            if eski:
                paket["olusturma"] = eski.get("olusturma", paket["olusturma"])
                paket["yorumlar"] = eski.get("yorumlar", [])
        return self.depo.kaydet(paket)

    def vaka_guncelle(self, vaka_id: str, alanlar: dict) -> dict:
        paket = self.depo.oku(vaka_id)
        if paket is None:
            raise ValueError("Vaka bulunamadı.")
        for ad in ("baslik", "aciklama", "etiketler", "llm_yorum", "render"):
            if ad in (alanlar or {}):
                paket[ad] = alanlar[ad]
        return self.depo.kaydet(paket)

    def vaka_listesi(self) -> list:
        return self.depo.listele()

    def vaka_oku(self, vaka_id: str) -> dict | None:
        return self.depo.oku(vaka_id)

    def vaka_sil(self, vaka_id: str) -> bool:
        return self.depo.sil(vaka_id)

    def yorum_ekle(self, vaka_id: str, metin: str) -> dict:
        paket = self.depo.oku(vaka_id)
        if paket is None:
            raise ValueError("Vaka bulunamadı.")
        metin = (metin or "").strip()
        if not metin:
            raise ValueError("Yorum boş olamaz.")
        paket.setdefault("yorumlar", []).append({
            "yazar": self.depo.profil().get("ad") or "(isimsiz)",
            "zaman": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "metin": metin[:4000],
        })
        self.depo.kaydet(paket)
        return paket

    # ------------------------------------------------------------ dosya alışverişi
    def vaka_disa_aktar(self, vaka_id: str) -> dict:
        import webview

        ozet = next((o for o in self.depo.listele() if o["id"] == vaka_id), None)
        onerilen = (ozet or {}).get("baslik") or vaka_id
        onerilen = "".join(c if (c.isalnum() or c in " -_") else "_" for c in onerilen)[:60].strip() or vaka_id
        hedef = self._pencere.create_file_dialog(
            webview.SAVE_DIALOG, save_filename=onerilen + ".ahut",
            file_types=("AHUT vaka dosyası (*.ahut)", "Tüm dosyalar (*.*)"),
        )
        if not hedef:
            return {"iptal": True}
        yol = hedef if isinstance(hedef, str) else hedef[0]
        return {"yol": self.depo.disa_aktar(vaka_id, Path(yol))}

    def vaka_ice_aktar(self) -> dict:
        import webview

        secim = self._pencere.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=True,
            file_types=("AHUT vaka dosyası (*.ahut)", "JSON (*.json)", "Tüm dosyalar (*.*)"),
        )
        if not secim:
            return {"iptal": True}
        eklenen, hatalar = [], []
        for yol in secim:
            try:
                eklenen.append(self.depo.ice_aktar(Path(yol)))
            except Exception as e:
                hatalar.append(f"{Path(yol).name}: {e}")
        return {"eklenen": eklenen, "hatalar": hatalar}

    def dosya_ac(self, yol: str) -> dict:
        """Komut satırından ya da çift tıklamayla gelen .ahut dosyasını kütüphaneye alır."""
        return {"ozet": self.depo.ice_aktar(Path(yol))}

    def rapor_kaydet(self, html: str, onerilen: str = "ahut_rapor") -> dict:
        import webview

        onerilen = "".join(c if (c.isalnum() or c in " -_") else "_" for c in onerilen)[:60].strip() or "ahut_rapor"
        hedef = self._pencere.create_file_dialog(
            webview.SAVE_DIALOG, save_filename=onerilen + ".html",
            file_types=("HTML rapor (*.html)", "Tüm dosyalar (*.*)"),
        )
        if not hedef:
            return {"iptal": True}
        yol = Path(hedef if isinstance(hedef, str) else hedef[0])
        if yol.suffix.lower() != ".html":
            yol = yol.with_suffix(".html")
        yol.write_text(html, encoding="utf-8")
        return {"yol": str(yol)}

    def csv_kaydet(self, metin: str, onerilen: str = "tablo") -> dict:
        """Görüntü alanındaki "Tablo Verisi"ni CSV olarak kaydeder (UTF-8, BOM'lu: Excel Türkçe karakterleri doğru açar)."""
        onerilen = "".join(c if (c.isalnum() or c in " -_") else "_" for c in (onerilen or ""))[:60].strip() or "tablo"
        yol = self._dialog("kaydet", onerilen + ".csv", ("CSV (*.csv)",))
        if not yol:
            return {"iptal": True}
        yol = Path(yol)
        if yol.suffix.lower() != ".csv":
            yol = yol.with_suffix(".csv")
        yol.write_text(metin, encoding="utf-8-sig")
        return {"yol": str(yol)}

    # ------------------------------------------------------------ topluluk
    def topluluk(self) -> list:
        return self.depo.topluluk()

    def topluluk_oku(self, vaka_id: str) -> dict | None:
        return self.depo.topluluk_oku(vaka_id)

    def topluluktan_al(self, vaka_id: str) -> dict:
        paket = self.depo.topluluk_oku(vaka_id)
        if paket is None:
            raise ValueError("Örnek vaka bulunamadı.")
        import uuid

        paket = dict(paket)
        paket["id"] = uuid.uuid4().hex[:12]
        return self.depo.kaydet(paket)

    # ------------------------------------------------------------ GitHub paylaşımı
    def _depo_nesnesi(self):
        p = self.depo.profil()
        adres = (p.get("github_depo") or "").strip()
        if not adres:
            raise ValueError("Önce profil ekranından paylaşım deposunu girin (örn. kullanici/depo).")
        return gh.Depo(adres, p.get("github_jeton"))

    def github_ayar(self) -> dict:
        """Jetonun kendisi ASLA ekrana dönmez; yalnızca var/yok bilgisi."""
        p = self.depo.profil()
        adres = (p.get("github_depo") or "").strip()
        bilgi = {"depo": adres, "jeton_var": bool((p.get("github_jeton") or "").strip()),
                 "site": None, "gecerli": False}
        if adres:
            try:
                d = gh.Depo(adres, None)
                bilgi["site"] = d.site_adresi
                bilgi["gecerli"] = True
            except gh.GitHubHatasi:
                pass
        return bilgi

    def github_sina(self) -> dict:
        try:
            return {"tamam": True, **self._depo_nesnesi().sina()}
        except (gh.GitHubHatasi, ValueError) as e:
            return {"tamam": False, "hata": str(e)}

    def github_site_kur(self) -> dict:
        if self.site_klasoru is None or not self.site_klasoru.is_dir():
            return {"hata": "Site dosyaları bulunamadı (site/ klasörü yok)."}
        try:
            return {"tamam": True, **self._depo_nesnesi().site_kur(self.site_klasoru)}
        except (gh.GitHubHatasi, ValueError) as e:
            return {"hata": str(e)}

    def github_paylas(self, vaka_id: str) -> dict:
        paket = self.depo.oku(vaka_id)
        if paket is None:
            return {"hata": "Vaka bulunamadı. Önce kütüphaneye kaydedin."}
        try:
            d = self._depo_nesnesi()
        except ValueError as e:
            return {"hata": str(e)}
        if not self._gh_kilit.acquire(blocking=False):
            return {"hata": "Başka bir paylaşım sürüyor."}
        try:
            self._olay("github", {"adim": "yukleniyor"})
            sonuc = d.paylas(paket)
            paket["paylasim"] = {"depo": d.tam_ad, "dosya": sonuc["dosya"],
                                 "adres": sonuc["site"], "zaman": _simdi_metni()}
            self.depo.kaydet(paket)
            return {"tamam": True, **sonuc, "depo": d.tam_ad}
        except gh.GitHubHatasi as e:
            return {"hata": str(e)}
        finally:
            self._gh_kilit.release()
            self._olay("github", {"adim": "bitti"})

    # --------- topluluk listesi: canlı, yoksa önbellek, o da yoksa yerel örnekler
    def _onbellek_oku(self) -> dict:
        try:
            return json.loads(self.onbellek_dosyasi.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _onbellek_yaz(self, veri: dict) -> None:
        try:
            gecici = self.onbellek_dosyasi.with_suffix(".tmp")
            gecici.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
            gecici.replace(self.onbellek_dosyasi)
        except Exception:
            pass

    def github_liste(self, tazele: bool = True) -> dict:
        """{kaynak: canli|onbellek|yerel, zaman, depo, liste:[ozet], hata}"""
        yerel = self.depo.topluluk()
        onbellek = self._onbellek_oku()

        def paketle(kaynak, liste, zaman=None, hata=None):
            # Paylaşılan bir vaka, uygulamayla gelen örneğin kopyasıysa listede
            # iki kez görünmesin: başlık da karşılaştırılır, GitHub kopyası kazanır.
            gorulen, basliklar, birlesik = set(), set(), []
            for o in list(liste) + yerel:
                kimlik, baslik = o.get("id"), (o.get("baslik") or "").strip().lower()
                if kimlik in gorulen or (baslik and baslik in basliklar):
                    continue
                gorulen.add(kimlik)
                if baslik:
                    basliklar.add(baslik)
                birlesik.append(o)
            return temizle({"kaynak": kaynak, "zaman": zaman, "depo": onbellek.get("depo"),
                            "liste": birlesik, "hata": hata})

        if not tazele:
            return paketle("onbellek" if onbellek.get("liste") else "yerel",
                           onbellek.get("liste") or [], onbellek.get("zaman"))
        try:
            d = self._depo_nesnesi()
        except ValueError as e:
            return paketle("yerel", [], None, str(e))

        try:
            dosyalar = d.liste()
            ozetler, paketler = [], {}
            for f in dosyalar:
                try:
                    p = d.indir(f["indirme"])
                except gh.GitHubHatasi:
                    continue
                if not isinstance(p, dict) or p.get("bicim") != "ahut-vaka":
                    continue
                o = self.depo.ozet(p)
                o["kaynak"] = "github"
                o["dosya"] = f["ad"]
                o["adres"] = d.vaka_adresi(f["ad"])
                ozetler.append(o)
                paketler[f["ad"]] = p
            zaman = _simdi_metni()
            self._onbellek_yaz({"zaman": zaman, "depo": d.tam_ad,
                                "liste": ozetler, "paketler": paketler})
            onbellek = {"depo": d.tam_ad}
            return paketle("canli", ozetler, zaman)
        except gh.GitHubHatasi as e:
            return paketle("onbellek" if onbellek.get("liste") else "yerel",
                           onbellek.get("liste") or [], onbellek.get("zaman"), str(e))

    def github_vaka(self, dosya: str) -> dict | None:
        """Önce önbellek, yoksa canlı indirme."""
        p = (self._onbellek_oku().get("paketler") or {}).get(dosya)
        if p:
            return p
        try:
            d = self._depo_nesnesi()
            for f in d.liste():
                if f["ad"] == dosya:
                    return d.indir(f["indirme"])
        except (gh.GitHubHatasi, ValueError):
            return None
        return None

    def github_al(self, dosya: str) -> dict:
        """Paylaşılan vakayı kendi kütüphaneme kopyala."""
        p = self.github_vaka(dosya)
        if not p:
            return {"hata": "Vaka indirilemedi."}
        import uuid as _u

        p = dict(p)
        p["id"] = _u.uuid4().hex[:12]
        p["ice_aktarma"] = _simdi_metni()
        return {"tamam": True, "ozet": self.depo.kaydet(p)}

    # ------------------------------------------------------------ kabuk işlemleri
    def klasor_goster(self, hangi: str = "render") -> dict:
        yol = {"render": self.render_klasoru, "veri": self.depo.veri,
               "vakalar": self.depo.vakalar}.get(hangi, self.render_klasoru)
        try:
            if sys.platform == "win32":
                os.startfile(str(yol))  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(yol)])
            else:
                subprocess.Popen(["xdg-open", str(yol)])
            return {"tamam": True, "yol": str(yol)}
        except Exception as e:
            return {"hata": str(e)}

    def baglanti_ac(self, url: str) -> dict:
        if not str(url).startswith(("http://", "https://")):
            return {"hata": "Yalnızca http/https bağlantıları açılır."}
        webbrowser.open(url)
        return {"tamam": True}

    def tam_ekran(self) -> dict:
        try:
            self._pencere.toggle_fullscreen()
            return {"tamam": True}
        except Exception as e:
            return {"hata": str(e)}

    def cikis(self) -> None:
        try:
            self._pencere.destroy()
        except Exception:
            pass
