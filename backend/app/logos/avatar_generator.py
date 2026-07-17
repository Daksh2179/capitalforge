"""Generates a deterministic letter-avatar PNG for tickers with no
real logo — same ticker always produces the same color and letter.
"""

import hashlib
import io

from PIL import Image, ImageDraw, ImageFont

_PALETTE = [
    "#2563EB", "#059669", "#D97706", "#DC2626",
    "#7C3AED", "#0891B2", "#DB2777", "#4D7C0F",
]
_SIZE = 64


def generate_avatar(ticker: str) -> bytes:
    letter = ticker[0].upper() if ticker else "?"
    color = _color_for(ticker)

    image = Image.new("RGB", (_SIZE, _SIZE), color)
    draw = ImageDraw.Draw(image)

    font = ImageFont.load_default(size=32)
    bbox = draw.textbbox((0, 0), letter, font=font)
    text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
    position = ((_SIZE - text_width) / 2, (_SIZE - text_height) / 2 - bbox[1])

    draw.text(position, letter, fill="white", font=font)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _color_for(ticker: str) -> str:
    digest = hashlib.md5(ticker.upper().encode()).hexdigest()
    index = int(digest, 16) % len(_PALETTE)
    return _PALETTE[index]