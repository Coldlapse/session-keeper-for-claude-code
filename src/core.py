"""Session Keeper for Claude Code — 핵심 로직 (Windows 전용).

- 실행 중인 Claude Code CLI 세션(claude / node cli.js) 탐지 + 세션 ID 해석
- Claude Desktop 창 위치/상태 수집
- 스냅샷 저장/불러오기, 복원(Windows Terminal 탭 또는 개별 콘솔 창)
- Claude Code SessionStart 훅 설치/제거, 시작프로그램 등록, 재부팅 예약
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import psutil

from paths import APP_NAME, IS_PACKAGED, data_dir

IS_WIN = sys.platform == "win32"
if IS_WIN:  # pragma: no cover - Windows 전용
    import win32con
    import win32gui
    import win32process
    import winreg

DATA_DIR = data_dir()
SNAP_DIR = DATA_DIR / "snapshots"
LIVE_DIR = DATA_DIR / "live"          # 훅이 기록하는 PID → 세션 매핑
CONFIG_PATH = DATA_DIR / "config.json"
STATE_PATH = DATA_DIR / "state.json"
AUTOSAVE_FILE = "_autosave.json"

CLAUDE_HOME = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_HOME / "projects"
SETTINGS_PATH = CLAUDE_HOME / "settings.json"
FROZEN = getattr(sys, "frozen", False)          # PyInstaller exe 여부
APP_DIR = Path(sys.executable).parent if FROZEN else Path(__file__).parent
HOOK_SCRIPT = APP_DIR / "csk_session_hook.py"
HOOK_EXE = APP_DIR / "csk-hook.exe"
HOOK_MARKERS = ("csk_session_hook", "csk-hook")

SHELLS = {"pwsh.exe", "powershell.exe", "cmd.exe", "bash.exe", "nu.exe"}
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
CREATE_NEW_CONSOLE = 0x00000010
CREATE_NO_WINDOW = 0x08000000

DEFAULT_CONFIG = {
    "autosave_minutes": 5,
    "terminal": "wt",              # "wt" = Windows Terminal 탭, "console" = 개별 창
    "shell": "pwsh",               # "pwsh" | "powershell"
    "claude_cmd": "claude",
    "extra_args": "",              # 복원 시 claude에 덧붙일 인자
    "restore_delay_sec": 20,       # 부팅 후 자동 복원까지 대기
    "restore_desktop": True,
    "desktop_launch": "",          # 비워두면 자동 탐지
    "start_minimized": True,
    "unexpected_reboot": "ask",    # 예고 없는 재부팅 뒤: "ask" 묻기 | "auto" 대기 후 자동 복원 | "off" 아무것도 안 함
}

UNEXPECTED_REBOOT_MODES = ("ask", "auto", "off")

Log = Callable[[str], None]


# ───────────────────────── 공통 유틸 ─────────────────────────
def ensure_dirs() -> None:
    for d in (DATA_DIR, SNAP_DIR, LIVE_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


LOG_PATH = DATA_DIR / "app.log"
LOG_MAX_BYTES = 1_000_000


def append_log_file(msg: str, path: Path | None = None) -> None:
    """로그 탭과 같은 내용을 파일에도 남긴다(재부팅 뒤 자동 복원을 사후에 확인하려고).
    1MB를 넘으면 app.log.1 하나만 남기고 새로 쓴다. 실패해도 앱 동작에는 영향을 주지 않는다."""
    path = path or LOG_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > LOG_MAX_BYTES:
            os.replace(path, path.with_name(path.name + ".1"))
        with path.open("a", encoding="utf-8") as f:
            f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg + "\n")
    except OSError:
        pass


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    saved = _read_json(CONFIG_PATH, {})
    # 1.0.0 이전 설정 이전: ask_after_unexpected_reboot(bool) → unexpected_reboot
    if "unexpected_reboot" not in saved and "ask_after_unexpected_reboot" in saved:
        saved["unexpected_reboot"] = "ask" if saved["ask_after_unexpected_reboot"] else "off"
    saved.pop("ask_after_unexpected_reboot", None)
    cfg.update(saved)
    if cfg["unexpected_reboot"] not in UNEXPECTED_REBOOT_MODES:
        cfg["unexpected_reboot"] = "ask"
    return cfg


def save_config(cfg: dict) -> None:
    _write_json(CONFIG_PATH, cfg)


def load_state() -> dict:
    return _read_json(STATE_PATH, {})


def save_state(state: dict) -> None:
    _write_json(STATE_PATH, state)


def _safe(fn, default=None):
    try:
        return fn()
    except (psutil.Error, OSError):
        return default


def _name(p) -> str:
    return (_safe(p.name, "") or "").lower()


def _ancestors(p, limit: int = 12) -> list:
    out, cur = [], p
    for _ in range(limit):
        cur = _safe(cur.parent)
        if cur is None:
            break
        out.append(cur)
    return out


# ───────────────────────── 데이터 모델 ─────────────────────────
@dataclass
class CodeSession:
    pid: int
    cwd: str
    session_id: str | None
    id_source: str      # hook | cmdline | guess | none
    title: str
    shell: str          # pwsh.exe / powershell.exe / cmd.exe ...
    host: str           # wt | console
    started: float


@dataclass
class DesktopWindow:
    hwnd: int
    title: str
    rect: list          # 일반 상태 좌표 [left, top, right, bottom]
    show: str           # normal | maximized | minimized


# ───────────────────────── 프로세스 분류 ─────────────────────────
def is_code_cli(p) -> bool:
    """Claude Code CLI 프로세스인지 (Claude Desktop과 구분)."""
    name = _name(p)
    if name == "node.exe":
        cmd = " ".join(_safe(p.cmdline, []) or []).lower()
        return "claude-code" in cmd
    if name == "claude.exe":
        exe = (_safe(p.exe, "") or "").lower()
        if "anthropicclaude" in exe or "windowsapps" in exe:
            return False                       # Desktop 설치 경로
        if any(a.startswith("--type=") for a in (_safe(p.cmdline, []) or [])):
            return False                       # Electron 보조 프로세스
        parent = _safe(p.parent)
        return (parent is not None and _name(parent) in SHELLS) or "\\.local\\bin\\" in exe
    return False


def is_desktop_embedded_cli(exe: str) -> bool:
    """Claude Desktop이 내장 실행하는 Claude Code (…\\Claude-Data\\…\\claude-code\\<ver>\\…\\claude.exe).
    Desktop도, 복원할 터미널 세션도 아니다. Desktop 실행 경로로 잘못 고르지 않도록 따로 거른다."""
    return "\\claude-code\\" in exe.lower()


def is_desktop_proc(p) -> bool:
    if _name(p) != "claude.exe" or is_code_cli(p):
        return False
    return not is_desktop_embedded_cli(_safe(p.exe, "") or "")


# ───────────────────────── 세션 ID 해석 ─────────────────────────
def project_dir_for(cwd: str) -> Path | None:
    enc = re.sub(r"[^A-Za-z0-9]", "-", cwd)
    d = PROJECTS_DIR / enc
    if d.is_dir():
        return d
    if PROJECTS_DIR.is_dir():                  # 드라이브 문자 대소문자 차이 대비
        for c in PROJECTS_DIR.iterdir():
            if c.name.lower() == enc.lower():
                return c
    return None


def transcript_path(cwd: str, session_id: str) -> Path | None:
    d = project_dir_for(cwd)
    if d:
        p = d / f"{session_id}.jsonl"
        if p.exists():
            return p
    # 폴더명 인코딩이 예상과 다를 때(긴 경로 등) 대비: 세션 ID 파일명으로 전체 검색
    if PROJECTS_DIR.is_dir():
        for p in PROJECTS_DIR.glob(f"*/{session_id}.jsonl"):
            return p
    return None


def project_has_history(cwd: str) -> bool:
    """이 폴더에서 --continue로 이어갈 대화 기록(jsonl)이 하나라도 있는지."""
    d = project_dir_for(cwd) if cwd else None
    return bool(d) and any(UUID_RE.fullmatch(f.stem) for f in d.glob("*.jsonl"))


def resume_mode(s: dict) -> str:
    """복원 방식 결정 — 복원 시점의 디스크 상태 기준.

    resume   : 세션 ID가 있고 그 대화 기록이 존재 → claude --resume <id>
    continue : ID는 모르지만 폴더에 대화 기록이 있음 → claude --continue (가장 최근 대화)
    new      : 대화 기록이 없음(메시지를 한 번도 안 보낸 세션, 정리된 세션) → claude
               ID가 있는데 기록이 없으면 --continue는 다른(옛) 대화를 열게 되므로 new로 처리
    """
    sid = s.get("session_id")
    cwd = s.get("cwd") or ""
    if sid:
        return "resume" if transcript_path(cwd, sid) else "new"
    return "continue" if project_has_history(cwd) else "new"


RESUME_LABEL = {"resume": "", "continue": "(--continue: 폴더의 최근 대화)",
                "new": "(새로 시작: 저장된 대화 없음)"}


_title_cache: dict[tuple[str, float], str] = {}


def session_title(path: Path | None) -> str:
    """요약 또는 첫 사용자 메시지로 세션 제목 만들기."""
    if not path or not path.exists():
        return ""
    key = (str(path), path.stat().st_mtime)
    if key in _title_cache:
        return _title_cache[key]
    summary, first_user = "", ""
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i > 400:
                    break
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("type") == "summary" and rec.get("summary"):
                    summary = rec["summary"]
                if not first_user and rec.get("type") == "user" and not rec.get("isMeta"):
                    content = (rec.get("message") or {}).get("content")
                    if isinstance(content, list):
                        content = " ".join(c.get("text", "") for c in content
                                           if isinstance(c, dict) and c.get("type") == "text")
                    if isinstance(content, str) and content.strip() and not content.lstrip().startswith("<"):
                        first_user = content.strip()
    except OSError:
        pass
    title = " ".join((summary or first_user).split())[:80]
    _title_cache[key] = title
    return title


def _session_from_cmdline(cmd: list[str]) -> str | None:
    for i, a in enumerate(cmd):
        if a in ("--resume", "-r", "--session-id") and i + 1 < len(cmd) and UUID_RE.fullmatch(cmd[i + 1]):
            return cmd[i + 1]
        if a.startswith(("--resume=", "--session-id=")):
            v = a.split("=", 1)[1]
            if UUID_RE.fullmatch(v):
                return v
    return None


def _hook_record(pid: int, started: float) -> dict | None:
    rec = _read_json(LIVE_DIR / f"{pid}.json", None)
    if rec and rec.get("ts", 0) >= started - 5:   # PID 재사용으로 남은 옛 기록 배제
        return rec
    return None


def prune_live_records() -> None:
    if not LIVE_DIR.is_dir():
        return
    for f in LIVE_DIR.glob("*.json"):
        try:
            if not psutil.pid_exists(int(f.stem)):
                f.unlink()
        except (ValueError, OSError):
            pass


# ───────────────────────── 탐지 ─────────────────────────
def list_code_sessions() -> list[CodeSession]:
    procs = [p for p in psutil.process_iter(["name"]) if _name(p) in ("claude.exe", "node.exe")]
    cli = [p for p in procs if is_code_cli(p)]
    cli_pids = {p.pid for p in cli}
    # 다른 claude CLI의 자식(중첩)은 제외
    top = [p for p in cli if not any(a.pid in cli_pids for a in _ancestors(p))]

    sessions: list[CodeSession] = []
    for p in top:
        anc = _ancestors(p)
        names = [_name(a) for a in anc]
        shell = next((n for n in names if n in ("pwsh.exe", "powershell.exe")),
                     next((n for n in names if n in SHELLS), "pwsh.exe"))
        host = "wt" if "windowsterminal.exe" in names else "console"
        started = _safe(p.create_time, time.time())
        cwd = _safe(p.cwd, "") or ""
        sid, src = None, "none"
        rec = _hook_record(p.pid, started)
        if rec:
            sid, src = rec.get("session_id"), "hook"
            cwd = rec.get("cwd") or cwd
        else:
            sid = _session_from_cmdline(_safe(p.cmdline, []) or [])
            if sid:
                src = "cmdline"
        sessions.append(CodeSession(p.pid, cwd, sid, src, "", shell, host, started))

    _guess_missing_ids(sessions)
    for s in sessions:
        if s.session_id:
            s.title = session_title(transcript_path(s.cwd, s.session_id))
    return sessions


def _guess_missing_ids(sessions: list[CodeSession]) -> None:
    """훅 기록이 없는 세션은 같은 폴더의 최근 수정 transcript로 추정."""
    claimed = {s.session_id for s in sessions if s.session_id}
    by_cwd: dict[str, list[CodeSession]] = {}
    for s in sessions:
        if not s.session_id and s.cwd:
            by_cwd.setdefault(s.cwd.lower(), []).append(s)
    for group in by_cwd.values():
        d = project_dir_for(group[0].cwd)
        if not d:
            continue
        earliest = min(s.started for s in group) - 60
        files = sorted(
            (f for f in d.glob("*.jsonl") if UUID_RE.fullmatch(f.stem)
             and f.stem not in claimed and f.stat().st_mtime >= earliest),
            key=lambda f: f.stat().st_mtime, reverse=True)
        # 최근 시작한 프로세스 ↔ 최근 수정 파일 순서로 짝짓기 (정확하지 않을 수 있음)
        for s, f in zip(sorted(group, key=lambda s: s.started, reverse=True), files):
            s.session_id, s.id_source = f.stem, "guess"
            claimed.add(f.stem)


def desktop_processes() -> list:
    return [p for p in psutil.process_iter(["name"]) if is_desktop_proc(p)]


def desktop_main_exe(procs: list) -> str:
    for p in procs:
        if not any(a.startswith("--type=") for a in (_safe(p.cmdline, []) or [])):
            return _safe(p.exe, "") or ""
    return ""


_SHOW = {1: "normal", 2: "minimized", 3: "maximized"}
_SHOW_REV = {"normal": 1, "minimized": 2, "maximized": 3}


def list_desktop_windows(pids: set[int]) -> list[DesktopWindow]:
    if not IS_WIN or not pids:
        return []
    out: list[DesktopWindow] = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd) or win32gui.GetWindow(hwnd, win32con.GW_OWNER):
            return True
        if win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOOLWINDOW:
            return True
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return True
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid in pids:
            pl = win32gui.GetWindowPlacement(hwnd)
            out.append(DesktopWindow(hwnd, title, list(pl[4]), _SHOW.get(pl[1], "normal")))
        return True

    win32gui.EnumWindows(cb, None)
    return out


# ───────────────────────── 스냅샷 ─────────────────────────
def take_snapshot(name: str = "") -> dict:
    sessions = list_code_sessions()
    dprocs = desktop_processes()
    windows = list_desktop_windows({p.pid for p in dprocs})
    return {
        "version": 1,
        "name": name or time.strftime("%Y-%m-%d %H:%M:%S"),
        "created": time.time(),
        "boot_time": psutil.boot_time(),
        "sessions": [asdict(s) for s in sessions],
        "desktop": {
            "running": bool(dprocs),
            "exe": desktop_main_exe(dprocs),
            "windows": [asdict(w) for w in windows],
        },
    }


def save_snapshot(snap: dict, filename: str | None = None) -> Path:
    ensure_dirs()
    if not filename:
        filename = time.strftime("snap_%Y%m%d_%H%M%S.json", time.localtime(snap["created"]))
    path = SNAP_DIR / filename
    _write_json(path, snap)
    return path


def list_snapshots() -> list[tuple[Path, dict]]:
    ensure_dirs()
    items = []
    for f in SNAP_DIR.glob("*.json"):
        data = _read_json(f, None)
        if data:
            items.append((f, data))
    items.sort(key=lambda t: t[1].get("created", 0), reverse=True)
    return items


def snapshot_summary(snap: dict) -> str:
    n_s = len(snap.get("sessions", []))
    d = snap.get("desktop", {})
    n_w = len(d.get("windows", [])) if d.get("running") else 0
    desk = f"Desktop 창 {n_w}" if d.get("running") else "Desktop 꺼짐"
    return f"Code 세션 {n_s} · {desk}"


def snapshot_is_empty(snap: dict) -> bool:
    return not snap.get("sessions") and not snap.get("desktop", {}).get("running")


# ───────────────────────── 복원 ─────────────────────────
def _shell_exe(cfg: dict) -> str:
    pref = "pwsh.exe" if cfg.get("shell") == "pwsh" else "powershell.exe"
    return pref if shutil.which(pref) else "powershell.exe"


def resume_command(cfg: dict, s: dict) -> str:
    base = cfg.get("claude_cmd", "claude")
    extra = (cfg.get("extra_args") or "").strip()
    mode = resume_mode(s)
    if mode == "resume":
        cmd = f"{base} --resume {s['session_id']}"
    elif mode == "continue":
        cmd = f"{base} --continue"
    else:
        cmd = base
    return f"{cmd} {extra}".strip()


def restore_sessions(sessions: list[dict], cfg: dict, log: Log = print) -> int:
    running = {s.session_id for s in list_code_sessions() if s.session_id}
    todo = []
    for s in sessions:
        if s.get("session_id") and s["session_id"] in running:
            log(f"건너뜀(이미 실행 중): {s['session_id'][:8]} {s.get('cwd')}")
            continue
        if not s.get("cwd") or not Path(s["cwd"]).is_dir():
            log(f"건너뜀(폴더 없음): {s.get('cwd')}")
            continue
        todo.append(s)
    if not todo:
        return 0

    shell = _shell_exe(cfg)
    use_wt = cfg.get("terminal") == "wt" and shutil.which("wt.exe")
    if use_wt:
        args = ["wt.exe", "-w", "new"]
        for i, s in enumerate(todo):
            if i:
                args.append(";")
            title = (Path(s["cwd"]).name + " · " + (s.get("title") or "")[:30]).replace(";", ",")
            args += ["new-tab", "--title", title, "--suppressApplicationTitle", "-d", s["cwd"],
                     shell, "-NoExit", "-Command", resume_command(cfg, s)]
        subprocess.Popen(args)
        for s in todo:
            log(f"복원(WT 탭): {s['cwd']} → {resume_command(cfg, s)}")
    else:
        if cfg.get("terminal") == "wt":
            log("wt.exe를 찾지 못해 개별 콘솔 창으로 복원합니다.")
        for s in todo:
            subprocess.Popen([shell, "-NoExit", "-Command", resume_command(cfg, s)],
                             cwd=s["cwd"], creationflags=CREATE_NEW_CONSOLE)
            log(f"복원(콘솔): {s['cwd']} → {resume_command(cfg, s)}")
            time.sleep(0.4)
    return len(todo)


def _desktop_launch_target(desk: dict, cfg: dict) -> str:
    if cfg.get("desktop_launch"):
        return cfg["desktop_launch"]
    exe = desk.get("exe") or ""
    if exe and "windowsapps" not in exe.lower():
        p = Path(exe)
        if p.parent.name.lower().startswith("app-"):       # Squirrel: 버전 폴더 대신 런처 사용
            stub = p.parent.parent / "claude.exe"
            if stub.exists():
                return str(stub)
        if p.exists():
            return str(p)
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "AnthropicClaude" / "claude.exe"
    return str(local) if local.exists() else "claude://"


def pair_windows(current: list[DesktopWindow], saved: list[dict]) -> list[tuple[DesktopWindow, dict]]:
    """저장된 창 배치를 지금 열린 창에 짝짓는다. 제목이 같은 창끼리 먼저, 남은 것은 열거 순서대로.
    Desktop은 재실행 시 창 위치는 되살리지만 어느 대화가 어느 자리에 오는지는 섞는다(2026-11-03 실기)."""
    pairs, left_cur, left_saved = [], list(current), []
    for w in saved:
        match = next((c for c in left_cur if c.title == w.get("title")), None)
        if match:
            pairs.append((match, w))
            left_cur.remove(match)
        else:
            left_saved.append(w)
    pairs += list(zip(left_cur, left_saved))
    return pairs


def restore_desktop(desk: dict, cfg: dict, log: Log = print) -> None:
    if not desk.get("running"):
        return
    procs = desktop_processes()
    if not procs:
        target = _desktop_launch_target(desk, cfg)
        log(f"Claude Desktop 실행: {target}")
        try:
            os.startfile(target)  # type: ignore[attr-defined]
        except OSError as e:
            log(f"Desktop 실행 실패: {e} (설정에서 실행 경로를 지정하세요)")
            return
    saved = desk.get("windows", [])
    if not saved:
        return
    windows: list[DesktopWindow] = []
    for _ in range(60):                       # 최대 30초 대기
        windows = list_desktop_windows({p.pid for p in desktop_processes()})
        if windows:
            break
        time.sleep(0.5)
    time.sleep(1.0)                           # 첫 렌더 후 앱이 스스로 위치를 잡는 것을 기다림
    windows = list_desktop_windows({p.pid for p in desktop_processes()}) or windows
    for cur, w in pair_windows(windows, saved):
        try:
            win32gui.SetWindowPlacement(
                cur.hwnd, (0, _SHOW_REV.get(w["show"], 1), (-1, -1), (-1, -1), tuple(w["rect"])))
        except Exception as e:  # noqa: BLE001
            log(f"창 배치 실패: {e}")
    log(f"Desktop 창 배치 복원: {min(len(windows), len(saved))}/{len(saved)}")
    if len(saved) > len(windows):
        log("※ 저장 당시보다 창이 적습니다. 추가 창은 직접 열어야 합니다.")


def restore_snapshot(snap: dict, cfg: dict, log: Log = print,
                     sessions: list[dict] | None = None, desktop: bool | None = None) -> None:
    sel = snap.get("sessions", []) if sessions is None else sessions
    do_desk = cfg.get("restore_desktop", True) if desktop is None else desktop
    if do_desk:
        restore_desktop(snap.get("desktop", {}), cfg, log)
    n = restore_sessions(sel, cfg, log)
    log(f"복원 완료: Code 세션 {n}개")


# ───────────────────────── 훅 (세션 ID 정확도) ─────────────────────────
def hook_command() -> str:
    if IS_PACKAGED:
        # MSIX: 버전마다 바뀌는 WindowsApps 경로 대신 실행 별칭(고정 경로, 패키지 컨텍스트) 사용
        alias = Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "WindowsApps" / "csk-hook.exe"
        return f'"{alias.as_posix()}"'
    if FROZEN:
        return f'"{HOOK_EXE.as_posix()}"'
    py = Path(sys.executable)
    if py.name.lower() == "pythonw.exe":
        py = py.with_name("python.exe")       # 훅은 stdin이 필요
    return f'"{py.as_posix()}" "{HOOK_SCRIPT.as_posix()}"'


def _settings() -> dict:
    return _read_json(SETTINGS_PATH, {})


def _is_ours(cmd: str) -> bool:
    return any(m in cmd for m in HOOK_MARKERS)


def hook_status() -> str:
    """'none' = 미설치, 'ok' = 현재 위치로 설치됨, 'stale' = 다른 경로(폴더 이동 등)로 설치됨."""
    cmds = [h.get("command", "") for g in _settings().get("hooks", {}).get("SessionStart", [])
            for h in g.get("hooks", []) if _is_ours(h.get("command", ""))]
    if not cmds:
        return "none"
    return "ok" if hook_command() in cmds else "stale"


def hook_installed() -> bool:
    return hook_status() != "none"


def _strip_hook(settings: dict) -> dict:
    groups = settings.get("hooks", {}).get("SessionStart", [])
    kept = []
    for g in groups:
        hs = [h for h in g.get("hooks", []) if not _is_ours(h.get("command", ""))]
        if hs:
            kept.append({**g, "hooks": hs})
    if "hooks" in settings:
        if kept:
            settings["hooks"]["SessionStart"] = kept
        else:
            settings["hooks"].pop("SessionStart", None)
        if not settings["hooks"]:
            settings.pop("hooks")
    return settings


def install_hook() -> None:
    # 백업은 우리 훅이 없을 때만: 경로 갱신(재설치) 때 백업하면 훅 넣기 전 원본 백업이 덮어써진다(2026-11-03 실기)
    if SETTINGS_PATH.exists() and not hook_installed():
        shutil.copy2(SETTINGS_PATH, SETTINGS_PATH.with_name("settings.json.csk-bak"))
    s = _strip_hook(_settings())
    s.setdefault("hooks", {}).setdefault("SessionStart", []).append(
        {"hooks": [{"type": "command", "command": hook_command(), "timeout": 10}]})
    _write_json(SETTINGS_PATH, s)


def uninstall_hook() -> None:
    if SETTINGS_PATH.exists():
        _write_json(SETTINGS_PATH, _strip_hook(_settings()))


# ───────────────────────── 시작프로그램 / 재부팅 ─────────────────────────
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def startup_managed_by_os() -> bool:
    """MSIX는 매니페스트의 startupTask로 자동 실행되고, Run 키 쓰기는 가상화되어 효과가 없다."""
    return IS_PACKAGED


def startup_command() -> str:
    if FROZEN:
        return f'"{APP_DIR / "ClaudeSessionKeeper.exe"}" --startup'
    py = Path(sys.executable)
    pyw = py.with_name("pythonw.exe")
    app = APP_DIR / "app.py"
    return f'"{pyw if pyw.exists() else py}" "{app}" --startup'


def is_startup_enabled() -> bool:
    if startup_managed_by_os():
        return True
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_startup(enabled: bool) -> None:
    if startup_managed_by_os():
        return
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except OSError:
                pass


def mark_pending_restore(snapshot_file: Path) -> None:
    st = load_state()
    st["pending_restore"] = snapshot_file.name
    st["pending_set_at"] = time.time()
    save_state(st)


def same_boot(a: float | None, b: float) -> bool:
    """psutil.boot_time()은 Windows에서 '현재 시각 - 가동 시간'으로 계산돼 호출마다 끝자리가 흔들린다
    (실측: 1793708205.108743 vs 1793708205.1087432). ==로 비교하면 같은 부팅을 다른 부팅으로 본다."""
    return a is not None and abs(a - b) < 5


def boot_action(cfg: dict, boot: float) -> tuple[str, dict | None]:
    """앱 시작 시 할 일을 정하고 state.json을 갱신한다.

    ("pending", 스냅샷) : 계획된 재부팅을 거쳤음 → 대기 후 자동 복원
    ("ask", 자동저장)   : 예고 없는 재부팅으로 보임 → 복원 여부를 물음 (설정 unexpected_reboot="ask")
    ("auto", 자동저장)  : 예고 없는 재부팅으로 보임 → 묻지 않고 대기 후 자동 복원 ("auto")
                          "off"면 예고 없는 재부팅은 무시한다. 앱 버튼으로 한 계획된 재부팅은 설정과 무관하게 복원한다.
    ("none", None)      : 할 일 없음(재부팅 전 앱만 다시 켬, 이번 부팅에서 이미 처리함 등)

    어느 쪽이든 이번 부팅을 처리했으면 asked_boot를 기록한다. 계획된 복원 뒤 같은 부팅에서 앱을 다시 켰을 때
    재부팅 전 자동저장을 '예기치 않은 재부팅'으로 보고 또 묻던 문제가 있었다(2026-11-03 실기에서 발견).
    """
    st = load_state()
    pending = st.get("pending_restore")
    if pending:
        if st.get("pending_set_at", 0) >= boot:
            return "none", None                      # 재부팅 전에 앱만 다시 켬: 대기 유지
        st["asked_boot"] = boot
        save_state(st)
        snap = _read_json(SNAP_DIR / pending, None)
        if snap:
            return "pending", snap                   # pending은 복원 실행/취소 때 지운다(도중 종료 대비)
        clear_pending_restore()
        return "none", None

    mode = cfg.get("unexpected_reboot", "ask")
    if mode not in ("ask", "auto") or same_boot(st.get("asked_boot"), boot):
        return "none", None
    auto = _read_json(SNAP_DIR / AUTOSAVE_FILE, None)
    if auto and auto.get("created", 0) < boot and not snapshot_is_empty(auto):
        st["asked_boot"] = boot
        save_state(st)
        return mode, auto
    return "none", None


def clear_pending_restore() -> None:
    st = load_state()
    st.pop("pending_restore", None)
    st.pop("pending_set_at", None)
    save_state(st)


def schedule_power(kind: str, delay: int = 10) -> None:
    flag = "/r" if kind == "restart" else "/s"
    subprocess.run(["shutdown", flag, "/t", str(delay)], creationflags=CREATE_NO_WINDOW, check=False)


def cancel_power() -> None:
    subprocess.run(["shutdown", "/a"], creationflags=CREATE_NO_WINDOW, check=False)
