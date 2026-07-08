"""
Генерация картинки перевода SCAM.

Сверху — крупная сумма (например «0,048»).
Снизу — строка «#SCAM отправил(а) {сумма} SCAM для {получатель}».

Возвращает PNG в виде bytes, чтобы сразу отправить в Telegram.
"""

import os
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

# --- Пути к шрифтам (лежат рядом, в assets/) ---------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_BOLD_PATH = os.path.join(BASE_DIR, "assets", "DejaVuSans-Bold.ttf")
FONT_REGULAR_PATH = os.path.join(BASE_DIR, "assets", "DejaVuSans.ttf")

# Системные запасные пути на случай, если assets/ не поедет
_FALLBACKS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

# --- Цвета -------------------------------------------------------------------
BG_TOP = (13, 17, 23)        # тёмный верх
BG_BOTTOM = (22, 27, 34)     # чуть светлее низ
ACCENT = (35, 197, 98)       # «денежный» зелёный
AMOUNT_COLOR = (255, 255, 255)
SUB_COLOR = (139, 148, 158)
HASH_COLOR = (35, 197, 98)

WIDTH = 900
HEIGHT = 500
PADDING = 60


def _load_font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    primary = FONT_BOLD_PATH if bold else FONT_REGULAR_PATH
    for path in (primary, *_FALLBACKS):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    # крайний случай — встроенный растровый шрифт (без масштабирования)
    return ImageFont.load_default()


def _fit_font(draw, text, max_width, bold, start_size, min_size=14):
    """Подбирает максимальный размер шрифта, при котором текст влезает по ширине."""
    size = start_size
    while size > min_size:
        font = _load_font(bold, size)
        w = draw.textlength(text, font=font)
        if w <= max_width:
            return font
        size -= 2
    return _load_font(bold, min_size)


def _gradient_fast(width, height, top, bottom):
    """Быстрый градиент через одну колонку + resize (без попиксельного цикла)."""
    col = Image.new("RGB", (1, height))
    top_r, top_g, top_b = top
    bot_r, bot_g, bot_b = bottom
    for y in range(height):
        t = y / max(height - 1, 1)
        col.putpixel(
            (0, y),
            (
                int(top_r + (bot_r - top_r) * t),
                int(top_g + (bot_g - top_g) * t),
                int(top_b + (bot_b - top_b) * t),
            ),
        )
    return col.resize((width, height))


def render_transfer_image(amount_str: str, recipient: str) -> bytes:
    """
    amount_str : сумма как строка ("0,048") — показывается 1-в-1.
    recipient  : кому перевели ("@user" или имя).
    """
    img = _gradient_fast(WIDTH, HEIGHT, BG_TOP, BG_BOTTOM)
    draw = ImageDraw.Draw(img)

    # Рамка-акцент
    draw.rounded_rectangle(
        [(18, 18), (WIDTH - 18, HEIGHT - 18)],
        radius=28,
        outline=ACCENT,
        width=3,
    )

    # --- Крупная сумма (сверху по центру) ---
    amount_font = _fit_font(
        draw, amount_str, WIDTH - 2 * PADDING, bold=True, start_size=200
    )
    a_w = draw.textlength(amount_str, font=amount_font)
    a_bbox = amount_font.getbbox(amount_str)
    a_h = a_bbox[3] - a_bbox[1]
    a_x = (WIDTH - a_w) / 2
    a_y = HEIGHT * 0.30 - a_h / 2 - a_bbox[1]

    # лёгкая «тень»
    draw.text((a_x + 4, a_y + 4), amount_str, font=amount_font, fill=(0, 0, 0))
    draw.text((a_x, a_y), amount_str, font=amount_font, fill=AMOUNT_COLOR)

    # значок SCAM под суммой
    tag_font = _load_font(True, 34)
    tag = "SCAM"
    t_w = draw.textlength(tag, font=tag_font)
    draw.text(
        ((WIDTH - t_w) / 2, HEIGHT * 0.30 + a_h / 2 + 6),
        tag,
        font=tag_font,
        fill=ACCENT,
    )

    # --- Разделитель ---
    line_y = HEIGHT * 0.66
    draw.line(
        [(PADDING, line_y), (WIDTH - PADDING, line_y)],
        fill=(48, 54, 61),
        width=2,
    )

    # --- Нижняя строка: #SCAM отправил(а) {сумма} SCAM для {получатель} ---
    sub_text = f"#SCAM отправил(а) {amount_str} SCAM для {recipient}"
    sub_font = _fit_font(
        draw, sub_text, WIDTH - 2 * PADDING, bold=False, start_size=40
    )
    s_w = draw.textlength(sub_text, font=sub_font)
    s_bbox = sub_font.getbbox(sub_text)
    s_h = s_bbox[3] - s_bbox[1]
    s_x = (WIDTH - s_w) / 2
    s_y = line_y + (HEIGHT - 18 - line_y) / 2 - s_h / 2 - s_bbox[1]

    # Раскрасим «#SCAM» акцентом, остальное — приглушённым
    prefix = "#SCAM "
    rest = sub_text[len(prefix):]
    p_w = draw.textlength(prefix, font=sub_font)
    draw.text((s_x, s_y), prefix, font=sub_font, fill=HASH_COLOR)
    draw.text((s_x + p_w, s_y), rest, font=sub_font, fill=SUB_COLOR)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


if __name__ == "__main__":
    # Быстрый локальный тест
    data = render_transfer_image("0,048", "@durov")
    with open("preview.png", "wb") as f:
        f.write(data)
    print("preview.png сохранён:", len(data), "байт")
