"""Zeichnet die Willkommens-Karte (PNG) mit Avatar, Name und Mitgliedsnummer."""

import io
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

WIDTH, HEIGHT = 1100, 400
AVATAR = 250
ACCENT = (247, 147, 26)        # Mancave-Orange
BG_TOP = (18, 18, 22)
BG_BOTTOM = (42, 30, 22)
TEXT = (245, 245, 245)
MUTED = (175, 175, 185)

FONT_DIRS = ["/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/dejavu/", "/Library/Fonts/", "C:/Windows/Fonts/"]


def _font(names: list[str], size: int):
    for d in FONT_DIRS:
        for n in names:
            if os.path.isfile(d + n):
                return ImageFont.truetype(d + n, size)
    return ImageFont.load_default()


def _fit(draw: ImageDraw.ImageDraw, text: str, names: list[str], size: int, max_width: int):
    """Schrift so lange verkleinern, bis der Text passt (lange Namen)."""
    while size > 18:
        font = _font(names, size)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= 4
    return _font(names, size)


BOLD = ["DejaVuSans-Bold.ttf", "arialbd.ttf"]
REGULAR = ["DejaVuSans.ttf", "arial.ttf"]


def render_welcome(avatar_bytes: bytes | None, name: str, number: int, server: str = "Mancave",
                   background_path: str | None = None) -> io.BytesIO:
    # Hintergrund: Verlauf, optional mit abgedunkeltem Server-Bild
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_TOP)
    grad = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        t = y / HEIGHT
        grad.line([(0, y), (WIDTH, y)], fill=tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)))
    if background_path and os.path.isfile(background_path):
        bg = ImageOps.fit(Image.open(background_path).convert("RGB"), (WIDTH, HEIGHT))
        bg = bg.filter(ImageFilter.GaussianBlur(6))
        img = Image.blend(img, bg, 0.35)
    draw = ImageDraw.Draw(img)

    # Akzentleisten
    draw.rectangle([0, 0, WIDTH, 6], fill=ACCENT)
    draw.rectangle([0, HEIGHT - 6, WIDTH, HEIGHT], fill=ACCENT)

    # Avatar rund mit Ring
    ax, ay = 70, (HEIGHT - AVATAR) // 2
    draw.ellipse([ax - 8, ay - 8, ax + AVATAR + 8, ay + AVATAR + 8], fill=ACCENT)
    if avatar_bytes:
        try:
            av = Image.open(io.BytesIO(avatar_bytes)).convert("RGB")
        except OSError:
            av = Image.new("RGB", (AVATAR, AVATAR), (60, 60, 70))
    else:
        av = Image.new("RGB", (AVATAR, AVATAR), (60, 60, 70))
    av = ImageOps.fit(av, (AVATAR, AVATAR))
    mask = Image.new("L", (AVATAR * 4, AVATAR * 4), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, AVATAR * 4, AVATAR * 4], fill=255)
    mask = mask.resize((AVATAR, AVATAR), Image.LANCZOS)  # glatter Rand
    img.paste(av, (ax, ay), mask)

    # Texte
    tx = ax + AVATAR + 60
    max_w = WIDTH - tx - 50
    draw.text((tx, 78), f"WILLKOMMEN IN DER {server.upper()}", font=_font(BOLD, 30), fill=ACCENT)
    draw.text((tx, 168), name, font=_fit(draw, name, BOLD, 64, max_w), fill=TEXT, anchor="lm")
    draw.text((tx, 222), f"Du bist Mitglied Nr. {number}", font=_font(BOLD, 38), fill=TEXT)
    draw.text((tx, 285), "Grind. Build. Level up.", font=_font(REGULAR, 26), fill=MUTED)

    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    buf.seek(0)
    return buf
