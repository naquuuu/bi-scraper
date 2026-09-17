# OWNERSHIP: public-derived
"""Image-dependence heuristic (visual-heavy manual-read flagging)."""

from __future__ import annotations

from bi_scraper.parsers.visual import count_content_images, is_visual_heavy

ICON_HTML = """
<html><body>
<img src="/Style Library/biweb/img/flag-indo.png" />
<img src="/SiteAssets/logo-bi@2x.png" />
<img src="/Sosial Media/icon-fb.svg" />
<img src="/SiteAssets/app-store.svg" />
</body></html>
"""

CHART_HTML = """
<html><body>
<img src="/id/rupiah/gambar-uang/PublishingImages/uang-1.jpg" />
<img src="/id/rupiah/gambar-uang/PublishingImages/uang-2.jpg" />
<img src="/id/rupiah/gambar-uang/PublishingImages/uang-3.jpg" />
</body></html>
"""


def test_icons_logos_and_social_are_not_content():
    assert count_content_images(ICON_HTML) == 0
    assert is_visual_heavy(0, 500) is False


def test_three_content_images_are_flagged():
    assert count_content_images(CHART_HTML) == 3
    assert is_visual_heavy(3, 5000) is True


def test_single_image_with_short_text_is_flagged():
    assert is_visual_heavy(1, 800) is True
    assert is_visual_heavy(1, 5000) is False


def test_data_uri_images_are_ignored():
    html = '<img src="data:image/png;base64,AAAA" />'
    assert count_content_images(html) == 0
