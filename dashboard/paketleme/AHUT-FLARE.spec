# -*- mode: python ; coding: utf-8 -*-
"""AHUT FLARE — PyInstaller tarifi.

Kullanım (paketleme klasöründen değil, proje kökünden):
    pyinstaller paketleme/AHUT-FLARE.spec --noconfirm --clean

Çıktı: dist/AHUT FLARE/AHUT FLARE.exe
"""
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

KOK = Path(SPECPATH).parent          # proje kökü
MOTOR = KOK / "motor"

# --- conda ortamı düzeltmesi -------------------------------------------------
# Conda, yerel kütüphaneleri <ortam>\Library\bin altında tutar ve bu klasör
# yalnızca "conda activate" ile PATH'e eklenir. PyInstaller doğrudan
# python.exe ile çağrıldığında orayı göremez; _ctypes.pyd'nin ihtiyaç duyduğu
# ffi-8.dll gibi dosyalar pakete girmez ve exe "DLL load failed" verir.
# Bu yüzden klasörü hem PATH'e ekliyor hem de kritik DLL'leri açıkça yazıyoruz.
ORTAM_BIN = Path(sys.executable).parent / "Library" / "bin"
binaries = []
if ORTAM_BIN.is_dir():
    os.environ["PATH"] = str(ORTAM_BIN) + os.pathsep + os.environ.get("PATH", "")
    for ad in ("ffi-8.dll", "ffi-7.dll", "ffi.dll",
               "libcrypto-3-x64.dll", "libssl-3-x64.dll",
               "sqlite3.dll", "liblzma.dll", "libbz2.dll", "bz2.dll", "zlib.dll",
               "libexpat.dll"):
        p = ORTAM_BIN / ad
        if p.exists():
            binaries.append((str(p), "."))

# Arayüz ve model dosyaları paketin içine konur (salt okunur).
datas = [
    (str(KOK / "arayuz"), "arayuz"),
]
# Topluluk sekmesinin örnek vakaları paketin içinde taşınır (salt okunur).
if (KOK / "veri" / "ornekler").is_dir():
    datas.append((str(KOK / "veri" / "ornekler"), "veri/ornekler"))
# GitHub Pages sitesinin kaynakları: uygulama bunları depoya kendisi yükler.
if (KOK / "site").is_dir():
    datas.append((str(KOK / "site"), "site"))
# motor/: alt klasörler dahil (modeller/, gaz_veri/ ...). Anahtar, önbellek ve kullanıcı verisi pakete GİRMEZ.
MOTOR_DISI = {"evren_anahtar.txt", "openfoam_sonuclar.csv"}
for p in sorted(MOTOR.rglob("*")):
    if (p.is_file() and "__pycache__" not in p.parts and "topluluk" not in p.relative_to(MOTOR).parts
            and p.name not in MOTOR_DISI and not p.name.endswith((".anahtar", ".sqlite", ".jsonl"))):
        datas.append((str(p), str(Path("motor") / p.relative_to(MOTOR).parent)))

datas += collect_data_files("sklearn")

hiddenimports = (
    collect_submodules("sklearn")
    + collect_submodules("scipy")
    + ["pandas", "numpy", "joblib", "psutil",
       "tahmin", "risk_modeli", "motor", "hafif_motor", "motor_kontrol", "llm_analiz",
       "damla_motoru", "gaz_motoru", "gaz_isinim", "topluluk_veri", "sqlite3"]
)

a = Analysis(
    [str(KOK / "ahut_flare.py")],
    pathex=[str(KOK), str(MOTOR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "tkinter", "IPython", "pytest", "notebook", "PyQt5", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="AHUT FLARE",
    icon=str(KOK / "arayuz" / "marka" / "ahut.ico"),
    console=False,                 # masaüstü uygulaması: konsol penceresi açılmaz
    disable_windowed_traceback=False,
    version=None,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False,
    name="AHUT FLARE",
)
