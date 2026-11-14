"""Eski koşu sonuçları (kosular/) pakette yoksa onlara bağlı testleri ATLA (başarısız sayma)."""
from pathlib import Path

import pytest

KOSULAR = Path(__file__).resolve().parents[1] / "kosular"
GEREKLI = KOSULAR / "sensorlu_hedef02" / "postProcessing"


def pytest_collection_modifyitems(config, items):
    if GEREKLI.exists():
        return
    atla = pytest.mark.skip(reason="eski koşu verisi yok (kosular/sensorlu_hedef02); paketle gelmez")
    for it in items:
        ad = it.nodeid
        if "test_legacy.py" in ad and "yoksa_uygunsuz" not in ad:
            it.add_marker(atla)
        elif "test_ozellik.py" in ad and "KOSU" not in ad and ("test_T4_" in ad):
            it.add_marker(atla)
        elif "varsayilan_cagri_mevcut_ciktiyla_ayni" in ad:
            it.add_marker(atla)
