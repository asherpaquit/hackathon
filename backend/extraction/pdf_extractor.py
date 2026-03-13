"""Primary PDF text/table extraction using pdfplumber.

For scanned/image pages, falls back to OCR pipeline.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pdfplumber

from extraction.page_classifier import classify_page, quality_score


# ── Section detection patterns ──────────────────────────────────────────────

ORIGIN_HEADER_RE = re.compile(
    r"^\s*ORIGIN\s*:\s*(.+?)$", re.IGNORECASE | re.MULTILINE
)
ORIGIN_VIA_RE = re.compile(
    r"^\s*ORIGIN\s+VIA\s*:\s*(.+?)$", re.IGNORECASE | re.MULTILINE
)
SCOPE_RE = re.compile(
    r"^\s*\[(.+?)\]\s*$", re.MULTILINE
)

# Contract header fields
CONTRACT_NO_RE = re.compile(r"SERVICE\s+CONTRACT\s+NO[.:]?\s*([A-Z0-9]+)|Contract\s+No[.:]?\s*([A-Z0-9]+)", re.IGNORECASE)
CARRIER_ABBREV_RE = re.compile(r"^([A-Z]{2,6})\s+SERVICE\s+CONTRACT", re.MULTILINE)
CARRIER_NAME_RE = re.compile(r"(?:CARRIER[\"']*\s+means?\s+|called\s+[\"']\s*CARRIER\s*[\"']\s+and\s+)([A-Za-z][\w\s,]+?)(?:\s*[,(]|\s+act)", re.IGNORECASE)
EFFECTIVE_RE = re.compile(r"Effective\s+Date\s+(\d{1,2}\s+\w+[,.]?\s*\d{4})", re.IGNORECASE)
EXPIRY_RE = re.compile(r"Expir(?:ation|y)\s+Date[:\s]+(\d{1,2}\s+\w+[,.]?\s*\d{4})", re.IGNORECASE)
COMMODITY_RE = re.compile(r"Commodity\s*:\s*(.+?)(?:\n|$)", re.IGNORECASE)

# Surcharge patterns
SURCHARGE_SECTION_RE = re.compile(
    r"(surcharge|subject to|inclusive|AMS|HEA|AGW|RDS|red sea)", re.IGNORECASE
)

# Arbitrary section marker
ARBITRARY_RE = re.compile(
    r"(ORIGIN|DESTINATION)\s+ARBITRAR", re.IGNORECASE
)


def extract_pdf(pdf_path: str) -> dict[str, Any]:
    """
    Extract all content from a freight contract PDF.

    Returns:
        {
          "metadata": {...},
          "pages_total": int,
          "sections": [{"origin", "origin_via", "scope", "raw_text", "tables": [...]}],
          "surcharge_text": str,
          "origin_arb_sections": [...],
          "dest_arb_sections": [...],
        }
    """
    path = Path(pdf_path)
    result = {
        "metadata": {},
        "pages_total": 0,
        "sections": [],
        "surcharge_text": "",
        "origin_arb_sections": [],
        "dest_arb_sections": [],
    }

    with pdfplumber.open(path) as pdf:
        result["pages_total"] = len(pdf.pages)
        all_text_parts: list[str] = []
        page_texts: list[str] = []

        for i, page in enumerate(pdf.pages):
            classification = classify_page(page)

            if classification == "text":
                text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
                page_texts.append(text)
                all_text_parts.append(text)
            elif classification == "image":
                text = _ocr_page(page)
                page_texts.append(text)
                all_text_parts.append(text)
            else:
                page_texts.append("")

        full_text = "\n".join(all_text_parts)

        # Extract contract metadata from first few pages
        result["metadata"] = _extract_metadata(full_text[:3000])

        # Split into rate sections and arbitrary sections
        _split_sections(full_text, result, pdf)

    return result


def _ocr_page(page) -> str:
    """Fallback OCR for image-based pages. Uses Claude Vision if available."""
    try:
        import shutil
        import io
        from PIL import Image

        img = page.to_image(resolution=200).original

        if shutil.which("tesseract"):
            import pytesseract
            return pytesseract.image_to_string(img, config="--oem 3 --psm 6")

        # Claude Vision fallback handled upstream via raw image bytes
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return f"[IMAGE_PAGE_BYTES:{buf.getvalue().hex()[:40]}...]"

    except Exception as e:
        return f"[OCR_ERROR: {e}]"


def _extract_metadata(text: str) -> dict:
    meta = {}

    m = CONTRACT_NO_RE.search(text)
    if m:
        meta["contract_id"] = (m.group(1) or m.group(2) or "").strip()
    else:
        meta["contract_id"] = ""

    # Carrier: try abbreviation from first line, then full name
    m = CARRIER_ABBREV_RE.search(text)
    meta["carrier"] = m.group(1).strip() if m else ""
    if not meta["carrier"]:
        m = CARRIER_NAME_RE.search(text)
        meta["carrier"] = m.group(1).strip() if m else ""

    m = EFFECTIVE_RE.search(text)
    meta["effective_date"] = m.group(1).strip().replace(",", "") if m else ""

    m = EXPIRY_RE.search(text)
    meta["expiration_date"] = m.group(1).strip().replace(",", "") if m else ""

    m = COMMODITY_RE.search(text)
    meta["commodity"] = m.group(1).strip() if m else ""

    return meta


def _split_sections(full_text: str, result: dict, pdf) -> None:
    """
    Walk the full text to carve out:
    - Rate sections (grouped by ORIGIN header)
    - Surcharge paragraphs
    - Origin/Destination arbitrary sections
    """
    lines = full_text.split("\n")
    current_scope = ""
    current_origin = ""
    current_origin_via = ""
    current_lines: list[str] = []
    in_arb = None  # "ORIGIN" | "DESTINATION" | None

    surcharge_lines: list[str] = []

    def flush_section():
        if current_origin and current_lines:
            raw = "\n".join(current_lines)
            tables = _parse_rate_table_from_text(raw)
            result["sections"].append({
                "origin": current_origin,
                "origin_via": current_origin_via,
                "scope": current_scope,
                "raw_text": raw,
                "tables": tables,
            })

    arb_current_lines: list[str] = []
    arb_type = None

    def flush_arb():
        if arb_type and arb_current_lines:
            raw = "\n".join(arb_current_lines)
            entry = {"type": arb_type, "raw_text": raw}
            if arb_type == "ORIGIN":
                result["origin_arb_sections"].append(entry)
            else:
                result["dest_arb_sections"].append(entry)

    for line in lines:
        stripped = line.strip()

        # Detect scope header like [NORTH AMERICA - ASIA (WB)]
        scope_m = SCOPE_RE.match(stripped)
        if scope_m:
            current_scope = scope_m.group(1).strip()
            continue

        # Detect arbitrary section start
        arb_m = ARBITRARY_RE.search(stripped)
        if arb_m:
            flush_section()
            flush_arb()
            current_origin = ""
            current_origin_via = ""
            current_lines = []
            arb_type = arb_m.group(1).upper()
            arb_current_lines = [line]
            in_arb = arb_type
            continue

        if in_arb:
            arb_current_lines.append(line)
            continue

        # Detect ORIGIN header
        origin_m = ORIGIN_HEADER_RE.match(stripped)
        if origin_m:
            flush_section()
            current_origin = origin_m.group(1).strip()
            current_origin_via = ""
            current_lines = []
            continue

        # Detect ORIGIN VIA
        via_m = ORIGIN_VIA_RE.match(stripped)
        if via_m:
            current_origin_via = via_m.group(1).strip()
            continue

        # Detect surcharge text
        if SURCHARGE_SECTION_RE.search(stripped):
            surcharge_lines.append(stripped)

        if current_origin:
            current_lines.append(line)

    flush_section()
    flush_arb()
    result["surcharge_text"] = "\n".join(surcharge_lines)


def _parse_rate_table_from_text(text: str) -> list[dict]:
    """
    Parse destination rate rows from a section's raw text.
    Each row typically: Destination | Country | Dest Via | Country | Term | Type | Cur | 20' | 40' | 40HC | 45' | Note
    Returns list of raw-parsed dicts (before Claude normalization).
    """
    rows = []
    for line in text.split("\n"):
        parts = line.split()
        if not parts:
            continue
        # Heuristic: rows with numbers that look like rates (3-5 digit USD)
        numeric_parts = [p for p in parts if re.match(r"^\d{2,5}$", p)]
        if len(numeric_parts) >= 2:
            rows.append({"raw_line": line.strip()})
    return rows
