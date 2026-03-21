"""Pure NLP freight data extraction — no LLM or internet required."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("nlp_extractor")


# ── Surcharge NLP ─────────────────────────────────────────────────────────────

_SURCHARGE_KW: dict[str, re.Pattern] = {
    "ams_china_japan":     re.compile(r"\b(?:AMS|america\s+manifest(?:\s+system)?(?:\s+surcharge)?)\b", re.I),
    "hea_heavy_surcharge": re.compile(r"\b(?:HEA|heavy\s+(?:lift|cargo|equipment|surcharge))\b", re.I),
    "agw":                 re.compile(r"\b(?:AGW|arbitrary\s+gross\s+weight|arbitrary\s+weight)\b", re.I),
    "rds_red_sea":         re.compile(r"\b(?:RDS|red\s+sea(?:\s+surcharge)?|redex)\b", re.I),
}

_SURCHARGE_VAL_RE = re.compile(
    r"(?:USD?\s*\$?\s*|(?::\s*|=\s*))(\d[\d,]*(?:\.\d+)?)"
    r"|(\d[\d,]*(?:\.\d+)?)\s*(?:USD|per\s+(?:BL|B/L|container|unit))",
    re.I,
)
_INCLUSIVE_RE = re.compile(r"\b(?:INCLUSIVE|INCLUDED|INCL\.?)\b", re.I)
_TARIFF_RE    = re.compile(r"\b(?:AS\s+PER\s+TARIFF|TARIFF|AS\s+PER\s+RATE\s+TARIFF)\b", re.I)


def _extract_surcharges_regex(surcharge_text: str) -> dict:
    """Extract surcharge values with regex — no LLM needed."""
    result: dict = {}
    lines = surcharge_text.split("\n")
    for key, kw_re in _SURCHARGE_KW.items():
        for idx, line in enumerate(lines):
            if not kw_re.search(line):
                continue
            # Look ahead up to 3 lines for the surcharge value
            lookahead = [line] + [lines[idx + j] for j in range(1, 4) if idx + j < len(lines)]
            for candidate in lookahead:
                if _INCLUSIVE_RE.search(candidate):
                    result[key] = "INCLUSIVE"; break
                if _TARIFF_RE.search(candidate):
                    result[key] = "TARIFF"; break
                m = _SURCHARGE_VAL_RE.search(candidate)
                if m:
                    val_str = (m.group(1) or m.group(2) or "").replace(",", "")
                    try:
                        result[key] = float(val_str); break
                    except ValueError:
                        pass
            if key in result:
                break
    return result


# ── Metadata NLP ──────────────────────────────────────────────────────────────

_CONTRACT_ID_EXTRA = re.compile(
    r"(?:CONTRACT\s+(?:NUMBER|NO\.?|#)\s*[:\-]?\s*|REF(?:ERENCE)?\s+NO\.?\s*[:\-]?\s*)([A-Z0-9][\w\-]{3,})",
    re.I,
)
_CARRIER_COLON_RE = re.compile(
    r"(?:CONTRACTED?\s+)?CARRIER\s*[:\-]\s*([A-Za-z][\w\s,\.]+?)(?:\n|,|\.|;|$)",
    re.I,
)
_DATE_EXTRA = [
    re.compile(r"(?:Effective\s+Date[:\s]+|Eff\.\s+Date[:\s]+|From\s+Date[:\s]+)"
               r"(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})", re.I),
    re.compile(r"(?:Expir(?:ation|y)\s+Date[:\s]+|Exp\.?\s+Date[:\s]+|To\s+Date[:\s]+|Through[:\s]+)"
               r"(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})", re.I),
    re.compile(r"(?:Effective\s+Date[:\s]+|Eff\.\s+Date[:\s]+)"
               r"([A-Za-z]+ \d{1,2},? \d{4}|\d{1,2} [A-Za-z]+ \d{4})", re.I),
    re.compile(r"(?:Expir(?:ation|y)\s+Date[:\s]+|Exp\.?\s+Date[:\s]+)"
               r"([A-Za-z]+ \d{1,2},? \d{4}|\d{1,2} [A-Za-z]+ \d{4})", re.I),
]
# YYYYMMDD date format as found in "< NOTE FOR COMMODITY >" blocks
_DATE_YYYYMMDD_RE = re.compile(r"valid\s+from\s+(\d{4})(\d{2})(\d{2})\s+to\s+(\d{4})(\d{2})(\d{2})", re.I)

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _yyyymmdd_to_dmy(year: str, month: str, day: str) -> str:
    mon = _MONTHS[int(month) - 1]
    return f"{int(day)} {mon} {int(year)}"


def _extract_metadata_enhanced(text: str, existing: dict) -> dict:
    meta = dict(existing)

    if not meta.get("contract_id"):
        m = _CONTRACT_ID_EXTRA.search(text)
        if m:
            meta["contract_id"] = m.group(1).strip()

    if not meta.get("carrier"):
        m = _CARRIER_COLON_RE.search(text)
        if m:
            meta["carrier"] = m.group(1).strip()

    if not meta.get("effective_date"):
        m = _DATE_EXTRA[0].search(text) or _DATE_EXTRA[2].search(text)
        if m:
            meta["effective_date"] = m.group(1).strip().rstrip(",")

    if not meta.get("expiration_date"):
        m = _DATE_EXTRA[1].search(text) or _DATE_EXTRA[3].search(text)
        if m:
            meta["expiration_date"] = m.group(1).strip().rstrip(",")

    # YYYYMMDD dates from NOTE blocks (use first occurrence)
    if not meta.get("effective_date") or not meta.get("expiration_date"):
        m = _DATE_YYYYMMDD_RE.search(text)
        if m:
            if not meta.get("effective_date"):
                meta["effective_date"] = _yyyymmdd_to_dmy(m.group(1), m.group(2), m.group(3))
            if not meta.get("expiration_date"):
                meta["expiration_date"] = _yyyymmdd_to_dmy(m.group(4), m.group(5), m.group(6))

    return meta


# ── Column header → field mappings ────────────────────────────────────────────

_RATE_COL: dict[str, str] = {
    # ── 20' containers ──────────────────────────────────────────────────────────
    "20": "base_rate_20", "20'": "base_rate_20", '20"': "base_rate_20",
    "20ft": "base_rate_20", "20gp": "base_rate_20", "20'gp": "base_rate_20",
    "20st": "base_rate_20", "20'st": "base_rate_20",
    "20dc": "base_rate_20", "20'dc": "base_rate_20",
    "20dv": "base_rate_20", "20'dv": "base_rate_20",
    "teu": "base_rate_20",
    "r20": "base_rate_20", "rate20": "base_rate_20", "rate 20": "base_rate_20",
    "20'gp/dc": "base_rate_20",
    "d2": "base_rate_20",                           # ATL0347N25 code: D2 = 20'
    # ── 40' containers ──────────────────────────────────────────────────────────
    "40": "base_rate_40", "40'": "base_rate_40", '40"': "base_rate_40",
    "40ft": "base_rate_40", "40gp": "base_rate_40", "40'gp": "base_rate_40",
    "40dv": "base_rate_40", "40'dv": "base_rate_40",
    "40dc": "base_rate_40", "40'dc": "base_rate_40",
    "40st": "base_rate_40", "40'st": "base_rate_40",
    "feu": "base_rate_40",
    "r40": "base_rate_40", "rate40": "base_rate_40", "rate 40": "base_rate_40",
    "40'gp/dc": "base_rate_40",
    "d4": "base_rate_40",                           # ATL0347N25 code: D4 = 40'
    # ── 40HC containers ─────────────────────────────────────────────────────────
    "40hc": "base_rate_40h", "40h": "base_rate_40h", "40hq": "base_rate_40h",
    "40'hc": "base_rate_40h", "40'h": "base_rate_40h", "40'hq": "base_rate_40h",
    "40hicube": "base_rate_40h", "40hi": "base_rate_40h", "hc40": "base_rate_40h",
    "40'hi": "base_rate_40h", "40rhc": "base_rate_40h",
    "hc": "base_rate_40h", "hq": "base_rate_40h",
    "hi cube": "base_rate_40h", "high cube": "base_rate_40h", "highcube": "base_rate_40h",
    "40hc/hq": "base_rate_40h", "40'hc/hq": "base_rate_40h",
    "d5": "base_rate_40h",                          # ATL0347N25 code: D5 = 40'HC
    # ── 45' containers ──────────────────────────────────────────────────────────
    "45": "base_rate_45", "45'": "base_rate_45", '45"': "base_rate_45",
    "45ft": "base_rate_45", "45hc": "base_rate_45", "45'hc": "base_rate_45",
    "45hq": "base_rate_45", "45'hq": "base_rate_45",
    "d7": "base_rate_45",                           # ATL0347N25 code: D7 = 45'HC
    # ── Destination ─────────────────────────────────────────────────────────────
    "destination": "destination_city", "dest": "destination_city",
    "pod": "destination_city", "port of discharge": "destination_city",
    "portof discharge": "destination_city", "discharge port": "destination_city",
    "discharging port": "destination_city", "destination port": "destination_city",
    "del": "destination_city", "place of delivery": "destination_city",
    "final dest": "destination_city", "fpod": "destination_city",
    "delivery": "destination_city", "delivery point": "destination_city",
    "discharge": "destination_city", "unloading": "destination_city",
    "unloading port": "destination_city", "to port": "destination_city",
    "portname": "destination_city", "port name": "destination_city",
    "point": "destination_city",                    # ATL0347N25 arb table column
    # ── Via / transshipment ─────────────────────────────────────────────────────
    "via": "destination_via_city", "dest via": "destination_via_city",
    "destination via": "destination_via_city", "t/s": "destination_via_city",
    "t/s port": "destination_via_city", "transship": "destination_via_city",
    "tranship": "destination_via_city", "transhipment": "destination_via_city",
    "transshipment": "destination_via_city", "ts port": "destination_via_city",
    "t/s via": "destination_via_city", "via port": "destination_via_city",
    "trunk lane": "destination_via_city",           # ATL0347N25 arb table column
    # ── Service ─────────────────────────────────────────────────────────────────
    "service": "service", "term": "service",
    # "type" intentionally NOT mapped to service — in OLTK contracts the Type
    # column holds cargo type ("Dry", "RF") which overwrites the correct Term
    # value ("CY", "Door").  Map it to _ignore so Term wins.
    "type": "_ignore",
    "mode": "service", "service type": "service", "svc": "service",
    "move type": "service", "terms": "service", "incoterm": "service",
    "service lane": "service",                      # ATL0347N25 arb table column
    # ── Remarks / notes ─────────────────────────────────────────────────────────
    "remarks": "remarks", "remark": "remarks", "note": "remarks",
    "notes": "remarks", "comment": "remarks", "comments": "remarks",
    "direct call": "remarks", "directcall": "remarks",
    # ── Explicitly ignored ───────────────────────────────────────────────────────
    "cntry": "_ignore", "country": "_ignore",
    "cur": "_ignore", "currency": "_ignore", "ccy": "_ignore", "usd": "_ignore",
    "loading port": "_ignore", "pol": "_ignore",
    "no": "_ignore", "no.": "_ignore", "seq": "_ignore",
    "#": "_ignore", "item": "_ignore", "sr": "_ignore",
    "unit": "_ignore", "validity": "_ignore", "valid": "_ignore",
    "effective": "_ignore", "expiry": "_ignore",
    "40ot": "_ignore", "40fr": "_ignore",
    "cmdt": "_ignore",                              # commodity column in arb tables
    "box": "_ignore",                               # box type column
    "lane": "_ignore",                              # generic lane column
}

_ARB_ORIGIN_EXTRA: dict[str, str] = {
    "origin": "origin_city", "pol": "origin_city",
    "inland origin": "origin_city", "origin city": "origin_city",
    "origin point": "origin_city", "port of loading": "origin_city",
    "point": "origin_city",                         # ATL0347N25 arb column
    "via": "origin_via_city", "pol via": "origin_via_city",
    "trunk port": "origin_via_city",
    "trunk lane": "origin_via_city",                # ATL0347N25 arb column
    "service lane": "service",                      # ATL0347N25 arb column
    "agw 20": "agw_20", "agw20": "agw_20", "agw 20'": "agw_20",
    "agw 40": "agw_40", "agw40": "agw_40", "agw 40'": "agw_40",
    "agw 45": "agw_45", "agw45": "agw_45", "agw 45'": "agw_45",
    "cmdt": "_ignore", "direct call": "_ignore",    # ATL0347N25 ignore columns
}

_ARB_DEST_EXTRA: dict[str, str] = {
    "destination": "destination_city", "inland dest": "destination_city",
    "dest city": "destination_city", "delivery point": "destination_city",
    "point": "destination_city",                    # ATL0347N25 arb column
    "via": "destination_via_city", "trunk port": "destination_via_city",
    "trunk lane": "destination_via_city",           # ATL0347N25 arb column
    "service lane": "service",                      # ATL0347N25 arb column
    "cmdt": "_ignore", "direct call": "_ignore",    # ATL0347N25 ignore columns
}

# Handles plain numbers "360" and commodity/rate codes "R2/2298" → extracts 2298
_NUMERIC_RE = re.compile(r"(?:[A-Za-z]\d*/)?(\d[\d,]*(?:\.\d+)?)")

_RATE_BOUNDS: dict[str, tuple[float, float]] = {
    "base_rate_20":  (0.0, 30_000.0),
    "base_rate_40":  (0.0, 45_000.0),
    "base_rate_40h": (0.0, 48_000.0),
    "base_rate_45":  (0.0, 50_000.0),
    "agw_20":  (0.0, 6_000.0),
    "agw_40":  (0.0, 6_000.0),
    "agw_45":  (0.0, 6_000.0),
}

# Values that should be treated as rate = 0 (waived/free charges)
_WAIVED_VALUES = {"WAIVED", "FREE", "WAIVE", "GRATIS", "NIL", "INCLUDED"}


# ── Grid extraction ───────────────────────────────────────────────────────────

def _normalize_header_key(cell: str) -> str:
    s = (cell.lower().strip()
         .replace("\u2018", "'").replace("\u2019", "'")
         .replace("\u201c", '"').replace("\u201d", '"')
         .replace("\u2018", "'").replace("\u2019", "'"))
    s = re.sub(r"[:()\[\]]", "", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _match_row_to_colmap(
    row: list[str],
    col_source: dict[str, str],
    compact_source: dict[str, str],
) -> dict[int, str]:
    """Match a single row's cells against column name dictionaries."""
    col_map: dict[int, str] = {}
    for col_idx, cell in enumerate(row):
        if not cell or not cell.strip():
            continue
        key = _normalize_header_key(cell)

        if key in col_source:
            col_map[col_idx] = col_source[key]
            continue

        compact = re.sub(r"[^a-z0-9]", "", key)
        if compact in compact_source:
            col_map[col_idx] = compact_source[compact]
            continue

        tokens = re.split(r"[\s/'\"\-]+", key)
        for i, tok in enumerate(tokens):
            tok_compact = re.sub(r"[^a-z0-9]", "", tok)
            if tok_compact in compact_source:
                field = compact_source[tok_compact]
                if field.startswith(("base_rate", "destination", "origin", "via")):
                    col_map[col_idx] = field
                    break
            if i + 1 < len(tokens):
                pair = tok_compact + re.sub(r"[^a-z0-9]", "", tokens[i + 1])
                if pair in compact_source:
                    field = compact_source[pair]
                    if field.startswith(("base_rate", "destination", "origin", "via")):
                        col_map[col_idx] = field
                        break
    return col_map


