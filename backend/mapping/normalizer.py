"""Port/city name normalization — expanded for accuracy."""

from __future__ import annotations
import re

# Canonical port names matching the ATL0347N25 template
PORT_MAP: dict[str, str] = {
    # China
    "SHANGHAI": "Shanghai", "SHA": "Shanghai",
    "NINGBO": "Ningbo", "NGB": "Ningbo", "NINGBO-ZHOUSHAN": "Ningbo",
    "ZHOUSHAN": "Ningbo",
    "QINGDAO": "Qingdao", "TAO": "Qingdao", "TSINGTAO": "Qingdao",
    "TIANJIN": "Xingang", "XINGANG": "Xingang",
    "TIANJIN XINGANG": "Xingang", "TIAN JIN": "Xingang",
    "DALIAN": "Dalian", "DLC": "Dalian",
    "DALIAN, LIAONING": "Dalian",
    "XIAMEN": "Xiamen", "XMN": "Xiamen",
    "YANTIAN": "Yantian", "YTN": "Yantian",
    "YANTIAN, GUANGDONG": "Yantian",
    "SHEKOU": "Shekou", "SKU": "Shekou",
    "CHIWAN": "Shekou",
    "GUANGZHOU": "Guangzhou", "GZU": "Guangzhou",
    "NANSHA": "Guangzhou",
    "NANSHA, GUANGDONG": "Guangzhou",
    "SHENZHEN": "Yantian",
    "HUANGPU": "Guangzhou",
    "XINSHA": "Guangzhou",
    "FUZHOU": "Fuzhou",
    "NANJING": "Nanjing",
    "LIANYUNGANG": "Lianyungang",
    "WUHAN": "Wuhan",
    "CHENGDU": "Chengdu",
    "CHONGQING": "Chongqing",
    "BEIJING": "Beijing",
    "XIAN": "Xian", "XI'AN": "Xian",
    "ZHENGZHOU": "Zhengzhou",
    "KUNMING": "Kunming",
    "HEFEI": "Hefei",
    "CHANGSHA": "Changsha",
    "NANNING": "Nanning",

    # Hong Kong / Macau
    "HONG KONG": "Hong Kong", "HKG": "Hong Kong", "HK": "Hong Kong",

    # Taiwan
    "KAOHSIUNG": "Kaohsiung", "KHH": "Kaohsiung",
    "KAOHSIUNG CITY": "Kaohsiung", "KAOHSIUNG PORT": "Kaohsiung",
    "KEELUNG": "Keelung (Chilung)", "CHILUNG": "Keelung (Chilung)", "KEL": "Keelung (Chilung)",
    "KEELUNG CITY": "Keelung (Chilung)",
    "TAICHUNG": "Taichung", "TXG": "Taichung",
    "TAICHUNG CITY": "Taichung", "TAICHUNG PORT": "Taichung",
    "TAIPEI": "Taipei", "TPE": "Taipei",
    "TAIPEI CITY": "Taipei",
    "TAOYUAN": "Taoyuan", "TAOYUAN CITY": "Taoyuan",

    # Japan
    "TOKYO": "Tokyo", "TYO": "Tokyo",
    "YOKOHAMA": "Yokohama", "YOK": "Yokohama",
    "NAGOYA": "Nagoya, Aichi", "NGO": "Nagoya, Aichi",
    "OSAKA": "Osaka", "OSA": "Osaka",
    "KOBE": "Kobe", "UKB": "Kobe",
    "SHIMIZU": "Shimizu",
    "KAWASAKI": "Kawasaki",
    "HAKATA": "Hakata",
    "KITAKYUSHU": "Kitakyushu",

    # Korea
    "BUSAN": "Pusan", "PUSAN": "Pusan", "PUS": "Pusan",
    "INCHEON": "Incheon", "ICN": "Incheon", "INCH'ON": "Incheon",
    "KWANGYANG": "KWANGYANG", "GWANGYANG": "KWANGYANG",

    # Southeast Asia
    "SINGAPORE": "Singapore", "SIN": "Singapore", "SGP": "Singapore",
    "PORT KLANG": "Port Klang", "PKL": "Port Klang", "KLANG": "Port Klang",
    "PENANG": "Penang", "PEN": "Penang", "GEORGE TOWN": "Penang",
    "PASIR GUDANG": "Pasir Gudang, Johor", "PGU": "Pasir Gudang, Johor",
    "JOHOR BAHRU": "Pasir Gudang, Johor",
    "TANJUNG PELEPAS": "Port Klang",
    "MANILA": "Manila", "MNL": "Manila",
    "SUBIC BAY": "Manila",
    "BANGKOK": "Bangkok", "BKK": "Bangkok",
    "LAEM CHABANG": "Laem Chabang", "LCB": "Laem Chabang",
    "LAT KRABANG": "Lat Krabang",
    "JAKARTA": "Jakarta, Java", "JKT": "Jakarta, Java",
    "TANJUNG PRIOK": "Jakarta, Java",
    "SURABAYA": "Surabaya", "SUB": "Surabaya",
    "SEMARANG": "Semarang, Java",
    "BELAWAN": "Belawan, Sumatra", "BLW": "Belawan, Sumatra",
    "MEDAN": "Belawan, Sumatra",
    "CAI MEP": "Cai Mep", "CMB": "Cai Mep",
    "HO CHI MINH": "Ho Chi Minh City", "SGN": "Ho Chi Minh City",
    "HO CHI MINH CITY": "Ho Chi Minh City", "HCMC": "Ho Chi Minh City",
    "SAIGON": "Ho Chi Minh City",
    "HAIPHONG": "Haiphong", "HPH": "Haiphong",
    "HAI PHONG": "Haiphong", "HAIPHONG CITY": "Haiphong",
    "HANOI": "Haiphong",
    "YANGON": "Yangon", "RANGOON": "Yangon",
    "PHNOM PENH": "Phnom Penh",
    "SIHANOUKVILLE": "Sihanoukville",

    # South Asia
    "NHAVA SHEVA": "Nhava Sheva (Jawaharlal Nehru)", "JNPT": "Nhava Sheva (Jawaharlal Nehru)",
    "JAWAHARLAL NEHRU": "Nhava Sheva (Jawaharlal Nehru)",
    "MUMBAI": "Nhava Sheva (Jawaharlal Nehru)", "BOMBAY": "Nhava Sheva (Jawaharlal Nehru)",
    "CHENNAI": "Chennai", "MAA": "Chennai", "MADRAS": "Chennai",
    "MUNDRA": "Mundra", "MUN": "Mundra",
    "PIPAVAV": "Pipavav (Victor) Port", "PPV": "Pipavav (Victor) Port",
    "HAZIRA": "Hazira",
    "KATTUPALLI": "Kattupalli",
    "COCHIN": "Cochin", "COK": "Cochin", "KOCHI": "Cochin",
    "KOLKATA": "Kolkata (ex Calcutta)", "CCU": "Kolkata (ex Calcutta)",
    "CALCUTTA": "Kolkata (ex Calcutta)",
    "TUTICORIN": "Tuticorin", "TUT": "Tuticorin",
    "KARACHI": "Karachi", "KHI": "Karachi",
    "MUHAMMAD BIN QASIM": "Muhammad Bin Qasim", "QASIM": "Muhammad Bin Qasim",
    "PORT QASIM": "Muhammad Bin Qasim",
    "CHITTAGONG": "Chittagong", "CGP": "Chittagong",
    "COLOMBO": "Colombo", "CMB": "Colombo",

    # Middle East
    "JEBEL ALI": "Jebel Ali", "DXB": "Jebel Ali", "DUBAI": "Jebel Ali",
    "DAMMAM": "Dammam", "DMM": "Dammam",
    "BAHRAIN": "Bahrain", "BAH": "Bahrain",
    "MUSCAT": "Muscat",
    "SOHAR": "Sohar",
    "AQABA": "Aqaba",

    # Africa
    "MOMBASA": "Mombasa", "MBA": "Mombasa",
    "CAPE TOWN": "Cape Town", "CPT": "Cape Town",
    "DURBAN": "Durban", "DUR": "Durban",
    "BEIRA": "Beira",
    "MAPUTO": "Maputo",
    "DAR ES SALAAM": "Dar Es Salaam",

    # US Ports
    "LOS ANGELES": "Los Angeles", "LAX": "Los Angeles", "LA": "Los Angeles",
    "LONG BEACH": "Los Angeles",
    "NEW YORK": "New York", "NYC": "New York", "NEW YORK/NEW JERSEY": "New York",
    "NEWARK": "New York",
    "SEATTLE": "Seattle", "SEA": "Seattle",
    "TACOMA": "Tacoma", "TAC": "Tacoma",
    "OAKLAND": "Oakland", "OAK": "Oakland",
    "HOUSTON": "Houston", "HOU": "Houston",
    "SAVANNAH": "Savannah", "SAV": "Savannah",
    "CHARLESTON": "Charleston", "CHS": "Charleston",
    "NORFOLK": "Norfolk", "ORF": "Norfolk",
    "JACKSONVILLE": "Jacksonville", "JAX": "Jacksonville",
    "MIAMI": "Miami", "MIA": "Miami",
    "MOBILE": "Mobile", "MOB": "Mobile",
    "BALTIMORE": "Baltimore", "BWI": "Baltimore",
    "PORT EVERGLADES": "Miami",
    "BOSTON": "Boston", "BOS": "Boston",
    "PORTLAND": "Portland",

    # US Inland
    "CHICAGO": "Chicago", "CHI": "Chicago",
    "ATLANTA": "Atlanta", "ATL": "Atlanta",
    "DALLAS": "Dallas", "DAL": "Dallas", "DFW": "Dallas",
    "MEMPHIS": "Memphis", "MEM": "Memphis",
    "NASHVILLE": "Nashville", "BNA": "Nashville",
    "CHARLOTTE": "Charlotte", "CLT": "Charlotte",
    "DILLON": "Dillon",
    "GREER": "Greer",
    "KANSAS CITY": "Kansas City",
    "DETROIT": "Detroit",
    "COLUMBUS": "Columbus",
    "CINCINNATI": "Cincinnati",
    "SAINT LOUIS": "Saint Louis", "ST LOUIS": "Saint Louis", "ST. LOUIS": "Saint Louis",
    "MINNEAPOLIS": "Minneapolis",
    "DENVER": "Denver",
    "PHOENIX": "Phoenix",
    "LAS VEGAS": "Las Vegas",
    "RENO": "Reno",
    "SAN ANTONIO": "San Antonio",
    "EL PASO": "El Paso",

    # Canada
    "VANCOUVER": "Vancouver", "YVR": "Vancouver",
    "HALIFAX": "Halifax", "YHZ": "Halifax",
    "MONTREAL": "Montreal",
    "TORONTO": "Toronto",

    # Europe
    "ROTTERDAM": "Rotterdam", "RTM": "Rotterdam",
    "HAMBURG": "Hamburg", "HAM": "Hamburg",
    "ANTWERP": "Antwerp", "ANR": "Antwerp",
    "FELIXSTOWE": "Felixstowe",
    "SOUTHAMPTON": "Southampton",
    "LE HAVRE": "Le Havre",
    "PIRAEUS": "Piraeus",
    "GENOA": "Genoa",
    "BARCELONA": "Barcelona",
    "VALENCIA": "Valencia",
    "BREMERHAVEN": "Bremerhaven",
}

