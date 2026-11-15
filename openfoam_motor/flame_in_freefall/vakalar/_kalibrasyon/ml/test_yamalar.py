"""T3: vaka_kur dosya yamalari (CFD YOK, decompose=False). Gecici dizinde calisir."""
import filecmp
import re
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import orkestrator as O   # noqa: E402
from ml import param as P  # noqa: E402

BASE = O.BASE


@pytest.fixture()
def tmp_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "RUNS", tmp_path)
    return tmp_path


def _dosyalar(kok):
    return {str(p.relative_to(kok)) for p in kok.rglob("*") if p.is_file()}


def _fark(a, b, yoksay=()):
    """a ve b dizinleri arasinda icerigi farkli dosyalar."""
    out = []
    for rel in sorted(_dosyalar(a) | _dosyalar(b)):
        if rel in yoksay:
            continue
        fa, fb = a / rel, b / rel
        if not fa.exists() or not fb.exists():
            out.append(rel)
        elif not filecmp.cmp(fa, fb, shallow=False):
            out.append(rel)
    return out


def test_T3_varsayilan_cagri_mevcut_ciktiyla_ayni(tmp_runs):
    """Varsayilan vaka_kur (yama yok) sensorlu_hedef02 ile bire bir ayni constant/ ve system/ uretir."""
    eski = O.RUNS.parent  # noqa
    mevcut = Path(__file__).resolve().parents[1] / "kosular" / "sensorlu_hedef02"
    case = O.vaka_kur("t3_varsayilan", 249200000000000.4, 24358.0, "sifir", 8.5, 2e-5, decompose=False)
    for alt in ("constant", "system"):
        assert _fark(case / alt, mevcut / alt) == [], f"{alt} farkli"


def test_T3_gaz_yamasi(tmp_runs):
    case = O.vaka_kur("t3_gaz", 1.0e13, 22000.0, "sifir", 7.5, decompose=False)
    s = (case / "constant/fluid/reactions").read_text()
    blok = re.search(r"CH4oxReaction\s*\{([^}]*)\}", s, re.S).group(1)
    assert re.search(r"\bA\s+1\.000000e\+13;", blok)
    assert re.search(r"\bTa\s+22000\.00;", blok)
    # CO reaksiyonu degismedi
    ref = (BASE / "constant/fluid/reactions").read_text()
    assert re.search(r"COoxReaction\s*\{[^}]*\}", s, re.S).group(0) == re.search(r"COoxReaction\s*\{[^}]*\}", ref, re.S).group(0)


def test_T3_piroliz_ve_eps_yamasi(tmp_runs):
    piro = {"A1": 3.0e10, "E1": 140000.0, "XL0": 400000.0}
    case = O.vaka_kur("t3_piro", 249200000000000.4, 24358.0, "sifir", 7.5, piroliz=piro, eps_sibal=0.85, decompose=False)
    fv = (case / "constant/sibal/fvModels").read_text()
    assert re.search(r"\bA1\s+3\.000000e\+10;", fv)
    assert re.search(r"\bE1\s+1\.400000e\+05;", fv)
    assert re.search(r"\bXL0\s+4\.000000e\+05;", fv)
    # fvModels'in geri kalani ayni: A1/E1/XL0 haric
    ref = (BASE / "constant/sibal/fvModels").read_text()
    norm = lambda t: re.sub(r"\b(A1|E1|XL0)\s+[0-9.eE+-]+;", r"\1 X;", t)
    assert norm(fv) == norm(ref)
    g = (case / "0/fluid/G").read_text()
    blok = re.search(r"fluid_to_sibal\s*\{[^}]*\}", g).group(0)
    assert "emissivity uniform 0.850000;" in blok
    # diger yamalarin emisivitesi degismedi (tel 0.7, giris 1.0)
    assert "fluid_to_tel { type MarshakRadiation; emissivityMode lookup; emissivity uniform 0.7;" in g
    refg = (BASE / "0/fluid/G").read_text()
    assert re.sub(r"(fluid_to_sibal\s*\{[^}]*?emissivity uniform )[0-9.]+;", r"\1X;", g) == \
           re.sub(r"(fluid_to_sibal\s*\{[^}]*?emissivity uniform )[0-9.]+;", r"\1X;", refg)


def test_T3_yamasiz_dosyalar_BASE_ile_ayni(tmp_runs):
    piro = {"A1": 3.0e10, "E1": 140000.0, "XL0": 400000.0}
    case = O.vaka_kur("t3_bire_bir", 1.0e13, 22000.0, "sifir", 7.5, piroliz=piro, eps_sibal=0.85, decompose=False)
    # kosuya gore degisen dosyalar yoksayilir
    yoksay = {"constant/fluid/reactions", "constant/fluid/chemistryProperties", "constant/sibal/fvModels",
              "system/controlDict", "system/functions"}
    assert _fark(case / "constant", BASE / "constant", {y.split("/", 1)[1] for y in yoksay if y.startswith("constant/")}) == []
    assert _fark(case / "system", BASE / "system", {y.split("/", 1)[1] for y in yoksay if y.startswith("system/")}) == []
    # 0/ : G disinda ayni
    assert _fark(case / "0", BASE / "0", {"fluid/G"}) == []


def test_T3_eslesmeyen_yama_hata_verir(tmp_runs):
    with pytest.raises(RuntimeError):
        O._tek_degistir("A1 1.0;", r"(\bXL0\s+)[0-9.eE+-]+;", lambda m: "x", "XL0")
    with pytest.raises(RuntimeError):
        O._tek_degistir("A1 1.0; A1 2.0;", r"(\bA1\s+)[0-9.eE+-]+;", lambda m: "x", "A1")


def test_T3_CFD_baslatilmadi():
    import subprocess
    n = int(subprocess.run("pgrep -x foamMultiRun | wc -l", shell=True, capture_output=True, text=True).stdout)
    assert n == 0, "test sirasinda solver calisiyor olmamali"
