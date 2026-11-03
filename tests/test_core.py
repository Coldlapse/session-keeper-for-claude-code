import os
import time

import pytest

import core

UUID_A = "11111111-1111-4111-8111-111111111111"
UUID_B = "22222222-2222-4222-8222-222222222222"
UUID_C = "33333333-3333-4333-8333-333333333333"


def make_transcript(home, cwd, sid, mtime=None):
    d = core.PROJECTS_DIR / core.re.sub(r"[^A-Za-z0-9]", "-", cwd)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{sid}.jsonl"
    p.write_text('{"type":"user","message":{"content":"hi"}}\n', encoding="utf-8")
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


# ───────── 명령줄에서 세션 ID ─────────
@pytest.mark.parametrize("cmd, expected", [
    (["claude", "--resume", UUID_A], UUID_A),
    (["claude", "-r", UUID_A], UUID_A),
    (["claude", "--session-id", UUID_A], UUID_A),
    (["claude", f"--resume={UUID_A}"], UUID_A),
    (["claude", f"--session-id={UUID_A}"], UUID_A),
    (["claude", "--resume"], None),                 # 값 없음(대화 선택 화면)
    (["claude", "--resume", "not-a-uuid"], None),
    (["claude", "--continue"], None),
    (["node", "cli.js", "-r", UUID_B, "--verbose"], UUID_B),
])
def test_session_from_cmdline(cmd, expected):
    assert core._session_from_cmdline(cmd) == expected


# ───────── 복원 모드 ─────────
def test_resume_mode_with_history(fake_home):
    make_transcript(fake_home, r"C:\work\proj", UUID_A)
    assert core.resume_mode({"cwd": r"C:\work\proj", "session_id": UUID_A}) == "resume"


def test_resume_mode_id_without_history_is_new(fake_home):
    # 다른 대화가 폴더에 있어도 --continue로 보내지 않는다(옛 대화가 열리므로)
    make_transcript(fake_home, r"C:\work\proj", UUID_B)
    assert core.resume_mode({"cwd": r"C:\work\proj", "session_id": UUID_A}) == "new"


def test_resume_mode_no_id(fake_home):
    assert core.resume_mode({"cwd": r"C:\work\empty", "session_id": None}) == "new"
    make_transcript(fake_home, r"C:\work\proj", UUID_A)
    assert core.resume_mode({"cwd": r"C:\work\proj", "session_id": None}) == "continue"


def test_transcript_found_by_global_search(fake_home):
    # 폴더명 인코딩이 예상과 다르면 projects/*/<id>.jsonl 전체 검색으로 찾는다
    d = core.PROJECTS_DIR / "weird-name"
    d.mkdir()
    (d / f"{UUID_A}.jsonl").write_text("{}\n", encoding="utf-8")
    assert core.resume_mode({"cwd": r"C:\work\proj", "session_id": UUID_A}) == "resume"


def test_project_dir_case_insensitive(fake_home):
    make_transcript(fake_home, r"c:\Work\Proj", UUID_A)
    assert core.project_dir_for(r"C:\work\proj") is not None


def test_resume_command(fake_home):
    make_transcript(fake_home, r"C:\p", UUID_A)
    cfg = dict(core.DEFAULT_CONFIG, extra_args="--model opus")
    assert core.resume_command(cfg, {"cwd": r"C:\p", "session_id": UUID_A}) == \
        f"claude --resume {UUID_A} --model opus"
    assert core.resume_command(cfg, {"cwd": r"C:\none", "session_id": None}) == "claude --model opus"


# ───────── ID 추정 ─────────
def _sess(pid, cwd, started, sid=None):
    return core.CodeSession(pid, cwd, sid, "cmdline" if sid else "none", "", "pwsh.exe", "wt", started)


def test_guess_pairs_recent_process_with_recent_file(fake_home):
    now = time.time()
    make_transcript(fake_home, r"C:\p", UUID_A, mtime=now - 10)   # 오래 전 시작한 세션의 파일
    make_transcript(fake_home, r"C:\p", UUID_B, mtime=now - 1)    # 최근 수정
    make_transcript(fake_home, r"C:\p", UUID_C, mtime=now - 5000)  # 두 프로세스 시작 전 → 후보 아님
    old, new = _sess(1, r"C:\p", now - 1000), _sess(2, r"C:\p", now - 100)
    core._guess_missing_ids([old, new])
    assert (new.session_id, new.id_source) == (UUID_B, "guess")
    assert (old.session_id, old.id_source) == (UUID_A, "guess")


def test_guess_skips_claimed_ids(fake_home):
    now = time.time()
    make_transcript(fake_home, r"C:\p", UUID_A, mtime=now - 1)
    known = _sess(1, r"C:\p", now - 100, sid=UUID_A)
    unknown = _sess(2, r"C:\p", now - 50)
    core._guess_missing_ids([known, unknown])
    assert unknown.session_id is None


