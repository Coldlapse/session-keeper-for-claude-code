"""데이터 경로 계산 — GUI와 훅이 같은 폴더를 쓰도록 공유한다 (Qt/psutil 의존 없음).

- 일반 실행(포터블 exe, 소스):   %APPDATA%/ClaudeSessionKeeper
- MSIX(스토어) 실행:             %LOCALAPPDATA%/Packages/<PFN>/LocalCache/Roaming/ClaudeSessionKeeper
  패키지 앱의 %APPDATA% 쓰기는 이 위치로 가상화되므로, 실제 경로를 직접 써서
  탐색기 '폴더 열기'와 훅(실행 별칭으로 패키지 컨텍스트에서 실행)이 같은 곳을 보게 한다.
"""
import ctypes
import os
import sys
from pathlib import Path

APP_NAME = "ClaudeSessionKeeper"
_APPMODEL_ERROR_NO_PACKAGE = 15700


def _package_family_name():
    if sys.platform != "win32":
        return None
    try:
        k32 = ctypes.windll.kernel32
        n = ctypes.c_uint32(0)
        rc = k32.GetCurrentPackageFamilyName(ctypes.byref(n), None)
        if rc == _APPMODEL_ERROR_NO_PACKAGE or n.value == 0:
            return None
        buf = ctypes.create_unicode_buffer(n.value)
        if k32.GetCurrentPackageFamilyName(ctypes.byref(n), buf) != 0:
            return None
        return buf.value
    except (AttributeError, OSError):
        return None


PACKAGE_FAMILY = _package_family_name()
IS_PACKAGED = PACKAGE_FAMILY is not None


def data_dir() -> Path:
    if IS_PACKAGED:
        return (Path(os.environ["LOCALAPPDATA"]) / "Packages" / PACKAGE_FAMILY
                / "LocalCache" / "Roaming" / APP_NAME)
    return Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
