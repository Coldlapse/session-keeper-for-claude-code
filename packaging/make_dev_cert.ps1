<#
.SYNOPSIS
  MSIX 로컬 설치 테스트용 자체 서명 인증서 생성 (Store 제출에는 필요 없음).
  관리자 PowerShell에서 실행: 인증서를 '신뢰할 수 있는 사람'에 등록한다.
#>
param([string]$Out = "dev.pfx", [string]$Password = "dev")
$ErrorActionPreference = "Stop"
$cert = New-SelfSignedCertificate -Type Custom -Subject "CN=ClaudeSessionKeeperDev" `
  -KeyUsage DigitalSignature -FriendlyName "Session Keeper for Claude Code Dev" `
  -CertStoreLocation "Cert:\CurrentUser\My" `
  -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")
$pwd = ConvertTo-SecureString $Password -Force -AsPlainText
Export-PfxCertificate -Cert $cert -FilePath $Out -Password $pwd | Out-Null
Import-PfxCertificate -FilePath $Out -CertStoreLocation "Cert:\LocalMachine\TrustedPeople" -Password $pwd | Out-Null
Write-Host "생성: $Out (CN=ClaudeSessionKeeperDev) — TrustedPeople 등록 완료"
