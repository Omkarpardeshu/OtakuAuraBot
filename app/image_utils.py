from io import BytesIO
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


def validate_image(data: bytes, max_bytes: int) -> str:
    if not data:
        raise ValueError("The image file is empty.")
    if len(data) > max_bytes:
        raise ValueError(f"Image is too large. Maximum allowed size is {max_bytes // (1024 * 1024)} MB.")
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
            image_format = image.format
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValueError("This file is not a valid supported image. Please send a JPG, PNG, or WebP image.")
    if image_format not in ALLOWED_FORMATS:
        raise ValueError("Supported image formats are JPG, PNG, and WebP.")
    return ALLOWED_FORMATS[image_format]


MAX_ANALYSIS_DIMENSION = 2560

def prepare_image_for_analysis(data: bytes, mime_type: str, max_dimension: int = MAX_ANALYSIS_DIMENSION) -> tuple[bytes, str]:
    """Downscale only very large images, preserving format and fine anime line detail."""
    try:
        with Image.open(BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source)
            if max(image.size) <= max_dimension:
                return data, mime_type
            image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
            output = BytesIO()
            image_format = source.format or ("JPEG" if mime_type == "image/jpeg" else "PNG")
            save_options = {}
            if image_format == "JPEG":
                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                save_options = {"quality": 92, "optimize": True}
            elif image_format == "WEBP":
                save_options = {"quality": 92, "method": 4}
            elif image_format == "PNG":
                save_options = {"optimize": True}
            image.save(output, format=image_format, **save_options)
            return output.getvalue(), ALLOWED_FORMATS[image_format]
    except (UnidentifiedImageError, OSError, ValueError, KeyError):
        # Validation is performed separately; never block a valid upload because
        # an optional optimization step failed. Send the original bytes instead.
        return data, mime_type