def test_guess_ignores_files_older_than_process(fake_home):
    now = time.time()
    make_transcript(fake_home, r"C:\p", UUID_A, mtime=now - 3600)
    s = _sess(1, r"C:\p", now - 60)
    core._guess_missing_ids([s])
    assert s.session_id is None


# ───────── 훅 설치/제거 ─────────
def test_strip_hook_keeps_foreign_hooks():
    settings = {"hooks": {"SessionStart": [
        {"hooks": [{"type": "command", "command": '"C:/x/csk-hook.exe"'},
                   {"type": "command", "command": "other.sh"}]},
        {"matcher": "startup", "hooks": [{"type": "command", "command": "py csk_session_hook.py"}]},
    ], "Stop": [{"hooks": [{"type": "command", "command": "beep"}]}]}}
    out = core._strip_hook(settings)
    assert out["hooks"]["SessionStart"] == [{"hooks": [{"type": "command", "command": "other.sh"}]}]
    assert "Stop" in out["hooks"]


def test_strip_hook_removes_empty_sections():
    settings = {"model": "x", "hooks": {"SessionStart": [
        {"hooks": [{"type": "command", "command": '"C:/x/csk-hook.exe"'}]}]}}
    assert core._strip_hook(settings) == {"model": "x"}


def test_install_uninstall_roundtrip(fake_home):
    original = {"model": "opus", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "beep"}]}]}}
    core._write_json(core.SETTINGS_PATH, original)
    core.install_hook()
    assert core.hook_status() == "ok"
    assert core.SETTINGS_PATH.with_name("settings.json.csk-bak").exists()
    core.install_hook()                                # 두 번 설치해도 하나만
    groups = core._settings()["hooks"]["SessionStart"]
    assert sum(core._is_ours(h["command"]) for g in groups for h in g["hooks"]) == 1
    core.uninstall_hook()
    assert core._settings() == original


def test_hook_status_stale_after_move(fake_home, monkeypatch):
    core.install_hook()
    monkeypatch.setattr(core, "hook_command", lambda: '"D:/moved/csk-hook.exe"')
    assert core.hook_status() == "stale"


# ───────── 스냅샷 ─────────
def test_snapshot_roundtrip(fake_home):
    snap = {"version": 1, "name": "t", "created": 1_700_000_000.0, "boot_time": 1.0,
            "sessions": [{"pid": 1, "cwd": "C:\\한글 폴더", "session_id": UUID_A, "id_source": "hook",
                          "title": "제목", "shell": "pwsh.exe", "host": "wt", "started": 1.0}],
            "desktop": {"running": True, "exe": "", "windows": []}}
    path = core.save_snapshot(snap)
    [(p, loaded)] = core.list_snapshots()
    assert p == path and loaded == snap
    assert core.snapshot_summary(loaded) == "Code 세션 1 · Desktop 창 0"
    assert not core.snapshot_is_empty(loaded)
    assert core.snapshot_is_empty({"sessions": [], "desktop": {"running": False}})


# ───────── 프로세스 분류 ─────────
class FakeProc:
    def __init__(self, pid, name, exe, cmdline=None, parent=None):
        self.pid, self._name, self._exe = pid, name, exe
        self._cmd = cmdline or [exe]
        self._parent = parent

    def name(self):
        return self._name

    def exe(self):
        return self._exe

    def cmdline(self):
        return self._cmd

    def parent(self):
        return self._parent


PWSH = FakeProc(10, "pwsh.exe", r"C:\Program Files\PowerShell\7\pwsh.exe")
DESKTOP_STORE = FakeProc(20, "claude.exe",
                         r"C:\Program Files\WindowsApps\Claude_4.4212.0.0_x64__pzs8sxrjxfjjc\app\claude.exe")