def _detect_header_row(
    grid: list[list[str]],
    col_source: dict[str, str] | None = None,
) -> tuple[int, dict[int, str]]:
    if col_source is None:
        col_source = _RATE_COL

    compact_source = {re.sub(r"[^a-z0-9]", "", k): v for k, v in col_source.items()}

    # Pass 1: single-row header detection
    for row_idx, row in enumerate(grid[:15]):
        col_map = _match_row_to_colmap(row, col_source, compact_source)
        rate_fields = [v for v in col_map.values() if v.startswith("base_rate")]
        if len(rate_fields) >= 2:
            return row_idx, col_map

    # Pass 2: multi-row merged header detection
    # Some PDFs have 2-row spanning headers where row N has category labels
    # (e.g., "Container Type") and row N+1 has the actual column names
    # (e.g., "20'", "40'", "40HC"). Merge consecutive pairs and re-check.
    for row_idx in range(min(len(grid) - 1, 10)):
        row_a = grid[row_idx]
        row_b = grid[row_idx + 1]
        # Merge: for each column, prefer the non-empty cell from row_b,
        # falling back to row_a. This captures the more specific label.
        max_cols = max(len(row_a), len(row_b))
        merged: list[str] = []
        for ci in range(max_cols):
            cell_a = row_a[ci].strip() if ci < len(row_a) else ""
            cell_b = row_b[ci].strip() if ci < len(row_b) else ""
            # Prefer the cell that has content; if both have content,
            # concatenate with space so "Container 20'" can match
            if cell_b and cell_a:
                merged.append(f"{cell_a} {cell_b}")
            else:
                merged.append(cell_b or cell_a)

        col_map = _match_row_to_colmap(merged, col_source, compact_source)
        # Also try row_b alone (it might have the actual headers)
        col_map_b = _match_row_to_colmap(row_b, col_source, compact_source)
        # Use whichever found more rate columns
        rate_merged = [v for v in col_map.values() if v.startswith("base_rate")]
        rate_b = [v for v in col_map_b.values() if v.startswith("base_rate")]
        best_map = col_map if len(rate_merged) >= len(rate_b) else col_map_b
        best_rate_count = max(len(rate_merged), len(rate_b))

        if best_rate_count >= 2:
            # Data rows start after the second header row
            return row_idx + 1, best_map

    return -1, {}


