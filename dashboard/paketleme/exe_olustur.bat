@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."

echo.
echo ================================================
echo   AHUT FLARE - kurulum paketi olusturucu
echo ================================================
echo.

rem --- Python'u bul: once yangin ortami, sonra PATH ---
call "%~dp0..\python_bul.bat"
if not defined PY (
  echo HATA: Python bulunamadi. Anaconda Prompt'ta "conda activate yangin" yapip tekrar deneyin.
  pause & exit /b 1
)
echo Python: %PY%

rem Conda yerel kutuphaneleri Library\bin altindadir ve yalnizca "conda activate"
rem ile PATH'e girer. Dogrudan python.exe cagrildiginda PyInstaller oradaki
rem DLL'leri goremez (ffi-8.dll gibi) ve exe "DLL load failed" verir.
for %%D in ("%PY%") do set "PYDIR=%%~dpD"
if exist "%PYDIR%Library\bin" set "PATH=%PYDIR%Library\bin;%PATH%"

"%PY%" -c "import sys,sklearn,numpy;print('  surum:',sys.version.split()[0],'| scikit-learn',sklearn.__version__,'| numpy',numpy.__version__)" || goto :hata
"%PY%" -m pip install --quiet pyinstaller pywebview || goto :hata

if exist build rmdir /s /q build
if exist "dist\AHUT FLARE" rmdir /s /q "dist\AHUT FLARE"

echo.
echo [1/3] Paketleniyor (5-10 dakika surebilir)...
"%PY%" -m PyInstaller paketleme\AHUT-FLARE.spec --noconfirm --clean || goto :hata

echo.
echo [2/3] Ek dosyalar kopyalaniyor...
rem GIZLILIK: evren_anahtar.txt dagitilan pakete KONULMAZ. Yalnizca bu bilgisayardaki
rem kurulu surumun calismasi icin kendi LocalAppData klasorune kopyalanir.
if exist "dist\AHUT FLARE\evren_anahtar.txt" del /q "dist\AHUT FLARE\evren_anahtar.txt"
if exist evren_anahtar.txt (
  if not exist "%LOCALAPPDATA%\AHUT FLARE" mkdir "%LOCALAPPDATA%\AHUT FLARE"
  copy /y evren_anahtar.txt "%LOCALAPPDATA%\AHUT FLARE\evren_anahtar.txt" >nul
  echo   anahtar yalnizca "%LOCALAPPDATA%\AHUT FLARE" icine kopyalandi ^(pakete girmedi^)
)
copy /y BENIOKU.txt "dist\AHUT FLARE\BENIOKU.txt" >nul
copy /y LICENSE "dist\AHUT FLARE\LICENSE.txt" >nul
if not exist "dist\AHUT FLARE\render" mkdir "dist\AHUT FLARE\render"
if exist "veri\ornekler" xcopy /e /i /y "veri\ornekler" "dist\AHUT FLARE\veri\ornekler" >nul

echo.
echo [3/3] Kurulum sihirbazi olusturuluyor...
set "ISCC="
for %%I in (
  "%PROGRAMFILES(X86)%\Inno Setup 6\ISCC.exe"
  "%PROGRAMFILES%\Inno Setup 6\ISCC.exe"
) do if not defined ISCC if exist %%I set "ISCC=%%~I"

if defined ISCC (
  "%ISCC%" paketleme\kurulum.iss || goto :hata
  echo.
  echo ===== TAMAM =====
  echo Kurulum dosyasi : paketleme\Cikti\AHUT-FLARE-Kurulum.exe
) else (
  echo Inno Setup bulunamadi, kurulum sihirbazi atlandi.
  echo   Kurmak icin: https://jrsoftware.org/isdl.php  ^(Inno Setup 6^)
  echo Tasinabilir surum hazirlaniyor...
  echo tasinabilir > "dist\AHUT FLARE\tasinabilir.txt"
  powershell -NoProfile -Command "Compress-Archive -Path 'dist\AHUT FLARE' -DestinationPath 'AHUT-FLARE-tasinabilir.zip' -Force" || goto :hata
  echo.
  echo ===== TAMAM =====
  echo Tasinabilir paket : AHUT-FLARE-tasinabilir.zip
)
echo Denemek icin     : "dist\AHUT FLARE\AHUT FLARE.exe"
echo.
pause
exit /b 0

:hata
echo.
echo HATA: yukaridaki mesaji ekibe iletin.
pause
exit /b 1
