"""T14: orkestrator guvenligi (CFD'siz kuru calistirma)."""
import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import orkestrator as O   # noqa: E402
from ml import kos_et as KE, param as P   # noqa: E402

ML = Path(__file__).resolve().parent


def test_T14_onay_dosyasi_yokken_CFD_baslamaz():
    assert not KE.ONAY.exists(), "ONAY_CFD kullanici onayi olmadan var olmamali"
    with pytest.raises(PermissionError):
        KE.kos_et("deneme", P.merkez(), "A")


def test_T14_kos_et_hicbir_surec_baslatmadi():
    n = int(subprocess.run("pgrep -x foamMultiRun | wc -l", shell=True, capture_output=True, text=True).stdout)
    assert n == 0


def test_T14_duvar_siniri_4p5_saat():
    assert O.KOSU_DUVAR_MAX == 4.5 * 3600


def test_T14_atomik_yazim(tmp_path):
    hedef = tmp_path / "s.json"
    O.atomik_yaz(hedef, [{"a": 1}, {"b": [1, 2]}])
    assert json.load(open(hedef)) == [{"a": 1}, {"b": [1, 2]}]
    assert not (tmp_path / "s.json.tmp").exists()
    # kaynakta tmp + os.replace deseni var
    src = Path(O.__file__).read_text()
    fn = src[src.index("def atomik_yaz"):src.index("SONUCLAR =")]
    assert "os.replace" in fn and ".tmp" in fn


def test_T14_cift_calistirma_engeli(tmp_path):
    k1 = KE.Kilit(tmp_path / "kilit")
    k2 = KE.Kilit(tmp_path / "kilit")
    with k1:
        with pytest.raises(BlockingIOError):
            with k2:
                pass
    with k2:                                 # birinci birakilinca ikincisi alabilir
        pass


def test_T14_sogutma_bekleme_mantigi(monkeypatch):
    sicak = iter([70.0, 70.0, 55.0])
    monkeypatch.setattr(O, "acpitz", lambda: next(sicak))
    monkeypatch.setattr(O.time, "sleep", lambda s: None)
    assert O.sogumayi_bekle() is True
    monkeypatch.setattr(O, "acpitz", lambda: 90.0)
    assert O.sogumayi_bekle() is False       # 10 dk (60 deneme) sonra vazgecer


def test_T14_ml_modulleri_solver_baslatan_cagri_icermez():
    """kos_et.py disinda ml/ kodu orkestrator.kos / subprocess / mpirun cagirmamali."""
    yasak_metin = ("foamMultiRun", "mpirun")
    for p in ML.glob("*.py"):
        if p.name.startswith("test_") or p.name == "kos_et.py":
            continue
        t = p.read_text()
        for y in yasak_metin:
            assert y not in t, f"{p.name} icinde {y}"
        agac = ast.parse(t)
        for n in ast.walk(agac):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "kos":
                pytest.fail(f"{p.name}: .kos( cagrisi")
            if isinstance(n, ast.Import) and any(a.name == "subprocess" for a in n.names):
                assert p.name == "legacy.py" or False, f"{p.name} subprocess iceri aktariyor"


def test_T14_testler_orkestratoru_calistirmaz():
    """Testler O.kos / O.main cagirmaz."""
    for p in ML.glob("test_*.py"):
        if p.name == "test_guvenlik.py":
            continue
        t = p.read_text()
        assert "O.kos(" not in t and "O.main(" not in t and "asama1(" not in t


def test_kos_et_tutusmada_durdurmaz():
    """faz_a_02 hatasi: grid_sonra=None orkestratorde 'tutusmada dur' demek; kos_et bunu gecmemeli."""
    from ml import kos_et as K
    import inspect
    kaynak = inspect.getsource(K.kos_et)
    assert "grid_sonra=None" not in kaynak
    assert K.GRID_SONRA_DURMA_YOK > 1e6
