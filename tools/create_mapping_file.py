"""Generate the offline font mapping under data/."""

import hashlib
import json
from pathlib import Path

from fontTools.ttLib import TTFont


ROOT = Path(__file__).resolve().parent.parent


def hash_glyph_commands(commands):
    return hashlib.sha1(json.dumps(commands, sort_keys=True).encode()).hexdigest()


def main():
    font = TTFont(ROOT / "SourceHanSansSC-VF.ttf")
    cmap = font.getBestCmap()
    glyph_unicodes = {}
    for code, name in cmap.items():
        glyph_unicodes.setdefault(name, []).append(code)
    mapping = {}
    for name in font.getGlyphOrder():
        unicodes = glyph_unicodes.get(name, [])
        if not any(0x4E00 <= code <= 0x9FFF for code in unicodes):
            continue
        glyph = font["glyf"][name]
        commands = []
        if glyph.numberOfContours > 0:
            commands = [f"CONTOUR_END:{glyph.endPtsOfContours}",
                        f"COORDS:{glyph.coordinates}"]
        elif glyph.isComposite():
            commands = ["COMPOSITE"] + [
                f"{component.glyphName}({component.x},{component.y})"
                for component in glyph.components
            ]
        mapping.setdefault(hash_glyph_commands(commands), unicodes[0])
    output = ROOT / "data" / "mapping_file.json"
    output.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
