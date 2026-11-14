"""Çözüm İzleyici arka ucu: koşu kuyruğu, günlük akışı ve donanım ölçümleri.

Sayıların hiçbiri uydurulmaz; ölçülemeyen değer None olur. Hiçbir işlem sudo gerektirmez.
Kendi başlattığımız koşular iptal edilebilir; başka oturumların (harici) koşuları yalnız izlenir, asla durdurulmaz.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

DURUMLAR = ("BEKLİYOR", "ÇALIŞIYOR", "DURAKLADI", "TAMAM", "IRAKSADI", "İPTAL", "DİSK DOLU")
FOAM_COZUCU = {"foamRun", "foamMultiRun", "foamRun.exe"}
FOAM_SURECLER = FOAM_COZUCU | {"mpirun", "mpiexec", "pimpleFoam", "buoyantFoam", "reactingFoam", "chtMultiRegionFoam"}
_RE_HATA = re.compile(r"FOAM FATAL|FATAL|\bError\b|\berror\b|HATA|Floating point|sigFpe.*(trap|exception)|No space left|çöktü", re.I)
_RE_UYARI = re.compile(r"warning|uyarı|DİKKAT|bounding|negative", re.I)
_RE_SAYI = r"([-+0-9.eE]+)"
SERI_EN_FAZLA = 400


def _seviye(satir: str) -> str:
    if _RE_HATA.search(satir) and "sigFpe : Enabling" not in satir:
        return "hata"
    return "uyari" if _RE_UYARI.search(satir) else "bilgi"


def _son_satir(yol: Path, bayt: int = 4096) -> str | None:
    try:
        with open(yol, "rb") as f:
            f.seek(0, os.SEEK_END)
            n = f.tell()
            f.seek(max(0, n - bayt))
            satirlar = [s for s in f.read().decode("utf-8", "replace").splitlines() if s.strip() and not s.startswith("#")]
            return satirlar[-1] if satirlar else None
    except OSError:
        return None


class _FoamAyrisici:
    """log.foamRun akışını adım adım çözer. Sıra: Courant → deltaT → Time → … → ExecutionTime."""

    def __init__(self):
        self.co = self.dt = self.t = None
        self.adim = 0
        self.saat = None          # ExecutionTime (s)
        self.sonsatir_t = -1e9    # en son örneklenen duvar saati
        self.zincir = deque(maxlen=4000)   # (duvar_saati, adim) — adım/dk için

    def isle(self, satir: str):
        """(adim_bitti_mi) döndürür; değerler özelliklerde."""
        m = re.match(r"\s*(?:\w+\s+)?Courant Number mean:\s*" + _RE_SAYI + r"\s+max:\s*" + _RE_SAYI, satir)
        if m:
            self.co = float(m.group(2))
            return False
        m = re.match(r"\s*deltaT\s*=\s*" + _RE_SAYI, satir)
        if m:
            self.dt = float(m.group(1))
            return False
        m = re.match(r"\s*Time\s*=\s*" + _RE_SAYI + r"\s*s?\s*$", satir)
        if m:
            self.t = float(m.group(1))
            self.adim += 1
            return False
        m = re.match(r"\s*ExecutionTime\s*=\s*" + _RE_SAYI + r"\s*s\s+ClockTime\s*=\s*" + _RE_SAYI, satir)
        if m:
            self.saat = float(m.group(2))
            self.zincir.append((self.saat, self.adim))
            return True
        return False

    def adim_dk(self):
        if len(self.zincir) < 2:
            return None
        t1, a1 = self.zincir[-1]
        t0, a0 = next(((t, a) for t, a in self.zincir if t >= t1 - 60), self.zincir[0])
        return 60.0 * (a1 - a0) / (t1 - t0) if t1 > t0 else None


class Izleyici:
    def __init__(self, veri: Path, kosu_klasoru: Path | None = None):
        self.veri = veri
        self.kayit_dosyasi = veri / "kosular.json"
        self.kosu_klasoru = kosu_klasoru if kosu_klasoru and kosu_klasoru.is_dir() else None
        self._kilit = threading.RLock()
        self._kosular: dict[str, dict] = {}
        self._popen: dict[str, subprocess.Popen] = {}
        self._ayr: dict[str, dict] = {}          # kaynak -> {ofset, ayrisici, seri, rows...}
        self._surecler: dict[int, object] = {}   # psutil.Process önbelleği (cpu_percent referansı için)
        self._bildirim: list[dict] = []
        self._olaylar: list[dict] = []           # uyarı olayları (ör. kaldırma denetimi) — kosular() ile bir kez verilir
        self.bitis_kancasi = None                # callable(kayit): TAMAM bitince ayrı iş parçacığında (ör. içe aktarma)
        self.disa_aktar_kancasi = None           # callable(kayit): TAMAM bitince 3B dışa aktarma başlatır
        self.kontrol_kancasi = None              # callable(kayit, log_metni) -> (tamam|None, mesaj)
        self._gecmis: dict[str, deque] = {}      # ilerleme için (duvar saati, t) örnekleri
        self._yukle()
        self._dongu = threading.Thread(target=self._calis, daemon=True)
        self._dongu.start()

    # ------------------------------------------------------------ kayıt
    def _yukle(self):
        try:
            for k in json.loads(self.kayit_dosyasi.read_text(encoding="utf-8")).get("kosular", []):
                if k.get("durum") in ("ÇALIŞIYOR", "BEKLİYOR", "DURAKLADI") and not k.get("harici"):
                    k["durum"] = "İPTAL"          # uygulama kapanırken yarım kalmış
                    k["bitis"] = k.get("bitis") or time.time()
                self._kosular[k["id"]] = k
        except (OSError, ValueError):
            pass

    def _yaz(self):
        try:
            self.veri.mkdir(parents=True, exist_ok=True)
            son = sorted(self._kosular.values(), key=lambda k: k.get("baslangic") or 0)[-100:]
            self.kayit_dosyasi.write_text(json.dumps({"kosular": son}, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass

    # ------------------------------------------------------------ koşu kuyruğu (kendi koşularımız)
    def kosu_ekle(self, ad: str, dizin: str, komut: list[str] | str, log: str = "log.kosu", cekirdek: int = 1,
                  ice_aktar: bool = False, kaldirma: bool = False, bitis_s: float | None = None) -> dict:
        """Kuyruğa bir koşu ekler; sırayla, aynı anda en çok bir tane çalışır. komut: argüman listesi (kabuk yok)."""
        d = Path(dizin).expanduser().resolve()
        if not d.is_dir():
            return {"hata": f"dizin yok: {d}"}
        if isinstance(komut, str):
            import shlex
            komut = shlex.split(komut)
        kid = f"k{int(time.time() * 1000)}"
        with self._kilit:
            self._kosular[kid] = {"id": kid, "ad": ad or d.name, "dizin": str(d), "log": log, "komut": list(komut),
                                  "cekirdek": cekirdek, "durum": "BEKLİYOR", "olusturma": time.time(),
                                  "ice_aktar": ice_aktar, "kaldirma": kaldirma, "bitis_s": bitis_s, "ice_aktarma": None, "kontrol": None,
                                  "baslangic": None, "bitis": None, "harici": False, "pid": None}
            self._yaz()
        return {"id": kid}

    def kosu_iptal(self, kid: str) -> dict:
        with self._kilit:
            k = self._kosular.get(kid)
            if not k:
                return {"hata": "koşu yok"}
            if k.get("harici"):
                return {"hata": "Harici koşu (başka oturum) buradan durdurulmaz."}
            if k["durum"] == "BEKLİYOR":
                k["durum"] = "İPTAL"
                k["bitis"] = time.time()
                self._yaz()
                return {"tamam": True}
            p = self._popen.get(kid)
            if p and p.poll() is None:
                k["iptal"] = True
                self._sinyal(p, signal.SIGTERM)
                if k["durum"] == "DURAKLADI":         # durdurulmuş süreç SIGTERM'i ancak uyanınca işler
                    self._sinyal(p, signal.SIGCONT)
                return {"tamam": True}
            return {"hata": "koşu çalışmıyor"}

    def _sinyal(self, p: subprocess.Popen, sig) -> None:
        """Kendi başlattığımız koşunun tüm süreçlerine (mpirun ve çözücü kopyaları dahil) sinyal yollar."""
        hedef = []
        try:
            import psutil
            ana = psutil.Process(p.pid)
            hedef = ana.children(recursive=True) + [ana]
        except Exception:  # noqa: BLE001
            pass
        for q in hedef:
            try:
                q.send_signal(sig)
            except Exception:  # noqa: BLE001
                pass
        try:                                          # yalnız kendi başlattığımız süreç grubu (PID ile)
            os.killpg(os.getpgid(p.pid), sig)
        except (OSError, ProcessLookupError):
            if not hedef:
                p.send_signal(sig)

    def kapat(self) -> None:
        """Uygulama kapanırken: kendi koşularımız (çalışan, duraklatılmış) sonlandırılır, bekleyenler iptal edilir.
        Böylece pencere kapandıktan sonra arkada sahipsiz mpirun/foamRun kalmaz."""
        with self._kilit:
            for kid, k in self._kosular.items():
                if k.get("harici"):
                    continue
                if k["durum"] == "BEKLİYOR":
                    k["durum"], k["bitis"] = "İPTAL", time.time()
                p = self._popen.get(kid)
                if p and p.poll() is None:
                    k["iptal"] = True
                    self._sinyal(p, signal.SIGTERM)
                    self._sinyal(p, signal.SIGCONT)
                    k["durum"], k["bitis"] = "İPTAL", time.time()
            self._yaz()
        bitis = time.time() + 5
        for p in list(self._popen.values()):
            while p.poll() is None and time.time() < bitis:
                time.sleep(0.1)
            if p.poll() is None:
                self._sinyal(p, signal.SIGKILL)

    def kosu_duraklat(self, kid: str) -> dict:
        """Çalışan koşuyu duraklatır (SIGSTOP): çekirdekler boşalır, bellek tutulur; Devam ile kaldığı yerden sürer."""
        with self._kilit:
            k = self._kosular.get(kid)
            if not k:
                return {"hata": "koşu yok"}
            if k.get("harici"):
                return {"hata": "Harici koşu (başka oturum) buradan duraklatılmaz."}
            p = self._popen.get(kid)
            if k["durum"] != "ÇALIŞIYOR" or not p or p.poll() is not None:
                return {"hata": "koşu çalışmıyor"}
            self._sinyal(p, signal.SIGSTOP)
            k["durum"], k["duraklama_bas"] = "DURAKLADI", time.time()
            self._yaz()
            return {"tamam": True}

    def kosu_devam(self, kid: str) -> dict:
        with self._kilit:
            k = self._kosular.get(kid)
            if not k:
                return {"hata": "koşu yok"}
            p = self._popen.get(kid)
            if k["durum"] != "DURAKLADI" or not p or p.poll() is not None:
                return {"hata": "koşu duraklatılmış değil"}
            self._sinyal(p, signal.SIGCONT)
            k["duraklama_top"] = (k.get("duraklama_top") or 0) + (time.time() - (k.get("duraklama_bas") or time.time()))
            k["durum"], k["duraklama_bas"] = "ÇALIŞIYOR", None
            self._gecmis.pop(kid, None)               # kalan süre tahmini duraklamadan etkilenmesin
            self._yaz()
            return {"tamam": True}

    def _baslat(self, k: dict):
        log = Path(k["dizin"]) / k["log"]
        try:
            f = open(log, "ab", buffering=0)
            p = subprocess.Popen(["nice", "-n", "19"] + k["komut"], cwd=k["dizin"], stdout=f, stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL, start_new_session=True)
        except Exception as e:  # noqa: BLE001
            k["durum"], k["bitis"], k["hata"] = "IRAKSADI", time.time(), str(e)
            return
        self._popen[k["id"]] = p
        k.update(durum="ÇALIŞIYOR", baslangic=time.time(), pid=p.pid)

    def _bitir(self, k: dict, durum: str):
        k["durum"], k["bitis"] = durum, time.time()
        self._bildirim.append({"id": k["id"], "ad": k["ad"], "durum": durum})
        self._yaz()
        if durum == "TAMAM" and self.disa_aktar_kancasi:          # 3B dışa aktarma (kendi ve harici koşular; yalnız okur)
            try:
                k["disa_aktarma"] = self.disa_aktar_kancasi(dict(k))
            except Exception as e:  # noqa: BLE001
                k["disa_aktarma"] = {"hata": f"{type(e).__name__}: {e}"}
        if durum == "TAMAM" and k.get("ice_aktar") and self.bitis_kancasi:
            k["ice_aktarma"] = "bekliyor"
            threading.Thread(target=self._kanca, args=(k,), daemon=True).start()
        try:   # masaüstü bildirimi (varsa; sessizce atlanır)
            if shutil.which("notify-send"):
                subprocess.Popen(["notify-send", "AHUT FLARE", f"Koşu {durum}: {k['ad']}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass

    def _kanca(self, k: dict):
        try:
            sonuc = self.bitis_kancasi(dict(k))
            k["ice_aktarma"] = "hata: " + str(sonuc["hata"]) if isinstance(sonuc, dict) and sonuc.get("hata") else "tamam"
        except Exception as e:  # noqa: BLE001
            k["ice_aktarma"] = f"hata: {type(e).__name__}: {e}"
        with self._kilit:
            self._yaz()

    def _kaldirma_denetle(self, k: dict):
        """Kendi koşumuzun ilk dakikasında günlükten kaldırmanın (p_rgh) açık olduğunu denetler."""
        if not k.get("kaldirma") or k.get("kontrol") or not k.get("baslangic") or time.time() - k["baslangic"] < 60 or not self.kontrol_kancasi:
            return
        try:
            with open(Path(k["dizin"]) / k["log"], "rb") as f:
                f.seek(0, os.SEEK_END)
                f.seek(max(0, f.tell() - 400000))
                metin = f.read().decode("utf-8", "replace")
            tamam, mesaj = self.kontrol_kancasi(dict(k), metin)
        except Exception as e:  # noqa: BLE001
            tamam, mesaj = None, f"denetlenemedi: {type(e).__name__}"
        k["kontrol"] = {"tamam": tamam, "mesaj": mesaj}
        self._olaylar.append({"id": k["id"], "ad": k["ad"], "tur": "kaldirma", "tamam": tamam, "mesaj": mesaj})

    def ilerleme(self, kid: str) -> dict | None:
        """Hafif ilerleme: günlüğün son 40 KB'ından t, adım, kalan süre (kendi örnek geçmişiyle). Günlük akışı (izle) ile karışmaz."""
        k = self._kosular.get(kid)
        if not k:
            return None
        yol = Path(k["dizin"]) / k["log"]
        try:
            with open(yol, "rb") as f:
                f.seek(0, os.SEEK_END)
                f.seek(max(0, f.tell() - 40000))
                m = f.read().decode("utf-8", "replace")
        except OSError:
            return {"durum": k["durum"]}
        tt = re.findall(r"^\s*Time\s*=\s*" + _RE_SAYI + r"\s*s?\s*$", m, re.M)
        ck = re.findall(r"ExecutionTime\s*=\s*" + _RE_SAYI + r"\s*s\s+ClockTime\s*=\s*" + _RE_SAYI, m)
        t = float(tt[-1]) if tt else None
        saat = float(ck[-1][1]) if ck else None
        bitis = k.get("bitis_s") or self._bitis_zamani(Path(k["dizin"]))
        g = self._gecmis.setdefault(kid, deque(maxlen=400))
        if t is not None and saat is not None and (not g or saat > g[-1][0]):
            g.append((saat, t))
        kalan = None
        if bitis and t is not None and len(g) >= 2:
            ilk = next((x for x in g if x[0] >= g[-1][0] - 300), g[0])
            if g[-1][0] > ilk[0] and g[-1][1] > ilk[1]:
                kalan = max(0.0, (bitis - t) * (g[-1][0] - ilk[0]) / (g[-1][1] - ilk[1]))
        return {"durum": k["durum"], "t": t, "bitis_t": bitis, "yuzde": (100.0 * t / bitis) if bitis and t is not None else None,
                "kalan_s": kalan, "duvar_s": saat}

    def kosu(self, kid: str) -> dict | None:
        with self._kilit:
            k = self._kosular.get(kid)
            return dict(k) if k else None

    def _bitis_durumu(self, k: dict, cikis: int | None) -> str:
        log = Path(k["dizin"]) / k["log"]
        son = ""
        try:
            with open(log, "rb") as f:
                f.seek(0, os.SEEK_END)
                f.seek(max(0, f.tell() - 20000))
                son = f.read().decode("utf-8", "replace")
        except OSError:
            pass
        if "No space left" in son or self.disk()["bos"] < 150e6:
            return "DİSK DOLU"
        if k.get("iptal"):
            return "İPTAL"
        if cikis == 0:
            return "TAMAM"
        return "IRAKSADI"

    def _calis(self):
        """Saniyede bir: kendi koşularımızın durumu, sıradaki koşu, harici koşu keşfi."""
        while True:
            try:
                with self._kilit:
                    for k0 in list(self._kosular.values()):
                        if k0["durum"] == "ÇALIŞIYOR" and not k0.get("harici"):
                            self._kaldirma_denetle(k0)
                    for kid, p in list(self._popen.items()):
                        r = p.poll()
                        if r is not None:
                            k = self._kosular[kid]
                            self._bitir(k, self._bitis_durumu(k, r))
                            del self._popen[kid]
                    if not self._popen:
                        sira = sorted((k for k in self._kosular.values() if k["durum"] == "BEKLİYOR"), key=lambda k: k["olusturma"])
                        if sira:
                            self._baslat(sira[0])
                    self._harici_tara()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(1.0)

    # ------------------------------------------------------------ harici koşular (başka oturumlar; yalnız izlenir)
    def _foam_surecleri(self):
        try:
            import psutil
        except ImportError:
            return []
        canli = {}
        for p in psutil.process_iter(["pid", "name"]):
            try:
                if p.info["name"] in FOAM_SURECLER:
                    canli[p.pid] = self._surecler.get(p.pid) or p
                    self._surecler[p.pid] = canli[p.pid]
            except (psutil.Error, OSError):
                pass
        for pid in list(self._surecler):
            if pid not in canli:
                del self._surecler[pid]
        return list(canli.values())

    def _harici_tara(self):
        try:
            import psutil
        except ImportError:
            return
        ownpids = {p.pid for p in self._popen.values()}
        dizinler: dict[str, int] = {}
        for p in self._foam_surecleri():
            try:
                if p.name() not in FOAM_COZUCU or p.pid in ownpids:
                    continue
                dizinler[p.cwd()] = dizinler.get(p.cwd(), 0) + 1
            except (psutil.Error, OSError):
                pass
        sahip = {k["dizin"] for k in self._kosular.values() if k["durum"] in ("ÇALIŞIYOR", "DURAKLADI") and not k.get("harici")}
        for d, n in dizinler.items():
            kid = "h:" + d
            if d in sahip or any(str(Path(d)).startswith(s) for s in sahip):
                continue
            k = self._kosular.get(kid)
            if not k or k["durum"] != "ÇALIŞIYOR":
                logs = sorted(Path(d).glob("log*"), key=lambda x: x.stat().st_mtime, reverse=True)
                logs = [x for x in logs if "decompose" not in x.name and "blockMesh" not in x.name] or logs
                self._kosular[kid] = k = {"id": kid, "ad": Path(d).parent.name + "/" + Path(d).name if Path(d).parent != Path(d) else d,
                                          "dizin": d, "log": logs[0].name if logs else "log.foamRun", "komut": [], "durum": "ÇALIŞIYOR",
                                          "olusturma": time.time(), "baslangic": time.time(), "bitis": None, "harici": True, "pid": None}
            k["cekirdek"] = n
        for kid, k in list(self._kosular.items()):
            if k.get("harici") and k["durum"] == "ÇALIŞIYOR" and k["dizin"] not in dizinler:
                self._bitir(k, self._bitis_durumu_harici(k))

    def _bitis_durumu_harici(self, k: dict) -> str:
        d = self._bitis_durumu(k, None)
        if d != "IRAKSADI":
            return d if d != "İPTAL" else "İPTAL"
        # çıkış kodu yok: günlükte bitiş izine bak
        a = self._ayr.get("k:" + k["id"])
        son = self._son_zaman(k)
        bitis_t = self._bitis_zamani(Path(k["dizin"]))
        if son is not None and bitis_t is not None and son >= bitis_t * 0.999:
            return "TAMAM"
        try:
            ic = (Path(k["dizin"]) / k["log"]).read_text(encoding="utf-8", errors="replace")[-6000:]
            if re.search(r"FOAM (FATAL|exiting)|Floating point exception", ic):
                return "IRAKSADI"
        except OSError:
            pass
        return "İPTAL"

    def _son_zaman(self, k):
        a = self._ayr.get(k["id"])
        return a["ayr"].t if a else None

    @staticmethod
    def _bitis_zamani(dizin: Path):
        try:
            m = re.search(r"^endTime\s+" + _RE_SAYI + ";", (dizin / "system" / "controlDict").read_text(), re.M)
            return float(m.group(1)) if m else None
        except (OSError, ValueError):
            return None

    # ------------------------------------------------------------ liste
    def kosular(self) -> dict:
        with self._kilit:
            liste = []
            simdi = time.time()
            for k in sorted(self._kosular.values(), key=lambda k: (k["durum"] not in ("ÇALIŞIYOR", "DURAKLADI", "BEKLİYOR"), -(k.get("baslangic") or k["olusturma"]))):
                liste.append({"id": k["id"], "ad": k["ad"], "dizin": k["dizin"], "durum": k["durum"], "harici": bool(k.get("harici")),
                              "baslangic": k.get("baslangic"), "bitis": k.get("bitis"), "cekirdek": k.get("cekirdek"),
                              "sure": ((k.get("bitis") or k.get("duraklama_bas") or simdi) - k["baslangic"] - (k.get("duraklama_top") or 0)) if k.get("baslangic") else None, "pid": k.get("pid"),
                              "ice_aktar": bool(k.get("ice_aktar")), "ice_aktarma": k.get("ice_aktarma"), "kontrol": k.get("kontrol")})
            bil, self._bildirim = self._bildirim, []
            olay, self._olaylar = self._olaylar, []
        return {"kosular": liste[:60], "biten": bil, "olaylar": olay}

    def kaynaklar(self) -> list[dict]:
        """Günlük akışı kaynakları: koşular + of_kosular/canli_*.log kuyruk günlükleri."""
        k = [{"id": x["id"], "ad": x["ad"], "tur": "kosu", "durum": x["durum"]} for x in self.kosular()["kosular"]]
        if self.kosu_klasoru:
            for p in sorted(self.kosu_klasoru.glob("canli_*.log"), key=lambda x: x.stat().st_mtime, reverse=True)[:6]:
                k.append({"id": "canli:" + p.name, "ad": p.name, "tur": "canli", "durum": ""})
        return k

    def _yol(self, kaynak: str) -> Path | None:
        if kaynak.startswith("canli:") and self.kosu_klasoru:
            p = (self.kosu_klasoru / kaynak[6:]).resolve()
            return p if p.parent == self.kosu_klasoru.resolve() and p.name.startswith("canli_") and p.suffix == ".log" else None
        k = self._kosular.get(kaynak)
        return (Path(k["dizin"]) / k["log"]) if k else None

    def log_yolu(self, kaynak: str) -> str | None:
        p = self._yol(kaynak)
        return str(p) if p else None

    # ------------------------------------------------------------ günlük akışı
    def izle(self, kaynak: str, ofset: int | None = None, sifirla: bool = False) -> dict:
        """Günlüğün yeni satırlarını (tail -f gibi) ve izleme serisini verir.
        Foam günlüğünde ~2 s'de bir adım satırı: {saat, kosu, adim, t, yuzde, dt, tmax, co, kalan}."""
        yol = self._yol(kaynak)
        if yol is None or not yol.is_file():
            return {"hata": "günlük yok", "satirlar": [], "ofset": 0}
        with self._kilit:
            a = self._ayr.get(kaynak)
            if a is None or sifirla:
                a = self._ayr[kaynak] = {"ofset": None, "ayr": _FoamAyrisici(), "seri": [], "son_ornek": -1e9, "son_satir": -1e9,
                                         "bitis_t": None, "tmax": None, "tmax_zaman": 0}
            canli = kaynak.startswith("canli:")
            if not canli and a["bitis_t"] is None:
                a["bitis_t"] = self._bitis_zamani(yol.parent)
            try:
                boyut = yol.stat().st_size
                with open(yol, "rb") as f:
                    bas = a["ofset"]
                    if bas is None or bas > boyut:
                        bas = max(0, boyut - (24000 if canli else 150000))
                        a["ofset"] = bas
                    f.seek(bas)
                    veri = f.read(400000)
                    a["ofset"] = bas + len(veri)
            except OSError as e:
                return {"hata": str(e), "satirlar": [], "ofset": 0}
            metin = veri.decode("utf-8", "replace")
            if bas > 0 and metin and not canli:       # ilk okumada yarım satırı at
                metin = metin.split("\n", 1)[-1] if a["son_satir"] < -1e8 else metin
            cikti = []
            ayr: _FoamAyrisici = a["ayr"]
            for s in metin.splitlines():
                if not s.strip():
                    continue
                if canli:
                    cikti.append({"seviye": _seviye(s), "metin": s})
                    continue
                if ayr.isle(s):
                    if ayr.saat - a["son_ornek"] >= 2.0 or a["son_ornek"] < 0:
                        a["son_ornek"] = ayr.saat
                        o = self._ornek(a, yol.parent)
                        cikti.append({"seviye": "bilgi", "satir": o, "metin": self._ornek_metni(o)})
                elif _seviye(s) != "bilgi" and "sigFpe : Enabling" not in s:
                    cikti.append({"seviye": _seviye(s), "metin": s.strip()})
            ozet = None
            if not canli:
                ozet = self._ozet(a)
            return {"satirlar": cikti[-300:], "ofset": a["ofset"], "seri": a["seri"][-SERI_EN_FAZLA:], "ozet": ozet,
                    "yol": str(yol)}

    def _tmax(self, a, dizin: Path):
        """postProcessing içindeki max(T) tablolarının son satırı; en büyük değer."""
        simdi = time.time()
        if simdi - a["tmax_zaman"] < 3.0:
            return a["tmax"]
        a["tmax_zaman"] = simdi
        en = None
        pp = dizin / "postProcessing"
        if pp.is_dir():
            for f in list(pp.glob("*/*/volFieldValue.dat")) + list(pp.glob("*/*/*/volFieldValue.dat")):
                try:
                    with open(f, "r", errors="replace") as fh:
                        bas = [fh.readline() for _ in range(6)]
                    bas = "".join(bas)
                    if "max(T)" not in bas:
                        continue
                    kolon = [x for x in re.split(r"\s+", next(l for l in bas.splitlines() if l.startswith("# Time")).replace("# Time", "").strip())]
                    son = _son_satir(f)
                    if not son:
                        continue
                    v = son.split()
                    for i, ad in enumerate(kolon):
                        if ad == "max(T)" and i + 1 < len(v):
                            x = float(v[i + 1])
                            en = x if en is None else max(en, x)
                except (OSError, ValueError, StopIteration):
                    continue
        a["tmax"] = en
        return en

    def _ornek(self, a, dizin: Path) -> dict:
        ayr = a["ayr"]
        tmax = self._tmax(a, dizin)
        yuzde = 100.0 * ayr.t / a["bitis_t"] if a["bitis_t"] and ayr.t is not None else None
        o = {"saat": time.strftime("%H:%M:%S"), "adim": ayr.adim, "t": ayr.t, "yuzde": yuzde, "dt": ayr.dt, "tmax": tmax, "co": ayr.co,
             "adim_dk": ayr.adim_dk(), "duvar": ayr.saat}
        a["seri"].append({k: o[k] for k in ("duvar", "t", "dt", "tmax", "co", "adim_dk")})
        if len(a["seri"]) > 2 * SERI_EN_FAZLA:
            a["seri"] = a["seri"][-SERI_EN_FAZLA:]
        o["kalan"] = self._kalan(a)
        return o

    @staticmethod
    def _kalan(a) -> float | None:
        s = a["seri"]
        if len(s) < 2 or not a["bitis_t"]:
            return None
        son = s[-1]
        ilk = next((x for x in s if x["duvar"] >= son["duvar"] - 300), s[0])
        if son["duvar"] <= ilk["duvar"] or son["t"] is None or ilk["t"] is None or son["t"] <= ilk["t"]:
            return None
        hiz = (son["t"] - ilk["t"]) / (son["duvar"] - ilk["duvar"])     # sim-s / duvar-s
        return max(0.0, (a["bitis_t"] - son["t"]) / hiz)

    def _ozet(self, a) -> dict:
        ayr = a["ayr"]
        return {"adim": ayr.adim, "t": ayr.t, "bitis_t": a["bitis_t"], "yuzde": (100.0 * ayr.t / a["bitis_t"]) if a["bitis_t"] and ayr.t is not None else None,
                "kalan": self._kalan(a), "bitis_saati": (time.time() + self._kalan(a)) if self._kalan(a) is not None else None,
                "adim_dk": ayr.adim_dk(), "duvar": ayr.saat}

    @staticmethod
    def _ornek_metni(o: dict) -> str:
        f = lambda v, b="{:.4g}": "–" if v is None else b.format(v)
        kalan = "–" if o["kalan"] is None else time.strftime("%H:%M:%S", time.gmtime(o["kalan"])) if o["kalan"] < 86400 else f"{o['kalan'] / 3600:.0f} sa"
        return (f"adım {o['adim']} | t {f(o['t'], '{:.6g}')} s | {f(o['yuzde'], '{:.1f}')} % | Δt {f(o['dt'], '{:.3g}')} | "
                f"Tmax {f(o['tmax'], '{:.1f}')} | Co {f(o['co'], '{:.3g}')} | kalan {kalan}")

    # ------------------------------------------------------------ donanım
    def disk(self) -> dict:
        try:
            u = shutil.disk_usage(self.veri if self.veri.exists() else Path.home())
            return {"bos": u.free, "toplam": u.total, "yuzde": 100.0 * u.used / u.total}
        except OSError:
            return {"bos": 0, "toplam": 0, "yuzde": None}

    def sistem_ek(self) -> dict:
        """Sıcaklık (coretemp), fan, güç profili, disk, pil/priz, foam süreçleri. Ölçülemeyen None."""
        s: dict = {"sicaklik": None, "fan": None, "profil": None, "pil": None, "disk": self.disk(), "foam": []}
        try:
            import psutil
        except ImportError:
            return s
        try:
            t = psutil.sensors_temperatures()
            ct = t.get("coretemp") or []
            if ct:
                paket = next((x.current for x in ct if x.label.startswith("Package")), None)
                cek = sorted(((x.label, x.current) for x in ct if x.label.startswith("Core")), key=lambda p: int(re.sub(r"\D", "", p[0]) or 0))
                s["sicaklik"] = {"paket": paket, "cekirdekler": [{"ad": a, "t": v} for a, v in cek],
                                 "yuksek": next((x.high for x in ct if x.label.startswith("Package")), None)}
        except (AttributeError, OSError):
            pass
        try:
            f = psutil.sensors_fans()
            liste = [{"ad": x.label or k, "rpm": x.current} for k, v in f.items() for x in v]
            s["fan"] = liste or None
        except (AttributeError, OSError):
            pass
        try:
            s["profil"] = Path("/sys/firmware/acpi/platform_profile").read_text().strip()
        except OSError:
            pass
        try:
            b = psutil.sensors_battery()
            if b:
                s["pil"] = {"yuzde": b.percent, "prizde": bool(b.power_plugged)}
        except (AttributeError, OSError):
            pass
        foam = []
        for p in self._foam_surecleri():
            try:
                foam.append({"pid": p.pid, "ad": p.name(), "cpu": p.cpu_percent(None), "cwd": p.cwd()})
            except (psutil.Error, OSError):
                pass
        cozucu = [x for x in foam if x["ad"] in FOAM_COZUCU]
        s["foam"] = {"surecler": foam, "cozucu": len(cozucu), "mpirun": sum(1 for x in foam if x["ad"] in ("mpirun", "mpiexec")),
                     "cekirdek": round(sum(x["cpu"] for x in cozucu) / 100.0, 1),
                     "calisma_dizinleri": sorted({x["cwd"] for x in cozucu})}
        return s
