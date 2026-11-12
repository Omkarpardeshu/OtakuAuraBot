from io import BytesIO
from PIL import Image
import pytest

from app.image_utils import validate_image, prepare_image_for_analysis


def make_image(fmt: str = "PNG") -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 8), "white").save(output, format=fmt)
    return output.getvalue()


def test_accepts_png():
    assert validate_image(make_image("PNG"), 100_000) == "image/png"


def test_accepts_jpeg():
    assert validate_image(make_image("JPEG"), 100_000) == "image/jpeg"


def test_rejects_empty_image():
    with pytest.raises(ValueError, match="empty"):
        validate_image(b"", 100_000)


def test_rejects_oversized_image():
    with pytest.raises(ValueError, match="too large"):
        validate_image(make_image(), 1)


def test_rejects_non_image():
    with pytest.raises(ValueError, match="valid supported image"):
        validate_image(b"not an image", 100_000)


def test_keeps_small_image_bytes_unchanged():
    data = make_image("PNG")
    prepared, mime = prepare_image_for_analysis(data, "image/png", max_dimension=64)
    assert prepared == data
    assert mime == "image/png"


def test_downscales_large_image_without_changing_aspect_ratio():
    output = BytesIO()
    Image.new("RGB", (4000, 2000), "white").save(output, format="JPEG")
    prepared, mime = prepare_image_for_analysis(output.getvalue(), "image/jpeg", max_dimension=1600)
    with Image.open(BytesIO(prepared)) as result:
        assert result.size == (1600, 800)
    assert mime == "image/jpeg"
