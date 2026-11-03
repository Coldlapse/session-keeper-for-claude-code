# Session Keeper for Claude Code

> **비공식 도구**입니다. Anthropic과 제휴·보증 관계가 없습니다. "Claude", "Claude Code"는 Anthropic의 상표입니다.

켜져 있는 **Claude Code** 세션(터미널의 `claude`)과 **Claude Desktop** 창을 한눈에 보고, 재부팅 전 상태를 스냅샷으로 저장했다가 부팅 후 그대로 되살리는 Windows 트레이 앱입니다.

## 기능

- **실행 중 보기**: Claude Code 세션별 작업 폴더, 세션 ID, 첫 질문(제목), 셸과 터미널 종류. Claude Desktop 창의 위치와 상태.
- **스냅샷 → 재부팅/종료**: 현재 상태를 저장하고 재부팅합니다. 다음 로그인 때 자동으로 복원합니다.
  - Claude Code 세션은 각 폴더에서 `claude --resume <세션ID>`로 다시 엽니다. Windows Terminal 탭으로 묶을 수도 있고, 개별 창으로 열 수도 있습니다.
  - Claude Desktop은 앱을 실행한 뒤 창 위치, 크기, 최대화 상태를 되돌립니다.
- **자동저장**: 기본 5분마다 저장합니다. Windows 업데이트처럼 예고 없이 재부팅되었을 때의 동작은 설정에서 고릅니다: 복원할지 묻기(기본), 묻지 않고 자동 복원, 아무것도 하지 않기(자동저장만 유지).
- **선택 복원**: 스냅샷에서 원하는 세션만 골라 복원합니다.
- **정확한 세션 매핑(선택)**: Claude Code의 `SessionStart` 훅을 설치하면, 같은 폴더에서 세션 여러 개를 돌려도 프로세스와 세션 ID를 정확히 짝지어 기록합니다.

## 설치

| 방법 | 설명 |
|---|---|
| Microsoft Store | (출시 후 링크) 자동 업데이트, 로그인 시 자동 실행 |
| 포터블 zip | [Releases](../../releases)에서 `ClaudeSessionKeeper-<버전>-win64-portable.zip` → 압축 풀고 `ClaudeSessionKeeper.exe` |

포터블 버전 참고:
- 서명되지 않은 exe라 SmartScreen이 뜨면 **추가 정보 → 실행**을 누르세요.
- `csk-hook.exe`와 `_internal` 폴더는 지우지 마세요.
- 폴더를 옮겨도 다음 실행 때 경로가 자동으로 갱신됩니다.

요구 사항: Windows 10 2004 이상 또는 Windows 11, x64

## 처음 설정

**설정** 탭에서:
1. **훅 설치**: `~/.claude/settings.json`에 SessionStart 훅을 추가합니다. 기존 파일은 `settings.json.csk-bak`으로 백업됩니다. 훅은 설치한 뒤 새로 시작하거나 재개한 세션부터 적용됩니다.
2. **Windows 시작 시 실행**: 포터블 버전에만 있는 설정입니다. 스토어 버전은 기본으로 켜져 있고, 작업 관리자의 시작 앱에서 끌 수 있습니다.

## 제거

앱을 지우기 **전에** 설정 탭에서 **훅 제거**를 누르세요. 앱을 먼저 지우면 `~/.claude/settings.json`에 훅이 남습니다. 이미 지웠다면 그 파일의 `hooks` → `SessionStart`에서 `csk-hook.exe` 항목을 직접 지우면 됩니다.

## 한계

- Claude Desktop **창 안에서 열려 있던 대화**는 외부에서 읽을 수 없어 복원하지 않습니다. 창 배치와 실행 여부만 복원합니다.
- 터미널 창의 화면 위치는 복원하지 않습니다.
- 스토어 버전은 Windows가 다른 스토어 앱들과 차례로 실행하므로, 로그인 뒤 앱이 켜지기까지 1~2분 걸릴 수 있습니다. 복원은 앱이 켜진 뒤 대기 시간(기본 20초)이 지나면 시작합니다.
- 응답을 생성하는 도중에 재부팅하면 그 응답은 끊깁니다. 대화 기록은 디스크에 남아 있어 `--resume`할 수 있습니다.
- 오래 쉬었던 대화는 Claude Code가 복원할 때 "Resume this conversation?"을 물을 수 있습니다. 탭마다 **Resume**을 고르면 이어집니다. 재부팅 직전까지 쓰던 대화는 보통 묻지 않습니다.

## 개인정보

네트워크 통신을 하지 않고, 아무것도 수집하지 않습니다. 자세한 내용은 [docs/PRIVACY.md](docs/PRIVACY.md)를 보세요.

## 개발

```powershell
pip install -r requirements.txt pytest
python -m pytest -q tests           # 단위 테스트
scripts\run_dev.bat                 # 소스 실행
.\scripts\build.ps1 [-Msix]         # exe(포터블 zip) [+ MSIX]
```

---

### English

Unofficial Windows tray app that lists running **Claude Code** CLI sessions and **Claude Desktop** windows, snapshots them, and restores them after a reboot (`claude --resume <id>` per folder, Desktop window placement). Includes autosave for unexpected reboots and an optional Claude Code `SessionStart` hook for exact PID↔session mapping. No network access, no telemetry. MIT licensed. Not affiliated with Anthropic.
