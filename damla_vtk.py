#!/usr/bin/env python3
"""
damla_vtk.py — sızıntı koşularının lagrangian damlalarını ParaView'in okuyabileceği VTK PolyData'ya çevirir.

ParaView 5.11'in OpenFOAM okuyucusu OpenFOAM 14'ün lagrangian bulutunu okuyamıyor. Bu betik of_gorsel_veri.py'deki
yolu kullanır: of_gorsel/_is/ altında geçici çalışma kopyası (processor* salt-okunur sembolik bağ),
reconstructPar (yalnız lagrangian) + foamToVTK, sonra vtk_noktalar ile aynı biçimde okuma.

Çıktı (koşu başına):  of_kosular/sizinti/<koşu>/damla_vtk/damla_<t>.vtp   noktalar [m] + d [m] + T [K]
                      of_kosular/sizinti/<koşu>/damla_vtk/damla.vtp.series   (ParaView zaman serisi)
Kullanım: python3 damla_vtk.py [uzay] [mars] [tek_damla]   (tek_damla -> of_kosular/tek_damla/isinimsiz/damla_vtk)
"""
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np

import of_gorsel_veri as ogv

LAG_ALAN = ("d", "T")
VAKALAR = {"uzay": "sizinti/uzay", "mars": "sizinti/mars", "tek_damla": "tek_damla/isinimsiz",
           "ince_uzay": "sizinti3d_ince/uzay", "ince_mars": "sizinti3d_ince/mars"}


def vtk_lagrangian_oku(f):
    """foamToVTK lagrangian (legacy ascii): POINTS + istenen alanlar (vtk_noktalar'ın genellemesi)."""
    t = Path(f).read_text(errors="replace").split()
    if "POINTS" not in t:
        return np.zeros((0, 3)), {}
    i = t.index("POINTS")
    n = int(t[i + 1])
    p = np.array(t[i + 3:i + 3 + 3 * n], dtype=float).reshape(n, 3)
    alan = {}
    for k in range(i, len(t) - 3):
        if t[k] in LAG_ALAN and t[k] not in alan and t[k + 1] == "1" and t[k + 2] == str(n):
            alan[t[k]] = np.array(t[k + 4:k + 4 + n], dtype=float)
    return p, alan


def vtp_yaz(dosya, p, alan):
    """VTK XML PolyData. vtk modülü varsa onunla, yoksa elle (ascii XML)."""
    try:
        import vtk
        from vtk.util.numpy_support import numpy_to_vtk
        pd = vtk.vtkPolyData()
        nok = vtk.vtkPoints()
        nok.SetData(numpy_to_vtk(np.ascontiguousarray(p, dtype=np.float64), deep=True))
        pd.SetPoints(nok)
        hucre = vtk.vtkCellArray()
        for j in range(len(p)):
            hucre.InsertNextCell(1)
            hucre.InsertCellPoint(j)
        pd.SetVerts(hucre)
        for ad, a in alan.items():
            v = numpy_to_vtk(np.ascontiguousarray(a, dtype=np.float64), deep=True)
            v.SetName(ad)
            pd.GetPointData().AddArray(v)
        if "d" in alan:
            pd.GetPointData().SetActiveScalars("d")
        w = vtk.vtkXMLPolyDataWriter()
        w.SetFileName(str(dosya))
        w.SetInputData(pd)
        w.SetDataModeToBinary()
        w.SetCompressorTypeToZLib()
        if w.Write() != 1:
            raise RuntimeError(f"yazılamadı: {dosya}")
        return
    except ImportError:
        pass
    n = len(p)
    sayi = lambda a: " ".join(f"{x:.9g}" for x in np.ravel(a))
    diz = "".join(f'        <DataArray type="Float64" Name="{ad}" format="ascii">{sayi(a)}</DataArray>\n'
                  for ad, a in alan.items())
    Path(dosya).write_text(
        '<?xml version="1.0"?>\n<VTKFile type="PolyData" version="1.0" byte_order="LittleEndian">\n  <PolyData>\n'
        f'    <Piece NumberOfPoints="{n}" NumberOfVerts="{n}" NumberOfLines="0" NumberOfStrips="0" NumberOfPolys="0">\n'
        f'      <PointData Scalars="d">\n{diz}      </PointData>\n'
        f'      <Points>\n        <DataArray type="Float64" NumberOfComponents="3" format="ascii">{sayi(p)}</DataArray>\n'
        '      </Points>\n'
        f'      <Verts>\n        <DataArray type="Int64" Name="connectivity" format="ascii">{sayi(np.arange(n))}</DataArray>\n'
        f'        <DataArray type="Int64" Name="offsets" format="ascii">{sayi(np.arange(1, n + 1))}</DataArray>\n'
        '      </Verts>\n    </Piece>\n  </PolyData>\n</VTKFile>\n')


