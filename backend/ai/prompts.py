"""Prompt templates for Claude AI freight data extraction."""

SYSTEM_PROMPT = (
    "You are a freight contract data extraction specialist. "
    "You extract structured rate data from ocean freight service contracts and "
    "output valid JSON conforming to the given schema. "
    "Be precise with port names, numeric values, and dates. "
    "Never infer values not present in the text. "
    "Always output ONLY the JSON requested — no explanation, no markdown fences."
)

METADATA_PROMPT = """Extract the contract header fields from this freight contract text.

TEXT:
{text}

Return JSON object:
{{
  "carrier": "string",
  "contract_id": "string",
  "effective_date": "DD MMM YYYY format",
  "expiration_date": "DD MMM YYYY format",
  "commodity": "string",
  "scope": "string (trade lane description)"
}}
"""

RATES_PROMPT = """Extract ALL freight rate rows from this section of a shipping contract.

CONTRACT:
- Carrier: {carrier}
- Contract ID: {contract_id}
- Effective: {effective_date}
- Expiration: {expiration_date}
- Commodity: {commodity}
- SCOPE: {scope}
- Origin: {origin_city}
- Origin Via: {origin_via}

SECTION TEXT:
{text}

Return a JSON array. Each element:
{{
  "destination_city": "city name only",
  "destination_via_city": "transit port or null",
  "service": "CY/CY or CY or CY/CFS",
  "base_rate_20": number or null,
  "base_rate_40": number or null,
  "base_rate_40h": number or null,
  "base_rate_45": number or null,
  "remarks": "string or null"
}}

Rules:
- All rates are USD integers — no currency symbol
- 40HC, 40H, 40HQ all mean 40-foot high cube → base_rate_40h
- Blank or dash → null
- destination_via_city is the intermediate trunk port (not the final destination)
- Do NOT include header rows
- Output ONLY the JSON array
"""

SURCHARGE_PROMPT = """Extract surcharge values from this freight contract text.

TEXT:
{text}

For each surcharge, output the per-TEU USD numeric value if stated,
"INCLUSIVE" if already included in base rate, "TARIFF" if subject to tariff, or null if not mentioned.

Return JSON:
{{
  "ams_china_japan": value,
  "hea_heavy_surcharge": value,
  "agw": value,
  "rds_red_sea": value
}}
"""

ORIGIN_ARB_PROMPT = """Extract origin arbitrary charges from this section.

SECTION TEXT:
{text}

CONTRACT:
- Carrier: {carrier}
- Contract ID: {contract_id}
- Effective: {effective_date}
- Expiration: {expiration_date}
- Commodity: {commodity}
- SCOPE: {scope}

Return JSON array. Each element:
{{
  "origin_city": "inland point/city",
  "origin_via_city": "trunk port this arbitrary is for",
  "service": "CY",
  "base_rate_20": number or null,
  "base_rate_40": number or null,
  "base_rate_40h": number or null,
  "base_rate_45": number or null,
  "agw_20": number or null,
  "agw_40": number or null,
  "agw_45": number or null,
  "remarks": "string or null"
}}

Output ONLY the JSON array.
"""

DEST_ARB_PROMPT = """Extract destination arbitrary charges from this section.

SECTION TEXT:
{text}

CONTRACT:
- Carrier: {carrier}
- Contract ID: {contract_id}
- Effective: {effective_date}
- Expiration: {expiration_date}
- Commodity: {commodity}
- SCOPE: {scope}

Return JSON array. Each element:
{{
  "destination_city": "inland point/city",
  "destination_via_city": "trunk port this arbitrary is over",
  "service": "CY",
  "base_rate_20": number or null,
  "base_rate_40": number or null,
  "base_rate_40h": number or null,
  "base_rate_45": number or null,
  "remarks": "string or null"
}}

Output ONLY the JSON array.
"""
