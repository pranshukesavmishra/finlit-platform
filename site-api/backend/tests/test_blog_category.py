"""The blog's topic chips and featured story: a post carries one of five categories (or none) and a featured flag, and both reach the public view."""
import pytest
from pydantic import ValidationError

from backend import server


def base(**kw):
    return dict(title="Does a high P/E mean overvalued?", contentType="ARTICLE", articleBody="<p>x</p>", articleFormat="HTML", **kw)


def test_the_five_categories_are_accepted_and_nothing_else():
    for c in ("Myth Busters", "Explainers", "Hot Topics", "Investing Basics", "Industry Insights"):
        assert server.ContentInput(**base(category=c)).category == c
    with pytest.raises(ValidationError):
        server.ContentInput(**base(category="Hot Tips"))
    assert server.ContentInput(**base()).category is None and server.ContentInput(**base()).featured is False


def test_category_and_featured_reach_the_public_view():
    doc = {"id": "1", "title": "t", "slug": "t", "excerpt": "", "contentType": "ARTICLE", "category": "Explainers", "featured": True}
    v = server.content_public_view(doc)
    assert v["category"] == "Explainers" and v["featured"] is True
    assert server.content_public_view({"id": "2"}).get("category") is None            # an older post without them still serves
