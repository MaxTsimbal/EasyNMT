from __future__ import annotations

import base64
import mimetypes
import os
import uuid
from pathlib import Path
from typing import Iterable

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename
from PIL import Image, UnidentifiedImageError

from .schemas import AttachmentRef


ALLOWED_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class AttachmentError(ValueError):
    pass


def save_image_upload(file: FileStorage, upload_dir: str, *, max_bytes: int) -> AttachmentRef:
    if not file or not file.filename:
        raise AttachmentError("Вибери фото для завантаження.")

    original_name = secure_filename(file.filename) or "solution.jpg"
    extension = Path(original_name).suffix.lower()
    guessed_type = (file.mimetype or mimetypes.guess_type(original_name)[0] or "").lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS or guessed_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise AttachmentError("Підтримуються PNG, JPG, JPEG і WEBP.")

    file.stream.seek(0, os.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    if size <= 0:
        raise AttachmentError("Файл порожній.")
    if size > max_bytes:
        raise AttachmentError(f"Фото завелике. Максимум {max_bytes // (1024 * 1024)} МБ.")

    os.makedirs(upload_dir, exist_ok=True)
    attachment_id = f"att-{uuid.uuid4()}"
    stored_name = f"{attachment_id}{extension}"
    stored_path = os.path.join(upload_dir, stored_name)
    file.save(stored_path)

    try:
        with Image.open(stored_path) as image:
            width, height = image.size
            image.verify()
        if width <= 0 or height <= 0 or width * height > 25_000_000:
            raise AttachmentError("Фото має непідтримуваний розмір.")
    except AttachmentError:
        try:
            os.remove(stored_path)
        except OSError:
            pass
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        try:
            os.remove(stored_path)
        except OSError:
            pass
        raise AttachmentError("Файл не схожий на справжнє зображення.")

    return AttachmentRef(
        id=attachment_id,
        original_name=original_name,
        mime_type=guessed_type,
        size_bytes=size,
        stored_path=stored_path,
        kind="image",
    )


def image_to_data_url(attachment: AttachmentRef) -> str:
    with open(attachment.stored_path, "rb") as source:
        encoded = base64.b64encode(source.read()).decode("ascii")
    return f"data:{attachment.mime_type};base64,{encoded}"


def normalize_attachment_ids(value: object, *, limit: int = 3) -> list[str]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, dict)):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text.startswith("att-") and len(text) <= 80 and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result
