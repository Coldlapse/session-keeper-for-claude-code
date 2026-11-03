<#
.SYNOPSIS
  dist/ClaudeSessionKeeper (PyInstaller 결과) → MSIX 패키지.
.EXAMPLE
  ./packaging/build_msix.ps1                       # Store 업로드용 (서명 안 함, Store가 서명)
  ./packaging/build_msix.ps1 -Dev -PfxPath dev.pfx # 로컬 설치 테스트용 (개발 ID + 자체 서명)
#>
param(
  [switch]$Dev,
  [string]$PfxPath,
  [string]$PfxPassword = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$dist = Join-Path $Root "dist\ClaudeSessionKeeper"
if (-not (Test-Path "$dist\ClaudeSessionKeeper.exe")) { throw "먼저 PyInstaller 빌드 필요 (scripts/build.ps1)" }

$version = (python -c "import sys; sys.path.insert(0,'src'); import version; print(version.MSIX_VERSION)").Trim()
$id = Get-Content "packaging\msix\identity.json" -Raw | ConvertFrom-Json
if ($Dev -or $id.Publisher -like "*CHANGE-ME*") {
  Write-Warning "개발 ID로 빌드합니다 (Store 업로드 불가). identity.json을 Partner Center 값으로 채우세요."
  $id.IdentityName = "Dev.ClaudeSessionKeeper"
  $id.Publisher = "CN=ClaudeSessionKeeperDev"
  $id.PublisherDisplayName = "Dev"
  $Dev = $true
}

$stage = Join-Path $Root "build\msix-stage"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory $stage | Out-Null
Copy-Item $dist (Join-Path $stage "ClaudeSessionKeeper") -Recurse
python packaging\msix\make_assets.py (Join-Path $stage "Assets")

$m = Get-Content "packaging\msix\AppxManifest.template.xml" -Raw -Encoding UTF8
$m = $m.Replace("{{IdentityName}}", $id.IdentityName).Replace("{{Publisher}}", $id.Publisher)
$m = $m.Replace("{{PublisherDisplayName}}", $id.PublisherDisplayName).Replace("{{DisplayName}}", $id.DisplayName)
$m = $m.Replace("{{Version}}", $version)
[IO.File]::WriteAllText((Join-Path $stage "AppxManifest.xml"), $m, (New-Object Text.UTF8Encoding $false))

$kit = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\makeappx.exe" -ErrorAction SilentlyContinue |
       Sort-Object FullName | Select-Object -Last 1
if (-not $kit) { throw "makeappx.exe 없음 — Windows SDK 설치 필요" }
$bin = Split-Path $kit.FullName

$suffix = if ($Dev) { "-dev" } else { "" }
$out = Join-Path $Root "dist\ClaudeSessionKeeper-$version-x64$suffix.msix"
& "$bin\makeappx.exe" pack /d $stage /p $out /o
if ($LASTEXITCODE) { throw "makeappx 실패" }

if ($PfxPath) {
  & "$bin\signtool.exe" sign /fd SHA256 /a /f $PfxPath /p $PfxPassword $out
  if ($LASTEXITCODE) { throw "signtool 실패" }
}
Write-Host "완료: $out"
