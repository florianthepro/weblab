@echo off
setlocal
title weblab Builder
pushd "%~dp0" || (echo Ordner nicht erreichbar. & pause & exit /b 1)
set "RC=0"
set "PYINSTALLER=pyinstaller==6.22.2"
set "PYTHONHASHSEED=1"
set "SOURCE_DATE_EPOCH=1735689600"

echo(
echo   weblab Builder - erzeugt dist\weblab.exe
echo(

set "PY="
for /f "delims=" %%P in ('where python.exe 2^>nul') do call :pruefe "%%~fP"
if defined PY goto :habpython
for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do call :pruefe "%%~fP"
:habpython
if not defined PY (
  echo   Python 3 wurde nicht gefunden.
  echo(
  echo   Bitte von  https://www.python.org/downloads/windows/  installieren
  echo   und dabei "Add python.exe to PATH" ankreuzen, dann builder.bat erneut starten.
  set "RC=1"
  goto :ende
)
echo   Python:   %PY%

set "BUILD=%CD%\build"
set "VENV=%BUILD%\venv"
set "VPY=%VENV%\Scripts\python.exe"
if not exist "%BUILD%" mkdir "%BUILD%"
if errorlevel 1 goto :fehler

echo   Umgebung ...
if not exist "%VPY%" "%PY%" -m venv "%VENV%"
if errorlevel 1 goto :fehler
"%VPY%" -m pip install --quiet --no-input --disable-pip-version-check --only-binary=:all: "%PYINSTALLER%"
if errorlevel 1 (
  echo   PyInstaller konnte nicht geladen werden - Internetverbindung pruefen.
  set "RC=1"
  goto :ende
)

echo   Symbol ...
"%VPY%" "desktop\make_icon.py"
if errorlevel 1 goto :fehler

echo   Bauen ... ^(beim ersten Mal ein paar Minuten^)
"%VPY%" -m PyInstaller --noconfirm --clean --onefile --windowed --noupx ^
  --name weblab --icon "desktop\weblab.ico" --version-file "desktop\version_info.txt" ^
  --add-data "software\weblab\ui.py;." --add-data "software\weblab\icon.py;." ^
  --exclude-module tkinter --exclude-module unittest ^
  --distpath "dist" --workpath "build\work" --specpath "build" ^
  "desktop\weblab_desktop.py"
if errorlevel 1 goto :fehler

echo(
echo   Fertig: %CD%\dist\weblab.exe
echo   Beim Weitergeben warnt Windows vor unbekanntem Herausgeber:
echo   "Weitere Informationen" und dann "Trotzdem ausfuehren".
goto :ende

:pruefe
if defined PY goto :eof
echo(%~1|find /i "\WindowsApps\" >nul && goto :eof
"%~1" -c "import sys;sys.exit(0 if sys.version_info[:2]>=(3,8) else 1)" >nul 2>&1 || goto :eof
set "PY=%~1"
goto :eof

:fehler
echo(
echo   Build fehlgeschlagen - die Meldung oben nennt die Ursache.
set "RC=1"

:ende
echo(
popd
pause
exit /b %RC%
