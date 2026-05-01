<# NSIS packaging helper - generic placeholder to invoke makensis on a provided installer script #>
param(
  [string]$installer = "scripts/installer.nsi"
)
if (-not (Get-Command makensis -ErrorAction SilentlyContinue)) {
  Write-Error "makensis not found in PATH. Install NSIS to proceed with NSIS packaging."
  exit 1
}
Write-Host "Running NSIS to build installer from $installer ..."
makensis $installer
