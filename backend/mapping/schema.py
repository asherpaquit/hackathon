"""Data schemas for freight contract extraction output."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RateRow:
    carrier: str = ""
    contract_id: str = ""
    effective_date: str = ""        # "DD MMM YYYY" — converted to Excel serial in writer
    expiration_date: str = ""
    commodity: str = ""
    origin_city: str = ""
    origin_via_city: Optional[str] = None
    destination_city: str = ""
    destination_via_city: Optional[str] = None
    service: str = "CY/CY"
    remarks: Optional[str] = None
    scope: str = ""
    base_rate_20: Optional[float] = None
    base_rate_40: Optional[float] = None
    base_rate_40h: Optional[float] = None
    base_rate_45: Optional[float] = None
    ams_china_japan: Optional[float] = None
    hea_heavy_surcharge: Optional[float] = None
    agw: Optional[float] = None
    rds_red_sea: Optional[str | float] = None  # float rate or "included" string
    # Reefer-specific rate columns
    reefer_rate_20: Optional[float] = None
    reefer_rate_40: Optional[float] = None
    reefer_rate_40h: Optional[float] = None
    reefer_rate_nor40: Optional[float] = None   # Non-Operating Reefer 40
    # Additional surcharges
    meo: Optional[str] = None                    # MEO surcharge
    pef: Optional[str] = None                    # PEF/PEL surcharge


@dataclass
class OriginArbitraryRow:
    carrier: str = ""
    contract_id: str = ""
    effective_date: str = ""
    expiration_date: str = ""
    commodity: Optional[str] = None
    origin_city: str = ""
    origin_via_city: str = ""
    service: str = "CY"
    remarks: Optional[str] = None
    scope: str = ""
    base_rate_20: Optional[float] = None
    base_rate_40: Optional[float] = None
    base_rate_40h: Optional[float] = None
    base_rate_45: Optional[float] = None
    agw_20: Optional[float] = None
    agw_40: Optional[float] = None
    agw_45: Optional[float] = None


@dataclass
class DestinationArbitraryRow:
    carrier: str = ""
    contract_id: str = ""
    effective_date: str = ""
    expiration_date: str = ""
    commodity: Optional[str] = None
    destination_city: str = ""
    destination_via_city: str = ""
    service: str = "CY"
    remarks: Optional[str] = None
    scope: str = ""
    base_rate_20: Optional[float] = None
    base_rate_40: Optional[float] = None
    base_rate_40h: Optional[float] = None
    base_rate_45: Optional[float] = None
