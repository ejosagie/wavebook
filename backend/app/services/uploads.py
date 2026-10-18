import mimetypes

from fastapi import UploadFile

IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def image_content_type(upload: UploadFile) -> str | None:
    if upload.content_type in IMAGE_TYPES:
        return upload.content_type
    guessed, _ = mimetypes.guess_type(upload.filename or "")
    return guessed if guessed in IMAGE_TYPES else None
