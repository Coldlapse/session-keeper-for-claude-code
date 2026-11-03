<#
.SYNOPSIS
  MSIX 로컬 설치 테스트용 자체 서명 인증서 생성 (Store 제출에는 필요 없음).
  관리자 PowerShell에서 실행: 공개 인증서를 이 PC의 '신뢰할 수 있는 사람'에 등록한다.
  같은 이름의 인증서가 이미 있으면 새로 만들지 않고 재사용한다.
#>
param([string]$Out = "dev.pfx", [string]$Password = "dev")
$ErrorActionPreference = "Stop"
$Subject = "CN=ClaudeSessionKeeperDev"

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
  [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw "관리자 권한 PowerShell에서 실행하세요 (LocalMachine 인증서 저장소에 쓰기 때문)." }

$cert = Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.Subject -eq $Subject -and $_.HasPrivateKey } |
  Sort-Object NotAfter -Descending | Select-Object -First 1
if ($cert) {
  Write-Host "기존 인증서 재사용: $($cert.Thumbprint)"
} else {
  $cert = New-SelfSignedCertificate -Type Custom -Subject $Subject `
    -KeyUsage DigitalSignature -FriendlyName "Session Keeper for Claude Code Dev" `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")
  Write-Host "새 인증서 생성: $($cert.Thumbprint)"
}

$pwd = ConvertTo-SecureString $Password -Force -AsPlainText
Export-PfxCertificate -Cert $cert -FilePath $Out -Password $pwd | Out-Null

# 신뢰 목록에는 개인 키 없이 공개 인증서만 넣는다
$cer = [IO.Path]::ChangeExtension($Out, ".cer")
Export-Certificate -Cert $cert -FilePath $cer | Out-Null
Import-Certificate -FilePath $cer -CertStoreLocation "Cert:\LocalMachine\TrustedPeople" | Out-Null
Write-Host "완료: $Out 서명용, $cer 공개 인증서 ($Subject). TrustedPeople 등록됨."
