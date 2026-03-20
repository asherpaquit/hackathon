"""Map extracted dicts to typed dataclass rows, with deduplication."""

from __future__ import annotations

from typing import Optional

from mapping.normalizer import normalize_port
from mapping.schema import RateRow, OriginArbitraryRow, DestinationArbitraryRow


def _f(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _rate_key(d: dict) -> tuple:
    """Unique key for a rate row — used to deduplicate."""
    return (
        str(d.get("origin_city", "")).upper().strip(),
        str(d.get("destination_city", "")).upper().strip(),
        str(d.get("destination_via_city", "") or "").upper().strip(),
        str(d.get("service", "")).upper().strip(),
        str(d.get("scope", "")).upper().strip(),
        _f(d.get("base_rate_20")),
        _f(d.get("base_rate_40")),
        _f(d.get("base_rate_40h")),
        _f(d.get("base_rate_45")),
    )


def _origin_arb_key(d: dict) -> tuple:
    return (
        str(d.get("origin_city", "")).upper().strip(),
        str(d.get("origin_via_city", "") or "").upper().strip(),
        str(d.get("service", "")).upper().strip(),
        _f(d.get("base_rate_20")),
        _f(d.get("base_rate_40")),
        _f(d.get("base_rate_40h")),
        _f(d.get("base_rate_45")),
    )


def _dest_arb_key(d: dict) -> tuple:
    return (
        str(d.get("destination_city", "")).upper().strip(),
        str(d.get("destination_via_city", "") or "").upper().strip(),
        str(d.get("service", "")).upper().strip(),
        _f(d.get("base_rate_20")),
        _f(d.get("base_rate_40")),
        _f(d.get("base_rate_40h")),
        _f(d.get("base_rate_45")),
    )


def map_rate_rows(structured: dict) -> list[RateRow]:
    seen: set[tuple] = set()
    rows = []
    for d in structured.get("rates", []):
        # Skip rows with no rate data at all (check both base and reefer columns)
        rate_fields = ("base_rate_20", "base_rate_40", "base_rate_40h", "base_rate_45",
                        "reefer_rate_20", "reefer_rate_40", "reefer_rate_40h", "reefer_rate_nor40")
        if not any(_f(d.get(f)) for f in rate_fields):
            continue
        # Skip rows with no destination
        dest = normalize_port(d.get("destination_city", ""))
        if not dest:
            continue

        key = _rate_key(d)
        if key in seen:
            continue
        seen.add(key)

        row = RateRow(
            carrier=d.get("carrier", ""),
            contract_id=d.get("contract_id", ""),
            effective_date=d.get("effective_date", ""),
            expiration_date=d.get("expiration_date", ""),
            commodity=d.get("commodity", ""),
            origin_city=normalize_port(d.get("origin_city", "")),
            origin_via_city=normalize_port(d.get("origin_via_city") or "") or None,
            destination_city=dest,
            destination_via_city=normalize_port(d.get("destination_via_city") or "") or None,
            service=d.get("service", "CY/CY"),
            remarks=d.get("remarks"),
            scope=d.get("scope", ""),
            base_rate_20=_f(d.get("base_rate_20")),
            base_rate_40=_f(d.get("base_rate_40")),
            base_rate_40h=_f(d.get("base_rate_40h")),
            base_rate_45=_f(d.get("base_rate_45")),
            ams_china_japan=_f(d.get("ams_china_japan")),
            hea_heavy_surcharge=_f(d.get("hea_heavy_surcharge")),
            agw=_f(d.get("agw")),
            rds_red_sea=d.get("rds_red_sea") if isinstance(d.get("rds_red_sea"), str) else _f(d.get("rds_red_sea")),
            reefer_rate_20=_f(d.get("reefer_rate_20")),
            reefer_rate_40=_f(d.get("reefer_rate_40")),
            reefer_rate_40h=_f(d.get("reefer_rate_40h")),
            reefer_rate_nor40=_f(d.get("reefer_rate_nor40")),
            meo=d.get("meo"),
            pef=d.get("pef"),
        )
        rows.append(row)
    return rows


def map_origin_arb_rows(structured: dict) -> list[OriginArbitraryRow]:
    seen: set[tuple] = set()
    rows = []
    for d in structured.get("origin_arbitraries", []):
        if not any(_f(d.get(f)) for f in ("base_rate_20", "base_rate_40", "base_rate_40h", "base_rate_45")):
            continue
        if not d.get("origin_city"):
            continue

        key = _origin_arb_key(d)
        if key in seen:
            continue
        seen.add(key)

        row = OriginArbitraryRow(
            carrier=d.get("carrier", ""),
            contract_id=d.get("contract_id", ""),
            effective_date=d.get("effective_date", ""),
            expiration_date=d.get("expiration_date", ""),
            commodity=d.get("commodity"),
            origin_city=normalize_port(d.get("origin_city", "")),
            origin_via_city=normalize_port(d.get("origin_via_city", "")),
            service=d.get("service", "CY"),
            remarks=d.get("remarks"),
            scope=d.get("scope", ""),
            base_rate_20=_f(d.get("base_rate_20")),
            base_rate_40=_f(d.get("base_rate_40")),
            base_rate_40h=_f(d.get("base_rate_40h")),
            base_rate_45=_f(d.get("base_rate_45")),
            agw_20=_f(d.get("agw_20")),
            agw_40=_f(d.get("agw_40")),
            agw_45=_f(d.get("agw_45")),
        )
        rows.append(row)
    return rows


def map_dest_arb_rows(structured: dict) -> list[DestinationArbitraryRow]:
    seen: set[tuple] = set()
    rows = []
    for d in structured.get("destination_arbitraries", []):
        if not any(_f(d.get(f)) for f in ("base_rate_20", "base_rate_40", "base_rate_40h", "base_rate_45")):
            continue
        if not d.get("destination_city"):
            continue

        key = _dest_arb_key(d)
        if key in seen:
            continue
        seen.add(key)

        row = DestinationArbitraryRow(
            carrier=d.get("carrier", ""),
            contract_id=d.get("contract_id", ""),
            effective_date=d.get("effective_date", ""),
            expiration_date=d.get("expiration_date", ""),
            commodity=d.get("commodity"),
            destination_city=normalize_port(d.get("destination_city", "")),
            destination_via_city=normalize_port(d.get("destination_via_city", "")),
            service=d.get("service", "CY"),
            remarks=d.get("remarks"),
            scope=d.get("scope", ""),
            base_rate_20=_f(d.get("base_rate_20")),
            base_rate_40=_f(d.get("base_rate_40")),
            base_rate_40h=_f(d.get("base_rate_40h")),
            base_rate_45=_f(d.get("base_rate_45")),
        )
        rows.append(row)
    return rows
