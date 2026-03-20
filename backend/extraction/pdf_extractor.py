"""PDF extraction: pdfplumber primary (fast, no PyTorch) with Docling fallback for scans."""

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

# Service-type parens at the END of an origin string: (CY), (CY/CY), (CFS), (FCL), (cy/cy) …
# Handles upper and mixed case.  Applied first so later regexes don't see the parens.
_ORIGIN_SERVICE_PARENS_RE = re.compile(r"\s*\([A-Za-z/]+\)\s*$")
# Strips US/CA/AU/etc. 2-letter state/province code after a comma: ", CA", ", BC", ", NSW"
_ORIGIN_STATE_RE          = re.compile(r",\s*[A-Z]{2}\s*$")
# Strips written country name after a comma: ", UNITED STATES", ", CHINA", ", TAIWAN"
# Requires ≥3 chars total after the first capital so 2-letter codes aren't matched here.
_ORIGIN_COUNTRY_RE        = re.compile(r",\s*[A-Z][A-Za-z ]{2,}$")
SCOPE_RE          = re.compile(r"^\s*\[(.+?)\]\s*$",                re.MULTILINE)
ARBITRARY_RE      = re.compile(r"(ORIGIN|DESTINATION)\s+ARBITRAR",  re.IGNORECASE)
SURCHARGE_RE      = re.compile(r"(surcharge|subject to|inclusive|AMS|HEA|AGW|RDS|red sea)", re.IGNORECASE)

