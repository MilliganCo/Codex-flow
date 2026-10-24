"""Optional development-only ASCII contact sheet. Requires an already installed Pillow.

The PNG is a preview of the actual saved text; it is never used by the application.
"""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def main():
    samples = json.loads((ROOT / "samples" / "manifest.json").read_text())
    # Pillow's built-in font: no downloaded assets or system font dependency.
    font = ImageFont.load_default(size=13)
    title = ImageFont.load_default(size=18)
    cell_w, cell_h = 8, 16
    panel_w, panel_h = 850, 730
    sheet = Image.new("RGB", (panel_w * 2, panel_h * 3), "#101816")
    draw = ImageDraw.Draw(sheet)
    for index, item in enumerate(samples):
        ox, oy = (index % 2) * panel_w, (index // 2) * panel_h
        draw.text((ox + 24, oy + 20), item["file"], font=title, fill="#d8edc3")
        lines = (ROOT / "samples" / item["file"]).read_text(encoding="ascii").splitlines()
        for row, line in enumerate(lines):
            for col, char in enumerate(line):
                if char != " ":
                    color = "#9ab57f" if char in ".:'o" else "#dfd3ad"
                    draw.text((ox + 24 + col * cell_w, oy + 62 + row * cell_h), char, font=font, fill=color)
    path = ROOT / "samples" / "contact-sheet.png"
    sheet.save(path)
    print(path)


if __name__ == "__main__":
    main()
