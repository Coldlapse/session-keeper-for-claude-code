"""Claude Code SessionStart 훅.

Claude Code가 세션을 시작/재개/clear/compact 할 때 호출되어
<데이터 폴더>/live/<claude PID>.json (paths.data_dir 참고) 에 세션 ID를 기록한다.
어떤 경우에도 Claude Code 동작을 방해하지 않도록 항상 exit 0.
"""
import json
import os
import sys
import time


def find_claude_pid():
    import psutil
    p = psutil.Process().parent()
    for _ in range(8):
        if p is None:
            return None
        name = p.name().lower()
        if name == "claude.exe":
            return p.pid
        if name == "node.exe" and "claude-code" in " ".join(p.cmdline()).lower():
            return p.pid
        p = p.parent()
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    sid = data.get("session_id")
    if not sid:
        return
    try:
        pid = find_claude_pid()
    except Exception:
        pid = None
    if not pid:
        return
    from paths import data_dir
    live = data_dir() / "live"
    live.mkdir(parents=True, exist_ok=True)
    rec = {
        "pid": pid,
        "session_id": sid,
        "cwd": data.get("cwd"),
        "transcript_path": data.get("transcript_path"),
        "source": data.get("source"),
        "ts": time.time(),
    }
    tmp = live / f"{pid}.json.tmp"
    tmp.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, live / f"{pid}.json")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