def cevir(ad):
    vaka = ogv.OFK / VAKALAR[ad]
    tum = ogv.zamanlar(vaka)
    adlar = [b for a, b in tum]
    is_ = ogv.CIK / "_is" / f"damla_{ad}"
    if is_.exists():
        shutil.rmtree(is_)
    is_.mkdir(parents=True)
    cik = vaka / "damla_vtk"
    try:
        shutil.copytree(vaka / "constant", is_ / "constant", symlinks=True)
        shutil.copytree(vaka / "system", is_ / "system", symlinks=True)
        cd = is_ / "system/controlDict"
        s = cd.read_text()
        import re
        s = re.sub(r"writeFormat\s+\w+;", "writeFormat     ascii;", s)
        cd.write_text(s)
        (is_ / "system/functions").write_text("FoamFile { format ascii; class dictionary; object functions; }\n")
        for p in sorted(vaka.glob("processor*")):
            (is_ / p.name).symlink_to(p.resolve(), target_is_directory=True)
        print(f"{ad}: reconstructPar (lagrangian, {len(adlar)} zaman)", flush=True)
        ogv.kabuk(f"reconstructPar -fields '(T)' -lagrangianFields '(d T)' -withZero", is_)
        print(f"{ad}: foamToVTK (lagrangian)", flush=True)
        ogv.kabuk("foamToVTK -ascii -noInternal -excludePatches '(\".*\")' -noFaceZones -useTimeName "
                  "-fields '(d T)'", is_)
        if cik.exists():
            shutil.rmtree(cik)
        cik.mkdir()
        seri, toplam = [], 0
        for tf, tn in tum:
            f = sorted((is_ / "VTK" / "lagrangian").glob(f"*/*_{tn}.vtk")) if (is_ / "VTK/lagrangian").exists() else []
            p, alan = vtk_lagrangian_oku(f[0]) if f else (np.zeros((0, 3)), {})
            for k in LAG_ALAN:
                alan.setdefault(k, np.zeros(len(p)))
            dosya = cik / f"damla_{tn}.vtp"
            vtp_yaz(dosya, p, alan)
            seri.append({"name": dosya.name, "time": tf})
            toplam += len(p)
            if tn in ("0.15", "0.2", "0.4", "1", "3"):
                print(f"  t = {tn}: {len(p)} parsel, d = {alan['d'].min() * 1e6 if len(p) else 0:.1f}–"
                      f"{alan['d'].max() * 1e6 if len(p) else 0:.1f} µm", flush=True)
        (cik / "damla.vtp.series").write_text(json.dumps({"file-series-version": "1.0", "files": seri}, indent=1))
        mb = sum(f.stat().st_size for f in cik.iterdir()) / 1e6
        print(f"{ad}: {len(seri)} zaman, toplam {toplam} parsel-kare -> {cik} ({mb:.1f} MB)", flush=True)
    finally:
        if not os.environ.get("OF_GORSEL_TUT"):
            shutil.rmtree(is_, ignore_errors=True)


if __name__ == "__main__":
    for a in sys.argv[1:] or ["uzay", "mars"]:
        cevir(a)
