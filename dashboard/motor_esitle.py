#!/usr/bin/env python3
"""motor_esitle.py — dashboard/motor/ klasörünü ana klasördeki güncel backend dosyalarıyla eşitler.

    python3 motor_esitle.py            # kopyala (değişenleri yazar)
    python3 motor_esitle.py --kontrol  # yalnız farkları göster, yazma

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
HEDEF = BURASI / "motor"

DOSYALAR = [
    # giriş noktası, model
    "tahmin.py", "risk_modeli.py", "modeller/risk.joblib",
    # fizik motorları
    "motor.py", "hafif_motor.py", "hafif_motor_parametreleri.json",
    "damla_motoru.py", "damla_motoru_parametreleri.json", "damla_ozellikleri.json",
    "gaz_motoru.py", "gaz_motoru_parametreleri.json", "gaz_ozellikleri.json", "gaz_isinim.py",
    # güven skoru, doğrulama tabloları
    "motor_kontrol.py", "motor_karsilastirma.csv", "hafif_motor_dogrulama_noktalar.csv",
    "damla_dogrulama.csv", "damla_flex_alev_hedef.csv", "damla_soguk_alev_etiket.csv", "damla_flex_rapor_eslesme.csv",
    "gaz_dogrulama_ozet.json", "motor_dogrulama.json", "motor_dogrulama_uret.py",
    "gaz_veri/bre_dehghani2021_tablo2.csv",
    # deney verisi (önbelleği yeniden üretmek / modeli yeniden eğitmek için)
    "psi_etiketli.csv", "psi_etiketli_bass1.csv", "psi_etiketli_flex.csv", "psi_etiketli_flex2.csv",
    "psi_etiketli_saffire.csv", "etiketli_gemma3.csv", "veri_temiz.csv",
    # yapay zeka
    "llm_analiz.py", "malzeme_onbellek.json",
    # yerleşik malzeme kütüphanesi (arayüz: Kütüphane > Malzemeler; modele girmez)
    "malzeme_kutuphanesi.json",
    # topluluk verisi
    "topluluk_veri.py", "topluluk_sablon.csv", "veri_cikar3.py", "veri_cikar.py", "temizle.py",
    # OpenFOAM tablosu araçları (eski paketteki gibi; openfoam_sonuclar.csv KONMAZ -> hafif/yönlendirici mod)
    "openfoam_kosular.py", "openfoam_kosular.csv", "openfoam_tarama.py", "openfoam_sonuclar_metan.csv",
    "ofm_analiz.py", "ofm_motor.py", "ofm_karsilastir.py", "ofm_dogrulama.py", "ofm_ice_aktar.py", "ofm_sonuc_donustur.py", "ofm_vaka.py",
    "damla_flex_alev_ozet.csv",
    # belgeler ve test
    "DASHBOARD.md", "DASHBOARD_TESLIM.md", "entegrasyon_test.py",
]
KORUNAN = {"mock_backend.py", "BACKEND_API.md"}     # dashboard ekibinin kendi dosyaları
YASAK = {"evren_anahtar.txt", "openfoam_sonuclar.csv"}


def main():
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
        print("UYARI: motor/evren_anahtar.txt var; pakete girmemeli")
    print(f"{len(DOSYALAR)} dosya, {degisen} {'farklı' if k.kontrol else 'yazıldı'}")


if __name__ == "__main__":
    main()
