"""Classify each PDF page as text, image, or blank."""

from __future__ import annotations

FREIGHT_KEYWORDS = {"origin", "destination", "carrier", "cy", "usd", "rate", "base"}


def classify_page(page) -> str:
    """Return 'text', 'image', or 'blank' for a pdfplumber page."""
    text = page.extract_text() or ""
    has_text = len(text.strip()) > 30

    # Check for keyword relevance (freight contract context)
    lower = text.lower()
    has_keywords = any(kw in lower for kw in FREIGHT_KEYWORDS)

    if has_text:
        return "text"

    # Check for images
    if page.images:
        return "image"

    return "blank"


def quality_score(text: str) -> float:
    """Simple heuristic: ratio of alphanumeric chars + keyword bonus."""
    if not text:
        return 0.0
    alnum = sum(c.isalnum() for c in text)
    ratio = alnum / len(text)
    lower = text.lower()
    keyword_bonus = sum(kw in lower for kw in FREIGHT_KEYWORDS) * 0.05
    return min(1.0, ratio + keyword_bonus)
