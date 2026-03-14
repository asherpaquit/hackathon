"""PDF extraction using Docling (whole-document, cached) with pdfplumber fallback."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("pdf_extractor")

# ── Section detection patterns ────────────────────────────────────────────────
ORIGIN_HEADER_RE  = re.compile(r"^\s*ORIGIN\s*:\s*(.+?)$",         re.IGNORECASE | re.MULTILINE)
ORIGIN_VIA_RE     = re.compile(r"^\s*ORIGIN\s+VIA\s*:\s*(.+?)$",   re.IGNORECASE | re.MULTILINE)
SCOPE_RE          = re.compile(r"^\s*\[(.+?)\]\s*$",                re.MULTILINE)
ARBITRARY_RE      = re.compile(r"(ORIGIN|DESTINATION)\s+ARBITRAR",  re.IGNORECASE)
SURCHARGE_RE      = re.compile(r"(surcharge|subject to|inclusive|AMS|HEA|AGW|RDS|red sea)", re.IGNORECASE)

# Contract header patterns
CONTRACT_NO_RE    = re.compile(r"SERVICE\s+CONTRACT\s+NO[.:]?\s*([A-Z0-9]+)|Contract\s+No[.:]?\s*([A-Z0-9]+)", re.IGNORECASE)
CARRIER_ABBREV_RE = re.compile(r"^([A-Z]{2,6})\s+SERVICE\s+CONTRACT", re.MULTILINE)
CARRIER_NAME_RE   = re.compile(r"(?:CARRIER[\"']*\s+means?\s+|called\s+[\"']\s*CARRIER\s*[\"']\s+and\s+)([A-Za-z][\w\s,]+?)(?:\s*[,(]|\s+act)", re.IGNORECASE)
EFFECTIVE_RE      = re.compile(r"Effective\s+Date\s+(\d{1,2}\s+\w+[,.]?\s*\d{4})",        re.IGNORECASE)
EXPIRY_RE         = re.compile(r"Expir(?:ation|y)\s+Date[:\s]+(\d{1,2}\s+\w+[,.]?\s*\d{4})", re.IGNORECASE)
COMMODITY_RE      = re.compile(r"Commodity\s*:\s*(.+?)(?:\n|$)",    re.IGNORECASE)


# ── Public entry point ────────────────────────────────────────────────────────

def extract_pdf(pdf_path: str) -> dict[str, Any]:
    """
    Extract all content from a freight contract PDF.
    Tries Docling first (structured table grids + OCR), falls back to pdfplumber.
    Docling raw output is cached to disk — re-processing the same PDF is instant.
    """
    try:
        return _extract_with_docling(pdf_path)
    except ImportError:
        logger.info("[pdf_extractor] Docling not installed — using pdfplumber fallback")
        return _extract_with_pdfplumber(pdf_path)
    except Exception as e:
        logger.warning(f"[pdf_extractor] Docling failed ({e}) — using pdfplumber fallback")
        return _extract_with_pdfplumber(pdf_path)


# ── Docling path ──────────────────────────────────────────────────────────────

def _pdf_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _extract_with_docling(pdf_path: str) -> dict[str, Any]:
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions, TableFormerMode, EasyOcrOptions,
    )

    path = Path(pdf_path)

    # ── Cache ─────────────────────────────────────────────────────────────────
    cache_dir  = path.parent / "_docling_cache"
    cache_dir.mkdir(exist_ok=True)
    cache_file = cache_dir / f"{_pdf_sha256(path)}_raw.json"

    if cache_file.exists():
        logger.info(f"[pdf_extractor] Docling cache hit → {cache_file.name}")
        with open(cache_file, encoding="utf-8") as f:
            elements = json.load(f)
    else:
        logger.info("[pdf_extractor] Running Docling on full PDF (first run)…")
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr                       = True
        pipeline_options.do_table_structure           = True
        pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE
        pipeline_options.generate_page_images         = True
        pipeline_options.generate_picture_images      = False
        pipeline_options.ocr_options                  = EasyOcrOptions(lang=["en"])

        converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
        )
        conv_result = converter.convert(str(path))
        doc_dict    = conv_result.document.export_to_dict()
        elements    = _build_elements(doc_dict)

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(elements, f, ensure_ascii=False)
        logger.info(f"[pdf_extractor] Docling cache saved → {cache_file.name}")

    pages_total = max((e["page"] for e in elements), default=1)
    full_text   = "\n".join(e["data"] for e in elements if e["type"] == "text")

    result: dict[str, Any] = {
        "metadata":            _extract_metadata(full_text[:3000]),
        "pages_total":         pages_total,
        "sections":            [],
        "surcharge_text":      "",
        "origin_arb_sections": [],
        "dest_arb_sections":   [],
        "_docling":            True,
    }
    _split_sections_from_elements(elements, result)
    return result


def _build_elements(doc_dict: dict) -> list[dict]:
    """Convert Docling export dict → sorted list of {type, page, y, data} elements."""
    elements: list[dict] = []

    for tb in doc_dict.get("texts", []):
        raw = tb.get("text", "")
        if not raw and isinstance(tb.get("data"), dict):
            raw = tb["data"].get("text", "")
        raw = raw.strip()
        if not raw:
            continue
        prov = tb.get("prov", [{}])
        page = prov[0].get("page_no", 1) if prov else 1
        y    = prov[0].get("bbox", {}).get("t", 0) if prov else 0
        elements.append({"type": "text", "page": page, "y": y, "data": raw})

    for tbl in doc_dict.get("tables", []):
        grid = _normalize_grid(tbl.get("data", {}).get("grid", []))
        if not grid or all(all(c == "" for c in row) for row in grid):
            continue
        prov = tbl.get("prov", [{}])
        page = prov[0].get("page_no", 1) if prov else 1
        y    = prov[0].get("bbox", {}).get("t", 0) if prov else 0
        elements.append({"type": "table", "page": page, "y": y, "data": grid})

    # Sort top-to-bottom per page (Docling uses screen coords: t=0 at top, increases down)
    elements.sort(key=lambda e: (e["page"], e["y"]))
    return elements


def _normalize_grid(grid: list) -> list[list[str]]:
    clean = []
    for row in grid:
        clean_row = []
        for cell in row:
            if isinstance(cell, dict):
                clean_row.append(cell.get("text", "").strip())
            else:
                clean_row.append(str(cell).strip())
        clean.append(clean_row)
    return clean


def _split_sections_from_elements(elements: list[dict], result: dict) -> None:
    """Walk sorted Docling elements to build sections, arbitraries, and surcharge text."""
    current_scope   = ""
    current_origin  = ""
    current_via     = ""
    current_texts:  list[str]             = []
    current_tables: list[list[list[str]]] = []
    in_arb          = None
    arb_type        = None
    arb_texts:      list[str]             = []
    arb_tables:     list[list[list[str]]] = []
    surcharge_lines: list[str]            = []

    def flush_section():
        nonlocal current_origin, current_via, current_texts, current_tables
        if current_origin and (current_texts or current_tables):
            result["sections"].append({
                "origin":     current_origin,
                "origin_via": current_via,
                "scope":      current_scope,
                "raw_text":   "\n".join(current_texts),
                "tables":     list(current_tables),
            })
        current_origin = ""
        current_via    = ""
        current_texts  = []
        current_tables = []

    def flush_arb():
        nonlocal arb_type, arb_texts, arb_tables
        if arb_type and (arb_texts or arb_tables):
            entry = {
                "type":     arb_type,
                "raw_text": "\n".join(arb_texts),
                "tables":   list(arb_tables),
            }
            if arb_type == "ORIGIN":
                result["origin_arb_sections"].append(entry)
            else:
                result["dest_arb_sections"].append(entry)
        arb_type   = None
        arb_texts  = []
        arb_tables = []

    for elem in elements:
        if elem["type"] == "table":
            if in_arb:
                arb_tables.append(elem["data"])
            elif current_origin:
                current_tables.append(elem["data"])
            continue

        text = elem["data"]

        scope_m = SCOPE_RE.match(text)
        if scope_m:
            current_scope = scope_m.group(1).strip()
            continue

        arb_m = ARBITRARY_RE.search(text)
        if arb_m:
            flush_section()
            flush_arb()
            in_arb    = arb_m.group(1).upper()
            arb_type  = in_arb
            arb_texts = [text]
            continue

        if in_arb:
            arb_texts.append(text)
            if SURCHARGE_RE.search(text):
                surcharge_lines.append(text)
            continue

        origin_m = ORIGIN_HEADER_RE.match(text)
        if origin_m:
            flush_section()
            current_origin = origin_m.group(1).strip()
            current_via    = ""
            in_arb         = None
            continue

        via_m = ORIGIN_VIA_RE.match(text)
        if via_m:
            current_via = via_m.group(1).strip()
            continue

        if SURCHARGE_RE.search(text):
            surcharge_lines.append(text)

        if current_origin:
            current_texts.append(text)

    flush_section()
    flush_arb()
    result["surcharge_text"] = "\n".join(surcharge_lines)


# ── pdfplumber fallback ───────────────────────────────────────────────────────

def _extract_with_pdfplumber(pdf_path: str) -> dict[str, Any]:
    import pdfplumber
    from extraction.page_classifier import classify_page

    path = Path(pdf_path)
    result: dict[str, Any] = {
        "metadata":            {},
        "pages_total":         0,
        "sections":            [],
        "surcharge_text":      "",
        "origin_arb_sections": [],
        "dest_arb_sections":   [],
        "_docling":            False,
    }

    with pdfplumber.open(path) as pdf:
        result["pages_total"] = len(pdf.pages)
        all_text_parts: list[str] = []
        for page in pdf.pages:
            classification = classify_page(page)
            if classification == "text":
                text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
            elif classification == "image":
                text = _ocr_page(page)
            else:
                text = ""
            all_text_parts.append(text)

        full_text = "\n".join(all_text_parts)
        result["metadata"] = _extract_metadata(full_text[:3000])
        _split_sections_text(full_text, result)

    return result


def _ocr_page(page) -> str:
    try:
        import shutil
        import io
        from PIL import Image

        img = page.to_image(resolution=200).original
        if shutil.which("tesseract"):
            import pytesseract
            return pytesseract.image_to_string(img, config="--oem 3 --psm 6")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return f"[IMAGE_PAGE_BYTES:{buf.getvalue().hex()[:40]}...]"
    except Exception as e:
        return f"[OCR_ERROR: {e}]"


def _extract_metadata(text: str) -> dict:
    meta: dict[str, str] = {}

    m = CONTRACT_NO_RE.search(text)
    meta["contract_id"] = (m.group(1) or m.group(2) or "").strip() if m else ""

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


def _split_sections_text(full_text: str, result: dict) -> None:
    """Original text-based section splitting for the pdfplumber fallback path."""
    lines           = full_text.split("\n")
    current_scope   = ""
    current_origin  = ""
    current_via     = ""
    current_lines:  list[str] = []
    in_arb          = None
    arb_type        = None
    arb_lines:      list[str] = []
    surcharge_lines: list[str] = []

    def flush_section():
        nonlocal current_origin, current_via, current_lines
        if current_origin and current_lines:
            result["sections"].append({
                "origin":     current_origin,
                "origin_via": current_via,
                "scope":      current_scope,
                "raw_text":   "\n".join(current_lines),
                "tables":     [],
            })
        current_origin = ""
        current_via    = ""
        current_lines  = []

    def flush_arb():
        nonlocal arb_type, arb_lines
        if arb_type and arb_lines:
            entry = {"type": arb_type, "raw_text": "\n".join(arb_lines), "tables": []}
            if arb_type == "ORIGIN":
                result["origin_arb_sections"].append(entry)
            else:
                result["dest_arb_sections"].append(entry)
        arb_type  = None
        arb_lines = []

    for line in lines:
        stripped = line.strip()

        scope_m = SCOPE_RE.match(stripped)
        if scope_m:
            current_scope = scope_m.group(1).strip()
            continue

        arb_m = ARBITRARY_RE.search(stripped)
        if arb_m:
            flush_section()
            flush_arb()
            in_arb    = arb_m.group(1).upper()
            arb_type  = in_arb
            arb_lines = [line]
            continue

        if in_arb:
            arb_lines.append(line)
            continue

        origin_m = ORIGIN_HEADER_RE.match(stripped)
        if origin_m:
            flush_section()
            current_origin = origin_m.group(1).strip()
            current_via    = ""
            in_arb         = None
            continue

        via_m = ORIGIN_VIA_RE.match(stripped)
        if via_m:
            current_via = via_m.group(1).strip()
            continue

        if SURCHARGE_RE.search(stripped):
            surcharge_lines.append(stripped)

        if current_origin:
            current_lines.append(line)

    flush_section()
    flush_arb()
    result["surcharge_text"] = "\n".join(surcharge_lines)
