"""Map Claude-extracted dicts to typed dataclass rows."""

from __future__ import annotations

from typing import Optional

from mapping.normalizer import normalize_port
from mapping.schema import RateRow, OriginArbitraryRow, DestinationArbitraryRow


def _f(val) -> Optional[float]:
    """Safe float conversion."""
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def map_rate_rows(structured: dict) -> list[RateRow]:
    rows = []
    for d in structured.get("rates", []):
        row = RateRow(
            carrier=d.get("carrier", ""),
            contract_id=d.get("contract_id", ""),
            effective_date=d.get("effective_date", ""),
            expiration_date=d.get("expiration_date", ""),
            commodity=d.get("commodity", ""),
            origin_city=normalize_port(d.get("origin_city", "")),
            origin_via_city=normalize_port(d.get("origin_via_city") or "") or None,
            destination_city=normalize_port(d.get("destination_city", "")),
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
            rds_red_sea=_f(d.get("rds_red_sea")),
        )
        rows.append(row)
    return rows


def map_origin_arb_rows(structured: dict) -> list[OriginArbitraryRow]:
    rows = []
    for d in structured.get("origin_arbitraries", []):
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
    rows = []
    for d in structured.get("destination_arbitraries", []):
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