def _extract_from_grid(
    grid: list[list[str]],
    context: dict,
    col_source: dict[str, str] | None = None,
) -> list[dict] | None:
    header_idx, col_map = _detect_header_row(grid, col_source)
    if header_idx == -1:
        return None

    rows: list[dict] = []
    for row in grid[header_idx + 1:]:
        if not any(c.strip() for c in row):
            continue

        row_dict = dict(context)
        has_rate = False

        for col_idx, field in col_map.items():
            if field == "_ignore":
                continue
            if col_idx >= len(row):
                continue
            cell = row[col_idx].strip()
            if not cell or cell in ("-", "—", "--", "N/A", "n/a", "TBN", "None"):
                continue

            if field.startswith("base_rate") or field.startswith("agw"):
                cell_upper = cell.upper().strip()
                if cell_upper in _WAIVED_VALUES:
                    row_dict[field] = 0.0
                    if field.startswith("base_rate"):
                        has_rate = True
                    continue
                m = _NUMERIC_RE.search(cell)
                if m:
                    try:
                        val = float(m.group(1).replace(",", ""))
                        bounds = _RATE_BOUNDS.get(field)
                        if bounds and not (bounds[0] <= val <= bounds[1]):
                            logger.debug(f"[rule] Rate out of bounds: {field}={val}")
                            continue
                        row_dict[field] = val
                        if field.startswith("base_rate"):
                            has_rate = True
                    except ValueError:
                        pass
            else:
                row_dict[field] = cell

        if has_rate:
            if not row_dict.get("service"):
                row_dict["service"] = "CY/CY"
            rows.append(row_dict)

    return rows if rows else None


