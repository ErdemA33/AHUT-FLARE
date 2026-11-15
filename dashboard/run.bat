@echo off
rem ============================================================
rem  AHUT FLARE - gelistirme baslaticisi
rem  Uygulamayi KONSOL PENCERESI ACMADAN baslatir: pythonw.exe
rem  kullanilir, boylece siyah pencere one gelip uygulamayi
rem  arkada birakmaz. Bir sey ters giderse troubleshoot.bat'i calistirin.
rem ============================================================
setlocal
cd /d "%~dp0"

call "%~dp0python_bul.bat"

if not defined PY (
  echo.
  echo   "yangin" ortami bulunamadi.
  echo   Anaconda Prompt'ta su komutlari calistirin:
  echo       conda activate yangin
  echo       python ahut_flare.py
  echo.
  pause
  exit /b 1
)

rem pythonw.exe = konsolsuz surum
set "PYW=%PY:python.exe=pythonw.exe%"
if not exist "%PYW%" set "PYW=%PY%"

start "AHUT FLARE" "%PYW%" "%~dp0ahut_flare.py" %*
exit /b 0
