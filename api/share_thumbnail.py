"""Safe conversion and OG HTML generation for the admin-uploaded share image.

All uploads are converted to a 1200x630 JPEG (padded, never cropped).
Keeping each asset under Firestore's per-document limit lets the existing
Cloud Run service account persist it without new cloud infrastructure.
"""
import hashlib
from html import escape
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

PUBLIC_BASE_URL = "https://chwijae-api-ejmdmrnztq-du.a.run.app/"
STATIC_FALLBACK_URL = PUBLIC_BASE_URL + "static/og-thumbnail-wide.jpg"
DEFAULT_OG_TITLE = "취재를 종합하면"
DEFAULT_OG_DESCRIPTION = "한국 언론의 기사에서 '취재를 종합하면' 표현의 사용을 기록하는 대시보드"
MAX_OG_TITLE_LENGTH = 100
MAX_OG_DESCRIPTION_LENGTH = 300
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


def validate_preview_copy(title, description):
    """Validate human-authored OG fields before persisting them."""
    if not isinstance(title, str) or not isinstance(description, str):
        raise ValueError("공유 제목과 설명을 모두 입력해주세요.")
    title = " ".join(title.split())
    description = " ".join(description.split())
    if not title or not description:
        raise ValueError("공유 제목과 설명을 모두 입력해주세요.")
    if len(title) > MAX_OG_TITLE_LENGTH:
        raise ValueError("공유 제목은 100자 이내로 입력해주세요.")
    if len(description) > MAX_OG_DESCRIPTION_LENGTH:
        raise ValueError("공유 설명은 300자 이내로 입력해주세요.")
    return title, description


def render_preview_html(html, url, title=DEFAULT_OG_TITLE,
                        description=DEFAULT_OG_DESCRIPTION):
    """Update preview fields in server-rendered HTML, including for JS-free crawlers.

    The visible dashboard heading and browser tab title remain unchanged.
    """
    if not url.startswith(PUBLIC_BASE_URL):
        raise ValueError("Invalid share image URL")
    title, description = validate_preview_copy(title, description)
    values = {
        'property="og:image"': url,
        'property="og:image:secure_url"': url,
        'name="twitter:image"': url,
        'property="og:title"': title,
        'name="twitter:title"': title,
        'property="og:description"': description,
        'name="twitter:description"': description,
        'name="description"': description,
    }
    # Each trusted tag attribute must exist exactly once.
    # Escape user text to prevent attribute injection and script markup.
    for identifier, raw in values.items():
        prefix = "<meta " + identifier + ' content="'
        if html.count(prefix) != 1:
            raise ValueError("Missing or repeated preview tag: " + identifier)
        start = html.index(prefix) + len(prefix)
        end = html.find('"', start)
        if end < 0:
            raise ValueError("Unterminated preview tag: " + identifier)
        html = html[:start] + escape(raw, quote=True) + html[end:]
    return html
