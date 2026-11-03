"""단일 버전 소스. 릴리스 시 여기만 올리고 같은 값으로 git tag(vX.Y.Z)를 붙인다."""
__version__ = "1.0.0"
# MSIX/Store는 4자리이고 마지막 자리가 0이어야 한다.
MSIX_VERSION = __version__ + ".0"