@pytest.mark.parametrize("proc, code, desktop", [
    (FakeProc(1, "claude.exe", r"C:\Users\u\.local\bin\claude.exe", parent=PWSH), True, False),
    (FakeProc(2, "claude.exe", r"C:\Users\u\.local\bin\claude.exe", parent=None), True, False),
    (FakeProc(3, "node.exe", r"C:\node\node.exe",
              [r"C:\node\node.exe", r"C:\npm\node_modules\@anthropic-ai\claude-code\cli.js"], PWSH), True, False),
    (FakeProc(4, "node.exe", r"C:\node\node.exe", [r"C:\node\node.exe", "server.js"], PWSH), False, False),
    (DESKTOP_STORE, False, True),
    (FakeProc(5, "claude.exe", DESKTOP_STORE._exe, [DESKTOP_STORE._exe, "--type=renderer"], DESKTOP_STORE),
     False, True),
    (FakeProc(6, "claude.exe", r"C:\Users\u\AppData\Local\AnthropicClaude\app-1.0.0\claude.exe"), False, True),
    # Desktop 내장 Claude Code: Desktop도 터미널 세션도 아님 (2026-11-03 실기에서 발견)
    (FakeProc(7, "claude.exe",
              r"C:\Users\u\AppData\Local\Claude-Data\claude_pzs8sxrjxfjjc\claude-code\2.1.309\9078b9c1d466\claude.exe",
              parent=DESKTOP_STORE), False, False),
])
def test_process_classification(proc, code, desktop):
    assert core.is_code_cli(proc) is code
    assert core.is_desktop_proc(proc) is desktop


def test_desktop_main_exe_skips_embedded_cli():
    embedded = FakeProc(7, "claude.exe",
                        r"C:\Users\u\AppData\Local\Claude-Data\x\claude-code\2.1.309\h\claude.exe",
                        parent=DESKTOP_STORE)
    procs = [p for p in (embedded, DESKTOP_STORE) if core.is_desktop_proc(p)]
    assert core.desktop_main_exe(procs) == DESKTOP_STORE._exe


def test_desktop_launch_target_store_uses_protocol(fake_home, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(fake_home / "nolocal"))
    assert core._desktop_launch_target({"exe": DESKTOP_STORE._exe}, {}) == "claude://"
    assert core._desktop_launch_target({"exe": ""}, {"desktop_launch": r"D:\c.exe"}) == r"D:\c.exe"


# ───────── 파일 로그 ─────────
def test_log_file_appends_and_rotates(fake_home, monkeypatch):
    monkeypatch.setattr(core, "LOG_MAX_BYTES", 50)
    core.append_log_file("첫 줄")
    core.append_log_file("둘째 줄 " + "x" * 60)        # 여기서 50바이트 초과
    assert core.LOG_PATH.read_text(encoding="utf-8").count("\n") == 2
    core.append_log_file("회전 후")
    assert "회전 후" in core.LOG_PATH.read_text(encoding="utf-8")
    assert "첫 줄" in core.LOG_PATH.with_name("app.log.1").read_text(encoding="utf-8")


# ───────── 부팅 후 처리 (재부팅 흐름) ─────────
BOOT = 2_000_000.0
CFG = dict(core.DEFAULT_CONFIG)


def _snap(created, sessions=1):
    return {"version": 1, "name": "s", "created": created, "sessions": [{"cwd": r"C:\p"}] * sessions,
            "desktop": {"running": False}}


def _pending(fake_home, set_at):
    path = core.save_snapshot(_snap(set_at - 1), "snap_x.json")
    core.save_state({"pending_restore": path.name, "pending_set_at": set_at})


def test_boot_planned_reboot_restores_then_never_asks(fake_home):
    core.save_snapshot(_snap(BOOT - 100), core.AUTOSAVE_FILE)      # 재부팅 전 자동저장도 있음
    _pending(fake_home, BOOT - 50)
    action, snap = core.boot_action(CFG, BOOT)
    assert action == "pending" and snap["name"] == "s"
    core.clear_pending_restore()                                    # 복원 실행(_do_pending)
    # 같은 부팅에서 앱을 다시 켜도 '예기치 않은 재부팅'으로 묻지 않는다 (2026-11-03 회귀)
    assert core.boot_action(CFG, BOOT) == ("none", None)


def test_boot_pending_cancelled_does_not_ask(fake_home):
    core.save_snapshot(_snap(BOOT - 100), core.AUTOSAVE_FILE)
    _pending(fake_home, BOOT - 50)
    core.boot_action(CFG, BOOT)
    core.clear_pending_restore()                                    # 트레이에서 취소
    assert core.boot_action(CFG, BOOT) == ("none", None)


def test_boot_app_restarted_before_reboot_keeps_waiting(fake_home):
    _pending(fake_home, BOOT + 10)                                  # 예약은 이번 부팅 이후
    assert core.boot_action(CFG, BOOT) == ("none", None)
    assert core.load_state()["pending_restore"] == "snap_x.json"


def test_boot_pending_snapshot_missing_clears(fake_home):
    core.save_state({"pending_restore": "gone.json", "pending_set_at": BOOT - 50})
    assert core.boot_action(CFG, BOOT) == ("none", None)
    assert "pending_restore" not in core.load_state()


