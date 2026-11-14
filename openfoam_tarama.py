#!/usr/bin/env python3
"""
openfoam_tarama.py — OpenFOAM'da oksijeni adım adım düşürür, alevin söndüğü noktayı bulur
ve sonucu risk modeliyle + literatür verisiyle karşılaştırır.

Vaka: OpenFOAM'un hazır "counterFlowFlame2D" örneği
  - soldan metan, sağdan hava (oksijen + azot), ikisi de 10 cm/s, karşılıklı
  - bu örnekte yerçekimi yok -> uzay (mikro-g) koşulu
  - 1 atm, tek adımlı metan tepkimesi
Her oksijen değeri için: havanın O2/N2 oranı değiştirilir, simülasyon çalışır,
son andaki en yüksek sıcaklığa bakılır:  > 1000 K -> alev sürdü (yandı), değilse söndü.

Kullanım (önce: source /opt/openfoam14/etc/bashrc):
  python3 openfoam_tarama.py                       # varsayılan oksijenler, 4 koşu aynı anda
  python3 openfoam_tarama.py --oksijen 21,16,13,12,11,10 --paralel 3
  python3 openfoam_tarama.py --sadece-karsilastir  # simülasyonları tekrar çalıştırmadan karşılaştır
Çıktılar:
  openfoam_sonuclar_metan.csv   (motor.py'nin tablo biçiminde)
  openfoam_karsilastirma.png
"""
import argparse
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

KOSU_KLASORU = Path("of_kosular")
CIKTI = Path("openfoam_sonuclar_metan.csv")
GRAFIK = Path("openfoam_karsilastirma.png")
YANDI_SICAKLIK = 1000.0      # K; giriş gazları 293 K, alev ~1900 K
M_O2, M_N2 = 31.999, 28.014
KOSUL = {"g": 1e-4, "basinc": 100.0, "akis": 10.0, "kalinlik": np.nan, "malzeme": "methane"}


def kaynak_vaka(yol):
    if yol:
        return Path(yol)
    tut = os.environ.get("FOAM_TUTORIALS")
    if not tut:
        raise SystemExit("OpenFOAM ortamı yüklü değil. Önce: source /opt/openfoam14/etc/bashrc")
    return Path(tut) / "multicomponentFluid" / "counterFlowFlame2D"


def kutle_kesri(o2_mol_yuzde):
    """Mol (hacim) yüzdesi -> kütle kesri (OpenFOAM kütle kesri kullanıyor)."""
    x = o2_mol_yuzde / 100
    y_o2 = x * M_O2 / (x * M_O2 + (1 - x) * M_N2)
    return y_o2, 1 - y_o2


def hava_degeri_yaz(dosya, deger):
    """0/O2 ya da 0/N2 dosyasında 'air' sınırının değerini değiştirir."""
    metin = dosya.read_text()
    yeni, n = re.subn(r"(air\s*\{[^}]*?value\s+uniform\s+)[0-9.eE+-]+", rf"\g<1>{deger:.6f}", metin)
    if n != 1:
        raise RuntimeError(f"{dosya}: 'air' değeri bulunamadı")
    dosya.write_text(yeni)


def sicaklik_oku(vaka):
    """En son zaman klasöründeki T alanından (en yüksek, ortalama) sıcaklık."""
    zamanlar = []
    for d in vaka.iterdir():
        try:
            if d.is_dir() and (d / "T").exists() and float(d.name) > 0:
                zamanlar.append((float(d.name), d))
        except ValueError:
            pass
    if not zamanlar:
        return np.nan, np.nan, np.nan
    t, d = max(zamanlar)
    metin = (d / "T").read_text()
    m = re.search(r"internalField\s+uniform\s+([0-9.eE+-]+)", metin)
    if m:
        v = np.array([float(m.group(1))])
    else:
        m = re.search(r"internalField\s+nonuniform\s+List<scalar>\s*\n?\s*(\d+)\s*\n?\s*\((.*?)\)\s*;", metin, re.S)
        v = np.array(m.group(2).split(), dtype=float)
    return t, float(v.max()), float(v.mean())


