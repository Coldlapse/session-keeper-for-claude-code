# -*- mode: python ; coding: utf-8 -*-
# 빌드: python -m PyInstaller --noconfirm packaging/ClaudeSessionKeeper.spec
# 결과: dist/ClaudeSessionKeeper/
#   ClaudeSessionKeeper.exe  GUI (windowed)
#   csk-hook.exe             Claude Code SessionStart 훅 (console, stdin 필요)
#   _internal/               두 exe가 공유하는 런타임
import sys
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo)

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
ICON = str(ROOT / "assets" / "icon.ico")
sys.path.insert(0, str(SRC))
from version import __version__  # noqa: E402

_v = tuple(int(x) for x in __version__.split(".")) + (0,)


def version_info(desc, internal):
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=_v, prodvers=_v),
        kids=[
            StringFileInfo([StringTable("041204B0", [
                StringStruct("FileDescription", desc),
                StringStruct("FileVersion", __version__),
                StringStruct("InternalName", internal),
                StringStruct("OriginalFilename", internal + ".exe"),
                StringStruct("ProductName", "Session Keeper for Claude Code"),
                StringStruct("ProductVersion", __version__),
                StringStruct("LegalCopyright", "MIT License"),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x0412, 1200])]),
        ])


EXCLUDES = ["tkinter", "unittest", "pydoc", "test", "PySide6.QtQml", "PySide6.QtQuick",
            "PySide6.QtPdf", "PySide6.QtSvg", "PySide6.QtOpenGL"]

gui_a = Analysis([str(SRC / "app.py")], pathex=[str(SRC)], excludes=EXCLUDES)
hook_a = Analysis([str(SRC / "csk_session_hook.py")], pathex=[str(SRC)],
                  excludes=EXCLUDES + ["PySide6", "shiboken6", "win32gui", "win32con"])


def _keep(entry):
    """빌드 환경 전용 스텁(Wine 빌드 시), 불필요한 대용량 파일 제외."""
    dest = entry[0].replace("\\", "/").lower()
    name = dest.rsplit("/", 1)[-1]
    if name.startswith(("api-ms-win-core-winrt", "icuuc", "mscms")) or name == "opengl32sw.dll":
        return False
    if "/translations/" in dest and not name.endswith("_ko.qm"):
        return False
    return True


for a in (gui_a, hook_a):
    a.binaries = [b for b in a.binaries if _keep(b)]
    a.datas = [d for d in a.datas if _keep(d)]

gui_exe = EXE(PYZ(gui_a.pure), gui_a.scripts, [], exclude_binaries=True,
              name="ClaudeSessionKeeper", icon=ICON, console=False, upx=False,
              version=version_info("Session Keeper for Claude Code", "ClaudeSessionKeeper"))
hook_exe = EXE(PYZ(hook_a.pure), hook_a.scripts, [], exclude_binaries=True,
               name="csk-hook", icon=ICON, console=True, upx=False,
               version=version_info("Session Keeper for Claude Code hook", "csk-hook"))

coll = COLLECT(gui_exe, gui_a.binaries, gui_a.datas,
               hook_exe, hook_a.binaries, hook_a.datas,
               name="ClaudeSessionKeeper", upx=False)
