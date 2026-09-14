"""Security: HTML sanitization and markdown rendering."""
from app.core.security import render_markdown_safe, sanitize_html


def test_sanitize_strips_scripts():
    dirty = '<p>Hello</p><script>alert("xss")</script><img src="x" onerror="alert(1)">'
    clean = sanitize_html(dirty)
    assert "<script" not in clean
    assert "onerror" not in clean
    assert "Hello" in clean


def test_sanitize_blocks_javascript_urls():
    dirty = '<a href="javascript:alert(1)">click</a>'
    clean = sanitize_html(dirty)
    assert "javascript:" not in clean


def test_sanitize_allows_safe_tags():
    clean = sanitize_html("<h2>Title</h2><p>Body <strong>bold</strong></p><ul><li>a</li></ul>")
    assert "<h2>" in clean
    assert "<strong>" in clean
    assert "<li>" in clean


def test_render_markdown_safe():
    html = render_markdown_safe("# Heading\n\nSome **bold** text and [link](https://example.com)")
    assert "<h1>" in html
    assert "<strong>bold</strong>" in html
    assert "https://example.com" in html
    assert "<script" not in html
