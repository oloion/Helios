@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
python -m PyInstaller Helios.spec --noconfirm
echo.
echo Built: dist\Helios.exe
