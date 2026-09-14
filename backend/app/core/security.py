"""Artifact sanitization.

Generated HTML is treated as untrusted. We sanitize server-side with ``nh3``
(the Rust-backed Ammonia allowlist engine) before persisting or serving, and
the frontend additionally renders artifacts inside a sandboxed iframe (no
``allow-same-origin``) for defense in depth.

Allowed tags/attributes are deliberately minimal: no scripts, no event
handlers, no external resource loading beyond http(s) images/links.
"""
from __future__ import annotations

import nh3

_ALLOWED_TAGS = {
    "a", "b", "blockquote", "br", "code", "del", "div", "em", "h1", "h2",
    "h3", "h4", "h5", "h6", "hr", "i", "img", "li", "ol", "p", "pre",
    "strong", "table", "tbody", "td", "th", "thead", "tr", "ul", "span",
    "figure", "figcaption",
}

_ALLOWED_ATTRIBUTES = {
    # "rel" is managed by nh3's link_rel option; don't duplicate it here.
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "title", "width", "height", "loading"},
    "th": {"colspan", "rowspan", "align"},
    "td": {"colspan", "rowspan", "align"},
    "*": {"class"},
}

# Only allow safe URL schemes to block `javascript:` and `data:` exfiltration.
_LINK_REL = "noopener noreferrer nofollow"


def sanitize_html(html: str) -> str:
    """Sanitize untrusted HTML using an allowlist."""
    return nh3.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        link_rel=_LINK_REL,
        url_schemes={"http", "https", "mailto"},
        strip_comments=True,
    )


def render_markdown_safe(md: str) -> str:
    """Render Markdown to sanitized HTML."""
    import markdown as md_lib

    html = md_lib.markdown(
        md,
        extensions=["extra", "sane_lists", "nl2br"],
        output_format="html5",
    )
    return sanitize_html(html)