# ── Text-line fallback ────────────────────────────────────────────────────────

# Tokens that signal the start of rate values (not part of city name)
_RATE_TOKEN_RE = re.compile(
    r"^(?:\d[\d,]*(?:\.\d+)?|N/A|TARIFF|INCLUSIVE|INCL\.?|WAIVED|FREE|NIL|-)$", re.I
)
# Header line contains ≥2 of these rate column keywords
_RATE_HDR_TOKEN_RE = re.compile(
    r"\b(20['\"]?|40['\"]?(?:HC|HQ|H)?|45['\"]?|D[2457]|TEU|FEU)\b", re.I
)
# Skip lines that are clearly column headers or separators
_SKIP_LINE_RE = re.compile(
    r"\b(SERVICE|TERM|MODE|CURRENCY|CUR|CNTRY|COUNTRY|REMARKS|REMARK|"
    r"DESTINATION|ORIGIN|VIA|TRUNK\s+LANE|SERVICE\s+LANE|POINT|BOX)\b",
    re.I,
)


def _extract_rates_from_text(text: str, context: dict) -> list[dict]:
    """
    Token-based fallback for rate extraction when no table grid is available.
    Finds a header line containing rate column keywords, then parses subsequent
    lines: leading alpha tokens → destination city, trailing numeric tokens → rates.
    """
    lines = [l for l in text.split("\n") if l.strip()]

    # Phase 1: find header line with ≥2 rate column keywords
    header_idx = -1
    header_fields: list[str] = []
    compact_source = {re.sub(r"[^a-z0-9]", "", k): v for k, v in _RATE_COL.items()}

    for i, line in enumerate(lines[:30]):
        fields: list[str] = []
        for m in _RATE_HDR_TOKEN_RE.finditer(line):
            tok_compact = re.sub(r"[^a-z0-9]", "", m.group(0).lower())
            f = compact_source.get(tok_compact)
            if f and f.startswith("base_rate"):
                fields.append(f)
        if len(fields) >= 2:
            header_idx = i
            header_fields = fields
            break

    if header_idx == -1:
        return []

    rows: list[dict] = []
    for line in lines[header_idx + 1:]:
        tokens = line.split()
        if not tokens or re.match(r"^[-=\s]+$", line):
            continue
        if _SKIP_LINE_RE.search(line):
            continue

        # Split: city tokens (alpha/mixed) then rate tokens (numeric/keywords)
        city_tokens: list[str] = []
        rate_tokens: list[str] = []
        in_rates = False

        for tok in tokens:
            if not in_rates and _RATE_TOKEN_RE.match(tok):
                in_rates = True
            if in_rates:
                rate_tokens.append(tok)
            else:
                city_tokens.append(tok)

        if not city_tokens or len(rate_tokens) < 2:
            continue

        dest = " ".join(city_tokens)
        # Skip header-like destinations
        if _SKIP_LINE_RE.search(dest):
            continue

        row = dict(context)
        row["destination_city"] = dest
        row.setdefault("service", "CY/CY")
        has_rate = False

        for i, field in enumerate(header_fields):
            if i >= len(rate_tokens):
                break
            val = rate_tokens[i]
            if val in ("-", "—", "N/A", "n/a"):
                continue
            if val.upper() == "TARIFF":
                row[field] = "TARIFF"; continue
            if val.upper() in ("INCLUSIVE", "INCL"):
                row[field] = "INCLUSIVE"; continue
            if val.upper() in _WAIVED_VALUES:
                row[field] = 0.0; has_rate = True; continue
            m = _NUMERIC_RE.search(val)
            if m:
                try:
                    num = float(m.group(1).replace(",", ""))
                    bounds = _RATE_BOUNDS.get(field)
                    if not bounds or bounds[0] <= num <= bounds[1]:
                        row[field] = num
                        has_rate = True
                except ValueError:
                    pass

        if has_rate:
            rows.append(row)

    return rows


# "Rates are valid to 20251231"  (end-only format used in LAX RF sections)
_DATE_VALID_TO_RE = re.compile(r"valid\s+to\s+(\d{4})(\d{2})(\d{2})", re.I)


def _extract_section_dates(
    section_text: str,
    fallback_effective: str,
    fallback_expiry: str,
) -> tuple[str, str]:
    """
    Extract validity dates from per-commodity NOTE blocks embedded in section text.

    Handles two formats used in OLTK contracts:
      "Rates are valid from 20250401 to 20250630"   → effective + expiry
      "Rates are valid to 20251231"                 → expiry only

    Falls back to the provided values when no NOTE dates are found.
    """
    # "valid from YYYYMMDD to YYYYMMDD" — full range
    m = _DATE_YYYYMMDD_RE.search(section_text)
    if m:
        eff = _yyyymmdd_to_dmy(m.group(1), m.group(2), m.group(3))
        exp = _yyyymmdd_to_dmy(m.group(4), m.group(5), m.group(6))
        return eff, exp

    # "valid to YYYYMMDD" — end date only
    m = _DATE_VALID_TO_RE.search(section_text)
    if m:
        exp = _yyyymmdd_to_dmy(m.group(1), m.group(2), m.group(3))
        return fallback_effective, exp

    return fallback_effective, fallback_expiry


# ── Context-aware table parsing ───────────────────────────────────────────────

# 1.  Per-section commodity inference
# Matches explicit commodity declarations embedded in section text.
_COMMODITY_INLINE_RE = re.compile(
    r"(?:"
    r"<\s*NOTE\s+FOR\s+COMMODITY[:\s]+"           # < NOTE FOR COMMODITY: FAK >
    r"|COMMODITY\s*[:\-]\s*"                        # COMMODITY: ALL CARGO
    r"|CMDT\s*[:\-]\s*"                             # CMDT: FAK
    r")([^\n<>]{2,80}?)(?:\s*>|\s*$)",
    re.I,
)