def test_boot_unexpected_reboot_asks_once(fake_home):
    core.save_snapshot(_snap(BOOT - 100), core.AUTOSAVE_FILE)
    action, auto = core.boot_action(CFG, BOOT)
    assert action == "ask" and auto["created"] == BOOT - 100
    assert core.boot_action(CFG, BOOT) == ("none", None)            # 같은 부팅에서 두 번 묻지 않음
    assert core.boot_action(CFG, BOOT + 1000)[0] == "ask"           # 다음 부팅에서는 다시 물음


@pytest.mark.parametrize("auto, cfg", [
    (_snap(BOOT + 10), CFG),                                        # 부팅 후 저장된 자동저장
    (_snap(BOOT - 100, sessions=0), CFG),                           # 빈 자동저장
    (_snap(BOOT - 100), dict(CFG, unexpected_reboot="off")),
])
def test_boot_no_ask(fake_home, auto, cfg):
    core.save_snapshot(auto, core.AUTOSAVE_FILE)
    assert core.boot_action(cfg, BOOT) == ("none", None)


# ───────── Desktop 창 짝짓기 ─────────
def _w(title, hwnd=0):
    return core.DesktopWindow(hwnd, title, [0, 0, 1, 1], "normal")


def test_pair_windows_by_title_then_order():
    cur = [_w("rekt.page", 1), _w("Claude", 2), _w("새 대화", 3), _w("Wallet Tracking", 4)]
    saved = [{"title": "Claude"}, {"title": "Wallet Tracking"}, {"title": "rekt.page"}, {"title": "사라진 대화"}]
    got = {c.hwnd: w["title"] for c, w in core.pair_windows(cur, saved)}
    assert got == {2: "Claude", 4: "Wallet Tracking", 1: "rekt.page", 3: "사라진 대화"}


def test_pair_windows_more_saved_than_open():
    got = core.pair_windows([_w("x", 1)], [{"title": "a"}, {"title": "b"}])
    assert [(c.hwnd, w["title"]) for c, w in got] == [(1, "a")]


def test_boot_time_jitter_is_same_boot(fake_home):
    # psutil.boot_time()은 호출마다 끝자리가 흔들린다 (2026-11-03 실기: ...108743 vs ...1087432)
    core.save_snapshot(_snap(BOOT - 100), core.AUTOSAVE_FILE)
    assert core.boot_action(CFG, BOOT)[0] == "ask"
    assert core.boot_action(CFG, BOOT + 0.0000004) == ("none", None)
    assert core.boot_action(CFG, BOOT - 0.9) == ("none", None)


def test_reinstall_keeps_original_backup(fake_home, monkeypatch):
    original = {"model": "opus"}
    core._write_json(core.SETTINGS_PATH, original)
    core.install_hook()
    monkeypatch.setattr(core, "hook_command", lambda: '"E:/moved/csk-hook.exe"')   # 폴더 이동 후 경로 갱신
    core.install_hook()
    assert core._read_json(core.SETTINGS_PATH.with_name("settings.json.csk-bak"), None) == original


# ───────── 예고 없는 재부팅 3단계 설정 ─────────
def test_unexpected_reboot_auto_restores_once(fake_home):
    core.save_snapshot(_snap(BOOT - 100), core.AUTOSAVE_FILE)
    cfg = dict(CFG, unexpected_reboot="auto")
    action, auto = core.boot_action(cfg, BOOT)
    assert action == "auto" and auto["created"] == BOOT - 100
    assert core.boot_action(cfg, BOOT) == ("none", None)            # 같은 부팅에서 다시 켜도 또 복원하지 않음


def test_unexpected_reboot_off_never_asks(fake_home):
    core.save_snapshot(_snap(BOOT - 100), core.AUTOSAVE_FILE)
    assert core.boot_action(dict(CFG, unexpected_reboot="off"), BOOT) == ("none", None)


@pytest.mark.parametrize("mode", ["off", "auto", "ask"])
def test_planned_reboot_ignores_unexpected_setting(fake_home, mode):
    _pending(fake_home, BOOT - 50)
    assert core.boot_action(dict(CFG, unexpected_reboot=mode), BOOT)[0] == "pending"


@pytest.mark.parametrize("saved, expected", [
    ({}, "ask"),
    ({"ask_after_unexpected_reboot": True}, "ask"),                # 1.0.0 이전 설정 이전
    ({"ask_after_unexpected_reboot": False}, "off"),
    ({"unexpected_reboot": "auto"}, "auto"),
    ({"unexpected_reboot": "auto", "ask_after_unexpected_reboot": False}, "auto"),
    ({"unexpected_reboot": "garbage"}, "ask"),
])
def test_config_unexpected_reboot_migration(fake_home, saved, expected):
    core._write_json(core.CONFIG_PATH, saved)
    cfg = core.load_config()
    assert cfg["unexpected_reboot"] == expected and "ask_after_unexpected_reboot" not in cfg
