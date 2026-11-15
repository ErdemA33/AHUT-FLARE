#!/usr/bin/env pvpython
"""scripts/of_3b_export.py — OpenFOAM koşusunu arayüzün 3B sahnesi için hafif biçime aktarır (pvpython; koşu klasörüne YAZMAZ*).

    pvpython scripts/of_3b_export.py KOSU_KLASORU [--kare 20] [--boyut 56 56 40] [--cikti KOSU_KLASORU_3b.npz]

Her ~kare zamanında alanlar (T, O2, yakıt, |U|) düzenli bir ızgaraya örneklenir (ResampleToImage) ve uint16'ya nicelenir;
izo yüzeyleri ve kesit arayüzde bu ızgaradan anında hesaplanır (alan / izo değeri / kesit konumu değiştirilebilsin diye).
Damla noktaları (droplet_vtk/*.vtp ya da lagrangian) varsa en yakın zamandan eklenir. Simetri düzlemi z = 0'da ise (alan
z ≥ 0) z'de yansıtılır (scripts/pv_3b.py gibi). Çıktı: np.savez_compressed, 30 MB altı (gerekirse ızgara küçültülür).
* .foam dosyası yoksa okuyucu için koşu klasörüne boş bir <ad>.foam yazılır (OpenFOAM/ParaView geleneği).
Çok bölgeli vakada (OpenFOAM: fluid/sibal/tel) yalnız 'fluid' bölgesi okunur.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
from paraview.simple import OpenFOAMReader, ResampleToImage, Reflect, UpdatePipeline
from paraview import servermanager
from vtk.util.numpy_support import vtk_to_numpy

YAKITLAR = {"C7H16": "n-heptane", "NC7H16": "n-heptane", "CH4": "methane", "C2H4": "ethylene", "CH3OH": "methanol", "C10H22": "n-decane"}
SINIR_MB = 30.0


def kosul_oku(d: Path, yakit_alani):
    """BILGI.json (OpenFOAM) / bilgi.json / constant/g'den koşul; okunamayan None."""
    k = {"malzeme": YAKITLAR.get(yakit_alani) if yakit_alani else None, "g": None, "oksijen": None, "basinc": None}
    for f in (d / "BILGI.json", d / "bilgi.json"):
        try:
            b = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        kk = b.get("kosullar") or {}
        k["malzeme"] = b.get("malzeme") or k["malzeme"]
        for a in ("g", "oksijen", "basinc", "akis"):
            if kk.get(a) is not None:
                k[a] = kk[a]
        if k["g"] is None and b.get("g") is not None:
            k["g"] = float(b["g"]) / 9.81 if float(b["g"]) > 1.5 else float(b["g"])
    if k["g"] is None:
        for f in (d / "constant" / "g", d / "constant" / "fluid" / "g"):
            if f.exists():
                m = re.search(r"value\s*\(\s*([-0-9.eE+]+)\s+([-0-9.eE+]+)\s+([-0-9.eE+]+)", f.read_text())
                if m:
                    k["g"] = round(float(np.linalg.norm([float(x) for x in m.groups()])) / 9.81, 4)
                break
        else:
            k["g"] = 0.0
    return k


def foam_dosyasi(d: Path) -> Path:
    v = sorted(d.glob("*.foam"))
    if v:
        return v[0]
    f = d / f"{d.name}.foam"
    f.write_text("")
    return f