_COMMODITY_KW_RES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"freight\s+all\s+kinds?",   re.I), "FAK"),
    (re.compile(r"\bfak\b",                  re.I), "FAK"),
    (re.compile(r"all\s+cargo",              re.I), "ALL CARGO"),
    (re.compile(r"all\s+commodit",           re.I), "ALL CARGO"),
    (re.compile(r"general\s+cargo",          re.I), "GENERAL CARGO"),
    (re.compile(r"dangerous\s+goods?",       re.I), "HAZARDOUS"),
    (re.compile(r"\bimdg\b",                 re.I), "HAZARDOUS"),
    (re.compile(r"hazardous",                re.I), "HAZARDOUS"),
    (re.compile(r"\breefer\b",               re.I), "REEFER"),
    (re.compile(r"refrigerated",             re.I), "REEFER"),
    (re.compile(r"household\s+goods?",       re.I), "HOUSEHOLD GOODS"),
    (re.compile(r"personal\s+effects?",      re.I), "PERSONAL EFFECTS"),
    (re.compile(r"project\s+cargo",          re.I), "PROJECT CARGO"),
    (re.compile(r"\bnvocc\b",                re.I), "NVOCC"),
    (re.compile(r"automotive",               re.I), "AUTOMOTIVE"),
    (re.compile(r"electronics?",             re.I), "ELECTRONICS"),
    (re.compile(r"garments?",                re.I), "GARMENT"),
    (re.compile(r"textiles?",                re.I), "TEXTILE"),
    (re.compile(r"machin(?:ery|es?)",        re.I), "MACHINERY"),
    (re.compile(r"chemical",                 re.I), "CHEMICAL"),
    (re.compile(r"furniture",                re.I), "FURNITURE"),
]

# 2.  Via / transshipment inference from free text
#     Matches: "VIA SINGAPORE", "ROUTING VIA: HK", "T/S AT KAOHSIUNG", "T/S BUSAN"
_VIA_TEXT_RE = re.compile(
    r"(?:^|[\s,;])"
    r"(?:VIA|ROUTING\s+VIA|ROUTE\s+VIA|T/S(?:\s+AT)?|TRANSSHIP(?:MENT)?\s+(?:AT|VIA))"
    r"\s*[:\-]?\s*"
    r"([A-Z][A-Z ]{2,28}?)(?:\s*[,\.;\(\n]|$)",
    re.I | re.MULTILINE,
)

# Stop-words that should never be treated as via port names
_VIA_STOPWORDS = re.compile(r"^(THE|AND|OR|IN|AT|OF|TO|FROM|FOR|BY|WITH|AS|IS|BE)$", re.I)


def _infer_section_commodity(section_text: str, global_commodity: str) -> str:
    """
    Infer the commodity for a section from its raw text.

    Priority order:
      1. Explicit inline declaration  (< NOTE FOR COMMODITY: FAK >, COMMODITY: …)
      2. Keyword pattern match        (reefer, hazardous, fak, etc.)
      3. Fallback to global_commodity (unchanged)
    """
    if not section_text:
        return global_commodity

    # 1. Explicit declaration
    m = _COMMODITY_INLINE_RE.search(section_text)
    if m:
        found = m.group(1).strip().rstrip(">").strip()
        if found:
            return found.upper()

    # 2. Keyword scan
    for kw_re, canonical in _COMMODITY_KW_RES:
        if kw_re.search(section_text):
            return canonical

    return global_commodity


def _infer_via_from_text(section_text: str, existing_via: str) -> str:
    """
    Extract the via/transshipment port from section free-text when no
    ORIGIN VIA: header is present.

    Common source patterns:
      "ROUTING: … VIA SINGAPORE"
      "T/S AT HONG KONG"
      "T/S BUSAN"
    Returns existing_via unchanged if it is already set.
    """
    if existing_via or not section_text:
        return existing_via

    m = _VIA_TEXT_RE.search(section_text)
    if not m:
        return existing_via

    via = m.group(1).strip().rstrip(".,;").strip()

    # Sanity guards: must be ≥3 chars and not a stop-word
    if len(via) < 3 or _VIA_STOPWORDS.match(via):
        return existing_via

    # Strip trailing service parens and state/country suffixes
    via = re.sub(r"\s*\([A-Za-z/]+\)\s*$", "", via)
    via = re.sub(r",\s*[A-Z]{2}\s*$", "", via.upper()).strip()
    via = via.split(",")[0].strip()

    return via if via else existing_via


def _split_multiline_cells(grid: list[list[str]]) -> list[list[str]]:
    """
    Expand table cells that contain embedded newlines (\\n) into separate rows.

    pdfplumber sometimes folds what should be multiple rows into one cell when
    the PDF uses borderless tables with tight row spacing.  For example:

        cell = "SHANGHAI\\nNINGBO"  →  two separate city names on consecutive rows

    Each column is split independently; columns with fewer lines are padded with
    empty strings so all sub-rows have the same width.
    """
    expanded: list[list[str]] = []
    for row in grid:
        if not any("\n" in cell for cell in row):
            expanded.append(row)
            continue

        split_cols = [cell.split("\n") for cell in row]
        max_lines = max(len(sc) for sc in split_cols)

        if max_lines == 1:
            expanded.append(row)
            continue

        # Pad shorter columns to the same line count
        for sc in split_cols:
            while len(sc) < max_lines:
                sc.append("")

        for line_idx in range(max_lines):
            sub_row = [sc[line_idx].strip() for sc in split_cols]
            if any(c for c in sub_row):
                expanded.append(sub_row)

    return expanded


def _detect_continuation_table(
    grid: list[list[str]],
    prev_col_map: dict[int, str] | None,
) -> dict[int, str] | None:
    """
    Detect whether a table is a page-break continuation of the previous one.

    When a rate table spans multiple pages, pdfplumber creates one table object
    per page.  The first has a header row; subsequent ones do not.  The current
    grid extractor returns None for headerless tables, silently dropping all rows
    on continuation pages.

    A table is treated as a continuation when ALL of the following hold:
      • A previous column-map exists (from the table on the preceding page)
      • The first row of this table does NOT look like a header
        (fewer than 2 cells match known column-name keywords)
      • The column count is within ±2 of the expected count
      • The first row contains at least one numeric-looking rate value

    Returns a col_map trimmed to this table's actual column count,
    or None if the table is not a continuation.
    """
    if prev_col_map is None or not grid:
        return None

    first_row = grid[0]
    actual_cols = len(first_row)

    # Reject if first row looks like a fresh header
    compact_keys = {re.sub(r"[^a-z0-9]", "", k) for k in _RATE_COL}
    header_hits = sum(
        1 for cell in first_row
        if re.sub(r"[^a-z0-9]", "", cell.lower()) in compact_keys
    )
    if header_hits >= 2:
        return None

    # Column count must roughly match the previous table
    expected_cols = max(prev_col_map.keys()) + 1
    if abs(actual_cols - expected_cols) > 2:
        return None

    # At least one cell in the first row must contain a rate-like number
    has_numeric = any(
        re.search(r"(?:[A-Za-z]\d*/)?(\d{2,6})", cell)
        for cell in first_row if cell.strip()
    )
    if not has_numeric:
        return None

    # Return col_map trimmed to valid column indices
    return {k: v for k, v in prev_col_map.items() if k < actual_cols}


