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
            for candidate in [line] + ([lines[idx + 1]] if idx + 1 < len(lines) else []):
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
    "service": "service", "term": "service", "type": "service",
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
    "base_rate_20":  (10.0, 30_000.0),
    "base_rate_40":  (10.0, 45_000.0),
    "base_rate_40h": (10.0, 48_000.0),
    "base_rate_45":  (10.0, 50_000.0),
    "agw_20":  (0.0, 6_000.0),
    "agw_40":  (0.0, 6_000.0),
    "agw_45":  (0.0, 6_000.0),
}


# ── Grid extraction ───────────────────────────────────────────────────────────

def _normalize_header_key(cell: str) -> str:
    s = (cell.lower().strip()
         .replace("\u2018", "'").replace("\u2019", "'")
         .replace("\u201c", '"').replace("\u201d", '"')
         .replace("\u2018", "'").replace("\u2019", "'"))
    s = re.sub(r"[:()\[\]]", "", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _detect_header_row(
    grid: list[list[str]],
    col_source: dict[str, str] | None = None,
) -> tuple[int, dict[int, str]]:
    if col_source is None:
        col_source = _RATE_COL

    compact_source = {re.sub(r"[^a-z0-9]", "", k): v for k, v in col_source.items()}

    for row_idx, row in enumerate(grid[:8]):
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

        rate_fields = [v for v in col_map.values() if v.startswith("base_rate")]
        if len(rate_fields) >= 2:
            return row_idx, col_map

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
    r"^(?:\d[\d,]*(?:\.\d+)?|N/A|TARIFF|INCLUSIVE|INCL\.?|-)$", re.I
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

    for i, line in enumerate(lines[:15]):
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

    base_context = {
        "origin_city":     origin,
        "origin_via_city": origin_via or None,
        "scope":           scope,
        "service":         "CY/CY",
    }

    # 1. Rule-based grid extraction
    rule_rows: list[dict] = []
    for grid in tables:
        rows = _extract_from_grid(grid, base_context)
        if rows:
            rule_rows.extend(rows)

    if rule_rows:
        _annotate_rows(rule_rows, carrier, contract_id, effective_date,
                       expiration_date, commodity, scope, origin, origin_via, surcharges)
        logger.info(f"[rule] {len(rule_rows)} rows for origin={origin}")
        return rule_rows

    # 2. Text-line fallback
    if raw_text.strip():
        text_rows = _extract_rates_from_text(raw_text, base_context)
        if text_rows:
            _annotate_rows(text_rows, carrier, contract_id, effective_date,
                           expiration_date, commodity, scope, origin, origin_via, surcharges)
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
    for grid in tables:
        rows = _extract_from_grid(grid, base_context, col_source=col_source)
        if rows:
            rule_rows.extend(rows)

    if rule_rows:
        logger.info(f"[rule] {len(rule_rows)} {arb_kind} arb rows")
        return rule_rows

    logger.debug(f"[nlp] No {arb_kind} arb rows found")
    return []


# ── Health check stub (Ollama no longer required) ─────────────────────────────

def check_ollama_health(host: str = "http://localhost:11434") -> dict:
    """Returns a stub — Ollama is no longer required in NLP mode."""
    return {"running": True, "models": [], "mode": "nlp"}


# ── Main entry point ──────────────────────────────────────────────────────────

def extract_with_ollama(
    extracted: dict,
    model: str = "",        # ignored — kept for API compatibility
    host: str = "",         # ignored — kept for API compatibility
    max_workers: int = 0,   # ignored — NLP is fast enough serially
    low_memory: bool = False,
) -> dict:
    """
    Pure NLP extraction. No LLM, no internet, no GPU required.
    All data is extracted using regex and rule-based grid parsing.
    """
    metadata = extracted.get("metadata", {})

    # Enhance metadata with wider regex patterns
    full_text = "\n".join(
        s.get("raw_text", "") for s in extracted.get("sections", [])
    )[:4000]
    metadata = _extract_metadata_enhanced(full_text, metadata)

    carrier         = metadata.get("carrier", "")
    contract_id     = metadata.get("contract_id", "")
    effective_date  = metadata.get("effective_date", "")
    expiration_date = metadata.get("expiration_date", "")
    commodity       = metadata.get("commodity", "")
    scope           = metadata.get("scope", "")

    sections = extracted.get("sections", [])
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

    # Extract rates for all sections
    all_rates: list[dict] = []
    for section in sections:
        rows = _extract_section_rates(
            section, carrier, contract_id,
            effective_date, expiration_date,
            commodity, surcharges,
        )
        all_rates.extend(rows)

    # Extract origin arbitraries
    origin_arbs: list[dict] = []
    for arb in extracted.get("origin_arb_sections", []):
        rows = _extract_arb_section(
            arb, "ORIGIN", carrier, contract_id,
            effective_date, expiration_date, commodity, scope,
        )
        origin_arbs.extend(rows)

    # Extract destination arbitraries
    dest_arbs: list[dict] = []
    for arb in extracted.get("dest_arb_sections", []):
        rows = _extract_arb_section(
            arb, "DESTINATION", carrier, contract_id,
            effective_date, expiration_date, commodity, scope,
        )
        dest_arbs.extend(rows)

    logger.info(
        f"[nlp] Done — {len(all_rates)} rates, "
        f"{len(origin_arbs)} origin arbs, {len(dest_arbs)} dest arbs"
    )

    return {
        "metadata":                metadata,
        "surcharges":              surcharges,
        "rates":                   all_rates,
        "origin_arbitraries":      origin_arbs,
        "destination_arbitraries": dest_arbs,
    }
