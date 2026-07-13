"""Creates a safe annotated copy of a student's uploaded solution."""
from __future__ import annotations

import os
import textwrap
from typing import Any

from PIL import Image, ImageDraw, ImageFont


def _font(size: int):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def create_annotated_solution(source_path: str, output_path: str, analysis: dict[str, Any]) -> str:
    image = Image.open(source_path).convert("RGB")
    width, height = image.size
    max_width = 1600
    if width > max_width:
        ratio = max_width / width
        image = image.resize((max_width, int(height * ratio)))
        width, height = image.size

    panel_h = max(240, int(height * 0.24))
    canvas = Image.new("RGB", (width, height + panel_h), "white")
    canvas.paste(image, (0, 0))
    draw = ImageDraw.Draw(canvas)

    box = analysis.get("error_box") or {}
    try:
        x = int(float(box.get("x", 0.08)) * width)
        y = int(float(box.get("y", 0.08)) * height)
        w = int(float(box.get("width", 0.45)) * width)
        h = int(float(box.get("height", 0.12)) * height)
        if w > 0 and h > 0:
            draw.rounded_rectangle((x, y, min(width - 4, x + w), min(height - 4, y + h)), radius=10, outline=(220, 45, 45), width=max(4, width // 300))
            draw.line((x + w // 2, min(height - 4, y + h), x + w // 2, height + 26), fill=(220, 45, 45), width=max(4, width // 350))
    except (TypeError, ValueError):
        pass

    draw.rectangle((0, height, width, height + panel_h), fill=(247, 249, 252))
    title_font = _font(max(24, width // 38))
    body_font = _font(max(18, width // 52))
    small_font = _font(max(16, width // 60))

    draw.text((28, height + 22), "Де з'явилася помилка", font=title_font, fill=(165, 28, 48))
    message = str(analysis.get("message") or "Перевір позначений крок.")
    correct = str(analysis.get("correct_step") or "Перепиши цей крок правильно й продовж розв’язання.")

    y_cursor = height + 72
    wrap_width = max(32, width // max(10, body_font.size // 2))
    for line in textwrap.wrap(message, width=wrap_width):
        draw.text((28, y_cursor), line, font=body_font, fill=(35, 42, 55))
        y_cursor += body_font.size + 8

    y_cursor += 8
    draw.text((28, y_cursor), "Як виправити:", font=small_font, fill=(21, 110, 70))
    y_cursor += small_font.size + 10
    for line in textwrap.wrap(correct, width=wrap_width):
        draw.text((28, y_cursor), line, font=body_font, fill=(22, 75, 54))
        y_cursor += body_font.size + 8

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    canvas.save(output_path, format="JPEG", quality=90, optimize=True)
    return output_path