def _extract_rows_with_colmap(
    grid: list[list[str]],
    col_map: dict[int, str],
    context: dict,
) -> list[dict]:
    """
    Extract data rows from a grid using a pre-determined column map.
    Used for continuation tables where the header row is on a previous page.
    Starts from row 0 (no header detection).
    """
    rows: list[dict] = []
    for row in grid:
        if not any(c.strip() for c in row):
            continue

        row_dict = dict(context)
        has_rate = False

        for col_idx, field in col_map.items():
            if field == "_ignore":
                continue
            if col_idx >= len(row):
                continue
            cell = row[col_idx].strip()
            if not cell or cell in ("-", "—", "--", "N/A", "n/a", "TBN", "None"):
                continue

            if field.startswith("base_rate") or field.startswith("agw"):
                cell_upper = cell.upper().strip()
                if cell_upper in _WAIVED_VALUES:
                    row_dict[field] = 0.0
                    if field.startswith("base_rate"):
                        has_rate = True
                    continue
                m = _NUMERIC_RE.search(cell)
                if m:
                    try:
                        val = float(m.group(1).replace(",", ""))
                        bounds = _RATE_BOUNDS.get(field)
                        if bounds and not (bounds[0] <= val <= bounds[1]):
                            logger.debug(f"[cont] OOB: {field}={val}")
                            continue
                        row_dict[field] = val
                        if field.startswith("base_rate"):
                            has_rate = True
                    except ValueError:
                        pass
            else:
                row_dict[field] = cell

        if has_rate:
            row_dict.setdefault("service", "CY/CY")
            rows.append(row_dict)

    return rows


def _extract_origin_grouped_from_table(
    grid: list[list[str]],
    col_source: dict[str, str],
) -> dict[str, list[dict]] | None:
    """
    Handle rate tables where origin/POL is a column rather than an ORIGIN: header.

    Some freight PDFs consolidate multiple origins into one large table:

        | Origin      | Destination | 20'  | 40'  | 40HC |
        | LOS ANGELES | SHANGHAI    | 1200 | 2200 | 2400 |
        |             | NINGBO      | 1150 | 2150 | 2350 |   ← origin carried forward
        | SEATTLE     | SHANGHAI    | 1100 | 2100 | 2300 |

    The origin cell is often blank on continuation rows — carried forward from
    the last non-empty value above (standard freight table convention).

    Returns a dict  {origin_city: [row_dict, ...]}  grouped by origin,
    or None if no origin column is found in the table.
    """
    header_idx, col_map = _detect_header_row(grid, col_source)
    if header_idx == -1:
        return None

    origin_col = next(
        (idx for idx, field in col_map.items() if field == "origin_city"), None
    )
    if origin_col is None:
        return None  # No origin column — handled by ORIGIN: section header

    groups: dict[str, list[dict]] = {}
    current_origin: str = ""

    for row in grid[header_idx + 1:]:
        if not any(c.strip() for c in row):
            continue

        # Pick up new origin when cell is non-empty (blank = carry forward)
        if origin_col < len(row) and row[origin_col].strip():
            raw = row[origin_col].strip()
            # Strip service parens, country/state codes, take city segment
            raw = re.sub(r"\s*\([A-Za-z/]+\)\s*$", "", raw)
            raw = re.sub(r",\s*[A-Z]{2}\s*$", "", raw.upper()).strip()
            current_origin = raw.split(",")[0].strip()

        if not current_origin:
            continue

        row_dict: dict = {}
        has_rate = False

        for col_idx, field in col_map.items():
            if field in ("_ignore", "origin_city"):
                continue
            if col_idx >= len(row):
                continue
            cell = row[col_idx].strip()
            if not cell or cell in ("-", "—", "--", "N/A", "n/a", "TBN", "None"):
                continue

            if field.startswith("base_rate") or field.startswith("agw"):
                cell_upper = cell.upper().strip()
                if cell_upper in _WAIVED_VALUES:
                    row_dict[field] = 0.0
                    if field.startswith("base_rate"):
                        has_rate = True
                    continue
                m = _NUMERIC_RE.search(cell)
                if m:
                    try:
                        val = float(m.group(1).replace(",", ""))
                        bounds = _RATE_BOUNDS.get(field)
                        if not bounds or bounds[0] <= val <= bounds[1]:
                            row_dict[field] = val
                            if field.startswith("base_rate"):
                                has_rate = True
                    except ValueError:
                        pass
            else:
                row_dict[field] = cell

        if has_rate:
            groups.setdefault(current_origin, []).append(row_dict)

    return groups if groups else None


# ── Annotate rows with contract metadata + surcharges ─────────────────────────

def _numeric(val) -> float | None:
    if val is None or val in ("TARIFF", "INCLUSIVE", ""):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _annotate_rows(
    rows: list[dict],
    carrier: str, contract_id: str,
    effective_date: str, expiration_date: str,
    commodity: str, scope: str,
    origin: str, origin_via: str,
    surcharges: dict,
) -> None:
    for row in rows:
        row.update({
            "carrier":             carrier,
            "contract_id":         contract_id,
            "effective_date":      effective_date,
            "expiration_date":     expiration_date,
            "commodity":           commodity,
            "scope":               scope,
            "origin_city":         origin,
            "origin_via_city":     origin_via or None,
            "ams_china_japan":     _numeric(surcharges.get("ams_china_japan")),
            "hea_heavy_surcharge": _numeric(surcharges.get("hea_heavy_surcharge")),
            "agw":                 _numeric(surcharges.get("agw")),
            "rds_red_sea":         _numeric(surcharges.get("rds_red_sea")),
        })


# ── Section extractors ────────────────────────────────────────────────────────

