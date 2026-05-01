Packaging Notes
- AppImage (Linux): prep AppDir with AppRun and bin; requires appimagetool to generate final AppImage.
- Windows: PyInstaller produces an EXE; for a full installer you can add NSIS later.
- Ensure PyInstaller bundles PySide6 Qt runtime; on Linux, consider including system libs if needed.
- For both platforms, ensure assets are located under the theme's assets path and that export creates themes_export/
- The MVP packaging scripts are scaffolding; you can adapt paths to your actual CI/CD.
