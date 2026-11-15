"""T1 (reparametrizasyon gidis-donus), T2 (tasarim sinirlari) ve yaml tutarliligi."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml import param as P, tasarim as T   # noqa: E402
import orkestrator as O                    # noqa: E402


def test_T1_theta_A_gidis_donus_gaz():
    # kilitli R1: A = 249200000000000, Ta = 24358 -> theta1 = 15.1064 (olay.log: theta1=15.106)
    th = O.theta1_of(249200000000000.0, 24358.0)
    assert th == pytest.approx(15.1064, abs=1e-3)
    A = O.a_hesapla(th, 24358.0)
    assert abs(A - 249200000000000.0) / 249200000000000.0 < 1e-4
    # param.a_gaz ile orkestrator ayni bicim
    u = th - 24358.0 * P.X_TEFF
    assert abs(P.a_gaz(u, 24358.0) - A) / A < 1e-9


def test_T1_piroliz_zhao_k650():
    A1, E1 = P.LIT_PIROLIZ["Zhao2017"]
    assert P.k_piroliz(A1, E1) == pytest.approx(0.01727, abs=2e-5)
    th = math.log(P.k_piroliz(A1, E1))
    assert abs(P.a_piroliz(th, E1) - A1) / A1 < 1e-12


def test_T1_merkez_sensorlu_hedef02():
    m = P.merkez()
    f = P.fiziksel(m)
    assert f["theta_g1"] == pytest.approx(15.1064, abs=1e-3)
    assert abs(f["A_gaz"] - 249200000000000.4) / 249200000000000.4 < 1e-9
    assert abs(f["A1"] - 1.626e11) / 1.626e11 < 1e-9
    assert P.uygun(m, "A")


def test_T1_band_kokleri():
    assert P.t_ign_band(P.U_ALT) == pytest.approx(P.BAND_T_UST, rel=1e-9)
    assert P.t_ign_band(P.U_UST) == pytest.approx(P.BAND_T_ALT, rel=1e-9)
    assert P.U_ALT < P.U_UST


def test_T2_tasarim_kisitlari():
    x, u, dm, drast = T.faz_a()
    assert x.shape == (8, 6)
    alt, ust = P.sinirlar("A")
    assert np.all(x >= alt - 1e-9) and np.all(x <= ust + 1e-9)
    for xi in x:
        f = P.fiziksel(xi)
        assert P.uygun(xi, "A")
        assert P.THETA_G1_ALT <= f["theta_g1"] <= P.THETA_G1_UST
        assert P.A1_ALT <= f["A1"] <= P.A1_UST
        assert P.TA1_FAZA_ALT <= f["Ta1"] <= P.TA1_UST
        assert P.BAND_T_ALT - 0.05 <= f["t_ign_band"] <= P.BAND_T_UST + 0.05
    # maximin mesafesi rastgele tasarimdan buyuk
    assert dm > drast


def test_T2_faz_B_alt_kutu_disi_nokta_mumkun():
    ad = T.aday_havuzu("B")
    ta = np.array([P.birimden(a, "B")[1] for a in ad])
    assert (ta < P.TA1_FAZA_ALT).any(), "Faz B'de Ta1 < 21000 uygun aday olmali"


def test_yaml_kod_tutarli():
    y = yaml.safe_load(open(Path(__file__).parent / "parametreler.yaml"))["parametreler"]
    assert y["u"]["sinir"] == pytest.approx([P.U_ALT, P.U_UST], abs=1e-5)
    assert y["theta_p"]["sinir"] == pytest.approx([P.THETA_P_ALT, P.THETA_P_UST], abs=1e-5)
    assert y["Ta1"]["sinir_faz_B"] == [P.TA1_ALT, P.TA1_UST]
    assert y["Ta1"]["sinir_faz_A"] == [P.TA1_FAZA_ALT, P.TA1_UST]
    assert y["E1"]["sinir"] == [P.E1_ALT, P.E1_UST]
    assert y["XL0"]["sinir"] == [P.XL0_ALT, P.XL0_UST]
    assert y["eps"]["sinir"] == [P.EPS_ALT, P.EPS_UST]
    assert y["u"]["theta_g1_siniri"] == pytest.approx([P.THETA_G1_ALT, P.THETA_G1_UST], abs=1e-3)
    assert set(y.keys()) == set(P.NAMES)


def test_XL0_sabit_plan_kosullu_kurali():
    assert P.XL0_SERBEST is False
    assert P.D == 6 and P.D_S == 5
    alt, ust = P.sinirlar("A")
    assert alt[4] == ust[4] == 300000.0
    u = np.full((3, P.D_S), 0.5)
    x = P.birimden(u, "A")
    assert x.shape == (3, 6) and np.all(x[:, 4] == 300000.0)
    assert np.allclose(P.birime(x, "A"), u)