# Matches "1) COMMODITY : Wood pulp..." or "COMMODITY : Beer, Chilled"
# These lines appear BEFORE the ORIGIN: header and carry the commodity context.
COMMODITY_HDR_RE  = re.compile(r"^\s*(?:\d+\)\s*)?COMMODITY\s*[:\-]\s*(.+)$", re.IGNORECASE)

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
    Uses pdfplumber (fast, no heavy deps) as primary.
    Falls back to Docling only if pdfplumber finds mostly image pages.
    """
    try:
        result = _extract_with_pdfplumber(pdf_path)
        total_text = sum(len(s.get("raw_text", "")) for s in result.get("sections", []))
        if total_text < 100 and result.get("pages_total", 0) > 2:
            logger.info("[pdf_extractor] pdfplumber found almost no text — trying Docling for OCR")
            try:
                return _extract_with_docling(pdf_path)
            except ImportError:
                logger.warning("[pdf_extractor] Docling not installed — returning pdfplumber result as-is. "
                               "Install optional deps (docling, easyocr) for scanned PDF support.")
            except Exception as e:
                logger.warning(f"[pdf_extractor] Docling failed ({e}) — returning pdfplumber result")
        return result
    except Exception as e:
        logger.warning(f"[pdf_extractor] pdfplumber failed ({e}) — trying Docling")
        try:
            return _extract_with_docling(pdf_path)
        except ImportError:
            logger.error("[pdf_extractor] Docling not installed. Install optional deps for scanned PDF support.")
            raise RuntimeError(
                "Could not extract text from PDF. "
                "For scanned PDFs install: docling easyocr (see requirements.txt)"
            ) from e
        except Exception as e2:
            logger.error(f"[pdf_extractor] Both extractors failed: {e2}")
            raise


# ── pdfplumber primary path (FAST — no PyTorch, no AI models) ────────────────

def _get_page_count_fast(pdf_path: str) -> int:
    """Use pypdf for instant page count — no full parse needed."""
    try:
        from pypdf import PdfReader
        return len(PdfReader(pdf_path).pages)
    except Exception:
        return 0


def _extract_with_pdfplumber(pdf_path: str) -> dict[str, Any]:
    import pdfplumber

    path = Path(pdf_path)
    result: dict[str, Any] = {
        "metadata":            {},
        "pages_total":         _get_page_count_fast(pdf_path),  # fast pre-count
        "sections":            [],
        "surcharge_text":      "",
        "origin_arb_sections": [],
        "dest_arb_sections":   [],
        "rules_text":          "",       # Sections 7-12 text for LLM rules extraction
        "_docling":            False,
    }

    elements: list[dict] = []

    with pdfplumber.open(path) as pdf:
        result["pages_total"] = len(pdf.pages)

        for page_num, page in enumerate(pdf.pages, 1):
            # Extract text and split into individual lines so that the section
            # splitter (designed for Docling's per-block output) can match
            # ORIGIN:, [SCOPE], and COMMODITY: patterns that appear mid-page.
            text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
            for line in text.split("\n"):
                line = line.strip()
                if line:
                    elements.append({"type": "text", "page": page_num, "y": 0, "data": line})

            # Multi-strategy table extraction (PDF Skill technique):
            # try three strategies in order and keep the one with the most data.
            tables = _extract_tables_best_strategy(page)

            for tbl in (tables or []):
                grid = _clean_pdfplumber_table(tbl)
                if grid and len(grid) >= 2:
                    elements.append({"type": "table", "page": page_num, "y": 50, "data": grid})

    if not elements:
        return result

    full_text = "\n".join(e["data"] for e in elements if e["type"] == "text")
    result["metadata"] = _extract_metadata(full_text[:3000])
    _split_sections_from_elements(elements, result)

    # ── Extract sections 7-12 text for LLM rules extraction ──────────────────
    # Find the last page containing an ORIGIN: header (end of rate sections).
    # Everything after that is sections 7-12 (duration, provisions, exceptions).
    last_origin_page = 0
    for e in elements:
        if e["type"] == "text" and ORIGIN_HEADER_RE.match(e["data"]):
            last_origin_page = e["page"]
    # Also consider the last page of arbitraries
    last_arb_page = 0
    for e in elements:
        if e["type"] == "text" and ARBITRARY_RE.search(e["data"]):
            last_arb_page = e["page"]
    cutoff_page = max(last_origin_page, last_arb_page)
    if cutoff_page > 0:
        rules_lines = [
            e["data"] for e in elements
            if e["type"] == "text" and e["page"] > cutoff_page
        ]
        result["rules_text"] = "\n".join(rules_lines)
        if rules_lines:
            logger.info(f"[pdf_extractor] Collected {len(rules_lines)} lines of rules text "
                        f"from pages {cutoff_page+1}–{result['pages_total']}")

    return result


def _extract_tables_best_strategy(page) -> list:
    """
    Try three extraction strategies and return whichever finds the most data.
    Based on PDF Skill reference.md — pdfplumber multi-strategy extraction.
    Strategy 1: line-based  — best for tables with explicit borders (most freight PDFs).
    Strategy 2: text-based  — best for borderless column-aligned tables.
    Strategy 3: hybrid      — lines for vertical, text for horizontal (mixed layouts).
    """
    def _non_empty_cells(tables):
        return sum(1 for t in tables for row in t for cell in row if cell and str(cell).strip())

    strategies = [
        {   # Strategy 1: explicit grid lines
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
            "snap_tolerance": 5,
            "join_tolerance": 5,
            "min_words_vertical": 2,
            "min_words_horizontal": 1,
        },
        {   # Strategy 2: whitespace / text column alignment
            "vertical_strategy": "text",
            "horizontal_strategy": "text",
            "snap_tolerance": 5,
            "min_words_vertical": 2,
            "min_words_horizontal": 1,
        },
        {   # Strategy 3: hybrid — line-split rows, text-split columns
            "vertical_strategy": "lines",
            "horizontal_strategy": "text",
            "snap_tolerance": 4,
            "join_tolerance": 4,
            "min_words_vertical": 1,
            "min_words_horizontal": 1,
        },
    ]

    best, best_score = [], 0
    for settings in strategies:
        try:
            tables = page.extract_tables(settings) or []
            score = _non_empty_cells(tables)
            if score > best_score:
                best, best_score = tables, score
        except Exception:
            continue
    return best


def _clean_pdfplumber_table(table: list[list]) -> list[list[str]]:
    """Clean pdfplumber table output into string grid."""
    if not table:
        return []
    clean = []
    for row in table:
        if row is None:
            continue
        clean_row = []
        for cell in row:
            clean_row.append(str(cell).strip() if cell is not None else "")
        # Skip completely empty rows
        if any(c for c in clean_row):
            clean.append(clean_row)
    return clean


# ── Docling fallback (for scanned/image PDFs only) ──────────────────────────

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
        PdfPipelineOptions, TableFormerMode,
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
        pipeline_options.table_structure_options.mode = TableFormerMode.FAST
        pipeline_options.generate_page_images         = False
        pipeline_options.generate_picture_images      = False

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
        "rules_text":          "",
        "_docling":            True,
    }
    _split_sections_from_elements(elements, result)

    # Extract sections 7-12 text (same logic as pdfplumber path)
    last_origin_page = 0
    for e in elements:
        if e["type"] == "text" and ORIGIN_HEADER_RE.match(e["data"]):
            last_origin_page = e["page"]
    last_arb_page = 0
    for e in elements:
        if e["type"] == "text" and ARBITRARY_RE.search(e["data"]):
            last_arb_page = e["page"]
    cutoff_page = max(last_origin_page, last_arb_page)
    if cutoff_page > 0:
        rules_lines = [e["data"] for e in elements if e["type"] == "text" and e["page"] > cutoff_page]
        result["rules_text"] = "\n".join(rules_lines)

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


# ── Origin/Via name cleaner ──────────────────────────────────────────────────

def _clean_origin_name(raw: str) -> str:
    """
    Strip noise from ORIGIN header values so only the city/port name remains.
    Designed to be generic — handles all common freight contract formats.

    Examples (all real formats seen in the wild):
      "LOS ANGELES, CA, UNITED STATES(CY)"  → "LOS ANGELES"
      "LOS ANGELES, CA, UNITED STATES (CY)" → "LOS ANGELES"
      "SHANGHAI, CHINA(CY/CY)"              → "SHANGHAI"
      "SHANGHAI, CN"                        → "SHANGHAI"
      "YANTIAN, GUANGDONG, CN"              → "YANTIAN"
      "BUSAN, KR"                           → "BUSAN"
      "LOS ANGELES, CA"                     → "LOS ANGELES"
      "NINGBO"                              → "NINGBO"
      "NEW YORK/NEW JERSEY"                 → "NEW YORK/NEW JERSEY"
    """
    if not raw or not raw.strip():
        return raw

    s = raw.strip().upper()

    # 1. Remove trailing service-type parens: (CY), (CY/CY), (CFS/CY), (FCL), etc.
    #    Handles both "...(CY)" and "... (CY)" (with or without leading space)
    s = _ORIGIN_SERVICE_PARENS_RE.sub("", s).strip()

    # 2. Remove written country name: ", UNITED STATES", ", CHINA", ", TAIWAN"
    #    Pattern requires ≥3 chars after first capital so 2-letter codes aren't matched here.
    s = _ORIGIN_COUNTRY_RE.sub("", s).strip()

    # 3. Remove 2-letter state/province code: ", CA", ", TX", ", BC", ", KR", etc.
    s = _ORIGIN_STATE_RE.sub("", s).strip()

    # 4. Take the first comma-delimited segment.
    #    Handles any residual ", PROVINCE" or ", SUBREGION" leftovers.
    city = s.split(",")[0].strip()

    # Safety: never return empty string — fall back to the cleaned (uppercased) value
    return city if city else s


# ── Shared section splitting ─────────────────────────────────────────────────

def _split_sections_from_elements(elements: list[dict], result: dict) -> None:
    """Walk sorted elements to build sections, arbitraries, and surcharge text."""
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
    # Buffer for consecutive ORIGIN: headers that share one rate table
    pending_origins: list[tuple[str, str]] = []  # (origin, via) pairs
    # Commodity lines that appear BEFORE the first ORIGIN: on a page.
    # They are prepended to the next section's raw_text so that
    # _infer_section_commodity() and the carry-forward in extract_with_ollama
    # can propagate the commodity and dates to the correct sections.
    pending_commodity_lines: list[str] = []

    def flush_section():
        nonlocal current_origin, current_via, current_texts, current_tables
        nonlocal pending_origins, pending_commodity_lines
        if current_origin and (current_texts or current_tables):
            # Prepend any pending commodity lines so they appear in raw_text.
            all_text = pending_commodity_lines + current_texts
            # Emit one section per pending origin (all share the same table/text)
            all_origins = pending_origins + [(current_origin, current_via)]
            for orig, via in all_origins:
                result["sections"].append({
                    "origin":     orig,
                    "origin_via": via,
                    "scope":      current_scope,
                    "raw_text":   "\n".join(all_text),
                    "tables":     list(current_tables),
                })
        pending_origins = []
        pending_commodity_lines = []
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

        # ── Scope header: "[NORTH AMERICA - ASIA (WB)]" ──────────────────────
        # Now that pages are split into individual lines this matches correctly.
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

        # ── ORIGIN: header ────────────────────────────────────────────────────
        origin_m = ORIGIN_HEADER_RE.match(text)
        if origin_m:
            new_origin = _clean_origin_name(origin_m.group(1))
            if current_origin and not (current_texts or current_tables):
                # Consecutive ORIGIN: headers with no content yet — buffer this one
                pending_origins.append((current_origin, current_via))
            else:
                flush_section()
            current_origin = new_origin
            current_via    = ""
            in_arb         = None
            continue

        via_m = ORIGIN_VIA_RE.match(text)
        if via_m:
            # Via lines also often have country/state suffixes — clean them too
            current_via = _clean_origin_name(via_m.group(1))
            continue

        # ── Commodity header: "1) COMMODITY : Wood pulp..." ──────────────────
        # These appear BEFORE the ORIGIN: line on each commodity group page.
        # Store in pending_commodity_lines so the subsequent section can find them.
        cmdt_m = COMMODITY_HDR_RE.match(text)
        if cmdt_m:
            if current_origin:
                # Already inside a section — add normally (also stored below)
                current_texts.append(text)
            else:
                # Before any ORIGIN: header — buffer for the next section
                pending_commodity_lines.append(text)
            continue

        if SURCHARGE_RE.search(text):
            surcharge_lines.append(text)

        if current_origin:
            current_texts.append(text)

    flush_section()
    flush_arb()
    result["surcharge_text"] = "\n".join(surcharge_lines)


# ── Metadata extraction ──────────────────────────────────────────────────────

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
