import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import core  # noqa: E402


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """실제 ~/.claude와 데이터 폴더 대신 임시 폴더를 쓰게 한다."""
    projects = tmp_path / "claude" / "projects"
    projects.mkdir(parents=True)
    data = tmp_path / "data"
    monkeypatch.setattr(core, "PROJECTS_DIR", projects)
    monkeypatch.setattr(core, "SETTINGS_PATH", tmp_path / "claude" / "settings.json")
    monkeypatch.setattr(core, "DATA_DIR", data)
    monkeypatch.setattr(core, "SNAP_DIR", data / "snapshots")
    monkeypatch.setattr(core, "LIVE_DIR", data / "live")
    monkeypatch.setattr(core, "CONFIG_PATH", data / "config.json")
    monkeypatch.setattr(core, "STATE_PATH", data / "state.json")
    monkeypatch.setattr(core, "LOG_PATH", data / "app.log")
    return tmp_path
