"""Port/city name normalization using template shared strings."""

from __future__ import annotations

import re

# Built from ATL0347N25 Template.xlsm sharedStrings.xml
PORT_MAP: dict[str, str] = {
    "BAHRAIN": "Bahrain",
    "HONG KONG": "Hong Kong",
    "SINGAPORE": "Singapore",
    "CHARLESTON": "Charleston",
    "DALIAN": "Dalian",
    "NINGBO": "Ningbo",
    "QINGDAO": "Qingdao",
    "SHANGHAI": "Shanghai",
    "XIAMEN": "Xiamen",
    "XINGANG": "Xingang",
    "YANTIAN": "Yantian",
    "CHICAGO": "Chicago",
    "LOS ANGELES": "Los Angeles",
    "SHEKOU": "Shekou",
    "HALIFAX": "Halifax",
    "HOUSTON": "Houston",
    "JACKSONVILLE": "Jacksonville",
    "MIAMI": "Miami",
    "MOBILE": "Mobile",
    "NEW YORK": "New York",
    "NORFOLK": "Norfolk",
    "OAKLAND": "Oakland",
    "SAVANNAH": "Savannah",
    "TACOMA": "Tacoma",
    "VANCOUVER": "Vancouver",
    "BELAWAN": "Belawan, Sumatra",
    "JAKARTA": "Jakarta, Java",
    "SEMARANG": "Semarang, Java",
    "SURABAYA": "Surabaya",
    "PUSAN": "Pusan",
    "PASIR GUDANG": "Pasir Gudang, Johor",
    "PENANG": "Penang",
    "PORT KLANG": "Port Klang",
    "MANILA": "Manila",
    "BANGKOK": "Bangkok",
    "LAEM CHABANG": "Laem Chabang",
    "LAT KRABANG": "Lat Krabang",
    "KAOHSIUNG": "Kaohsiung",
    "KEELUNG": "Keelung (Chilung)",
    "CHILUNG": "Keelung (Chilung)",
    "TAICHUNG": "Taichung",
    "TAOYUAN": "Taoyuan",
    "CAI MEP": "Cai Mep",
    "HAIPHONG": "Haiphong",
    "HO CHI MINH": "Ho Chi Minh City",
    "HO CHI MINH CITY": "Ho Chi Minh City",
    "INCHEON": "Incheon",
    "KWANGYANG": "KWANGYANG",
    "TAIPEI": "Taipei",
    "KOBE": "Kobe",
    "NAGOYA": "Nagoya, Aichi",
    "OSAKA": "Osaka",
    "SHIMIZU": "Shimizu",
    "TOKYO": "Tokyo",
    "YOKOHAMA": "Yokohama",
    "JEBEL ALI": "Jebel Ali",
    "CHENNAI": "Chennai",
    "COCHIN": "Cochin",
    "HAZIRA": "Hazira",
    "KATTUPALLI": "Kattupalli",
    "KOLKATA": "Kolkata (ex Calcutta)",
    "CALCUTTA": "Kolkata (ex Calcutta)",
    "MUNDRA": "Mundra",
    "NHAVA SHEVA": "Nhava Sheva (Jawaharlal Nehru)",
    "JAWAHARLAL NEHRU": "Nhava Sheva (Jawaharlal Nehru)",
    "PIPAVAV": "Pipavav (Victor) Port",
    "TUTICORIN": "Tuticorin",
    "MOMBASA": "Mombasa",
    "COLOMBO": "Colombo",
    "BEIRA": "Beira",
    "MAPUTO": "Maputo",
    "KARACHI": "Karachi",
    "MUHAMMAD BIN QASIM": "Muhammad Bin Qasim",
    "DAMMAM": "Dammam",
    "CHITTAGONG": "Chittagong",
    "CAPE TOWN": "Cape Town",
    "DURBAN": "Durban",
    "ATLANTA": "Atlanta",
    "CHARLOTTE": "Charlotte",
    "DALLAS": "Dallas",
    "DILLON": "Dillon",
    "GREER": "Greer",
    "MEMPHIS": "Memphis",
    "NASHVILLE": "Nashville",
    "KAWASAKI": "Kawasaki",
}

# Remove province/state suffix patterns like ", Shandong" or ", Java"
_PROVINCE_RE = re.compile(r",\s*[A-Z][a-zA-Z\s]+$")


def normalize_port(raw: str) -> str:
    """Normalize a raw port/city name to the Excel template's canonical form."""
    if not raw:
        return raw

    # Strip parenthetical extras like "(Chilung)" if we have base name
    clean = raw.strip()

    # Look up by uppercase key
    upper = clean.upper()

    # Direct match
    if upper in PORT_MAP:
        return PORT_MAP[upper]

    # Try without province suffix: "QINGDAO, SHANDONG" → "QINGDAO"
    base = _PROVINCE_RE.sub("", upper).strip()
    if base in PORT_MAP:
        return PORT_MAP[base]

    # Try first word only (e.g. "JAKARTA, JAVA" → "JAKARTA")
    first = upper.split(",")[0].strip()
    if first in PORT_MAP:
        return PORT_MAP[first]

    # Fall back to title case
    return clean.title()
