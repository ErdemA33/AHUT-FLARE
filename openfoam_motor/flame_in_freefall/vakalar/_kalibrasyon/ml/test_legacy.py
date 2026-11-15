"""T13: eski kosu uygunlugu (ag/cozucu ayni mi). CFD YOK."""
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import orkestrator as O   # noqa: E402
from ml import legacy as L   # noqa: E402


def _kayit(ad):
    return next(r for r in json.load(open(O.SONUC)) if r["ad"] == ad)


def test_T13_uygun_koşu():
    ok, f = L.uygunluk("izgara_01_th+0.00_Ta24358", _kayit("izgara_01_th+0.00_Ta24358"))
    assert ok and f == []


def test_T13_R2_degismis_kosu_uygunsuz():
    ok, f = L.uygunluk("r2_01_th-1_Ta-1", _kayit("r2_01_th-1_Ta-1"))
    assert not ok and any("reactions" in x for x in f)


def test_T13_bozulan_dosya_yakalanir(tmp_path, monkeypatch):
    kopya_kok = tmp_path / "kosular"
    kopya_kok.mkdir()
    kaynak = O.RUNS / "dar_01_m75_Ta24358"
    hedef = kopya_kok / "dar_01_m75_Ta24358"
    for alt in ("constant", "system"):
        shutil.copytree(kaynak / alt, hedef / alt)
    kayit = _kayit("dar_01_m75_Ta24358")
    monkeypatch.setattr(O, "RUNS", kopya_kok)
    ok, f = L.uygunluk("dar_01_m75_Ta24358", kayit)
    assert ok, f
    # mesh dosyasini boz
    p = hedef / "constant/polyMesh/points"
    if not p.exists():
        cands = list((hedef / "constant").rglob("points"))
        assert cands, "points dosyasi bulunamadi"
        p = cands[0]
    p.write_bytes(p.read_bytes() + b"\n// bozuk\n")
    ok2, f2 = L.uygunluk("dar_01_m75_Ta24358", kayit)
    assert not ok2 and any("points" in x for x in f2)


def test_T13_kosu_dizini_yoksa_uygunsuz():
    ok, f = L.uygunluk("yok_boyle_kosu", {"ad": "yok_boyle_kosu", "A": 1e13, "Ta": 24000.0})
    assert not ok
