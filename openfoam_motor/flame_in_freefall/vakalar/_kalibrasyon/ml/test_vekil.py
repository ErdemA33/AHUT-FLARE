"""T6 (GP birim) ve T7 (hiperparametre kurtarma; yalniz algoritma)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml.vekil import GP, matern52, q2   # noqa: E402


def _veri(n=13, d=6, seed=1, gur=0.01):
    rng = np.random.default_rng(seed)
    X = rng.random((n, d))
    f = lambda X: np.sin(2 * X[:, 0]) + X[:, 1] ** 2 + 0.5 * X[:, 2]
    return X, f(X) + rng.normal(0, gur, n), f


def test_T6_enterpolasyon_egitim_noktalarinda():
    X, y, _ = _veri()
    g = GP(1e-4).fit(X, y)
    mu, var = g.tahmin(X)
    assert np.abs(mu - y).max() < 0.02          # nugget sd = 0.01
    assert var.min() >= 0


def test_T6_kapali_LOO_yeniden_uydurmaya_esit():
    X, y, _ = _veri()
    g = GP(1e-4).fit(X, y)
    a, b = g.loo()
    a2, b2 = g.loo_yeniden()
    assert np.abs(a - a2).max() < 1e-8
    assert np.abs(b - b2).max() < 1e-8


def test_T6_kernel_pozitif_tanimli_ve_simetrik():
    rng = np.random.default_rng(3)
    X = rng.random((20, 6))
    K = matern52(X, X, 0.7, 2.0)
    assert np.allclose(K, K.T)
    assert np.linalg.eigvalsh(K).min() > -1e-9
    assert np.allclose(np.diag(K), 2.0)


def test_T6_tahmin_varyansi_veriden_uzakta_artar():
    X, y, _ = _veri()
    g = GP(1e-4).fit(X, y)
    _, v_yakin = g.tahmin(X[:1] + 1e-3)
    _, v_uzak = g.tahmin(np.full((1, 6), 5.0))
    assert v_uzak[0] > v_yakin[0]


def test_T6_hiperparametre_sinirlari():
    X, y, _ = _veri()
    g = GP(1e-4).fit(X, y)
    assert 0.3 - 1e-9 <= g.l <= 3.0 + 1e-9


def test_T6_gercek_degerde_makul_tahmin():
    X, y, f = _veri(n=40, d=3, gur=0.005)
    g = GP(2.5e-5).fit(X, y)
    rng = np.random.default_rng(9)
    Xt = rng.random((200, 3))
    mt, _ = g.tahmin(Xt)
    assert np.sqrt(np.mean((mt - f(Xt)) ** 2)) < 0.1 * f(Xt).std()


def test_T7_uzunluk_olcegi_kurtarma_yalniz_algoritma():
    """Bilinen l'li GP cekimlerinde l kurtarma (n=60, d=2); algoritma testi, vekil dogrulugu degil."""
    oran = []
    for seed in range(10):
        rng = np.random.default_rng(100 + seed)
        X = rng.random((60, 2))
        K = matern52(X, X, 0.8, 1.0) + 1e-8 * np.eye(60)
        y = np.linalg.cholesky(K) @ rng.standard_normal(60) + 0.001 * rng.standard_normal(60)
        g = GP(1e-6).fit(X, y)
        oran.append(g.l / 0.8)
    assert 0.6 < np.median(oran) < 1.6
