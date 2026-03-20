"""Write extracted freight data into the XLSM template, preserving VBA macros."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from openpyxl import load_workbook

from mapping.field_mapper import map_rate_rows, map_origin_arb_rows, map_dest_arb_rows
from mapping.schema import RateRow, OriginArbitraryRow, DestinationArbitraryRow

logger = logging.getLogger("excel_writer")

# Excel serial date epoch
_EXCEL_EPOCH = date(1899, 12, 30)

# ── Header → field name mapping (for dynamic column detection) ──────────────

_HEADER_TO_FIELD = {
    # Exact matches (lowercased header text → field name)
    "carrier": "carrier",
    "contract id": "contract_id",
    "effective_date": "effective_date",
    "effective date": "effective_date",
    "expiration_date": "expiration_date",
    "expiration date": "expiration_date",
    "commodity": "commodity",
    "origin_city": "origin_city",
    "origin city": "origin_city",
    "origin_via_city": "origin_via_city",
    "origin via city": "origin_via_city",
    "origin via": "origin_via_city",
    "destination_city": "destination_city",
    "destination city": "destination_city",
    "destination_via_city": "destination_via_city",
    "destination via city": "destination_via_city",
    "destination via": "destination_via_city",
    "service": "service",
    "remarks": "remarks",
    "scope": "scope",
    "baserate 20": "base_rate_20",
    "baserate20": "base_rate_20",
    "base rate 20": "base_rate_20",
    "baserate 40": "base_rate_40",
    "baserate40": "base_rate_40",
    "base rate 40": "base_rate_40",
    "baserate 40h": "base_rate_40h",
    "baserate40h": "base_rate_40h",
    "baserate 40hc": "base_rate_40h",
    "base rate 40h": "base_rate_40h",
    "base rate 40hc": "base_rate_40h",
    "baserate 45": "base_rate_45",
    "baserate45": "base_rate_45",
    "base rate 45": "base_rate_45",
    # Surcharges
    "ams": "ams_china_japan",
    "ams/aci": "ams_china_japan",
    "hea": "hea_heavy_surcharge",
    "agw": "agw",
    "rds": "rds_red_sea",
    "red sea": "rds_red_sea",
    "meo": "meo",
    "pef": "pef",
    "pel": "pef",
    # Reefer columns
    "reefer 20": "reefer_rate_20",
    "reefer20": "reefer_rate_20",
    "reefer 40": "reefer_rate_40",
    "reefer40": "reefer_rate_40",
    "reefer 40h": "reefer_rate_40h",
    "reefer 40hc": "reefer_rate_40h",
    "reefer40h": "reefer_rate_40h",
    "reefer40hc": "reefer_rate_40h",
    "non operating reefer": "reefer_rate_nor40",
    "non-operating reefer": "reefer_rate_nor40",
    "nor 40": "reefer_rate_nor40",
    "reefer 40 nor": "reefer_rate_nor40",
}

# Keyword-based fallback matching (checked if exact match fails)
_HEADER_KEYWORDS = [
    ("reefer", "40", "nor"),    # "Reefer40NOR" → reefer_rate_nor40
    ("non", "oper", "reefer"),  # "Non Operating Reefer" → reefer_rate_nor40
    ("reefer", "40h"),          # "Reefer40HC" → reefer_rate_40h
    ("reefer", "40"),           # "Reefer40" → reefer_rate_40
    ("reefer", "20"),           # "Reefer20" → reefer_rate_20
    ("red", "sea"),             # "Red Sea Diversion" → rds_red_sea
]
_HEADER_KEYWORD_FIELDS = [
    "reefer_rate_nor40",
    "reefer_rate_nor40",
    "reefer_rate_40h",
    "reefer_rate_40",
    "reefer_rate_20",
    "rds_red_sea",
]


def _read_header_mapping(ws) -> list[str]:
    """
    Read row 1 headers from a worksheet and return a list of field names.
    Handles varying template column layouts (LAX vs CHI vs ATL).
    """
    cols = []
    for cell in ws[1]:
        raw = (cell.value or "")
        header = raw.strip().lower()
        header = header.replace("_", " ").strip()

        # Try direct exact match
        field = _HEADER_TO_FIELD.get(header)

        # Try without underscores/spaces collapsed
        if not field:
            collapsed = header.replace(" ", "")
            for key, f in _HEADER_TO_FIELD.items():
                if key.replace(" ", "") == collapsed:
                    field = f
                    break

        # Try keyword-based matching
        if not field:
            for keywords, kw_field in zip(_HEADER_KEYWORDS, _HEADER_KEYWORD_FIELDS):
                if all(kw in header for kw in keywords):
                    field = kw_field
                    break

        if field:
            cols.append(field)
        else:
            # Unknown column — store placeholder so column indices stay correct
            col_letter = cell.column_letter
            if header:
                logger.debug(f"[excel_writer] Unknown header in col {col_letter}: '{raw}'")
            cols.append(f"_unknown_{col_letter}")

    return cols


# ── Fallback hardcoded column mappings (used if header row is empty) ────────

RATES_COLS_FALLBACK = [
    "carrier",           # A
    "contract_id",       # B
    "effective_date",    # C
    "expiration_date",   # D
    "commodity",         # E
    "origin_city",       # F
    "origin_via_city",   # G
    "destination_city",  # H
    "destination_via_city",  # I
    "service",           # J
    "remarks",           # K
    "scope",             # L
    "base_rate_20",      # M
    "base_rate_40",      # N
    "base_rate_40h",     # O
    "base_rate_45",      # P
    "ams_china_japan",   # Q
    "hea_heavy_surcharge",  # R
    "agw",               # S
    "rds_red_sea",       # T
]

ORIGIN_ARB_COLS = [
    "carrier",           # A
    "contract_id",       # B
    "effective_date",    # C
    "expiration_date",   # D
    "commodity",         # E
    "origin_city",       # F
    "origin_via_city",   # G
    "service",           # H
    "remarks",           # I  (skip J)
    "scope",             # J  → actual col index 9 → J
    "base_rate_20",      # K
    "base_rate_40",      # L
    "base_rate_40h",     # M
    "base_rate_45",      # N
    "agw_20",            # O
    "agw_40",            # P
    "agw_45",            # Q
]

DEST_ARB_COLS = [
    "carrier",           # A
    "contract_id",       # B
    "effective_date",    # C
    "expiration_date",   # D
    "commodity",         # E
    "destination_city",  # F
    "destination_via_city",  # G
    "service",           # H
    "remarks",           # I
    "scope",             # J
    "base_rate_20",      # K
    "base_rate_40",      # L
    "base_rate_40h",     # M
    "base_rate_45",      # N
]


def _to_excel_date(value: str) -> Optional[int]:
    """Convert 'DD MMM YYYY' string to Excel serial number."""
    if not value:
        return None
    formats = ["%d %b %Y", "%d %B %Y", "%Y-%m-%d", "%m/%d/%Y"]
    for fmt in formats:
        try:
            d = datetime.strptime(value.strip(), fmt).date()
            return (d - _EXCEL_EPOCH).days
        except ValueError:
            continue
    return None


def _cell_value(obj, field: str):
    val = getattr(obj, field, None)
    if field in ("effective_date", "expiration_date"):
        return _to_excel_date(val) if isinstance(val, str) else val
    return val


def _write_rows(ws, start_row: int, rows: list, columns: list[str]) -> int:
    """Write rows to worksheet. Returns number of rows written."""
    for i, row_obj in enumerate(rows):
        excel_row = start_row + i
        for col_idx, field in enumerate(columns, start=1):
            if field.startswith("_unknown_"):
                continue
            val = _cell_value(row_obj, field)
            ws.cell(row=excel_row, column=col_idx, value=val)
    return len(rows)


def write_excel(structured: dict, template_path: str, output_path: str) -> None:
    """
    Populate the XLSM template with extracted data and save.

    Args:
        structured: output from claude_extractor.extract_with_claude()
        template_path: path to ATL0347N25 Template.xlsm
        output_path: where to save the result
    """
    # Map to typed dataclasses
    rate_rows = map_rate_rows(structured)
    origin_arb_rows = map_origin_arb_rows(structured)
    dest_arb_rows = map_dest_arb_rows(structured)

    # Load template preserving VBA
    wb = load_workbook(template_path, keep_vba=True)

    # ── Rates sheet ──────────────────────────────────────────────────────────
    ws_rates = wb["Rates"]

    # Dynamic column mapping: read header row from template
    rates_cols = _read_header_mapping(ws_rates)
    # Validate: if header row was empty or unrecognizable, fall back to hardcoded
    known = [c for c in rates_cols if not c.startswith("_unknown_")]
    if len(known) < 5:
        logger.warning("[excel_writer] Template header row unrecognizable, using fallback column mapping")
        rates_cols = RATES_COLS_FALLBACK
    else:
        logger.info(f"[excel_writer] Dynamic column mapping: {len(known)} fields from {len(rates_cols)} columns")

    # Clear existing data rows (keep header row 1)
    max_existing = ws_rates.max_row
    if max_existing > 1:
        for row in ws_rates.iter_rows(min_row=2, max_row=max_existing):
            for cell in row:
                cell.value = None

    _write_rows(ws_rates, start_row=2, rows=rate_rows, columns=rates_cols)

    # ── Origin Arbitraries sheet ─────────────────────────────────────────────
    if "Origin Arbitraries" in wb.sheetnames and origin_arb_rows:
        ws_orig = wb["Origin Arbitraries"]
        max_existing = ws_orig.max_row
        if max_existing > 1:
            for row in ws_orig.iter_rows(min_row=2, max_row=max_existing):
                for cell in row:
                    cell.value = None
        _write_rows(ws_orig, start_row=2, rows=origin_arb_rows, columns=ORIGIN_ARB_COLS)

    # ── Destination Arbitraries sheet ────────────────────────────────────────
    if "Destination Arbitraries" in wb.sheetnames and dest_arb_rows:
        ws_dest = wb["Destination Arbitraries"]
        max_existing = ws_dest.max_row
        if max_existing > 1:
            for row in ws_dest.iter_rows(min_row=2, max_row=max_existing):
                for cell in row:
                    cell.value = None
        _write_rows(ws_dest, start_row=2, rows=dest_arb_rows, columns=DEST_ARB_COLS)

    wb.save(output_path)
    print(f"[excel_writer] Saved {len(rate_rows)} rate rows, "
          f"{len(origin_arb_rows)} origin arbs, "
          f"{len(dest_arb_rows)} dest arbs → {output_path}")