def _extract_section_rates(
    section: dict,
    carrier: str, contract_id: str,
    effective_date: str, expiration_date: str,
    commodity: str, surcharges: dict,
) -> list[dict]:
    origin     = section.get("origin", "")
    origin_via = section.get("origin_via", "")
    scope      = section.get("scope", "")
    raw_text   = section.get("raw_text", "")
    tables     = section.get("tables", [])

    if not origin:
        return []

    # ── Context enrichment ────────────────────────────────────────────────────
    # Override global commodity with any per-section declaration in the raw text.
    section_commodity = _infer_section_commodity(raw_text, commodity)

    # Fill in missing via port from inline routing text when no ORIGIN VIA: header.
    section_via = _infer_via_from_text(raw_text, origin_via)

    base_context: dict = {
        "origin_city":     origin,
        "origin_via_city": section_via or None,
        "scope":           scope,
        "service":         "CY/CY",
    }

    # ── Rule-based grid extraction ────────────────────────────────────────────
    rule_rows: list[dict] = []
    # Keep the last successful column-map for detecting page-break continuations.
    prev_col_map: dict[int, str] | None = None

    for grid in tables:
        # Step 1: Expand cells that fold multiple rows via embedded newlines.
        grid = _split_multiline_cells(grid)

        # Step 2: Standard header-based grid extraction.
        rows = _extract_from_grid(grid, base_context)
        if rows:
            # Save col_map for possible continuation on the next page.
            _, prev_col_map = _detect_header_row(grid)
            rule_rows.extend(rows)
            continue

        # Step 3: Continuation table — same column structure but no header row.
        #         Occurs when a rate table spans multiple pages; pdfplumber
        #         creates a separate table object per page.
        cont_map = _detect_continuation_table(grid, prev_col_map)
        if cont_map is not None:
            cont_rows = _extract_rows_with_colmap(grid, cont_map, base_context)
            if cont_rows:
                logger.debug(f"[cont] {len(cont_rows)} continuation rows for origin={origin}")
                rule_rows.extend(cont_rows)
            continue

        # Step 4: Origin-as-column table — some PDFs embed origin as a column
        #         instead of using ORIGIN: section headers.  Match rows whose
        #         origin cell corresponds to the current section origin.
        origin_groups = _extract_origin_grouped_from_table(grid, _RATE_COL)
        if origin_groups:
            for grp_origin, grp_rows in origin_groups.items():
                # Accept an exact match or a prefix match to handle
                # normalisation differences (e.g. "LOS ANGELES" vs "LOS ANGELES CA")
                if (grp_origin == origin
                        or origin.startswith(grp_origin)
                        or grp_origin.startswith(origin)):
                    for r in grp_rows:
                        # Apply base context without overwriting already-set fields
                        for k, v in base_context.items():
                            r.setdefault(k, v)
                        r.setdefault("service", "CY/CY")
                    rule_rows.extend(grp_rows)

    if rule_rows:
        _annotate_rows(
            rule_rows, carrier, contract_id, effective_date, expiration_date,
            section_commodity, scope, origin, section_via, surcharges,
        )
        log_extra = ""
        if section_via and section_via != origin_via:
            log_extra += f"  via={section_via}"
        if section_commodity != commodity:
            log_extra += f"  cmdt={section_commodity}"
        logger.info(f"[rule] {len(rule_rows)} rows  origin={origin}{log_extra}")
        return rule_rows

    # ── Text-line fallback ────────────────────────────────────────────────────
    if raw_text.strip():
        text_rows = _extract_rates_from_text(raw_text, base_context)
        if text_rows:
            _annotate_rows(
                text_rows, carrier, contract_id, effective_date, expiration_date,
                section_commodity, scope, origin, section_via, surcharges,
            )
            logger.info(f"[text] {len(text_rows)} rows for origin={origin}")
            return text_rows

    logger.debug(f"[nlp] No rates found for origin={origin}")
    return []


def _extract_arb_section(
    arb_section: dict, arb_kind: str,
    carrier: str, contract_id: str,
    effective_date: str, expiration_date: str,
    commodity: str, scope: str,
) -> list[dict]:
    raw_text = arb_section.get("raw_text", "")
    tables   = arb_section.get("tables", [])

    if not raw_text.strip() and not tables:
        return []

    col_source = {**_RATE_COL, **(_ARB_ORIGIN_EXTRA if arb_kind == "ORIGIN" else _ARB_DEST_EXTRA)}
    base_context = {
        "carrier": carrier, "contract_id": contract_id,
        "effective_date": effective_date, "expiration_date": expiration_date,
        "commodity": commodity, "scope": scope,
    }

    rule_rows: list[dict] = []
    prev_col_map: dict[int, str] | None = None

    for grid in tables:
        # Expand multiline cells
        grid = _split_multiline_cells(grid)

        # Standard header-based extraction
        rows = _extract_from_grid(grid, base_context, col_source=col_source)
        if rows:
            _, prev_col_map = _detect_header_row(grid, col_source)
            rule_rows.extend(rows)
            continue

        # Continuation table detection (page-spanning arb tables)
        cont_map = _detect_continuation_table(grid, prev_col_map)
        if cont_map is not None:
            cont_rows = _extract_rows_with_colmap(grid, cont_map, base_context)
            if cont_rows:
                logger.debug(f"[cont] {len(cont_rows)} continuation {arb_kind} arb rows")
                rule_rows.extend(cont_rows)
            continue

    if rule_rows:
        logger.info(f"[rule] {len(rule_rows)} {arb_kind} arb rows")
        return rule_rows

    # Text-line fallback for arb sections
    if raw_text.strip():
        text_rows = _extract_rates_from_text(raw_text, base_context)
        if text_rows:
            logger.info(f"[text] {len(text_rows)} {arb_kind} arb rows from text fallback")
            return text_rows

    logger.debug(f"[nlp] No {arb_kind} arb rows found")
    return []


# ── Health check stub (Ollama no longer required) ─────────────────────────────

def check_ollama_health(host: str = "http://localhost:11434") -> dict:
    """Returns a stub — Ollama is no longer required in NLP mode."""
    return {"running": True, "models": [], "mode": "nlp"}


# ── Rules application (post-processing via ProvisionRegistry) ────────────────

def _apply_rules(all_rates: list[dict], origin_arbs: list[dict],
                 dest_arbs: list[dict], rules: dict) -> None:
    """
    Apply extracted rules to rate rows in-place using the ProvisionRegistry.

    The registry stores each rule once and stamps provision IDs on every
    row it applies to — enabling full auditability.
    """
    from ai.provision_registry import ProvisionRegistry

    registry = ProvisionRegistry()

    # Register all rules as provisions
    registered_ids = registry.register_from_rules(rules)

    if not registered_ids:
        logger.info("[rules] No provisions to apply")
        return

    # Apply provisions to all rows (rates + arbs)
    registry.apply_to_rows(all_rates, origin_arbs, dest_arbs, rules)

    logger.info(f"[rules] Applied {len(registered_ids)} provisions to "
                f"{len(all_rates)} rates, {len(origin_arbs)} origin arbs, "
                f"{len(dest_arbs)} dest arbs")


