# OWNERSHIP: public-derived
"""Image-dependence heuristic: flag pages whose text alone misrepresents them."""

from __future__ import annotations

from bs4 import BeautifulSoup

# Assets that never count as "content": icons, logos, social/app badges, chrome.
_EXCLUDED_SRC_FRAGMENTS = (
    "/style library/",
    "/_layouts/",
    "/sosial media/",
    "/siteassets/bi",
    "icon",
    "logo",
    "favicon",
    "flag-",
    "flag_",
    "arrow",
    "chevron",
    "app-store",
    "play-store",
    "spcommon",
    "facebook",
    "instagram",
    "youtube",
    "twitter",
    "tiktok",
    "spotify",
    "whatsapp",
    "banner",
)


def content_image_srcs(html: str) -> list[str]:
    """Image srcs that plausibly carry page content (chrome/icons excluded)."""

    soup = BeautifulSoup(html, "lxml")
    srcs: list[str] = []
    for image in soup.find_all("img"):
        src = str(image.get("src") or "").strip().lower().split("?", 1)[0]
        if not src or src.startswith("data:"):
            continue
        if any(fragment in src for fragment in _EXCLUDED_SRC_FRAGMENTS):
            continue
        srcs.append(src)
    return srcs


def count_content_images(html: str) -> int:
    """Count images that plausibly carry page content (excludes chrome/icons)."""

    return len(content_image_srcs(html))


def is_visual_heavy(image_count: int, text_length: int) -> bool:
    """Conservative flag: many figures, or figures with very little text."""

    return image_count >= 3 or (image_count >= 1 and text_length < 1500)


def is_visual_heavy_unique(
    unique_image_count: int, image_count: int, text_length: int
) -> bool:
    """Flag rule for the frequency-filtered audit.

    ``unique_image_count`` counts images that are rare across the corpus (not
    shared site chrome). Shared-layout images alone never trigger the flag;
    the raw count still applies when the page has almost no text.
    """

    return unique_image_count >= 3 or (image_count >= 3 and text_length < 1500) or (
        unique_image_count >= 1 and text_length < 1500
    )
