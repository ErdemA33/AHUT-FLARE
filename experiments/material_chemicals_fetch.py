#!/usr/bin/env python3
"""material_chemicals_fetch.py — `chemicals` kütüphanesinden (Caleb Bell, MIT lisanslı; sürüm kaydedilir) saf sıvı/gaz
özelliklerini ve her değerin ALT KAYNAĞINI (chemicals'ın seçtiği yöntem/veri tablosu) çeker.

    dashboard/.venv/bin/python experiments/material_chemicals_fetch.py   -> experiments/material_chemicals_ham.json

chemicals sudo'suz dashboard/.venv'e kuruldu (pip). Değer değiştirilmez; yalnız birim çevrilir.
  Tb, Tc (K); Hvap Tb'de ve 298 K'de (CRC tablosu, J/mol); parlama noktası, kendiliğinden tutuşma (K);
  LFL/UFL (hacim kesri); sıvı yoğunluğu 298,15 K (Perry's 8E DIPPR-105 katsayıları, yoksa VDI PPDS-2);
  HHV/LHV: chemicals.combustion.combustion_data (oluşum entalpisi Hf'den; Hf'nin kaynağı yazılır).
"""
import json
from pathlib import Path

import chemicals
from chemicals import critical as cr
from chemicals import phase_change as pc
from chemicals import reaction as rx
from chemicals import safety as sf
from chemicals import volume as vo
from chemicals.combustion import LHV_from_HHV, combustion_data
from chemicals.dippr import EQ105
from chemicals.identifiers import search_chemical

CAS = {"ethanol": "64-17-5", "isopropanol": "67-63-0", "methanol": "67-56-1", "n-heptane": "142-82-5",
       "n-decane": "124-18-5", "acetone": "67-64-1", "propylene-glycol": "57-55-6", "mmh": "60-34-4",
       "hydrazine": "302-01-2", "hydrogen": "1333-74-0", "methane": "74-82-8", "ethylene": "74-85-1",
       "ethane": "74-84-0", "propane": "74-98-6", "carbon-monoxide": "630-08-0", "ammonia": "7664-41-7",
       "acetylene": "74-86-2",
       # 2. genişletme (2026-11-13)
       "dmc": "616-38-6", "dec": "105-58-8", "ec": "96-49-1", "glycerol": "56-81-5", "ethylene-glycol": "107-21-1",
       "udmh": "57-14-7", "ethyl-acetate": "141-78-6", "hydrogen-peroxide": "7722-84-1", "n-butane": "106-97-8",
       "isobutane": "75-28-5", "dme": "115-10-6", "nitrous-oxide": "10024-97-2", "formaldehyde": "50-00-0",
       "hydrogen-sulfide": "7783-06-4", "oxygen": "7782-44-7"}
SIVI = {"ethanol", "isopropanol", "methanol", "n-heptane", "n-decane", "acetone", "propylene-glycol", "mmh", "hydrazine",
        "dmc", "dec", "ec", "glycerol", "ethylene-glycol", "udmh", "ethyl-acetate", "hydrogen-peroxide"}
T0 = 298.15


def yontemli(f, yontemler, *a, **k):
    m = yontemler(*a, **k)
    if not m:
        return None, None
    try:
        return f(*a, method=m[0], **k), m[0]
    except Exception:  # noqa: BLE001
        return None, None


def main():
    vo._load_rho_data()
    out = {"kaynak": f"chemicals {chemicals.__version__} (Caleb Bell; https://github.com/CalebBell/chemicals)",
           "maddeler": {}}
    for ad, cas in CAS.items():
        kim = search_chemical(cas)
        mw = kim.MW
        k = {"cas": cas, "ad": kim.common_name, "formul": kim.formula, "MW": mw}
        k["Tb"] = yontemli(pc.Tb, pc.Tb_methods, cas)
        k["Tc"] = yontemli(cr.Tc, cr.Tc_methods, cas)
        k["T_flash"] = yontemli(sf.T_flash, sf.T_flash_methods, cas)
        k["T_autoignition"] = yontemli(sf.T_autoignition, sf.T_autoignition_methods, cas)
        k["LFL"] = (sf.LFL(CASRN=cas), (sf.LFL_methods(CASRN=cas) or [None])[0])   # chemicals'ın varsayılan yöntemi
        k["UFL"] = (sf.UFL(CASRN=cas), (sf.UFL_methods(CASRN=cas) or [None])[0])
        if cas in pc.Hvap_data_CRC.index:
            r = pc.Hvap_data_CRC.loc[cas]
            k["Hvap_CRC"] = {"Tb": None if r.Tb != r.Tb else float(r.Tb),
                             "HvapTb_J_mol": None if r.HvapTb != r.HvapTb else float(r.HvapTb),
                             "Hvap298_J_mol": None if r.Hvap298 != r.Hvap298 else float(r.Hvap298),
                             "tablo": "CRC Handbook (chemicals Hvap_data_CRC)"}
        if ad in SIVI:
            if cas in vo.rho_data_Perry_8E_105_l.index:
                r = vo.rho_data_Perry_8E_105_l.loc[cas]
                if r.Tmin <= T0 <= r.Tmax:
                    rho_mol = EQ105(T0, r.C1, r.C2, r.C3, r.C4)          # mol/m3
                    k["rho_l_298"] = (rho_mol * mw / 1000, "Perry's 8E Tablo 2-32 (DIPPR 105) katsayıları")
            if "rho_l_298" not in k and cas in vo.rho_data_VDI_PPDS_2.index:
                r = vo.rho_data_VDI_PPDS_2.loc[cas]
                Vm = vo.volume_VDI_PPDS(T0, r.Tc, r.rhoc, r.A, r.B, r.C, r.D, r.MW)
                k["rho_l_298"] = (mw / Vm / 1000, "VDI Isı Atlası PPDS-2 katsayıları")
        # yanma ısısı: sıvıda sıvı Hf, gazda gaz Hf
        if ad in SIVI:
            Hf, yHf = yontemli(rx.Hfl, rx.Hfl_methods, cas)
        else:
            Hf, yHf = yontemli(rx.Hfg, rx.Hfg_methods, cas)
        if Hf is not None or cas == "1333-74-0":
            try:
                Hf = Hf if Hf is not None else 0.0
                cd = combustion_data(kim.formula, Hf=Hf, MW=mw)
                n_h2o = cd.stoichiometry.get("H2O", 0)
                k["HHV"] = {"J_mol": cd.HHV, "LHV_J_mol": LHV_from_HHV(cd.HHV, n_h2o), "Hf_J_mol": Hf,
                            "Hf_kaynak": yHf or "element (Hf = 0)"}
            except Exception as e:  # noqa: BLE001
                k["HHV"] = {"hata": str(e)}
        out["maddeler"][ad] = k
        print(ad, kim.formula, {x: (k[x][0] if isinstance(k.get(x), tuple) else None) for x in
                                ("Tb", "Tc", "T_flash", "LFL", "UFL", "rho_l_298")}, flush=True)
    Path(__file__).with_name("material_chemicals_ham.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
