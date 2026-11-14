"""T11 (yapisal-hata karar fonksiyonu) ve T12 (Faz B durma kurallari)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml import karar as K   # noqa: E402

LISTE = ["tel eps", "gaz sogurmasi", "is"]


def test_T11_hepsi_saglanirsa_yapisal():
    s, a = K.yapisal_karar(True, 0, True, LISTE)
    assert s.startswith("yapisal")


@pytest.mark.parametrize("loo,uy,day,liste", [
    (False, 0, True, LISTE),     # a bozuk
    (True, 0, False, LISTE),     # c bozuk
    (True, 0, True, []),         # d bozuk
])
def test_T11_bir_sart_bozulursa_belirsiz(loo, uy, day, liste):
    s, a = K.yapisal_karar(loo, uy, day, liste)
    assert s == "belirsiz"


def test_T11_uyumlu_bolge_varsa_yapisal_denmez():
    s, a = K.yapisal_karar(True, 17, True, LISTE)
    assert s == "uyumlu_bolge_var"


def test_T11_korelasyon_modu_esigi():
    assert K.korelasyon_modu({"a": np.array([[1, 0.4], [0.4, 1]])}) == "kosegen"
    assert K.korelasyon_modu({"a": np.array([[1, 0.6], [0.6, 1]])}) == "tam"
    assert K.korelasyon_modu({"a": np.array([[1, 0.2], [0.2, 1]]), "b": np.array([[1, -0.7], [-0.7, 1]])}) == "tam"
    assert K.korelasyon_modu({"a": np.eye(1)}) == "kosegen"


def test_T11_erken_radyometre_testi_donmus_tanim():
    assert K.ERKEN_RAD_ORAN == 0.25 and K.ERKEN_RAD_MIN_KOSU == 3
    assert K.ERKEN_RAD_GOSTERGELER == ("R13_+1", "R13_+3")
    assert K.ERKEN_RAD_ETIKET == "[tahmin: tasarim secimi, olculmedi]"
    # model 1.0-1.3 (aralik 0.3), medyan 1.075, deney 3.2 -> fark 2.125; oran 0.141 < 0.25 -> degistiremiyor
    assert "degistiremiyor" in K.erken_radyometre_testi([1.0, 1.1, 1.3, 1.05], 3.2)
    assert "parametrelerle degisiyor" in K.erken_radyometre_testi([1.0, 2.5, 4.0, 3.0], 3.2)
    assert "bilinmiyor" in K.erken_radyometre_testi([1.0, 1.1], 3.2)
    assert K.erken_radyometre_testi([1.0, 1.0, 1.0], 1.0) == "gosterge uyumlu"
    # kesin esitsizlik: aralik = 0.5, medyan 0.25, fark = 2.0 -> oran tam 0.25 -> degistiremiyor DEGIL
    assert "parametrelerle degisiyor" in K.erken_radyometre_testi([0.0, 0.5, 0.25], 2.25)
    # NaN'lar (sansurlu) atlanir
    assert "degistiremiyor" in K.erken_radyometre_testi([1.0, float("nan"), 1.1, 1.05], 3.2)


# ---------------- T12 ----------------
def test_T12_zorunlu_dis_nokta_once():
    dur, neden = K.faz_b_dur([0.30], True, False, 0, False, dis_nokta_yapildi=False)
    assert not dur and "zorunlu" in neden


def test_T12_azami_4_kosu():
    dur, neden = K.faz_b_dur([0.3, 0.25, 0.2, 0.15, 0.1], True, False, 0, False, True)
    assert dur and "azami" in neden


def test_T12_yapisal_sartlar_dur():
    dur, neden = K.faz_b_dur([0.3, 0.0], True, True, 0, False, True)
    assert dur and "yapisal" in neden


def test_T12_ardisik_basarisizlik():
    dur, neden = K.faz_b_dur([0.3, 0.3], True, False, 2, False, True)
    assert dur and "tutusmama" in neden


def test_T12_sure_bitti():
    dur, neden = K.faz_b_dur([0.3, 0.3], True, False, 0, True, True)
    assert dur and "sure" in neden


def test_T12_hacim_azalma_kurali():
    # iki art arda goreli azalma %5 ve %2 (< %10) ve LOO gecti -> dur
    dur, neden = K.faz_b_dur([0.30, 0.285, 0.28], True, False, 0, False, True)
    assert dur and "%10" in neden
    # ilk azalma %50 -> devam
    dur, _ = K.faz_b_dur([0.30, 0.15, 0.145], True, False, 0, False, True)
    assert not dur
    # LOO gecmediyse hacim kurali tek basina durdurmaz
    dur, _ = K.faz_b_dur([0.30, 0.285, 0.28], False, False, 0, False, True)
    assert not dur
    # yalniz bir faz B kosusu: hacim kurali henuz uygulanmaz
    dur, _ = K.faz_b_dur([0.30, 0.299], True, False, 0, False, True)
    assert not dur


def test_T12_esikler_on_yazili():
    assert K.FAZ_B_MAKS_KOSU == 4 and K.HACIM_AZALMA_ESIK == 0.10 and K.KORELASYON_ESIK == 0.5