_PROVINCE_RE    = re.compile(r",\s*[A-Z][a-zA-Z\s]+$")
# 2-letter ISO country codes that sometimes appear after port name: "DALIAN CN", "BUSAN KR"
_COUNTRY_CODE_RE = re.compile(r"\s+[A-Z]{2}$")
# "CITY/PORT/TERMINAL" suffix that some PDFs append: "KAOHSIUNG CITY" → "KAOHSIUNG"
_CITY_SUFFIX_RE  = re.compile(r"\s+(?:CITY|PORT|TERMINAL)$")

# Pre-sorted list for partial-match fallback (longest key first → avoids short key shadowing)
# Built once at import time so normalize_port() never re-sorts on every call.
_PARTIAL_MATCH_KEYS: list[tuple[str, str]] = sorted(
    ((k, v) for k, v in PORT_MAP.items() if len(k) >= 4),
    key=lambda x: -len(x[0]),
)


def normalize_port(raw: str) -> str:
    """Normalize a raw port/city name to canonical form."""
    if not raw:
        return raw

    clean = raw.strip()
    upper = clean.upper()

    # Direct match
    if upper in PORT_MAP:
        return PORT_MAP[upper]

    # Strip trailing 2-letter country code: "DALIAN CN" → "DALIAN"
    stripped_cc = _COUNTRY_CODE_RE.sub("", upper).strip()
    if stripped_cc in PORT_MAP:
        return PORT_MAP[stripped_cc]

    # Strip CITY/PORT/TERMINAL suffix: "KAOHSIUNG CITY" → "KAOHSIUNG"
    stripped_city = _CITY_SUFFIX_RE.sub("", upper).strip()
    if stripped_city in PORT_MAP:
        return PORT_MAP[stripped_city]

    # Without province suffix: "QINGDAO, SHANDONG" → "QINGDAO"
    base = _PROVINCE_RE.sub("", upper).strip()
    if base in PORT_MAP:
        return PORT_MAP[base]

    # After stripping province + country code
    base_cc = _COUNTRY_CODE_RE.sub("", base).strip()
    if base_cc in PORT_MAP:
        return PORT_MAP[base_cc]

    # First word only: "JAKARTA, JAVA" → "JAKARTA"
    first = upper.split(",")[0].strip()
    if first in PORT_MAP:
        return PORT_MAP[first]

    # First word after stripping CITY suffix
    first_stripped = _CITY_SUFFIX_RE.sub("", first).strip()
    if first_stripped in PORT_MAP:
        return PORT_MAP[first_stripped]

    # Partial match — check if any known port name appears inside the raw value.
    # Uses pre-sorted list (longest key first) so "LONG BEACH" wins over "BEACH".
    for key, canonical in _PARTIAL_MATCH_KEYS:
        if key in upper:
            return canonical

    return clean.title()