def damla_noktalari(d: Path, t: float):
    kat = d / "droplet_vtk"
    if not kat.is_dir():
        return None
    adaylar = []
    for f in kat.glob("damla_*.vtp"):
        m = re.match(r"damla_([0-9.eE+-]+)\.vtp$", f.name)
        if m:
            adaylar.append((abs(float(m.group(1)) - t), f))
    if not adaylar:
        return None
    from vtkmodules.vtkIOXML import vtkXMLPolyDataReader
    r = vtkXMLPolyDataReader()
    r.SetFileName(str(min(adaylar)[1]))
    r.Update()
    p = r.GetOutput().GetPoints()
    return None if p is None else vtk_to_numpy(p.GetData()).astype(np.float32)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("kosu")
    a.add_argument("--kare", type=int, default=20)
    a.add_argument("--boyut", type=int, nargs=3, default=[56, 56, 40])
    a.add_argument("--cikti")
    k = a.parse_args()
    d = Path(k.kosu).resolve()
    cikti = Path(k.cikti) if k.cikti else d.parent / f"{d.name}_3b.npz"
    r = OpenFOAMReader(FileName=str(foam_dosyasi(d)))
    if (d / "processor0").is_dir():
        r.CaseType = "Decomposed Case"
    if (d / "constant" / "fluid").is_dir():
        r.MeshRegions = ["fluid/internalMesh"] if "fluid/internalMesh" in r.GetProperty("MeshRegions").Available else ["internalMesh"]
    r.UpdatePipelineInformation()
    mevcut = list(r.CellArrays.Available) if hasattr(r.CellArrays, "Available") else list(r.GetProperty("CellArrayInfo")[::2])
    yakit = next((x for x in YAKITLAR if x in mevcut), None)
    alanlar = [x for x in ("T", "O2", yakit, "U") if x and x in mevcut]
    r.CellArrays = alanlar
    zamanlar = [t for t in r.TimestepValues if t > 0] if r.TimestepValues else []
    if not zamanlar:
        raise SystemExit("zaman adımı yok (alan çıktısı yazılmamış)")
    sec = sorted({zamanlar[int(round(i * (len(zamanlar) - 1) / max(1, k.kare - 1)))] for i in range(min(k.kare, len(zamanlar)))})
    UpdatePipeline(time=sec[-1], proxy=r)
    di = r.GetDataInformation().GetBounds()
    yansit = abs(di[4]) < 1e-9 and di[5] > 0
    kaynak = Reflect(Input=r, Plane="Z Min", CopyInput=1) if yansit else r
    nx, ny, nz = k.boyut
    while True:
        boyut_mb = len(sec) * len(alanlar) * nx * ny * nz * 2 / 1e6
        if boyut_mb < SINIR_MB * 1.6 or nx < 24:      # sıkıştırma ~%40+ kazandırır; yine de sonda denetlenir
            break
        nx, ny, nz = int(nx * 0.85), int(ny * 0.85), int(nz * 0.85)
    rs = ResampleToImage(Input=kaynak, SamplingDimensions=[nx, ny, nz], UseInputBounds=1)
    veri = {x: np.zeros((len(sec), nz, ny, nx), np.uint16) for x in alanlar}
    aralik = {x: [np.inf, -np.inf] for x in alanlar}
    ham = {x: [] for x in alanlar}
    damla = []
    for i, t in enumerate(sec):
        rs.UpdatePipeline(t)
        img = servermanager.Fetch(rs)
        pd = img.GetPointData()
        gecerli = vtk_to_numpy(pd.GetArray("vtkValidPointMask")).astype(bool) if pd.GetArray("vtkValidPointMask") else None
        for x in alanlar:
            v = vtk_to_numpy(pd.GetArray(x)).astype(np.float32)
            if v.ndim == 2:
                v = np.linalg.norm(v, axis=1)
            if gecerli is not None:
                v = np.where(gecerli, v, np.nan)
            ham[x].append(v)
            aralik[x] = [min(aralik[x][0], float(np.nanmin(v))), max(aralik[x][1], float(np.nanmax(v)))]
        p = damla_noktalari(d, t)
        if p is not None and yansit:
            p = np.vstack([p, p * np.array([1, 1, -1], np.float32)])
        damla.append(np.zeros((0, 3), np.float32) if p is None else p)
        print(f"kare {i + 1}/{len(sec)} t={t:g}", flush=True)
    for x in alanlar:
        lo, hi = aralik[x]
        for i, v in enumerate(ham[x]):
            q = np.where(np.isnan(v), 0, np.clip((v - lo) / (hi - lo if hi > lo else 1) * 65534 + 1, 1, 65535))
            veri[x][i] = q.astype(np.uint16).reshape(nz, ny, nx)
    sinir = img.GetBounds()
    kos = kosul_oku(d, yakit)
    meta = {"kosu": str(d), "ad": f"{d.parent.name}/{d.name}", "zamanlar": sec, "alanlar": alanlar, "yakit_alani": yakit,
            "aralik": aralik, "boyut": [nx, ny, nz], "sinir": list(sinir), "yansitildi": bool(yansit), "kosul": kos,
            "damla_sayisi": [int(len(x)) for x in damla],
            "aciklama": "Alanlar düzenli ızgaraya örneklendi (ResampleToImage) ve uint16'ya nicelendi: 0 = alan dışı; 1–65535 = aralık."}
    np.savez_compressed(cikti, meta=np.frombuffer(json.dumps(meta, ensure_ascii=False).encode(), np.uint8),
                        **{f"alan_{x}": veri[x] for x in alanlar}, **{f"damla_{i}": p for i, p in enumerate(damla)})
    mb = cikti.stat().st_size / 1e6
    print(f"Yazıldı: {cikti} ({mb:.1f} MB; {len(sec)} kare, ızgara {nx}×{ny}×{nz}, alanlar {alanlar}, yansıtma {yansit})")
    if mb > SINIR_MB:
        print("UYARI: 30 MB sınırı aşıldı; --boyut küçültün", file=sys.stderr)


if __name__ == "__main__":
    main()
