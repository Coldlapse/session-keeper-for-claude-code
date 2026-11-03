# Microsoft Store submission guide

Method: **MSIX package submission.** The Store signs the package, so no code-signing certificate has to be bought.
Submitting an MSI/EXE installer is also possible, but that route needs a signed installer and a fixed HTTPS URL per version, so it isn't used here.

## 0. Before submitting
- [x] App name: "Session Keeper for Claude Code" (nominative use of the trademark). This is the name reserved in step 1.
- [x] Public privacy policy URL: https://sessionkeeper.coldlapse.dev/privacy.html
- [x] Hands-on tests of the portable build and the MSIX build

## 1. Partner Center
1. Open a developer account. Start at https://storedeveloper.microsoft.com → **Get started for free** → **Individual developer**.
   Individual registration has been free since September 2025. Other entry points (Partner Center directly, Visual Studio) may still show the old paid flow.
   You need a personal Microsoft account and a government-issued ID plus a selfie for identity verification. An Individual account can't be converted to a Company account later.
2. **Apps and games → New product → MSIX or PWA app** → reserve the name.
3. Copy these three values from **Product management → Product identity** into `packaging/msix/identity.json`, exactly as shown:
   - `Package/Identity/Name` → `IdentityName`
   - `Package/Identity/Publisher` → `Publisher` (keep the `CN=...` form)
   - `Package/Properties/PublisherDisplayName` → `PublisherDisplayName`
   - `DisplayName` must match the reserved name exactly.
4. Commit, then push a `v<version>` tag. CI produces `ClaudeSessionKeeper-<ver>.0-x64.msix` as a build artifact. `.\scripts\build.ps1 -Msix` builds the same file locally.

## 2. Submission fields
| Field | Value |
|---|---|
| Price | Free |
| Category | Developer tools (secondary: Productivity) |
| Privacy policy URL | https://sessionkeeper.coldlapse.dev/privacy.html |
| Website | https://sessionkeeper.coldlapse.dev |
| Support contact | https://github.com/Coldlapse/session-keeper-for-claude-code/issues |
| Age rating | Questionnaire: no user interaction, no personal data sharing, no purchases |
| Package | The `.msix` above |
| Device family | Windows 10/11 Desktop only |

### Restricted capability justification (runFullTrust)
If the Store asks why the package needs it:

> This is a Win32 desktop app (Python/Qt) packaged with MSIX. It needs runFullTrust to enumerate local processes and top-level windows (to find Claude Code CLI and Claude Desktop), restore window placement, launch Windows Terminal/PowerShell to resume sessions, and run shutdown.exe when the user explicitly chooses "snapshot and restart". No network access.

### Notes for certification
> The app works without any other software installed: lists will simply be empty. The UI is Korean. To exercise it: open the app → "스냅샷 저장" (Save snapshot) → the Snapshots tab ("스냅샷") shows the entry. The "스냅샷 → 재부팅" (Snapshot → Restart) button schedules a restart only after a confirmation dialog; "재부팅/종료 취소" cancels it. The optional "훅 설치" (Install hook) button edits %USERPROFILE%\.claude\settings.json (a config file of the third-party Claude Code CLI) only on user click, after backing it up; if the app was moved, it updates the path of the hook it installed earlier. The app is unofficial and not affiliated with Anthropic.

## 3. Store listing (ko-KR)
The listing text below is Korean on purpose: it is the copy for the Korean store page.

**Short description**
Claude Code 세션과 Claude Desktop 창을 저장하고 재부팅 후 그대로 복원하는 비공식 도구

**Description**
재부팅할 때마다 Claude Code 세션을 하나씩 다시 열고 계셨나요? Session Keeper for Claude Code는 실행 중인 Claude Code 세션(작업 폴더, 세션 ID)과 Claude Desktop 창 배치를 저장해 두었다가, 부팅 후 버튼 하나로 또는 자동으로 되살립니다.

• 실행 중인 Claude Code 세션과 Claude Desktop 창 한눈에 보기
• 스냅샷 후 재부팅 → 로그인하면 자동 복원
• 5분 주기 자동저장, 예기치 않은 재부팅 뒤 복원(묻기·자동·끄기 선택)
• 원하는 세션만 골라 복원, Windows Terminal 탭으로 묶어 열기
• 선택 사항: Claude Code 훅으로 세션을 정확히 식별

네트워크를 사용하지 않으며 어떤 데이터도 수집하지 않습니다.
본 앱은 Anthropic과 관련 없는 비공식 도구입니다. Claude는 Anthropic의 상표입니다.

**Features**: 세션 스냅샷 / 재부팅 후 자동 복원 / 자동저장 / 선택 복원 / Windows Terminal 탭 복원
**Keywords**: Claude Code, 세션 복원, 재부팅, 터미널, 개발자 도구, Windows Terminal, 스냅샷

## 4. Store listing (en-US)
**Short description**: Unofficial tool to snapshot Claude Code sessions and Claude Desktop windows and restore them after a reboot.

**Description**: Stop reopening every Claude Code session by hand after a restart. Session Keeper for Claude Code records running Claude Code CLI sessions (folder + session ID) and Claude Desktop window placement, then restores them after you sign back in, automatically or with one click. Autosave covers unexpected reboots; pick individual sessions to restore; reopen them as Windows Terminal tabs. The interface is currently in Korean. No network access, no data collection. Not affiliated with Anthropic; Claude is a trademark of Anthropic.

## 5. Screenshots (at least 1, 4 recommended, 1366×768 or larger)
1. Running tab: 2–3 sessions plus Desktop windows
2. Snapshots tab: selective restore with checkboxes
3. Restart confirmation dialog
4. Settings tab (hook installed)

Use demo folders and sessions so no personal folder names or conversation titles appear.

## 6. Submitting an update
Bump `src/version.py` → push a tag → upload the new `.msix` from the CI artifact as an **update submission**. The version must be higher than the previous submission.
