"""3B sahne arka ucu: vaka geometrisi (blockMeshDict/polyMesh), ağ kenarları, 3B sonuç dosyaları (of_3b_export.py çıktısı),
arka planda dışa aktarma ve ParaView'ı açma. Backend sayılarına dokunmaz; yalnız dosya okur (ve dışa aktarma çıktısı yazar)."""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

import numpy as np

_kilit = threading.RLock()
_onbellek: dict = {}


def _b64(a: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode("ascii")


# ------------------------------------------------------------------ OpenFOAM ASCII okuma
def _foam_liste(yol: Path) -> str:
    s = yol.read_text(errors="ignore")
    i = s.find("(", s.find("FoamFile") + 1 if "FoamFile" in s else 0)
    m = re.search(r"\n(\d+)\s*\n\(", s)
    return s[m.end() - 1:] if m else s[i:]


def noktalar(yol: Path) -> np.ndarray:
    metin = _foam_liste(yol)
    v = re.findall(r"\(([-0-9.eE+]+) ([-0-9.eE+]+) ([-0-9.eE+]+)\)", metin)
    return np.array(v, dtype=np.float64)


def yuzler(yol: Path) -> list:
    metin = _foam_liste(yol)
    return [list(map(int, m.split())) for m in re.findall(r"\d+\(([\d ]+)\)", metin)]


# ------------------------------------------------------------------ OpenFOAM vakası geometrisi
def ofm_geometri(paket: Path) -> dict | None:
    """OpenFOAM Saffire vakası (motor_c/vaka): bölgelerin sınırları (m), tel konumu. Önbellekli."""
    v = paket / "vaka"
    if not v.is_dir():
        return None
    with _kilit:
        if "geo" in _onbellek:
            return _onbellek["geo"]
        bolge = {}
        for ad in ("fluid", "sibal", "tel"):
            f = v / "constant" / ad / "polyMesh" / "points"
            if f.exists():
                p = noktalar(f)
                bolge[ad] = {"min": p.min(0).round(6).tolist(), "max": p.max(0).round(6).tolist(), "nokta": len(p)}
        bm = (v / "system" / "blockMeshDict").read_text(errors="ignore")
        tel = re.search(r"xw=([0-9.eE+-]+) r=([0-9.eE+-]+)", bm)
        g = {"kaynak": "vaka", "dosya": str(v / "system" / "blockMeshDict"), "bolge": bolge,
             "tel": {"x": float(tel.group(1)), "r": float(tel.group(2))} if tel else None, "boyut": "2B",
             "not": "OpenFOAM Saffire-III S1 vakası: 2B (z derinliği 10 mm), y = 0 numune yüzeyi; boyutlar polyMesh'ten."}
        _onbellek["geo"] = g
        return g


def ofm_izgara(paket: Path, bolgeler=("fluid", "sibal")) -> dict | None:
    """2B vakada z = zmin düzlemindeki yüzlerin benzersiz kenarları (hücre kenarları) — Float32 [x0 y0 z0 x1 y1 z1 ...] base64."""
    v = paket / "vaka"
    with _kilit:
        if "izgara" in _onbellek:
            return _onbellek["izgara"]
        parcalar, sayi = [], 0
        for ad in bolgeler:
            pm = v / "constant" / ad / "polyMesh"
            if not (pm / "points").exists():
                continue
            p = noktalar(pm / "points")
            zmin = p[:, 2].min()
            alt = np.abs(p[:, 2] - zmin) < 1e-9
            kenar = set()
            for f in yuzler(pm / "faces"):
                if all(alt[i] for i in f):
                    for a, b in zip(f, f[1:] + f[:1]):
                        kenar.add((a, b) if a < b else (b, a))
            k = np.array(sorted(kenar), dtype=np.int64)
            parcalar.append(p[k.reshape(-1)].reshape(-1, 6).astype(np.float32))
            sayi += len(k)
        if not parcalar:
            return None
        r = {"kenar": sayi, "veri": _b64(np.vstack(parcalar))}
        _onbellek["izgara"] = r
        return r


# ------------------------------------------------------------------ 3B sonuçlar (npz)
def _kokler(proje: Path, ofm_kok: Path | None) -> list[Path]:
    return [x for x in (proje / "of_kosular", (ofm_kok / "ofm_kosu") if ofm_kok else None) if x and x.is_dir()]


def sonuc_listesi(proje: Path, ofm_kok: Path | None) -> list[dict]:
    cikti = []
    for kok in _kokler(proje, ofm_kok):
        for f in list(kok.glob("*_3b.npz")) + list(kok.glob("*/*_3b.npz")) + list(kok.glob("*/*/*_3b.npz")):
            m = sonuc_meta(f)
            if m:
                cikti.append({"yol": str(f), "ad": m.get("ad"), "kosul": m.get("kosul"), "zaman_sayisi": len(m.get("zamanlar", [])),
                              "alanlar": m.get("alanlar"), "kosu": m.get("kosu"), "boyut_mb": round(f.stat().st_size / 1e6, 1)})
    return sorted(cikti, key=lambda x: x["ad"] or "")


def _npz(yol: Path):
    with _kilit:
        k = ("npz", str(yol), yol.stat().st_mtime)
        if k not in _onbellek:
            for eski in [x for x in _onbellek if isinstance(x, tuple) and x[0] == "npz" and x[1] == str(yol)]:
                del _onbellek[eski]
            _onbellek[k] = np.load(yol)
        return _onbellek[k]


def sonuc_meta(yol: Path) -> dict | None:
    try:
        return json.loads(bytes(_npz(Path(yol))["meta"]).decode())
    except Exception:  # noqa: BLE001
        return None


def sonuc_kare(yol: Path, i: int) -> dict:
    z = _npz(Path(yol))
    m = json.loads(bytes(z["meta"]).decode())
    i = max(0, min(int(i), len(m["zamanlar"]) - 1))
    d = z[f"damla_{i}"] if f"damla_{i}" in z.files else np.zeros((0, 3), np.float32)
    if len(d) > 6000:                                   # arayüz için seyrelt
        d = d[:: int(np.ceil(len(d) / 6000))]
    return {"i": i, "t": m["zamanlar"][i], "alanlar": {a: _b64(z[f"alan_{a}"][i]) for a in m["alanlar"]},
            "damla": _b64(d.astype(np.float32)), "damla_sayisi": int(len(d))}


# ------------------------------------------------------------------ dışa aktarma (arka planda) ve ParaView
_aktarimlar: dict[str, dict] = {}


def disa_aktar_baslat(proje: Path, dizin: str) -> dict:
    d = Path(dizin).resolve()
    if not d.is_dir():
        return {"hata": "dizin yok"}
    if not ((d / "processor0").is_dir() or any(re.fullmatch(r"[0-9.eE+-]+", x.name) and x.name != "0" for x in d.iterdir() if x.is_dir())):
        return {"hata": "alan çıktısı (zaman klasörü) yok: 3B dışa aktarılamaz", "atlandi": True}
    pv = shutil.which("pvpython")
    if not pv:
        return {"hata": "pvpython yok"}
    with _kilit:
        a = _aktarimlar.get(str(d))
        if a and a["p"].poll() is None:
            return {"durum": "sürüyor"}
        log = open(d.parent / f"{d.name}_3b.log", "w")
        p = subprocess.Popen(["nice", "-n", "19", pv, str(proje / "of_3b_export.py"), str(d)], stdout=log, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, start_new_session=True)
        _aktarimlar[str(d)] = {"p": p, "bas": time.time(), "log": str(d.parent / f"{d.name}_3b.log")}
    return {"durum": "başladı", "pid": p.pid}


def disa_aktar_durumu() -> list[dict]:
    with _kilit:
        return [{"dizin": k, "durum": "sürüyor" if v["p"].poll() is None else ("tamam" if v["p"].returncode == 0 else f"hata ({v['p'].returncode})"),
                 "sure_s": round(time.time() - v["bas"], 1), "log": v["log"]} for k, v in _aktarimlar.items()]


def paraview_ac(proje: Path, dizin: str, gecici: Path) -> dict:
    d = Path(dizin).resolve()
    if not d.is_dir():
        return {"hata": "dizin yok"}
    pv = shutil.which("paraview")
    if not pv:
        return {"hata": "paraview kurulu değil"}
    env = dict(os.environ)
    betik = proje / "pv_3b.py"
    if betik.exists() and d.parent.name == "sizinti3d_ince":
        env["PV_KOK"] = str(d.parent)
        komut = [pv, f"--script={betik}"]
        aciklama = "pv_3b.py (uzay | mars, izo 1200/2400 K, damlalar)"
    else:
        foam = next(iter(sorted(d.glob("*.foam"))), None)
        if foam is None:
            foam = d / f"{d.name}.foam"
            foam.write_text("")
        gecici.mkdir(parents=True, exist_ok=True)
        s = gecici / "pv_ac.py"
        bolge = '\nr.MeshRegions = ["fluid/internalMesh"]' if (d / "constant" / "fluid").is_dir() else ""
        s.write_text("from paraview.simple import *\n"
                     f"r = OpenFOAMReader(FileName={str(foam)!r})\n"
                     + ("r.CaseType = 'Decomposed Case'\n" if (d / "processor0").is_dir() else "") + bolge.lstrip("\n") + "\n"
                     "Show(r); ColorBy(GetDisplayProperties(r), ('CELLS', 'T')); ResetCamera(); Render()\n", encoding="utf-8")
        komut = [pv, f"--script={s}"]
        aciklama = "Decomposed Case" if (d / "processor0").is_dir() else "Reconstructed Case"
    p = subprocess.Popen(komut, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return {"tamam": True, "pid": p.pid, "aciklama": aciklama, "komut": " ".join(komut)}
