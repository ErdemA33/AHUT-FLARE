#!/usr/bin/env python3
"""engine_sync.py — dashboard/engine/ klasörünü ana klasördeki güncel backend dosyalarıyla eşitler.

    python3 engine_sync.py            # kopyala (değişenleri yazar)
    python3 engine_sync.py --kontrol  # yalnız farkları göster, yazma

Liste DASHBOARD.md §5'e göre. Dashboard ekibinin kendi dosyaları (mock_backend.py, BACKEND_API.md) korunur.
evren_anahtar.txt ASLA kopyalanmaz; yerel denemede ahut_flare.py ana klasördekini EVREN_ANAHTAR_DOSYASI ile gösterir.
"""
import argparse
import filecmp
import shutil
import sys
from pathlib import Path

BURASI = Path(__file__).resolve().parent
ANA = BURASI.parent                 # ~/nasaspaceapp
HEDEF = BURASI / "engine"

DOSYALAR = [
    # giriş noktası, model
    "predict.py", "risk_model.py", "models/risk.joblib",
    # fizik motorları
    "engine.py", "light_engine.py", "light_engine_parameters.json",
    "droplet_engine.py", "droplet_engine_parameters.json", "droplet_features.json",
    "gas_engine.py", "gas_engine_parameters.json", "gas_features.json", "gas_radiation.py",
    # güven skoru, doğrulama tabloları
    "engine_check.py", "engine_comparison.csv", "light_engine_validation_points.csv",
    "droplet_validation.csv", "droplet_flex_flame_target.csv", "droplet_cold_flame_label.csv", "droplet_flex_report_matching.csv",
    "gas_validation_summary.json", "engine_validation.json", "engine_validation_generate.py",
    "gas_data/bre_dehghani2021_table2.csv",
    # deney verisi (önbelleği yeniden üretmek / modeli yeniden eğitmek için)
    "psi_labeled.csv", "psi_labeled_bass1.csv", "psi_labeled_flex.csv", "psi_labeled_flex2.csv",
    "psi_labeled_saffire.csv", "labeled_gemma3.csv", "data_clean.csv",
    # yapay zeka
    "llm_analysis.py", "material_cache.json",
    # yerleşik malzeme kütüphanesi (arayüz: Kütüphane > Malzemeler; modele girmez)
    "material_library.json",
    # topluluk verisi
    "community_data.py", "community_template.csv", "data_extract3.py", "data_extract.py", "clean.py",
    # OpenFOAM tablosu araçları (eski paketteki gibi; openfoam_sonuclar.csv KONMAZ -> hafif/yönlendirici mod)
    "openfoam_runs.py", "openfoam_runs.csv", "openfoam_scan.py", "openfoam_results_methane.csv",
    "ofm_analysis.py", "ofm_engine.py", "ofm_compare.py", "ofm_validation.py", "ofm_import.py", "ofm_result_convert.py", "ofm_case.py",
    "ofm_materials.py", "ofm_material_params.json",
    "droplet_flex_flame_summary.csv",
    # belgeler ve test
    "DASHBOARD.md", "DASHBOARD_DELIVERY.md", "integration_test.py",
]
KORUNAN = {"mock_backend.py", "BACKEND_API.md"}     # dashboard ekibinin kendi dosyaları
YASAK = {"evren_anahtar.txt", "openfoam_sonuclar.csv"}


AYRISTI = ("DÜZEN DEĞİŞTİ: scripts/ altındaki kopyalar artık dashboard/engine/ ile aynı DEĞİL (scripts/ dosyaları depo kökünü "
           "'Path(__file__).parent.parent' ile bulur ve veriyi data/ altında arar; engine/ kopyaları veriyi kendi yanında arar). "
           "Bu betik dosyaları kopyalayınca dashboard bozulurdu, bu yüzden devre dışı. Eşitlemek için ya iki kopyayı elle taşıyın ya da "
           "yolları tek bir ayar noktasına bağlayın.")


def main():
    if "--zorla" not in sys.argv:
        sys.exit(AYRISTI)
    sys.argv.remove("--zorla")
    a = argparse.ArgumentParser()
    a.add_argument("--kontrol", action="store_true")
    k = a.parse_args()
    eksik = [d for d in DOSYALAR if not (ANA / d).is_file()]
    if eksik:
        sys.exit("Ana klasörde yok: " + ", ".join(eksik))
    assert not YASAK & set(DOSYALAR)
    degisen = 0
    for d in DOSYALAR:
        kaynak, hedef = ANA / d, HEDEF / d
        if hedef.is_file() and filecmp.cmp(kaynak, hedef, shallow=False):
            continue
        degisen += 1
        print(("fark  " if k.kontrol else "yaz   ") + d)
        if not k.kontrol:
            hedef.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(kaynak, hedef)
    fazla = sorted(str(p.relative_to(HEDEF)) for p in HEDEF.rglob("*")
                   if p.is_file() and "__pycache__" not in p.parts and str(p.relative_to(HEDEF)) not in DOSYALAR
                   and p.name not in KORUNAN)
    for f in fazla:
        print("listede yok (dokunulmadı): " + f)
    if (HEDEF / "evren_anahtar.txt").exists():
        print("UYARI: engine/evren_anahtar.txt var; pakete girmemeli")
    print(f"{len(DOSYALAR)} dosya, {degisen} {'farklı' if k.kontrol else 'yazıldı'}")


if __name__ == "__main__":
    main()
