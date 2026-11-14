"""T8 (history matching cekirdegi), T9 (korelasyon), T10 (delta_min)."""
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import chi2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml.history_matching import Problem, ledoit_wolf_korelasyon, NIVEL   # noqa: E402


class Stub:
    """Sabit ortalama/varyans donduren vekil (cebirsel dogrulama icin)."""
    def __init__(self, mu, var):
        self.mu, self.var = mu, var

    def tahmin(self, X):
        m = len(np.atleast_2d(X))
        return np.full(m, self.mu), np.full(m, self.var)


def _prob(mus, vars_, z, So, nug=0.0, R=None):
    ozs = [f"f{i}" for i in range(len(mus))]
    gps = {f: Stub(m, v) for f, m, v in zip(ozs, mus, vars_)}
    return Problem(gps, {"S": ozs}, dict(zip(ozs, z)), {"S": np.asarray(So)}, nug, R_emu={"S": R} if R is not None else None), ozs


def test_T8_chi2_esikleri():
    assert chi2.ppf(NIVEL, 1) == pytest.approx(9.0, abs=0.01)     # 3 sigma
    assert chi2.ppf(NIVEL, 3) > chi2.ppf(NIVEL, 1)


def test_T8_birlesik_gosterge_elle_chi2():
    mus, vars_ = [1.0, 2.0, 3.0], [0.04, 0.09, 0.01]
    z = [1.3, 1.5, 3.2]
    So = np.array([[0.02, 0.005, 0.0], [0.005, 0.03, 0.002], [0.0, 0.002, 0.01]])
    R = np.array([[1, 0.6, 0.2], [0.6, 1, 0.1], [0.2, 0.1, 1.0]])
    pr, ozs = _prob(mus, vars_, z, So, nug=0.0, R=R)
    g = pr.gosterge(np.zeros((2, 6)), mod="tam")
    sd = np.sqrt(vars_)
    S = np.outer(sd, sd) * R + So
    r = np.array(z) - np.array(mus)
    el = float(r @ np.linalg.solve(S, r))
    assert g["S"][0][0] == pytest.approx(el, rel=1e-10)
    assert g["S"][1] == pytest.approx(chi2.ppf(NIVEL, 3))


def test_T8_gercek_icerir_ve_uzak_dislar():
    pr, _ = _prob([0.0], [0.01], [0.05], [[0.01]])           # |r| = 0.05, toplam sd = sqrt(0.02) = 0.141 -> I2 = 0.125
    uy, _ = pr.uyumlu(np.zeros((1, 6)), mod="kosegen", max_basarisiz=0)
    assert uy[0]
    pr2, _ = _prob([0.0], [0.01], [2.0], [[0.01]])
    uy2, _ = pr2.uyumlu(np.zeros((1, 6)), mod="kosegen", max_basarisiz=0)
    assert not uy2[0]


def test_T8_ikinci_en_kotu_sensor_kurali():
    # 3 sensor: biri uyumsuz -> gecer, ikisi uyumsuz -> kalir
    def pb(zs):
        gps = {f"f{i}": Stub(0.0, 0.0) for i in range(3)}
        so = {f"S{i}": [f"f{i}"] for i in range(3)}
        S = {f"S{i}": np.array([[0.01]]) for i in range(3)}
        return Problem(gps, so, {f"f{i}": zs[i] for i in range(3)}, S, 0.0)
    assert pb([0.0, 0.0, 5.0]).uyumlu(np.zeros((1, 6)), mod="kosegen")[0][0]
    assert not pb([0.0, 5.0, 5.0]).uyumlu(np.zeros((1, 6)), mod="kosegen")[0][0]


def test_T9_korelasyon_tam_ile_kosegen_fark_verir():
    rho = 0.9
    R = np.array([[1, rho], [rho, 1.0]])
    So = np.eye(2) * 0.0
    sig = 1.0
    # vekil belirsizligi sd=1 her ozellik; ortalama sifir
    for z, beklenen in (([1.0, 1.0], "tam_kucuk"), ([1.0, -1.0], "tam_buyuk")):
        pr, _ = _prob([0.0, 0.0], [sig ** 2, sig ** 2], z, [[1e-12, 0], [0, 1e-12]], R=R)
        Itam = pr.gosterge(np.zeros((1, 6)), mod="tam")["S"][0][0]
        Ikos = pr.gosterge(np.zeros((1, 6)), mod="kosegen")["S"][0][0]     # max_j r_j^2/var = 1
        if beklenen == "tam_kucuk":
            assert Itam < 2 * Ikos            # ayni yonde artik, pozitif korelasyonda toplam sapma beklenenden cok
            assert Itam == pytest.approx(2 / (1 + rho), rel=1e-6)
        else:
            assert Itam == pytest.approx(2 / (1 - rho), rel=1e-6)           # zit yonde artik: korelasyon varken pek olasi degil
            assert Itam > 9 * Ikos


def test_T9_ledoit_wolf_gecerli_korelasyon_ve_tekil_durum():
    rng = np.random.default_rng(5)
    Z = rng.standard_normal((4, 3))                # n < p benzeri tekil ornek (n=4, p=3, serbestlik az)
    R, a = ledoit_wolf_korelasyon(Z)
    assert np.allclose(np.diag(R), 1.0)
    assert np.allclose(R, R.T)
    assert np.linalg.eigvalsh(R).min() > 0
    assert 0.0 <= a <= 1.0
    Z2 = np.column_stack([Z[:, 0], Z[:, 0], Z[:, 1]])  # tam tekil
    R2, a2 = ledoit_wolf_korelasyon(Z2)
    assert np.linalg.eigvalsh(R2).min() > 0


def test_T9_ledoit_wolf_bilinen_korelasyonu_yakalar():
    rng = np.random.default_rng(6)
    n = 500
    a = rng.standard_normal(n)
    Z = np.column_stack([a, 0.8 * a + 0.6 * rng.standard_normal(n)])
    R, _ = ledoit_wolf_korelasyon(Z)
    assert R[0, 1] == pytest.approx(0.8, abs=0.06)


def test_T10_delta_min_bilinen_ofset():
    off, sig, nug = 0.5, 0.05, 0.0
    pr, _ = _prob([0.0], [0.0], [off], [[sig ** 2]], nug=nug)
    kp = pr.delta_min(np.zeros((1, 6)), mod="kosegen", max_basarisiz=0)
    beklenen = np.sqrt(off ** 2 / (9 * sig ** 2) - 1.0)
    assert kp == pytest.approx(beklenen, rel=0.01)


def test_T10_delta_min_zaten_uyumluysa_sifir():
    pr, _ = _prob([0.0], [0.0], [0.01], [[0.05 ** 2]])
    assert pr.delta_min(np.zeros((1, 6)), mod="kosegen", max_basarisiz=0) == 0.0


def test_T10_emulator_varyansi_x2_bosu_degistirebilir():
    pr, _ = _prob([0.0], [0.01], [0.5], [[0.0004]])   # r^2/toplam: x1 -> 24 (>9), x4 -> 6.2 (<9)
    uy1, _ = pr.uyumlu(np.zeros((1, 6)), mod="kosegen", max_basarisiz=0, emu_var_carpan=1.0)
    uy2, _ = pr.uyumlu(np.zeros((1, 6)), mod="kosegen", max_basarisiz=0, emu_var_carpan=4.0)
    assert (not uy1[0]) and uy2[0]
