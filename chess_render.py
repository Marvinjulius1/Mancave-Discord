"""Zeichnet ein Schachbrett als PNG (Pillow + Schach-Symbole aus der Schriftart DejaVu Sans)."""

import io
import os

import chess
from PIL import Image, ImageDraw, ImageFont

SQUARE = 80
MARGIN = 28
LIGHT = (240, 217, 181)
DARK = (181, 136, 99)
LAST_MOVE = (246, 246, 105, 150)
CHECK = (235, 64, 52, 170)
BG = (35, 37, 43)
COORD = (200, 200, 200)

# Gefüllte Symbole für beide Farben – Weiß wird hell gefüllt, Schwarz dunkel, jeweils mit Kontur
GLYPHS = {chess.KING: "♚", chess.QUEEN: "♛", chess.ROOK: "♜", chess.BISHOP: "♝", chess.KNIGHT: "♞", chess.PAWN: "♟"}
LETTERS = {chess.KING: "K", chess.QUEEN: "D", chess.ROOK: "T", chess.BISHOP: "L", chess.KNIGHT: "S", chess.PAWN: "B"}

FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/DejaVuSans.ttf",
    "C:/Windows/Fonts/seguisym.ttf",  # Windows: Segoe UI Symbol enthält die Schach-Symbole
]


def _font(size: int):
    for path in FONT_PATHS:
        if os.path.isfile(path):
            return ImageFont.truetype(path, size), True
    return ImageFont.load_default(), False  # Notfall: Buchstaben statt Symbole


PIECE_FONT, HAS_GLYPHS = _font(int(SQUARE * 0.82))
COORD_FONT, _ = _font(15)


def render_board(board: chess.Board, flipped: bool = False) -> io.BytesIO:
    size = SQUARE * 8 + MARGIN * 2
    img = Image.new("RGBA", (size, size), BG)
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    odraw = ImageDraw.Draw(overlay)

    def xy(square: int) -> tuple[int, int]:
        file, rank = chess.square_file(square), chess.square_rank(square)
        col = 7 - file if flipped else file
        row = rank if flipped else 7 - rank
        return MARGIN + col * SQUARE, MARGIN + row * SQUARE

    for square in chess.SQUARES:
        x, y = xy(square)
        light = (chess.square_file(square) + chess.square_rank(square)) % 2 == 1
        draw.rectangle([x, y, x + SQUARE - 1, y + SQUARE - 1], fill=LIGHT if light else DARK)

    # Letzten Zug und Schach markieren
    if board.move_stack:
        last = board.peek()
        for sq in (last.from_square, last.to_square):
            x, y = xy(sq)
            odraw.rectangle([x, y, x + SQUARE - 1, y + SQUARE - 1], fill=LAST_MOVE)
    if board.is_check():
        king = board.king(board.turn)
        if king is not None:
            x, y = xy(king)
            odraw.ellipse([x + 4, y + 4, x + SQUARE - 5, y + SQUARE - 5], fill=CHECK)
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    # Figuren
    for square, piece in board.piece_map().items():
        x, y = xy(square)
        cx, cy = x + SQUARE // 2, y + SQUARE // 2
        white = piece.color == chess.WHITE
        fill = (250, 250, 250) if white else (25, 25, 25)
        stroke = (30, 30, 30) if white else (235, 235, 235)
        text = GLYPHS[piece.piece_type] if HAS_GLYPHS else LETTERS[piece.piece_type]
        draw.text((cx, cy + 2), text, font=PIECE_FONT, fill=fill, anchor="mm",
                  stroke_width=2 if white else 1, stroke_fill=stroke)

    # Koordinaten
    files = "abcdefgh"
    for i in range(8):
        f = files[7 - i] if flipped else files[i]
        r = str(i + 1) if flipped else str(8 - i)
        cx = MARGIN + i * SQUARE + SQUARE // 2
        cy = MARGIN + i * SQUARE + SQUARE // 2
        draw.text((cx, MARGIN // 2), f, font=COORD_FONT, fill=COORD, anchor="mm")
        draw.text((cx, size - MARGIN // 2), f, font=COORD_FONT, fill=COORD, anchor="mm")
        draw.text((MARGIN // 2, cy), r, font=COORD_FONT, fill=COORD, anchor="mm")
        draw.text((size - MARGIN // 2, cy), r, font=COORD_FONT, fill=COORD, anchor="mm")

    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG", optimize=True)
    buf.seek(0)
    return buf
