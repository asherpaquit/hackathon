"""Write extracted freight data into the XLSM template, preserving VBA macros."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from openpyxl import load_workbook

from mapping.field_mapper import map_rate_rows, map_origin_arb_rows, map_dest_arb_rows
from mapping.schema import RateRow, OriginArbitraryRow, DestinationArbitraryRow

# Excel serial date epoch
_EXCEL_EPOCH = date(1899, 12, 30)

# ── Column mappings ─────────────────────────────────────────────────────────

RATES_COLS = [
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
    # Clear existing data rows (keep header row 1)
    max_existing = ws_rates.max_row
    if max_existing > 1:
        for row in ws_rates.iter_rows(min_row=2, max_row=max_existing):
            for cell in row:
                cell.value = None

    _write_rows(ws_rates, start_row=2, rows=rate_rows, columns=RATES_COLS)

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
