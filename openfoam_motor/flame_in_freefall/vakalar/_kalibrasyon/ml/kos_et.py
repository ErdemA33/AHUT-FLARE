"""CFD baslatma sarmalayicisi. KULLANICI ONAYI OLMADAN CFD BASLATMAZ.

Onay: ml/ONAY_CFD dosyasi yoksa PermissionError. Bu dosyayi YALNIZCA kullanici olusturur (ya da olusturmami acikca ister).
Gece (08.11) kullanici talimati: ilk CFD kosusunu onaylamadan baslatma.
Cift kosu engeli: ml/KILIT uzerinde flock + calisan foamMultiRun kontrolu.
"""
import fcntl
from pathlib import Path

ML_DIR = Path(__file__).resolve().parent
ONAY = ML_DIR / "ONAY_CFD"
KILIT = ML_DIR / "KILIT"
UFUK_VARSAYILAN = 7.5       # s
# orkestrator grid_sonra=None ise tutusma gorulunce kosuyu DURDURUR (izgara taramasi icin). Kalibrasyon ufka kadar kosmali:
GRID_SONRA_DURMA_YOK = 1.0e9   # s; tutusmadan sonra durdurma esigi asla gelmez
TOPLAM_MAX_S = 80 * 3600    # orkestratorun 30 saatlik toplam siniri yerine (63 saatlik plan)


def onay_var():
    return ONAY.exists()


class Kilit:
    """Ayni anda tek kos_et: ikinci cagri BlockingIOError."""
    def __init__(self, yol=KILIT):
        self.yol = Path(yol)

    def __enter__(self):
        self.f = open(self.yol, "w")
        try:
            fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.f.close()
            raise
        return self

    def __exit__(self, *a):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


def kos_et(ad, x, faz="A", ufuk=UFUK_VARSAYILAN):
    """x: 6'lik parametre vektoru (param.NAMES sirasi). Onay yoksa hicbir sey yapmaz, hata verir."""
    if not onay_var():
        raise PermissionError(f"CFD onayi yok: {ONAY} dosyasi bulunamadi. Kullanici onayi olmadan CFD baslatilmaz.")
    import sys
    sys.path.insert(0, str(ML_DIR.parent))
    import orkestrator as O
    from . import param as P
    if not P.uygun(x, faz):
        raise ValueError("parametre vektoru kisitlari saglamiyor")
    f = P.fiziksel(x)
    with Kilit():
        if O.solver_sayisi() > 0:
            raise RuntimeError("calisan foamMultiRun var; ikinci kosu baslatilmaz")
        O.TOPLAM_MAX = TOPLAM_MAX_S
        return O.kos(ad, f["A_gaz"], f["Ta1"], "sifir", ufuk, "ml", grid_sonra=GRID_SONRA_DURMA_YOK,
                     piroliz={"A1": f["A1"], "E1": f["E1"], "XL0": f["XL0"]}, eps_sibal=f["eps"])
