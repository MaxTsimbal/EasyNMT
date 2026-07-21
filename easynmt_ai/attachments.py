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


def save_quiz_solution_upload(
    file: FileStorage,
    upload_dir: str,
    *,
    max_bytes: int,
    max_dimension: int = 2400,
) -> AttachmentRef:
    """Save a temporary, privacy-clean image for question 12.

    The source upload is validated, EXIF orientation is applied, metadata is
    removed by re-encoding, and very large images are downscaled. The returned
    file is always JPEG and should be deleted immediately after grading.
    """

    max_bytes = max(256 * 1024, min(12 * 1024 * 1024, int(max_bytes)))
    max_dimension = max(640, min(4096, int(max_dimension)))
    if not file or not file.filename:
        raise AttachmentError("Вибери фото розв’язання або напиши відповідь текстом.")
    original_name = secure_filename(file.filename) or "solution.jpg"
    extension = Path(original_name).suffix.lower()
    guessed_type = (file.mimetype or mimetypes.guess_type(original_name)[0] or "").lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS or guessed_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise AttachmentError("Для завдання №12 підтримуються PNG, JPG, JPEG і WEBP.")

    file.stream.seek(0, os.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    if size <= 0:
        raise AttachmentError("Фото порожнє.")
    if size > max_bytes:
        limit_mb = max(1, max_bytes // (1024 * 1024))
        raise AttachmentError(f"Фото завелике. Максимум {limit_mb} МБ.")

    os.makedirs(upload_dir, exist_ok=True)
    attachment_id = f"att-{uuid.uuid4()}"
    stored_path = os.path.join(upload_dir, f"{attachment_id}.jpg")
    try:
        from PIL import ImageOps

        with Image.open(file.stream) as image:
            image.load()
            image = ImageOps.exif_transpose(image)
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > 30_000_000:
                raise AttachmentError("Фото має непідтримуваний розмір.")
            image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
            if image.mode not in {"RGB", "L"}:
                background = Image.new("RGB", image.size, "white")
                if "A" in image.getbands():
                    background.paste(image, mask=image.getchannel("A"))
                else:
                    background.paste(image)
                image = background
            elif image.mode == "L":
                image = image.convert("RGB")
            image.save(stored_path, format="JPEG", quality=90, optimize=True)
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

    sanitized_size = os.path.getsize(stored_path)
    return AttachmentRef(
        id=attachment_id,
        original_name=original_name,
        mime_type="image/jpeg",
        size_bytes=sanitized_size,
        stored_path=stored_path,
        kind="image",
    )


def delete_attachment(attachment: AttachmentRef | None) -> None:
    """Best-effort deletion for temporary uploads."""

    if attachment is None:
        return
    try:
        os.remove(attachment.stored_path)
    except FileNotFoundError:
        pass
    except OSError:
        pass
