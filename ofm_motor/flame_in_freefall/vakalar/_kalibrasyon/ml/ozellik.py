"""Ozellik cikarimi: model (postProcessing) ve deney (CSV) icin ayni tanimlarla varis zamanlari.

Ozellikler (plan Revize 3): t_ign (yalniz model; deneyde gaz tutusmasi olcumu yok) + varis zamanlari:
  radyometre R13 (R1/R3 ortalamasi, model vekili: sensRadMenba 5 sensor ortalamasi, G/4*0.1 mW/cm2): +1, +3, +10
  TC7 (A, sensYuzey 0), TC8 (B, sensGaz 0), TC9 (C, sensGaz 1): +5, +20, +100 K
Varis = sinyalin esigi gecip en az PERS saniye ustunde kaldigi ilk an (karsilastir_sensor.esik_zamani ile ayni).
Sansur: ufukta ulasilmayan varis -> NaN.
"""
import sys
from pathlib import Path
import numpy as np

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
import karsilastir_sensor as KS   # noqa: E402  (deney_yukle, esik_zamani, probe_yukle, T_IGN, PERS)

T_ISIK = 1500.0
ES_RAD = (1.0, 3.0, 10.0)
ES_TC = (5.0, 20.0, 100.0)

# ozellik adi -> (sensor grubu, esik)
OZELLIKLER = (
    [(f"R13_+{e:g}", "R13", e) for e in ES_RAD]
    + [(f"TC7_+{e:g}K", "TC7", e) for e in ES_TC]
    + [(f"TC8_+{e:g}K", "TC8", e) for e in ES_TC]
    + [(f"TC9_+{e:g}K", "TC9", e) for e in ES_TC]
)
SENSORLER = ["R13", "TC7", "TC8", "TC9"]
# model probe dosyasi ve sutun (sutun 0 = zaman)
MODEL_PROBE = {
    "TC7": ("sibal/sensYuzey", 1),
    "TC8": ("fluid/sensGaz", 1),
    "TC9": ("fluid/sensGaz", 2),
}


def gazmax_oku(case):
    case = Path(case)
    dirs = sorted((case / "postProcessing/fluid/gazMax").glob("*"), key=lambda p: float(p.name))
    rows = []
    for d in dirs:
        f = d / "volFieldValue.dat"
        if not f.exists():
            continue
        for line in open(f):
            if line.startswith("#") or not line.strip():
                continue
            p = line.split()
            try:
                rows.append((float(p[0]), float(p[1])))
            except ValueError:
                pass
    return rows


def t_ign(case, t_isik=T_ISIK):
    for t, T in gazmax_oku(case):
        if T > t_isik:
            return t
    return None


def _varis(t, y, esik):
    v = KS.esik_zamani(np.asarray(t), np.asarray(y), esik)
    return np.nan if v is None else float(v)


def model_sinyalleri(case):
    """Her sensor grubu icin (t, y) taban cikarilmis sinyal. Radyometre: mW/cm2, TC: K."""
    case = Path(case)
    out = {}
    rd = KS.probe_yukle(case / "postProcessing/fluid/sensRadMenba/0/G")
    if rd is not None:
        g = rd[:, 1:].mean(axis=1) / 4.0 * 0.1       # G/4 [W/m2] -> mW/cm2
        out["R13"] = (rd[:, 0], g - g[1])             # ilk satir G=0 (baslangic kosulu), taban ikinci satir
    for ad, (yol, kol) in MODEL_PROBE.items():
        a = KS.probe_yukle(case / "postProcessing" / yol / "0" / "T")
        if a is not None:
            out[ad] = (a[:, 0], a[:, kol] - a[0, kol])
    return out


def model_ozellikleri(case):
    sig = model_sinyalleri(case)
    f = {}
    for ad, grup, esik in OZELLIKLER:
        if grup in sig:
            f[ad] = _varis(sig[grup][0], sig[grup][1], esik)
        else:
            f[ad] = np.nan
    f["t_ign"] = np.nan if t_ign(case) is None else t_ign(case)
    return f


