<#
Script to build Windows executable using PyInstaller
Requires: Python, PyInstaller in PATH
#>
pyinstaller --noconfirm --windowed --onefile --name "egbtheme-creator_btcr" src/main.py
