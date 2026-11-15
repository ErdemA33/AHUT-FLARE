@echo off
chcp 65001 >nul
rem ============================================================
rem  AHUT FLARE - sorun giderme
rem  Uygulama acilmiyorsa BU dosyaya cift tiklayin.
rem  Once pencere acmadan kendi kendini sinar, sonra uygulamayi
rem  konsol acik halde baslatir; butun hatalar ekranda kalir.
rem ============================================================
setlocal
cd /d "%~dp0"

echo.
echo ================================================
echo   AHUT FLARE - sorun giderme
echo ================================================
echo.

call "%~dp0python_bul.bat"

if not defined PY (
  echo [HATA] "yangin" conda ortami bulunamadi.
  echo        Model bu ortam olmadan calismaz.
  echo.
  pause
  exit /b 1
)
echo Python   : %PY%

"%PY%" -c "import sys,sklearn,numpy,webview;print('Paketler : Python',sys.version.split()[0],'| scikit-learn',sklearn.__version__,'| numpy',numpy.__version__,'| pywebview tamam')"
if errorlevel 1 (
  echo.
  echo [HATA] Gerekli paketlerden biri eksik. Sunu calistirin:
  echo        "%PY%" -m pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

echo.
echo --- 1. adim: kendi kendini sinama (pencere acilmaz) ---
"%PY%" ahut_flare.py --sinama
if errorlevel 1 (
  echo.
  echo [HATA] Sinama basarisiz. Yukaridaki [HATA] satirlarini ekibe iletin.
  echo.
  pause
  exit /b 1
)

echo.
echo --- 2. adim: uygulama baslatiliyor ---
echo Bu pencere ACIK kalacak. Uygulama penceresi 5-10 saniye icinde
echo ayri bir pencerede acilir. Gorev cubugunda "AHUT FLARE" arayin.
echo Kapatmak icin uygulama penceresini kapatin.
echo.
"%PY%" ahut_flare.py --ayikla
echo.
echo Uygulama kapandi.
pause
