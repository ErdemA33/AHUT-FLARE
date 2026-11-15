@echo off
rem ============================================================
rem  AHUT FLARE - Python yorumlayicisini bulur, PY degiskenine yazar.
rem  run.bat, troubleshoot.bat ve paketleme\build_exe.bat bunu
rem  "call" ile kullanir. Sabit klasor yolu YOK; sira:
rem    1) YANGIN_PYTHON ortam degiskeni (tam yol)
rem    2) proje klasorundeki .venv\Scripts\python.exe
rem    3) etkin conda ortami (CONDA_PREFIX)
rem    4) "conda env list" icinde "yangin" adli ortam
rem    5) Windows Python baslaticisi: py -3.12
rem    6) PATH'teki python
rem ============================================================
set "PY="
set "_KOK=%~dp0"

if defined YANGIN_PYTHON if exist "%YANGIN_PYTHON%" set "PY=%YANGIN_PYTHON%"

if not defined PY if exist "%_KOK%.venv\Scripts\python.exe" set "PY=%_KOK%.venv\Scripts\python.exe"

if not defined PY if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\python.exe" set "PY=%CONDA_PREFIX%\python.exe"

if not defined PY (
  for /f "usebackq tokens=1,* delims= " %%A in (`conda env list 2^>nul`) do (
    if /i "%%A"=="yangin" if not defined PY call :conda_yolu "%%B"
  )
)

if not defined PY (
  for /f "usebackq delims=" %%P in (`py -3.12 -c "import sys;print(sys.executable)" 2^>nul`) do set "PY=%%P"
)

if not defined PY (
  for /f "usebackq delims=" %%P in (`where python 2^>nul`) do if not defined PY set "PY=%%P"
)
set "_KOK="
exit /b 0

:conda_yolu
rem "conda env list" satiri: "yangin   [*]  C:\...\envs\yangin" -> yildizi at
set "_YOL=%~1"
if "%_YOL:~0,2%"=="* " set "_YOL=%_YOL:~2%"
for /f "tokens=* delims= " %%Y in ("%_YOL%") do set "_YOL=%%Y"
if exist "%_YOL%\python.exe" set "PY=%_YOL%\python.exe"
set "_YOL="
exit /b 0
