"""
Generate PWA icon sets for both apps.
Monogram v1: terracotta background, white serif "K".
Maskable variants pad the glyph into the inner 80% safe zone.
Run: python scripts/generate_pwa_icons.py
"""
from PIL import Image, ImageDraw, ImageFont

TERRACOTTA = "#B4533C"
CREAM      = "#F4EDDF"
FONT       = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
APPS       = ["employee_pwa", "owner_pwa"]
SIZES      = [192, 512]


def make_icon(size: int, maskable: bool) -> Image.Image:
    img  = Image.new("RGB", (size, size), TERRACOTTA)
    draw = ImageDraw.Draw(img)
    # Maskable icons get clipped to a circle by the OS — keep the glyph in the safe zone
    glyph_scale = 0.42 if maskable else 0.58
    font = ImageFont.truetype(FONT, int(size * glyph_scale))
    # Center the "K" using its bounding box
    l, t, r, b = draw.textbbox((0, 0), "K", font=font)
    draw.text(((size - (r - l)) / 2 - l, (size - (b - t)) / 2 - t), "K", font=font, fill=CREAM)
    return img


for app in APPS:
    for size in SIZES:
        make_icon(size, False).save(f"{app}/public/icon-{size}.png")
        make_icon(size, True).save(f"{app}/public/icon-maskable-{size}.png")
    print(f"{app}: 4 icons written")
