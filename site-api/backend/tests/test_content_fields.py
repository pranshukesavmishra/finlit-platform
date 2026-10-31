from backend import server


def make(**kw):
    base = {"title": "A post title", "contentType": "ARTICLE", "articleBody": "<p>x</p>", "articleFormat": "HTML"}
    return server.ContentInput(**{**base, **kw})


def test_tags_are_trimmed_deduplicated_and_capped():
    item = make(tags=["  Tax ", "tax", "SIP   plans", "", "x" * 50])
    assert item.tags == ["Tax", "SIP plans", "x" * 30]


def test_category_and_tags_default_empty_and_appear_in_public_view():
    item = make()
    assert item.category == "" and item.tags == []
    view = server.content_public_view({**item.model_dump(), "id": "1"})
    assert view["category"] == "" and view["tags"] == []
    view = server.content_public_view({"id": "2", "category": "Basics", "tags": ["a"]})
    assert view["category"] == "Basics" and view["tags"] == ["a"]


def test_article_html_is_sanitised_for_storage():
    html = server.sanitize_article_html('<p onclick="x()">hi</p><script>alert(1)</script><iframe src="https://e.com"></iframe><a href="javascript:alert(1)">l</a>')
    assert "script" not in html and "iframe" not in html and "onclick" not in html and "javascript:" not in html
