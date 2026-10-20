"""Safe conversion and OG HTML generation for the admin-uploaded share image.

All uploads are converted to a 1200x630 JPEG (padded, never cropped).
Keeping each asset under Firestore's per-document limit lets the existing
Cloud Run service account persist it without new cloud infrastructure.
"""
import hashlib
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

PUBLIC_BASE_URL = "https://chwijae-api-ejmdmrnztq-du.a.run.app/"
STATIC_FALLBACK_URL = PUBLIC_BASE_URL + "static/og-thumbnail-wide.jpg"
THUMBNAIL_SIZE = (1200, 630)
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 12_000_000
MAX_STORED_BYTES = 500_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


class InvalidThumbnail(ValueError):
    pass


def process_thumbnail(raw):
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise InvalidThumbnail("이미지는 최대 5MB까지 업로드할 수 있습니다.")
    try:
        with Image.open(BytesIO(raw)) as source:
            if source.format not in ALLOWED_FORMATS:
                raise InvalidThumbnail("JPG, PNG, WEBP 이미지만 등록할 수 있습니다.")
            width, height = source.size
            if width < 400 or height < 210:
                raise InvalidThumbnail("이미지는 최소 400×210픽셀 이상이어야 합니다.")
            if width * height > MAX_IMAGE_PIXELS:
                raise InvalidThumbnail("이미지가 너무 큽니다. 1200×630 크기로 줄여주세요.")
            # Reject malformed and truncated images, including mislabeled uploads.
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGBA")
        fitted = ImageOps.contain(image, THUMBNAIL_SIZE, method=Image.Resampling.LANCZOS)
        background = Image.new("RGB", THUMBNAIL_SIZE, "#f4f8fd")
        center = ((THUMBNAIL_SIZE[0] - fitted.width) // 2,
                  (THUMBNAIL_SIZE[1] - fitted.height) // 2)
        background.paste(fitted, center, fitted.getchannel("A"))
        for quality in (86, 78, 69, 58):
            buf = BytesIO()
            background.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
            result = buf.getvalue()
            if len(result) <= MAX_STORED_BYTES:
                return result
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        if isinstance(exc, InvalidThumbnail):
            raise
        raise InvalidThumbnail("유효한 이미지 파일이 아닙니다.") from exc
    raise InvalidThumbnail("이미지를 500KB 이하로 변환할 수 없습니다.")


def image_version(jpeg):
    return hashlib.sha256(jpeg).hexdigest()


def image_url(version=None):
    return (PUBLIC_BASE_URL + "share-images/" + version + ".jpg") if version else STATIC_FALLBACK_URL


def render_preview_html(html, url):
    """Homepage OG tags are replaced in HTML served to robots; no JS needed."""
    if not url.startswith(PUBLIC_BASE_URL):
        raise ValueError("Invalid share image URL")
    # Only change URL values for the existing OG/Twitter image tags.
    targets = (
        '<meta property="og:image" content="',
        '<meta property="og:image:secure_url" content="',
        '<meta name="twitter:image" content="',
    )
    for prefix in targets:
        start = html.find(prefix)
        if start == -1:
            raise ValueError("Missing Open Graph image tag: " + prefix)
        begin = start + len(prefix)
        end = html.find('"', begin)
        if end == -1:
            raise ValueError("Unterminated OG image tag")
        html = html[:begin] + url + html[end:]
    return html