def kos(kaynak, o2, sure):
    vaka = KOSU_KLASORU / f"O2_{o2:05.2f}"
    if vaka.exists():
        shutil.rmtree(vaka)
    shutil.copytree(kaynak, vaka)
    y_o2, y_n2 = kutle_kesri(o2)
    hava_degeri_yaz(vaka / "0" / "O2", y_o2)
    hava_degeri_yaz(vaka / "0" / "N2", y_n2)
    if sure:
        cd = vaka / "system" / "controlDict"
        cd.write_text(re.sub(r"(endTime\s+)[0-9.eE+-]+;", rf"\g<1>{sure};", cd.read_text()))
    for komut in (["blockMesh"], ["foamRun"]):
        with open(vaka / f"log.{komut[0]}", "w") as log:
            r = subprocess.run(komut, cwd=vaka, stdout=log, stderr=subprocess.STDOUT)
        if r.returncode != 0:
            return {"oksijen": o2, "hata": f"{komut[0]} hata verdi (bkz. {vaka}/log.{komut[0]})"}
    t, tmax, tort = sicaklik_oku(vaka)
    yandi = int(tmax > YANDI_SICAKLIK) if not np.isnan(tmax) else np.nan
    print(f"  O2 %{o2:5.1f} -> en yüksek sıcaklık {tmax:6.0f} K -> {'YANDI' if yandi == 1 else 'SÖNDÜ'}",
          flush=True)
    return {"oksijen": o2, "son_zaman": t, "sicaklik": tmax, "ort_sicaklik": tort, "yandi": yandi}


def simule_et(arg):
    if not shutil.which("foamRun"):
        raise SystemExit("foamRun bulunamadı. Önce: source /opt/openfoam14/etc/bashrc")
    kaynak = kaynak_vaka(arg.vaka)
    oksijenler = [float(x) for x in arg.oksijen.split(",")]
    KOSU_KLASORU.mkdir(exist_ok=True)
    print(f"{len(oksijenler)} simülasyon, aynı anda {arg.paralel} tane (her biri ~30 sn - birkaç dk)...")
    with ThreadPoolExecutor(arg.paralel) as h:
        sonuc = list(h.map(lambda o: kos(kaynak, o, arg.sure), oksijenler))
    df = pd.DataFrame(sonuc).sort_values("oksijen")
    for _, s in df[df.get("hata", pd.Series(dtype=str)).notna()].iterrows() if "hata" in df else []:
        print("  HATA:", s.hata)
    df = df.dropna(subset=["yandi"])
    yanan, sonen = df[df.yandi == 1].oksijen, df[df.yandi == 0].oksijen
    sinir = (yanan.min() + sonen[sonen < yanan.min()].max()) / 2 if len(yanan) and len(sonen[sonen < yanan.min()]) else np.nan
    t = pd.DataFrame({**{k: [v] * len(df) for k, v in KOSUL.items()},
                      "oksijen": df.oksijen.values, "yandi": df.yandi.values.astype(int),
                      "yayilma_hizi": np.nan, "min_oksijen": sinir, "sicaklik": df.sicaklik.values,
                      "kaynak": "OpenFOAM counterFlowFlame2D (mikro-g, 1 atm, 10 cm/s)"})
    t.to_csv(CIKTI, index=False, encoding="utf-8-sig")
    print(f"\nOpenFOAM sönme sınırı: %{sinir:.1f} O2" if not np.isnan(sinir) else "\nOpenFOAM sönme sınırı: bulunamadı (aralığı genişlet)")
    print(f"Kaydedildi: {CIKTI}")
    return t