def ufuk(case):
    sig = model_sinyalleri(case)
    return float(max(s[0][-1] for s in sig.values())) if sig else 0.0


# ---------------- deney ----------------
TABAN = KS.TABAN_PENCERE   # (40, 59) telemetri zamani


def deney_sinyalleri(csv_baslangic=KS.T_IGN):
    """Dondurur: sozluk grup -> (t [igniter baslangicina gore, s], y taban cikarilmis), taban sd sozlugu."""
    ad, v = KS.deney_yukle()
    sut = {a: i for i, a in enumerate(ad)}
    te = v[:, 0] - csv_baslangic
    taban = (v[:, 0] >= TABAN[0]) & (v[:, 0] <= TABAN[1])
    m = te >= 0
    sig, sd = {}, {}
    r = 0.5 * (v[:, sut["radiometer1_mW_cm2"]] + v[:, sut["radiometer3_mW_cm2"]])
    sig["R13"] = (te[m], (r - r[taban].mean())[m]); sd["R13"] = float(r[taban].std(ddof=1))
    for g, kol in (("TC7", "sample_temp1_K"), ("TC8", "sample_temp2_K"), ("TC9", "sample_temp3_K")):
        y = v[:, sut[kol]]
        sig[g] = (te[m], (y - y[taban].mean())[m]); sd[g] = float(y[taban].std(ddof=1))
    ham = {"R13": r, "TC7": v[:, sut["sample_temp1_K"]], "TC8": v[:, sut["sample_temp2_K"]], "TC9": v[:, sut["sample_temp3_K"]]}
    return sig, sd, taban, ham, te


def deney_ozellikleri():
    sig, sd, *_ = deney_sinyalleri()
    f = {}
    for ad, grup, esik in OZELLIKLER:
        f[ad] = _varis(sig[grup][0], sig[grup][1], esik)
    return f, sd


def varis_belirsizligi(t, y, esik, sd):
    """Esik +-sd kaydirmasindan varis zamani yarim araligi (gurultu kaynakli belirsizlik)."""
    a = _varis(t, y, esik + sd)
    b = _varis(t, y, esik - sd)
    if np.isnan(a) or np.isnan(b):
        return np.nan
    return 0.5 * abs(a - b)


def blok_bootstrap_gurultu(artik, n_orn, blok, rng):
    """Taban artiklarindan blok bootstrap gurultu gercekleri (n_orn,) uzunlukta."""
    artik = np.asarray(artik)
    nb = int(np.ceil(n_orn / blok))
    out = np.empty(nb * blok)
    for i in range(nb):
        s = int(rng.integers(0, len(artik) - blok))
        out[i * blok:(i + 1) * blok] = artik[s:s + blok]
    return out[:n_orn]


def olcum_kovaryans(grup, ozellik_adlari, n=200, blok=30, seed=11, pencere=15):
    """Bir sensor grubunun varis ozelliklerinin olcum kovaryansi: parametrik blok bootstrap.
    y* = savgol(y) + bootstrap gurultu; varis yeniden hesaplanir. Dondurur (kov, ort, kullanilan_n)."""
    from scipy.signal import savgol_filter
    sig, sd, taban, ham, te = deney_sinyalleri()
    t, y = sig[grup]
    smooth = savgol_filter(y, pencere, 3)
    artik = (ham[grup] - ham[grup][taban].mean())[taban]
    rng = np.random.default_rng(seed)
    esikler = {ad: e for ad, g, e in OZELLIKLER if g == grup}
    sonuc = []
    for _ in range(n):
        g = blok_bootstrap_gurultu(artik, len(y), blok, rng)
        yy = smooth + g
        sonuc.append([_varis(t, yy, esikler[a]) for a in ozellik_adlari])
    S = np.array(sonuc)
    ok = ~np.isnan(S).any(axis=1)
    if ok.sum() < 10:
        return None, None, int(ok.sum())
    return np.cov(S[ok].T), S[ok].mean(axis=0), int(ok.sum())
