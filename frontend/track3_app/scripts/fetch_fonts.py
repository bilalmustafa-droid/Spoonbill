"""Fetch the bundled CJK font used by PDF export.

Downloads Noto Sans TC (SIL Open Font License 1.1) from the google/fonts repository, instantiates the
Regular (wght=400) static TrueType instance from the variable font, and writes:

    track3_app/assets/fonts/NotoSansTC-Regular.ttf
    track3_app/assets/fonts/OFL.txt

The OFL allows bundling, so the generated file is committed; this script documents how it was produced
and lets anyone regenerate it. It needs network access and fonttools (`pip install fonttools`).

Run:  python track3_app/scripts/fetch_fonts.py
"""

from __future__ import annotations

import io
import sys
import urllib.request
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
VARIABLE_URL = "https://github.com/google/fonts/raw/main/ofl/notosanstc/NotoSansTC%5Bwght%5D.ttf"
LICENSE_URL = "https://github.com/google/fonts/raw/main/ofl/notosanstc/OFL.txt"
OUT_FONT = FONT_DIR / "NotoSansTC-Regular.ttf"
OUT_LICENSE = FONT_DIR / "OFL.txt"


def _download(url: str) -> bytes:
    print(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as resp:
        return resp.read()


def main() -> None:
    try:
        from fontTools.ttLib import TTFont
        from fontTools.varLib.instancer import instantiateVariableFont
    except ImportError:
        sys.exit("fonttools is required: pip install fonttools")

    FONT_DIR.mkdir(parents=True, exist_ok=True)
    variable = TTFont(io.BytesIO(_download(VARIABLE_URL)))
    static = instantiateVariableFont(variable, {"wght": 400}, updateFontNames=True)
    static.save(OUT_FONT)
    OUT_LICENSE.write_bytes(_download(LICENSE_URL))
    print(f"OK: wrote {OUT_FONT} ({OUT_FONT.stat().st_size / 1e6:.1f} MB) and {OUT_LICENSE.name}")


if __name__ == "__main__":
    main()