def karsilastir(t):
    import joblib
    import risk_modeli as r
    rm = joblib.load(r.MODEL_DOSYASI)
    o2 = np.arange(8, 25.01, 0.5)
    kosullar = pd.DataFrame({"g_seviyesi": KOSUL["g"], "oksijen_yuzde": o2, "basinc_kpa": KOSUL["basinc"],
                             "akis_hizi_cm_s": KOSUL["akis"], "kalinlik_mm": np.nan, "malzeme_sade": "methane",
                             "numune_tipi": "gas_jet", "yakit_turu": "gaz", "akis_yonu": "ters",
                             "seyreltici": "n2"})
    p, s, _ = rm.ihtimal(kosullar)
    model_sinir = o2[np.argmax(p >= 0.5)] if (p >= 0.5).any() else np.nan

    # literatür: modelin eğitim verisindeki metan noktaları (uzay ortamı)
    lit = pd.DataFrame()
    if Path(r.VERI).exists():
        d = r.etiketli_veri(pd.read_csv(r.VERI, low_memory=False))
        lit = d[d.malzeme_sade.astype(str).str.contains("methane") & (d.g_seviyesi < 0.01)
                & (d.numune_tipi.astype(str) == "gas_jet")]

    print("\n=== KARŞILAŞTIRMA: metan alevi, uzay (mikro-g), 1 atm ===")
    print(f"{'O2 %':>6} | {'OpenFOAM':>9} | {'Model':>14} | Literatür (±0.5% O2)")
    for _, x in t.iterrows():
        i = np.argmin(np.abs(o2 - x.oksijen))
        yakin = lit[(lit.oksijen_yuzde - x.oksijen).abs() <= 0.5] if len(lit) else lit
        lit_yazi = f"{int(yakin.yanar.sum())} yandı / {int((1 - yakin.yanar).sum())} söndü" if len(yakin) else "-"
        print(f"{x.oksijen:6.1f} | {'YANDI' if x.yandi else 'söndü':>9} | %{100 * p[i]:3.0f} (±{100 * s[i]:2.0f}) "
              f"{'yanar' if p[i] >= .5 else 'söner':>5} | {lit_yazi}")
    yazi = lambda v: "bulunamadı (aralığı genişlet)" if pd.isna(v) else f"%{v:.1f}"
    print(f"\nLiteratür filtresi (metan + g<0.01 + gas_jet): {len(lit)} nokta geçti")
    print(f"Sönme sınırı:  OpenFOAM {yazi(t.min_oksijen.iloc[0])}   |   model {yazi(model_sinir)}")
    uyum = np.mean([(p[np.argmin(np.abs(o2 - x.oksijen))] >= .5) == bool(x.yandi) for _, x in t.iterrows()])
    print(f"Model ile OpenFOAM {len(t)} koşunun %{100 * uyum:.0f}'inde aynı sonucu verdi.")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.fill_between(o2, 100 * (p - s), 100 * (p + s), color="#90caf9", alpha=.5, label="Model belirsizliği")
    ax.plot(o2, 100 * p, color="#1565c0", lw=2.5, label="Risk modeli: yanma ihtimali")
    ax.scatter(t.oksijen, 100 * t.yandi, s=120, marker="s", color="#e65100", zorder=5,
               label="OpenFOAM (100 = yandı, 0 = söndü)")
    if len(lit):
        ax.scatter(lit.oksijen_yuzde, 100 * lit.yanar + np.random.default_rng(0).uniform(-3, 3, len(lit)),
                   s=25, color="#2e7d32", alpha=.6, label="Literatür deneyleri (metan gaz jeti, mikro-g)")
    ax.axhline(50, color="gray", ls=":", lw=1)
    ax.set_xlim(8, 25)
    ax.set_ylim(-8, 108)
    ax.set_xlabel("Oksijen (%)")
    ax.set_ylabel("Yanma ihtimali (%)")
    ax.set_title("Metan alevi, uzay ortamı, 1 atm: OpenFOAM – model – deney karşılaştırması")
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(GRAFIK, dpi=140)
    print(f"Grafik: {GRAFIK}")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--oksijen", default="21,18,16,14,12,10,9,8,7,6,5")
    a.add_argument("--paralel", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a.add_argument("--sure", type=float, help="simülasyon süresi (s); varsayılan örnekteki 0.5")
    a.add_argument("--vaka", help="başka bir case klasörü (varsayılan: OpenFOAM örneği)")
    a.add_argument("--sadece-karsilastir", action="store_true")
    arg = a.parse_args()
    t = pd.read_csv(CIKTI) if arg.sadece_karsilastir else simule_et(arg)
    karsilastir(t)


if __name__ == "__main__":
    main()
