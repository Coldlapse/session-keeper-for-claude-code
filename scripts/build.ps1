# 로컬 빌드: 포터블 zip (+ 옵션으로 MSIX)
#   ./scripts/build.ps1            → dist/ClaudeSessionKeeper-<ver>-win64-portable.zip
#   ./scripts/build.ps1 -Msix      → + Store 업로드용 msix
param([switch]$Msix)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
python -m pip install -r requirements.txt -r requirements-build.txt
if ($LASTEXITCODE) { throw "pip 실패" }
python -m PyInstaller --noconfirm --distpath dist --workpath build\pyi packaging\ClaudeSessionKeeper.spec
if ($LASTEXITCODE) { throw "PyInstaller 실패" }
$ver = (python -c "import sys; sys.path.insert(0,'src'); import version; print(version.__version__)").Trim()
Copy-Item README.md, LICENSE dist\ClaudeSessionKeeper\
$zip = "dist\ClaudeSessionKeeper-$ver-win64-portable.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive dist\ClaudeSessionKeeper $zip
Write-Host "포터블: $zip"
if ($Msix) { & "$PSScriptRoot\..\packaging\build_msix.ps1" }
