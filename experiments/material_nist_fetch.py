#!/usr/bin/env python3
"""material_nist_fetch.py — NIST Chemistry WebBook'tan (webbook.nist.gov, SRD 69) saf sıvı/gaz özelliklerini çeker.

    python3 experiments/material_nist_fetch.py      -> experiments/material_nist_ham.json (her tablonun bütün satırları)

Çekilen: molar kütle; Tboil (K), ΔvapH° / ΔvapH (kJ/mol), ΔcH°liquid / ΔcH°gas (kJ/mol).
Seçim kuralları scripts/material_library_generate.py'de; burada hiçbir değer seçilmez ya da değiştirilmez.
"""
import html
import json
import re
import time
import subprocess
from pathlib import Path

CAS = {   # NIST WebBook kimliği (C + CAS numarası)
    "ethanol": "C64175", "isopropanol": "C67630", "methanol": "C67561", "n-heptane": "C142825",
    "n-decane": "C124185", "acetone": "C67641", "propylene-glycol": "C57556", "mmh": "C60344",
    "hydrazine": "C302012", "hydrogen": "C1333740", "methane": "C74828", "ethylene": "C74851",
    "ethane": "C74840", "propane": "C74986", "carbon-monoxide": "C630080", "ammonia": "C7664417",
    "acetylene": "C74862",
    # 2. genişletme (2026-11-13)
    "dmc": "C616386", "dec": "C105588", "ec": "C96491", "glycerol": "C56815", "ethylene-glycol": "C107211",
    "udmh": "C57147", "ethyl-acetate": "C141786", "hydrogen-peroxide": "C7722841", "n-butane": "C106978",
    "isobutane": "C75285", "dme": "C115106", "nitrous-oxide": "C10024972", "formaldehyde": "C50000",
    "hydrogen-sulfide": "C7783064", "oxygen": "C7782447",
}
MASKE = {"gaz_termo": 1, "yogun_termo": 2, "faz_degisimi": 4}
URL = "https://webbook.nist.gov/cgi/cbook.cgi?ID={id}&Units=SI&Mask={m}"


def metin(x):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x))).strip()


def satirlar(sayfa):
    out = []
    for tablo in re.findall(r"<table[^>]*class=\"data\"[^>]*>(.*?)</table>", sayfa, re.S):
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tablo, re.S):
            hucre = [metin(h) for h in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
            if len(hucre) >= 3 and hucre[0] not in ("Quantity",):
                out.append(hucre)
    return out


def main():
    ham = {"kaynak": "NIST Chemistry WebBook, NIST Standard Reference Database Number 69, https://webbook.nist.gov",
           "cekim": time.strftime("%Y-%m-%d"), "maddeler": {}}
    hedef = Path(__file__).with_name("material_nist_ham.json")
    if hedef.exists():                       # kaldığı yerden devam
        ham["maddeler"] = json.loads(hedef.read_text(encoding="utf-8")).get("maddeler", {})
    for ad, id_ in CAS.items():
        if ad in ham["maddeler"]:
            continue
        kayit = {"nist_id": id_, "adres": URL.format(id=id_, m=0).replace("&Mask=0", "")}
        for anahtar, m in MASKE.items():
            # urllib bu sunucuda yanıtı okurken takılıyor (bağlantı açık kalıyor); curl kullanılır
            for deneme in range(3):
                r = subprocess.run(["curl", "-s", "-m", "60", "-A", "Mozilla/5.0 (malzeme-kutuphanesi)",
                                    URL.format(id=id_, m=m)], capture_output=True)
                if r.returncode == 0 and r.stdout:
                    sayfa = r.stdout.decode("utf-8", "replace")
                    break
                print("  yeniden dene", ad, anahtar, r.returncode, flush=True)
                time.sleep(5)
            else:
                raise SystemExit(f"{ad} {anahtar}: NIST'e ulaşılamadı")
            if anahtar == "gaz_termo":
                mw = re.search(r"Molecular weight</a>:</strong>\s*([0-9.]+)", sayfa) or \
                     re.search(r"Molecular weight[^0-9]*([0-9]+\.[0-9]+)", sayfa)
                kayit["molar_kutle"] = float(mw.group(1)) if mw else None
                ad_m = re.search(r"<title>(.*?)</title>", sayfa, re.S)
                kayit["nist_adi"] = metin(ad_m.group(1)) if ad_m else None
            kayit[anahtar] = satirlar(sayfa)
            time.sleep(1.0)
        ham["maddeler"][ad] = kayit
        hedef.write_text(json.dumps(ham, ensure_ascii=False, indent=1), encoding="utf-8")
        print(ad, kayit.get("nist_adi"), kayit.get("molar_kutle"),
              {k: len(kayit[k]) for k in MASKE}, flush=True)


if __name__ == "__main__":
    main()
