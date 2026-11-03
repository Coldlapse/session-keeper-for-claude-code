"""assets/icon.png → MSIX 로고 PNG 생성. 사용: python packaging/msix/make_assets.py <출력폴더>"""
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SIZES = {  # 파일명: (캔버스 w, h, 아이콘 크기)
    "Square44x44Logo.png": (44, 44, 44),
    "Square44x44Logo.targetsize-44_altform-unplated.png": (44, 44, 44),
    "Square150x150Logo.png": (150, 150, 120),
    "Wide310x150Logo.png": (310, 150, 120),
    "StoreLogo.png": (50, 50, 50),
}


def main(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    src = Image.open(ROOT / "assets" / "icon.png").convert("RGBA")
    for name, (w, h, s) in SIZES.items():
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        icon = src.resize((s, s), Image.LANCZOS)
        canvas.paste(icon, ((w - s) // 2, (h - s) // 2), icon)
        canvas.save(out / name)
    print(f"assets → {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
