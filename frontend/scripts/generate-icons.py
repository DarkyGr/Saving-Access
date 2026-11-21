"""
Raster copies of public/favicon.svg (Pillow), for browsers and phones that do
not use an SVG icon: favicon.ico (16, 32, 48) and apple-touch-icon.png (180).

    python scripts/generate-icons.py      (from frontend/)

Drawn at 4x and scaled down for smooth edges. Keep the shapes in step with
favicon.svg (64x64 grid).
"""

from pathlib import Path

from PIL import Image, ImageDraw

INDIGO = (79, 70, 229, 255)
WHITE = (255, 255, 255, 255)
PUBLIC = Path(__file__).resolve().parent.parent / "public"


def draw(size: int, *, rounded: bool = True) -> Image.Image:
    big = size * 4
    s = big / 64
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if rounded:
        d.rounded_rectangle((0, 0, big - 1, big - 1), radius=14 * s, fill=INDIGO)
    else:
        d.rectangle((0, 0, big, big), fill=INDIGO)
    # Shield: top point, shoulders, then a curved point at the bottom.
    shield = [(32, 9), (50, 16), (50, 30)]
    for i in range(1, 11):
        t = i / 10
        shield.append((50 - 18 * t, 30 + 25 * t ** 0.7))
    for i in range(1, 11):
        t = i / 10
        shield.append((32 - 18 * t, 55 - 25 * t ** (1 / 0.7)))
    shield += [(14, 16)]
    d.polygon([(x * s, y * s) for x, y in shield], fill=WHITE)
    d.ellipse(((32 - 5.5) * s, (29 - 5.5) * s, (32 + 5.5) * s, (29 + 5.5) * s), fill=INDIGO)
    d.polygon([(29.5 * s, 32.5 * s), (34.5 * s, 32.5 * s), (36.1 * s, 43 * s), (27.9 * s, 43 * s)], fill=INDIGO)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    draw(48).save(PUBLIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    # iOS rounds the corners itself: a full square looks right there.
    draw(180, rounded=False).convert("RGB").save(PUBLIC / "apple-touch-icon.png", optimize=True)
    print("icons written to", PUBLIC)


if __name__ == "__main__":
    main()
