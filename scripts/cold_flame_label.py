#!/usr/bin/env python3
"""
scripts/cold_flame_label.py — NASA/TP-2015-216046 (Dietrich ve ark., "Detailed Results From FLEX, 2009-2011")
şekil altyazılarından test başına soğuk alev etiketi çıkarır (CSV'lere dokunmaz; ayrı dosya yazar).

Kural (altyazı metni):
  1  : "cool flame" + (indicative / probably / consistent / evidence / likely / indicating) ve olumsuzlama yok
  0  : "no evidence of (a) cool flame", "no cool flame", "probably no ... cool flame", "no evidence of cool flame formation"
  NaN: "not known / not clear / difficult to determine" ya da altyazıda soğuk alev geçmiyor
Çıktı: data/droplet_cold_flame_label.csv  (test = CSV test no, rapor_no, yakit_altyazi, soguk_alev, kanit)
Önce: python3 scripts/flex_flame_quantify.py (rapor no -> CSV test eşlemesi)
Kullanım: python3 scripts/cold_flame_label.py [rapor.pdf]
"""
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

KOK = Path(__file__).resolve().parent.parent
RAPOR = Path("/mnt/ssd/nasaspaceapp/FLEX12/1/makaleler/20150023456.pdf")
CIKTI = KOK / "data/droplet_cold_flame_label.csv"


def altyazilar(pdf):
    m = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    m = re.sub(r"NASA/TP—2015-216046\s+\d+", " ", m)
    parca = re.split(r"Figure \d+\.\s*[—-]\s*Test FLEX\s*[−–-]\s*(\d+)\.", m)
    out = {}
    for i in range(1, len(parca) - 1, 2):
        no = int(parca[i])
        metin = " ".join(parca[i + 1].split())
        metin = re.split(r"Figure \d+\.\s*[—-]", metin)[0]
        out.setdefault(no, "")
        out[no] += " " + metin
    return out


def etiket(metin):
    t = metin.lower()
    if "cool flame" not in t and "cool-flame" not in t:
        return np.nan, ""
    cumle = [c.strip() for c in re.split(r"(?<=[.;])\s+", metin) if "cool flame" in c.lower()]
    k = " ".join(cumle)
    kl = k.lower()
    if re.search(r"no evidence of (a |prolonged )?cool flame|no cool flame|probably no[, ]|no, or only very brief|"
                 r"appears to be no cool flame|no evidence of cool flame", kl):
        return 0, k
    if re.search(r"not known|not clear|difficult to determine|unclear", kl):
        return np.nan, k
    if re.search(r"indicat|probably|consistent|evidence|likely|suggest", kl):
        return 1, k
    return np.nan, k


def main():
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else RAPOR
    a = altyazilar(pdf)
    sat = []
    for no, metin in sorted(a.items()):
        y = re.search(r"(heptane|methanol|decane|ethanol|propanol)", metin.lower())
        e, k = etiket(metin)
        sat.append({"test": no, "yakit_altyazi": y.group(1) if y else None, "soguk_alev": e, "kanit": k[:400]})
    t = pd.DataFrame(sat).rename(columns={"test": "rapor_no"})
    # rapordaki FLEX–NNN numarası CSV test numarasıyla aynı değil (rapor tabloda olmayan denemeleri de sayıyor);
    # eşleme scripts/flex_flame_quantify.py'nin koşul + ölçüm hizalamasından (data/droplet_flex_report_matching.csv)
    es = KOK / "data/droplet_flex_report_matching.csv"
    if es.exists():
        e = pd.read_csv(es)[["rapor_no", "test"]]
        t = t.merge(e, on="rapor_no", how="left")
    else:
        print("UYARI: data/droplet_flex_report_matching.csv yok -> önce python3 scripts/flex_flame_quantify.py; "
              "test = rapor numarası varsayıldı (yanlış olabilir)")
        t["test"] = t.rapor_no
    t = t[["test", "rapor_no", "yakit_altyazi", "soguk_alev", "kanit"]]
    t.to_csv(CIKTI, index=False, encoding="utf-8-sig")
    print(f"CSV testiyle eşleşen: {int(t.test.notna().sum())} / {len(t)}")
    print(f"{len(t)} test altyazısı; soğuk alev: {int((t.soguk_alev == 1).sum())} var, "
          f"{int((t.soguk_alev == 0).sum())} yok, {int(t.soguk_alev.isna().sum())} belirsiz/söz yok")
    print(t.groupby("yakit_altyazi").soguk_alev.agg(["count", "sum", "size"]))
    print(f"Kaydedildi: {CIKTI.name}")


if __name__ == "__main__":
    main()
