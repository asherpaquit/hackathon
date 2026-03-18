"""Compact prompt templates for Ollama freight data extraction."""

SYSTEM_PROMPT = (
    "You are a freight contract data extraction specialist. "
    "Output ONLY valid JSON — no explanation, no markdown, no code fences. "
    "Be precise with port names and numbers. Never infer or guess missing values."
)

METADATA_PROMPT = """Extract metadata from this freight contract text:
{text}

Return this exact JSON (fill in values, keep empty string if not found):
{{"carrier":"","contract_id":"","effective_date":"DD MMM YYYY","expiration_date":"DD MMM YYYY","commodity":"","scope":""}}

Rules: effective_date and expiration_date must be in "DD MMM YYYY" format (e.g. "1 Jan 2026")."""

RATES_PROMPT = """Extract ALL freight rate rows from the data below.
Carrier:{carrier} Contract:{contract_id} Effective:{effective_date} Expiry:{expiration_date} Commodity:{commodity} Scope:{scope}
ORIGIN:{origin_city} Via:{origin_via}

{text}

Return a JSON array — one object per destination row:
[{{"destination_city":"","destination_via_city":null,"service":"CY/CY","base_rate_20":null,"base_rate_40":null,"base_rate_40h":null,"base_rate_45":null,"remarks":null}}]

Rules:
- Numbers only for rates: strip commas ("2,500"→2500), commodity codes ("R2/2298"→2298)
- 40HC / 40HQ / 40H / HC → base_rate_40h
- TARIFF or INCLUSIVE → keep as that string (not null)
- Blank cell / dash / N/A → null
- Default service to "CY/CY" if not shown
- Use exact port names from the text"""

SURCHARGE_PROMPT = """Extract surcharge amounts from this freight contract text:
{text}

Return this exact JSON:
{{"ams_china_japan":null,"hea_heavy_surcharge":null,"agw":null,"rds_red_sea":null}}

Rules: Use a USD number if shown, "INCLUSIVE" if stated inclusive, "TARIFF" if as per tariff, null if not mentioned."""

ORIGIN_ARB_PROMPT = """Extract origin arbitrary charges.
Carrier:{carrier} Contract:{contract_id} Effective:{effective_date} Expiry:{expiration_date} Commodity:{commodity} Scope:{scope}

{text}

Return a JSON array:
[{{"origin_city":"","origin_via_city":null,"service":"CY","base_rate_20":null,"base_rate_40":null,"base_rate_40h":null,"base_rate_45":null,"agw_20":null,"agw_40":null,"agw_45":null,"remarks":null}}]

Rules: Numbers only for rates. Blank/dash→null. Use exact port names from the text."""

DEST_ARB_PROMPT = """Extract destination arbitrary charges.
Carrier:{carrier} Contract:{contract_id} Effective:{effective_date} Expiry:{expiration_date} Commodity:{commodity} Scope:{scope}

{text}

Return a JSON array:
[{{"destination_city":"","destination_via_city":null,"service":"CY","base_rate_20":null,"base_rate_40":null,"base_rate_40h":null,"base_rate_45":null,"remarks":null}}]

Rules: Numbers only for rates. Blank/dash→null. Use exact port names from the text."""
