"""Rapor yardimcilari: ana etki (duyarlilik) ve metin ozeti. CFD calistirmaz."""
import numpy as np
from scipy.stats import qmc


def ana_etki_sobol(f, d, n=4096, seed=3):
    """Birinci derece Sobol indeksleri (Saltelli/Jansen kestirimi). f: (m,d)->(m,) birim kupte."""
    s = qmc.Sobol(d=2 * d, scramble=True, seed=seed)
    AB = s.random(n)
    A, B = AB[:, :d], AB[:, d:]
    fA, fB = f(A), f(B)
    V = np.var(np.concatenate([fA, fB]))
    S = np.empty(d)
    for i in range(d):
        ABi = A.copy(); ABi[:, i] = B[:, i]
        S[i] = np.mean(fB * (f(ABi) - fA)) / V          # Saltelli 2010 birinci derece kestirici
    return S


def metin_ozeti(basliklar, satirlar):
    """Basit hizali tablo metni."""
    genislik = [max(len(str(b)), *(len(str(r[i])) for r in satirlar)) for i, b in enumerate(basliklar)]
    out = ["  ".join(str(b).ljust(w) for b, w in zip(basliklar, genislik))]
    out += ["  ".join(str(c).ljust(w) for c, w in zip(r, genislik)) for r in satirlar]
    return "\n".join(out)


# ---- delta_min karsilastirma listesi (plan Revize 3; yeni kalem: ag/sayisal hata) ----
# (kalem, deger, birim, etiket)
DELTA_KARSILASTIRMA = [
    ("radyometre olcum gurultusu sd", 0.2, "mW/cm2", "[olculdu: DEVIR_NOTU bolum 6]"),
    ("TC olcum gurultusu sd (TC7, TC8, TC9)", (0.98, 1.07, 1.00), "K", "[olculdu: CSV taban penceresi 40-59 s]"),
    ("CFD tekrar gurultusu (varis zamani)", (0.003, 0.006), "s", "[olculdu: ayni parametreli kosu ciftleri]"),
    ("AG HATASI: Nl5-Nl7, tele 1 mm yakin (0.8 s, tutusma oncesi)", 20.66, "K", "[olculdu: test_Nl5/test_Nl7 gazProb/T]"),
    ("ag hatasi: Nl5-Nl7, tele 0.2 mm yanal / 0.32 mm", (11.78, 1.96), "K", "[olculdu: test_Nl5/test_Nl7 gazProb/T]"),
    ("zaman adimi hatasi: maxCo 0.3-0.5 (0.8 s)", 0.14, "K", "[olculdu: test_Nl7/test_maxCo05, en fazla]"),
    ("ag hatasi: TUTUSMA ZAMANI", None, "s", "[bilinmiyor: tutusma sonrasi Nl5/Nl14 kosusu yok]"),
    ("ag hatasi: TC varis zamanlari", None, "s", "[bilinmiyor]"),
    ("TC konum belirsizligi", None, "m", "[bilinmiyor]"),
    ("radyometre vekili (G/4, 2B P1)", None, "mW/cm2", "[bilinmiyor]"),
]
