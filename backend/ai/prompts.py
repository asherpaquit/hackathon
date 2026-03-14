"""Compact prompt templates for Ollama freight data extraction."""

SYSTEM_PROMPT = (
    "You are a freight contract data extraction specialist. "
    "Extract structured data and output valid JSON only. "
    "Be precise with port names and numbers. Never infer missing values."
)

METADATA_PROMPT = """Extract from this freight contract text:
{text}

Return JSON:
{{"carrier":"","contract_id":"","effective_date":"DD MMM YYYY","expiration_date":"DD MMM YYYY","commodity":"","scope":""}}"""

RATES_PROMPT = """Extract rate rows. Carrier:{carrier} Contract:{contract_id} Dates:{effective_date}-{expiration_date} Commodity:{commodity} Scope:{scope} Origin:{origin_city} Via:{origin_via}

{text}

Return JSON array:
[{{"destination_city":"","destination_via_city":null,"service":"CY/CY","base_rate_20":null,"base_rate_40":null,"base_rate_40h":null,"base_rate_45":null,"remarks":null}}]
Rules: USD integers only. 40HC/40HQ→base_rate_40h. Blank/dash→null."""

SURCHARGE_PROMPT = """Extract surcharges from:
{text}

Return JSON (USD number, "INCLUSIVE", "TARIFF", or null):
{{"ams_china_japan":null,"hea_heavy_surcharge":null,"agw":null,"rds_red_sea":null}}"""

ORIGIN_ARB_PROMPT = """Extract origin arbitrary charges.
Carrier:{carrier} Contract:{contract_id} Dates:{effective_date}-{expiration_date} Commodity:{commodity} Scope:{scope}

{text}

Return JSON array:
[{{"origin_city":"","origin_via_city":"","service":"CY","base_rate_20":null,"base_rate_40":null,"base_rate_40h":null,"base_rate_45":null,"agw_20":null,"agw_40":null,"agw_45":null,"remarks":null}}]"""

DEST_ARB_PROMPT = """Extract destination arbitrary charges.
Carrier:{carrier} Contract:{contract_id} Dates:{effective_date}-{expiration_date} Commodity:{commodity} Scope:{scope}

{text}

Return JSON array:
[{{"destination_city":"","destination_via_city":"","service":"CY","base_rate_20":null,"base_rate_40":null,"base_rate_40h":null,"base_rate_45":null,"remarks":null}}]"""