# ── Main entry point ──────────────────────────────────────────────────────────

def extract_with_ollama(
    extracted: dict,
    model: str = "",        # ignored — kept for API compatibility
    host: str = "",         # ignored — kept for API compatibility
    max_workers: int = 0,   # ignored — NLP is fast enough serially
    low_memory: bool = False,
    rules: dict | None = None,
) -> dict:
    """
    Pure NLP extraction. No LLM, no internet, no GPU required.
    All data is extracted using regex and rule-based grid parsing.
    """
    metadata = extracted.get("metadata", {})
    sections = extracted.get("sections", [])

    # Enhance metadata with wider regex patterns (search first 4000 chars of all sections)
    full_text = "\n".join(s.get("raw_text", "") for s in sections)[:4000]
    metadata = _extract_metadata_enhanced(full_text, metadata)

    carrier         = metadata.get("carrier", "")
    contract_id     = metadata.get("contract_id", "")
    effective_date  = metadata.get("effective_date", "")
    expiration_date = metadata.get("expiration_date", "")
    commodity       = metadata.get("commodity", "")
    scope           = metadata.get("scope", "")

    # If no expiration date was found in the contract header, scan all section
    # texts for per-commodity NOTE blocks ("valid from/to YYYYMMDD").
    # These are the ONLY expiry source in many OLTK contracts.
    if not expiration_date:
        for s in sections:
            _, found_exp = _extract_section_dates(s.get("raw_text", ""), "", "")
            if found_exp:
                expiration_date = found_exp
                logger.info(f"[nlp] Expiration from NOTE block: {expiration_date}")
                break

    for s in sections:
        if not s.get("scope"):
            s["scope"] = scope

    # Default surcharges (fallback if not found in text)
    surcharges: dict = {
        "ams_china_japan":    35,
        "hea_heavy_surcharge": "TARIFF",
        "agw":                 "TARIFF",
        "rds_red_sea":         "INCLUSIVE",
    }

    # Extract surcharges with regex
    surcharge_text = extracted.get("surcharge_text", "")
    if surcharge_text.strip():
        found = _extract_surcharges_regex(surcharge_text)
        surcharges.update(found)
        logger.info(f"[nlp] Surcharges: {found}")

    # ── Rate extraction with commodity + expiry carry-forward ─────────────────
    #
    # In OLTK contracts the commodity and validity dates are declared in
    # "< NOTE FOR COMMODITY >" blocks that appear at the END of a section's
    # text (after the rate table), immediately before the next ORIGIN: header.
    # pdfplumber places this text in the CURRENT section's raw_text, not the
    # next one.  We therefore:
    #   1. Process the current section using the RUNNING state.
    #   2. After processing, update the running state from any NOTE found in
    #      the current section's raw_text — these apply to subsequent sections.
    all_rates: list[dict] = []
    running_commodity = commodity
    running_expiry    = expiration_date

    for section in sections:
        raw = section.get("raw_text", "")

        rows = _extract_section_rates(
            section, carrier, contract_id,
            effective_date, running_expiry,
            running_commodity, surcharges,
        )
        all_rates.extend(rows)

        # Update running state from NOTE blocks in this section's text.
        # _infer_section_commodity also catches "COMMODITY : ..." lines.
        running_commodity = _infer_section_commodity(raw, running_commodity)
        _, found_exp = _extract_section_dates(raw, effective_date, running_expiry)
        if found_exp != running_expiry:
            logger.debug(f"[nlp] Expiry carry-forward: {running_expiry} → {found_exp}")
            running_expiry = found_exp

    # Extract origin arbitraries
    origin_arbs: list[dict] = []
    for arb in extracted.get("origin_arb_sections", []):
        rows = _extract_arb_section(
            arb, "ORIGIN", carrier, contract_id,
            effective_date, running_expiry, running_commodity, scope,
        )
        origin_arbs.extend(rows)

    # Extract destination arbitraries
    dest_arbs: list[dict] = []
    for arb in extracted.get("dest_arb_sections", []):
        rows = _extract_arb_section(
            arb, "DESTINATION", carrier, contract_id,
            effective_date, running_expiry, running_commodity, scope,
        )
        dest_arbs.extend(rows)

    logger.info(
        f"[nlp] Done — {len(all_rates)} rates, "
        f"{len(origin_arbs)} origin arbs, {len(dest_arbs)} dest arbs"
    )

    # ── Apply rules (Section 7-12) via ProvisionRegistry ─────────────────────
    # Rules are now ALWAYS extracted (regex primary + optional LLM).
    # The old approach only applied rules when Ollama was running.
    if rules and any(rules.get(k) for k in ("scope_dates", "scope_surcharges", "reefer_codes")):
        logger.info("[nlp] Applying provisions to rate rows...")
        _apply_rules(all_rates, origin_arbs, dest_arbs, rules)
    else:
        # Even without explicit rules, try regex-based rules extraction
        # from the raw section text as a last resort
        rules_text = extracted.get("rules_text", "")
        if rules_text.strip():
            try:
                from ai.rules_extractor import extract_rules_regex
                auto_rules = extract_rules_regex(rules_text)
                if any(auto_rules.get(k) for k in ("scope_dates", "scope_surcharges", "reefer_codes")):
                    logger.info("[nlp] Auto-extracted rules from contract text (regex)")
                    _apply_rules(all_rates, origin_arbs, dest_arbs, auto_rules)
            except Exception as e:
                logger.debug(f"[nlp] Auto-rules extraction failed: {e}")

    # Also try to extract glossary/reefer info from full text if not in rules
    if not rules or not rules.get("container_glossary"):
        full_text = "\n".join(s.get("raw_text", "") for s in sections)
        try:
            from ai.rules_extractor import extract_preamble_rules
            preamble = extract_preamble_rules(full_text)
            if preamble.get("container_glossary"):
                logger.info(f"[nlp] Found {len(preamble['container_glossary'])} container codes from document text")
                # Apply reefer remapping if we found reefer codes
                if preamble.get("reefer_codes"):
                    _apply_rules(all_rates, origin_arbs, dest_arbs, preamble)
        except Exception as e:
            logger.debug(f"[nlp] Preamble rules extraction failed: {e}")

    return {
        "metadata":                metadata,
        "surcharges":              surcharges,
        "rates":                   all_rates,
        "origin_arbitraries":      origin_arbs,
        "destination_arbitraries": dest_arbs,
    }
