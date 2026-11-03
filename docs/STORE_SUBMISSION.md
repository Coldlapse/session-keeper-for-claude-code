# Microsoft Store 제출 가이드

방식: **MSIX 패키지 제출**입니다. Store가 패키지에 서명하므로 코드 서명 인증서를 따로 살 필요가 없습니다.
MSI/EXE 설치 파일을 제출하는 방식도 있지만, 그쪽은 인증서 서명과 버전별 고정 HTTPS URL 호스팅이 필요해서 쓰지 않습니다.

## 0. 제출 전 결정
- [ ] 앱 이름: 상표 검토. 아래 1단계에서 예약할 이름입니다.
- [ ] 개인정보 처리방침 공개 URL. 예: GitHub에 올린 `docs/PRIVACY.md` 링크
- [ ] 실기 테스트(포터블, MSIX) 통과

## 1. Partner Center
1. Partner Center 개발자 계정을 등록합니다. 개인 계정으로 충분하고, 등록 비용과 정책은 등록 화면에서 확인하세요.
2. **앱 → 새 제품 → MSIX 또는 PWA 앱** → 이름 예약
3. **제품 관리 → 제품 ID**에 나오는 다음 세 값을 `packaging/msix/identity.json`에 그대로 복사합니다.
   - `Package/Identity/Name` → `IdentityName`
   - `Package/Identity/Publisher` → `Publisher` (`CN=...` 형식 그대로)
   - `Package/Properties/PublisherDisplayName` → `PublisherDisplayName`
   - `DisplayName`은 예약한 이름과 정확히 같아야 합니다.
4. 커밋한 뒤 `v<버전>` 태그를 푸시하면 CI 아티팩트에 `ClaudeSessionKeeper-<ver>.0-x64.msix`가 생깁니다. 로컬에서 `.\scripts\build.ps1 -Msix`로 만들어도 됩니다.

## 2. 제출 항목
| 항목 | 값 |
|---|---|
| 가격 | 무료 |
| 카테고리 | 개발자 도구 (보조: 생산성) |
| 개인정보 처리방침 URL | §0에서 정한 URL |
| 연령 등급 | 설문 응답: 사용자 간 소통 없음, 개인정보 공유 없음, 구매 없음 |
| 패키지 | 위 `.msix` 업로드 |
| 장치 패밀리 | Windows 10/11 Desktop만 |

### 제한된 기능 사유 (runFullTrust)
Store가 사유를 물으면 다음 내용을 입력합니다:

> This is a Win32 desktop app (Python/Qt) packaged with MSIX. It needs runFullTrust to enumerate local processes and top-level windows (to find Claude Code CLI and Claude Desktop), restore window placement, launch Windows Terminal/PowerShell to resume sessions, and run shutdown.exe when the user explicitly chooses "snapshot and restart". No network access.

### 인증 참고 사항 (Notes for certification)
> The app works without any other software installed: lists will simply be empty. To exercise it: open the app → "스냅샷 저장" (Save snapshot) → Snapshots tab shows the entry. The "스냅샷 → 재부팅" button schedules a restart only after a confirmation dialog; "재부팅/종료 취소" cancels it. The optional "훅 설치" button edits %USERPROFILE%\.claude\settings.json (a config file of the third-party Claude Code CLI) only on user click, after backing it up. The app is unofficial and not affiliated with Anthropic.

## 3. 스토어 목록 (ko-KR)
**짧은 설명**
Claude Code 세션과 Claude Desktop 창을 저장하고 재부팅 후 그대로 복원하는 비공식 도구

**설명**
재부팅할 때마다 Claude Code 세션을 하나씩 다시 열고 계셨나요? Session Keeper for Claude Code는 실행 중인 Claude Code 세션(작업 폴더, 세션 ID)과 Claude Desktop 창 배치를 저장해 두었다가, 부팅 후 버튼 하나로 또는 자동으로 되살립니다.

• 실행 중인 Claude Code 세션과 Claude Desktop 창 한눈에 보기
• 스냅샷 후 재부팅 → 로그인하면 자동 복원
• 5분 주기 자동저장, 예기치 않은 재부팅 뒤 복원(묻기·자동·끄기 선택)
• 원하는 세션만 골라 복원, Windows Terminal 탭으로 묶어 열기
• 선택 사항: Claude Code 훅으로 세션을 정확히 식별

네트워크를 사용하지 않으며 어떤 데이터도 수집하지 않습니다.
본 앱은 Anthropic과 관련 없는 비공식 도구입니다. Claude는 Anthropic의 상표입니다.

**기능 목록**: 세션 스냅샷 / 재부팅 후 자동 복원 / 자동저장 / 선택 복원 / Windows Terminal 탭 복원
**키워드**: Claude Code, 세션 복원, 재부팅, 터미널, 개발자 도구, Windows Terminal, 스냅샷

## 4. 스토어 목록 (en-US)
**Short description**: Unofficial tool to snapshot Claude Code sessions and Claude Desktop windows and restore them after a reboot.

**Description**: Stop reopening every Claude Code session by hand after a restart. Session Keeper for Claude Code records running Claude Code CLI sessions (folder + session ID) and Claude Desktop window placement, then restores them after you sign back in — automatically or with one click. Autosave covers unexpected reboots; pick individual sessions to restore; reopen them as Windows Terminal tabs. No network access, no data collection. Not affiliated with Anthropic; Claude is a trademark of Anthropic.

## 5. 스크린샷 (최소 1장, 권장 4장, 1366×768 이상)
1. 실행 중 탭: 세션 2~3개 + Desktop 창
2. 스냅샷 탭: 체크박스로 선택 복원
3. 재부팅 확인 대화상자
4. 설정 탭 (훅 설치됨)

화면에 개인 폴더명이나 대화 제목이 나오지 않도록 데모용 폴더와 세션으로 찍으세요.

## 6. 업데이트 제출
`src/version.py`를 올림 → 태그 푸시 → CI 아티팩트의 새 `.msix`를 **업데이트 제출**에 업로드합니다. 버전은 이전 제출보다 커야 합니다.
