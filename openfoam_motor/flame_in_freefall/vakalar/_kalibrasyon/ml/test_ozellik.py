"""T4 (regresyon: bilinen hedef_02 ciktisi) ve T5 (ozellik cikarimi)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml import ozellik as Oz   # noqa: E402

KOSU = Path(__file__).resolve().parents[1] / "kosular/sensorlu_hedef02"


# ---------------- T4 ----------------
def test_T4_model_TC9_regresyon():
    f = Oz.model_ozellikleri(KOSU)
    assert f["TC9_+5K"] == pytest.approx(3.56, abs=0.02)
    assert f["TC9_+20K"] == pytest.approx(5.10, abs=0.02)
    assert f["TC9_+100K"] == pytest.approx(5.60, abs=0.02)


def test_T4_model_radyometre_vekili_regresyon():
    f = Oz.model_ozellikleri(KOSU)
    assert f["R13_+1"] == pytest.approx(1.08, abs=0.02)
    assert f["R13_+3"] == pytest.approx(2.88, abs=0.02)
    assert f["R13_+10"] == pytest.approx(3.94, abs=0.02)


def test_T4_deney_TC9_regresyon():
    f, sd = Oz.deney_ozellikleri()
    assert f["TC9_+5K"] == pytest.approx(4.26, abs=0.02)
    assert f["TC9_+20K"] == pytest.approx(4.75, abs=0.02)
    assert f["TC9_+100K"] == pytest.approx(7.03, abs=0.02)


def test_T4_tign_ve_ufuk():
    assert Oz.t_ign(KOSU) == pytest.approx(3.68568, abs=1e-4)
    assert Oz.ufuk(KOSU) == pytest.approx(7.52, abs=0.02)


# ---------------- T5 ----------------
def test_T5_varis_tam_rampa():
    t = np.arange(0, 10, 0.02)
    y = np.clip(t - 2.0, 0, None) * 10.0      # 2 s'den sonra 10 birim/s
    assert Oz._varis(t, y, 5.0) == pytest.approx(2.5, abs=0.03)
    assert Oz._varis(t, y, 20.0) == pytest.approx(4.0, abs=0.03)


def test_T5_sansur_nan():
    t = np.arange(0, 5, 0.02)
    y = np.clip(t - 2.0, 0, None) * 1.0
    assert np.isnan(Oz._varis(t, y, 100.0))


def test_T5_gecici_tepe_varis_sayilmaz():
    t = np.arange(0, 10, 0.02)
    y = np.zeros_like(t)
    y[(t > 3.0) & (t < 3.06)] = 50.0           # 0.06 s'lik sivri tepe (PERS = 0.15 s'den kisa)
    y[t >= 6.0] = 50.0
    assert Oz._varis(t, y, 20.0) == pytest.approx(6.0, abs=0.03)


def test_T5_gurultude_kararli():
    rng = np.random.default_rng(0)
    t = np.arange(0, 10, 0.033)
    y = np.clip(t - 3.0, 0, None) * 8.0
    v = [Oz._varis(t, y + rng.normal(0, 0.3, len(t)), 10.0) for _ in range(30)]
    assert np.nanstd(v) < 0.1
    assert np.nanmean(v) == pytest.approx(4.25, abs=0.1)


def test_T5_olcum_kovaryans_PSD_ve_mantikli():
    for g in Oz.SENSORLER:
        ad = [a for a, gg, e in Oz.OZELLIKLER if gg == g]
        K, m, n = Oz.olcum_kovaryans(g, ad, n=60)
        assert K is not None and n >= 10
        assert np.all(np.linalg.eigvalsh(K) > -1e-9)
        assert np.all(np.sqrt(np.diag(K)) < 1.0)    # varis belirsizligi 1 s'den kucuk (olculdu: 0.02-0.33)


def test_T5_ozellik_adlari_tam():
    f = Oz.model_ozellikleri(KOSU)
    assert set(f) == {a for a, g, e in Oz.OZELLIKLER} | {"t_ign"}
