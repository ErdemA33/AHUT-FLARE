"""T15 (sentetik kurtarma: YALNIZ algoritma), T16 mekanik testi (gercek veri yokken kod calisiyor mu), MCMC, Sobol."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml import sentetik_test as S, loo_gercek as LG, param as P, rapor as Rp, posterior_mcmc as M   # noqa: E402


def test_T15_sentetik_kurtarma_kapsama_kosegen():
    k = S.kurtarma(n_tekrar=30, seed=0, mod="kosegen")
    assert k >= 0.85, k


def test_T15_sentetik_kurtarma_kapsama_tam():
    k = S.kurtarma(n_tekrar=30, seed=1, mod="tam")
    assert k >= 0.85, k


def test_T15_sinir_aciklamasi_kodda():
    assert "vekil dogrulugunu SINAMAZ" in Path(S.__file__).read_text()


def _loo_veri(n=13, seed=4, aykiri=None):
    rng = np.random.default_rng(seed)
    Xu = rng.random((n, P.D_S))
    X = P.birimden(Xu, "B")
    Y = S.oyuncak(Xu) + rng.normal(0, 0.005, (n, 9))
    if aykiri is not None:
        Y[aykiri, 0] += 5.0
    return X, Y


def test_T16_mekanik_loo_rapor_yapisi():
    X, Y = _loo_veri()
    S_cfd = {s: (0.005 ** 2) * np.eye(3) for s in S.SENSOR}
    rap, z, ok = LG.loo_gercek(X, Y, S.OZ, S.SENSOR, 0.005, S_cfd)
    assert rap["fold_toplam"] == 13
    assert 0 <= rap["fold_gecen"] <= 13
    assert sum(rap["z_histogram"]) == int((~np.isnan(z)).sum())
    assert set(rap) >= {"z_ortalama", "z_sd", "z_min", "z_maks", "z_histogram", "loo_gecti", "theta_kurtarilan"}


def test_T16_aykiri_kosu_LOO_gecmez():
    X, Y = _loo_veri(aykiri=3)
    S_cfd = {s: (0.005 ** 2) * np.eye(3) for s in S.SENSOR}
    rap, z, ok = LG.loo_gercek(X, Y, S.OZ, S.SENSOR, 0.005, S_cfd)
    assert not rap["loo_gecti"]
    assert abs(z[3, 0]) > 3


def test_mcmc_gauss_kurtarma():
    mu = np.array([0.4, 0.6])
    lp = lambda x: -np.inf if np.any(x < 0) or np.any(x > 1) else -0.5 * np.sum(((x - mu) / 0.05) ** 2)
    rng = np.random.default_rng(0)
    x0 = 0.5 + 0.01 * rng.standard_normal((16, 2))
    z, kabul = M.topluluk_mcmc(lp, x0, 1500, seed=1)
    s = z[500:].reshape(-1, 2)
    assert s.mean(axis=0) == pytest.approx(mu, abs=0.02)
    assert s.std(axis=0) == pytest.approx([0.05, 0.05], abs=0.015)
    assert 0.1 < kabul < 0.9


def test_sobol_ana_etki_bilinen():
    f = lambda X: X[:, 0] + 2.0 * X[:, 1]
    Sx = Rp.ana_etki_sobol(f, 3, n=8192)
    assert Sx == pytest.approx([0.2, 0.8, 0.0], abs=0.03)


def test_delta_karsilastirma_ag_hatasi_kalemi():
    ag = [k for k in Rp.DELTA_KARSILASTIRMA if k[0].startswith("AG HATASI")]
    assert len(ag) == 1 and ag[0][1] == 20.66 and "olculdu" in ag[0][3]
    tut = [k for k in Rp.DELTA_KARSILASTIRMA if "TUTUSMA ZAMANI" in k[0]]
    assert len(tut) == 1 and tut[0][1] is None and "bilinmiyor" in tut[0][3]
    # etiketsiz kalem yok
    assert all(k[3].startswith("[") for k in Rp.DELTA_KARSILASTIRMA)
