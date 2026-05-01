!define APP_NAME "egbtheme-creator_btcr"
Name "${APP_NAME}"
OutFile "${APP_NAME}_setup.exe"
InstallDir "$PROGRAMFILES\\${APP_NAME}"
Page Directory
Page InstFiles

Section "Main"
  SetOutPath "$INSTDIR"
  MessageBox MB_OK|MB_ICONINFORMATION " NSIS placeholder installer for ${APP_NAME}. In a full build, the packaged executable will be installed here."
SectionEnd
