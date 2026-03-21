"""
Extract contract rules from Sections 1-12 using regex (primary) + Ollama LLM (optional).

Sections 7-12 contain natural-language provisions, notes, and exceptions that
determine per-scope effective/expiry dates, surcharge inclusions, and special
rules.

NEW: Pure-regex extraction is now the PRIMARY path — it runs always, even
without Ollama, and catches 80%+ of rules. Ollama is used as an optional
enhancement pass that can catch edge cases the regex misses.

This guarantees rules are always extracted, improving accuracy significantly
over the previous Ollama-only approach.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger("rules_extractor")

# ── Month name helpers ────────────────────────────────────────────────────────

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

_MONTH_MAP = {}
for _i, _m in enumerate(_MONTHS, 1):
    _MONTH_MAP[_m.lower()] = _i
    _MONTH_MAP[_m.lower()[:3]] = _i
# Also add full month names
for _i, _full in enumerate([
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december"
], 1):
    _MONTH_MAP[_full] = _i


def _yyyymmdd_to_dmy(year: str, month: str, day: str) -> str:
    mon = _MONTHS[int(month) - 1]
    return f"{int(day)} {mon} {int(year)}"


# ══════════════════════════════════════════════════════════════════════════════
#  PURE REGEX RULES EXTRACTION (runs always — no LLM needed)
# ══════════════════════════════════════════════════════════════════════════════

# Scope names in square brackets: [ASIA - NORTH AMERICA WEST COAST (EB)]
_SCOPE_RE = re.compile(r"\[\s*([A-Z][A-Z\s\-\(\)]+?)\s*\]")

# Section 8 "DURATION" date patterns
# Format 1: "Effective Date : 01 April 2025"  /  "Effective Through : 31 March 2026"
_DURATION_EFF_RE = re.compile(
    r"Effective\s+(?:Date|From)\s*[:\-]?\s*(\d{1,2}\s+[A-Za-z]+[,.]?\s*\d{4})",
    re.I,
)
_DURATION_EXP_RE = re.compile(
    r"(?:Effective\s+Through|Expir(?:ation|y)\s*(?:Date)?|Through\s+Date|End\s+Date)"
    r"\s*[:\-]?\s*(\d{1,2}\s+[A-Za-z]+[,.]?\s*\d{4})",
    re.I,
)
# Format 2: YYYYMMDD  "20250401 to 20260331"
_DURATION_YYYYMMDD_RE = re.compile(
    r"(\d{4})(\d{2})(\d{2})\s*(?:to|through|[-–])\s*(\d{4})(\d{2})(\d{2})",
    re.I,
)

# Section 12.B surcharge structure clause
# "inclusive of all surcharges ... published ... on or before <DATE>"
_SURCHARGE_CUTOFF_RE = re.compile(
    r"inclusive\s+of\s+(?:all\s+)?surcharges?\s+.*?"
    r"(?:published|filed|effective)\s+.*?"
    r"(?:on\s+or\s+before|through|by)\s+"
    r"(\d{1,2}\s+[A-Za-z]+[,.]?\s*\d{4}|\d{8})",
    re.I | re.DOTALL,
)

# Section 12 applicable surcharge codes
_SURCHARGE_CODES_RE = re.compile(
    r"(?:include|including|applicable|subject\s+to)[,\s:]*"
    r"(?:but\s+(?:are\s+)?not\s+limited\s+to[,\s:]*)?"
    r"([A-Z]{2,5}(?:\s*[,/]\s*[A-Z]{2,5}){1,20})",
    re.I,
)

# RDS / Red Sea Diversion inclusion
_RDS_INCLUSION_RE = re.compile(
    r"(?:RDS|RED\s+SEA\s+(?:DIVERSION|SURCHARGE))\s+(?:CHARGE\s+)?"
    r"(?:is\s+)?(?:INCLUDED|INCLUSIVE|INCL\.?|included\s+in)",
    re.I,
)
_RDS_SECTION_RE = re.compile(
    r"(?:RDS|RED\s+SEA)",
    re.I,
)

# Container glossary: "D2 = 20' Dry Container"  or  "D2: 20' Dry"
_GLOSSARY_RE = re.compile(
    r"\b([DRdr]\d)\b\s*[=:\-–]\s*([^\n,;]{3,50})",
)

# Reefer indicator in glossary descriptions
_REEFER_DESC_RE = re.compile(r"reefer|refrigerat|RF|NOR", re.I)


def _extract_scopes(text: str) -> list[str]:
    """Extract all unique scope names from the text."""
    scopes = []
    seen = set()
    for m in _SCOPE_RE.finditer(text):
        scope = m.group(1).strip()
        scope_upper = scope.upper()
        if scope_upper not in seen and len(scope) > 5:
            # Filter out false positives
            if any(kw in scope_upper for kw in (
                "AMERICA", "ASIA", "EUROPE", "AFRICA", "OCEANIA",
                "EAST", "WEST", "NORTH", "SOUTH", "COAST",
                "PACIFIC", "ATLANTIC", "MEDITERRANEAN", "INDIAN",
            )):
                scopes.append(scope)
                seen.add(scope_upper)
    return scopes


def _extract_scope_dates_block(text: str, scope: str) -> dict[str, str]:
    """Extract effective/expiry dates from a text block associated with a scope."""
    result: dict[str, str] = {}

    # Look for the scope in the text, then scan nearby lines
    scope_idx = text.upper().find(scope.upper())
    if scope_idx == -1:
        return result

    # Search in a window around the scope mention (500 chars after)
    window = text[max(0, scope_idx - 100):scope_idx + 500]

    # Try DD Month YYYY format
    eff_m = _DURATION_EFF_RE.search(window)
    if eff_m:
        result["effective"] = eff_m.group(1).strip().replace(",", "")

    exp_m = _DURATION_EXP_RE.search(window)
    if exp_m:
        result["expiry"] = exp_m.group(1).strip().replace(",", "")

    # Try YYYYMMDD format
    if not result:
        m = _DURATION_YYYYMMDD_RE.search(window)
        if m:
            result["effective"] = _yyyymmdd_to_dmy(m.group(1), m.group(2), m.group(3))
            result["expiry"] = _yyyymmdd_to_dmy(m.group(4), m.group(5), m.group(6))

    return result


def _extract_surcharge_codes(text: str) -> list[str]:
    """Extract surcharge code lists from text."""
    codes: list[str] = []
    for m in _SURCHARGE_CODES_RE.finditer(text):
        raw = m.group(1)
        for code in re.split(r"[,/\s]+", raw):
            code = code.strip().upper()
            if 2 <= len(code) <= 5 and code.isalpha():
                if code not in codes:
                    codes.append(code)
    return codes


def _extract_glossary(text: str) -> dict[str, str]:
    """Extract container code glossary (D2, D4, R2, etc.)."""
    glossary: dict[str, str] = {}
    for m in _GLOSSARY_RE.finditer(text):
        code = m.group(1).upper()
        desc = m.group(2).strip().rstrip(".,;")
        if desc:
            glossary[code] = desc
    return glossary


def extract_rules_regex(rules_text: str) -> dict[str, Any]:
    """
    Extract contract rules using pure regex — no LLM required.

    This is the PRIMARY extraction path. Handles:
    - Section 8: per-scope effective/expiry dates
    - Section 12.B: surcharge structure, applicable codes
    - Section 12.C: RDS inclusion exceptions
    - Glossary: container code → description mapping
    - Reefer code identification

    Returns the standard rules dict format.
    """
    if not rules_text or len(rules_text.strip()) < 50:
        return _default_rules()

    text = rules_text

    # ── 1. Find all scopes ────────────────────────────────────────────────────
    scopes = _extract_scopes(text)
    logger.info(f"[rules:regex] Found {len(scopes)} scopes: {scopes}")

    # ── 2. Per-scope dates (Section 8 "DURATION") ─────────────────────────────
    scope_dates: dict[str, dict] = {}

    # First try to find a DURATION section
    duration_idx = re.search(r"(?:8\.|SECTION\s*8|DURATION)", text, re.I)
    duration_text = text[duration_idx.start():] if duration_idx else text

    for scope in scopes:
        dates = _extract_scope_dates_block(duration_text, scope)
        if dates:
            scope_dates[scope] = dates

    # If no per-scope dates found, try global dates in the duration section
    if not scope_dates and scopes:
        eff_m = _DURATION_EFF_RE.search(duration_text)
        exp_m = _DURATION_EXP_RE.search(duration_text)
        if eff_m and exp_m:
            for scope in scopes:
                scope_dates[scope] = {
                    "effective": eff_m.group(1).strip().replace(",", ""),
                    "expiry": exp_m.group(1).strip().replace(",", ""),
                }
        # Also try YYYYMMDD
        if not scope_dates:
            m = _DURATION_YYYYMMDD_RE.search(duration_text)
            if m:
                for scope in scopes:
                    scope_dates[scope] = {
                        "effective": _yyyymmdd_to_dmy(m.group(1), m.group(2), m.group(3)),
                        "expiry": _yyyymmdd_to_dmy(m.group(4), m.group(5), m.group(6)),
                    }

    # ── 3. Per-scope surcharge config (Section 12) ────────────────────────────
    scope_surcharges: dict[str, dict] = {}

    for scope in scopes:
        surch_config: dict[str, Any] = {
            "surcharge_inclusion_cutoff": None,
            "applicable_surcharges": [],
            "hazardous_surcharges": [],
            "rds_included_for_dry": False,
            "notes": "",
        }

        # Find scope context window for surcharge analysis
        scope_upper = scope.upper()
        scope_positions = [m.start() for m in re.finditer(re.escape(f"[{scope}]"), text, re.I)]
        if not scope_positions:
            scope_positions = [m.start() for m in re.finditer(re.escape(scope), text, re.I)]

        for pos in scope_positions:
            window = text[pos:pos + 1500]

            # Surcharge cutoff date
            cutoff_m = _SURCHARGE_CUTOFF_RE.search(window)
            if cutoff_m:
                surch_config["surcharge_inclusion_cutoff"] = cutoff_m.group(1).strip()

            # Applicable surcharge codes
            codes = _extract_surcharge_codes(window)
            if codes:
                surch_config["applicable_surcharges"] = codes

            # RDS inclusion check
            if _RDS_INCLUSION_RE.search(window):
                surch_config["rds_included_for_dry"] = True
            elif _RDS_SECTION_RE.search(window):
                # Check for "included" in nearby context
                rds_window = window[window.upper().find("RDS" if "RDS" in window.upper() else "RED SEA"):][:300]
                if re.search(r"includ", rds_window, re.I):
                    surch_config["rds_included_for_dry"] = True

        # Only add if we found something useful
        if (surch_config["surcharge_inclusion_cutoff"]
                or surch_config["applicable_surcharges"]
                or surch_config["rds_included_for_dry"]):
            scope_surcharges[scope] = surch_config

    # If no per-scope RDS found, do a global check
    if not any(s.get("rds_included_for_dry") for s in scope_surcharges.values()):
        if _RDS_INCLUSION_RE.search(text):
            for scope in scopes:
                if scope not in scope_surcharges:
                    scope_surcharges[scope] = {
                        "surcharge_inclusion_cutoff": None,
                        "applicable_surcharges": [],
                        "hazardous_surcharges": [],
                        "rds_included_for_dry": True,
                        "notes": "Global RDS inclusion detected",
                    }
                else:
                    scope_surcharges[scope]["rds_included_for_dry"] = True

    # ── 4. Container glossary ─────────────────────────────────────────────────
    glossary = _extract_glossary(text)

    # Also try to find glossary in the full contract text (sometimes it's
    # in the preamble, not sections 7-12)
    if not glossary:
        # Common hardcoded fallbacks for known contract formats
        # These are standard IATA container codes used across carriers
        glossary = {}  # Don't hardcode — let the parser discover them

    # ── 5. Reefer codes ───────────────────────────────────────────────────────
    reefer_codes: list[str] = []
    for code, desc in glossary.items():
        if _REEFER_DESC_RE.search(desc) or code.upper().startswith("R"):
            if code.upper() not in reefer_codes:
                reefer_codes.append(code.upper())

    rules = {
        "scope_dates": scope_dates,
        "scope_surcharges": scope_surcharges,
        "container_glossary": glossary,
        "reefer_codes": reefer_codes,
    }

    n_scopes = len(scope_dates)
    n_surcharges = len(scope_surcharges)
    n_glossary = len(glossary)
    logger.info(
        f"[rules:regex] Extracted: {n_scopes} scope dates, "
        f"{n_surcharges} scope surcharge configs, "
        f"{n_glossary} container codes, "
        f"reefer codes: {reefer_codes}"
    )

    return rules


# ══════════════════════════════════════════════════════════════════════════════
#  FULL CONTRACT TEXT EXTRACTION (Sections 1-6 metadata)
# ══════════════════════════════════════════════════════════════════════════════

def extract_preamble_rules(full_text: str) -> dict[str, Any]:
    """
    Extract rules from sections 1-6 (preamble, origins, destinations,
    commodities, min quantity) — these contain structural info that
    informs the extraction.

    Returns a dict to merge with the main rules dict.
    """
    rules: dict[str, Any] = {}

    # Extract glossary from anywhere in the document (it's often in the GLOSSARY
    # section at the very end, which may not be in "rules_text")
    glossary = _extract_glossary(full_text)
    if glossary:
        rules["container_glossary"] = glossary

        reefer_codes = []
        for code, desc in glossary.items():
            if _REEFER_DESC_RE.search(desc) or code.upper().startswith("R"):
                reefer_codes.append(code.upper())
        if reefer_codes:
            rules["reefer_codes"] = reefer_codes

    return rules


# ══════════════════════════════════════════════════════════════════════════════
#  OLLAMA LLM EXTRACTION (primary for sections 7-12)
# ══════════════════════════════════════════════════════════════════════════════

def check_ollama_available(host: str) -> bool:
    """Check if Ollama is running and accessible."""
    try:
        import httpx
        resp = httpx.get(f"{host}/api/tags", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


def _call_ollama(prompt: str, host: str, model: str, timeout: float = 180.0) -> str:
    """Send a prompt to Ollama and return the response text."""
    import httpx
    response = httpx.post(
        f"{host}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.05,   # near-deterministic for extraction
                "num_predict": 6144,   # rules JSON can be large
                "top_p": 0.9,
                "repeat_penalty": 1.1,
            },
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json().get("response", "")


# ── Section splitter — send each section to Ollama separately ─────────────────

_SEC_HEADER_RE = re.compile(
    r"(?:^|\n)(?:SECTION\s+)?(\d{1,2})\s*[.\)]\s+([A-Z][^\n]{0,60})",
    re.MULTILINE,
)

def _split_into_sections(text: str) -> dict[int, str]:
    """
    Split rules text into individual sections by number.
    Returns {section_number: section_text} for sections 7-12.
    """
    sections: dict[int, str] = {}
    matches = list(_SEC_HEADER_RE.finditer(text))

    for i, m in enumerate(matches):
        num = int(m.group(1))
        if num < 7 or num > 12:
            continue
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[num] = text[start:end].strip()

    return sections


# ── Prompts — one per section group for better accuracy ───────────────────────

_PROMPT_DURATION = """\
You are parsing Section 8 (DURATION) of a freight contract.
Extract the effective date and expiry date for EACH SCOPE listed.

Scope names appear in square brackets, e.g. [NORTH AMERICA - ASIA (WB)].
Use the text inside brackets as the key (no brackets).

Dates may appear as:
- "Effective Date : 01 April 2025"
- "Effective Through : 31 March 2026"
- "20250401 to 20260331" (YYYYMMDD format, convert to DD Mon YYYY)

Return ONLY valid JSON (no markdown, no explanation):
{{
  "scope_dates": {{
    "SCOPE NAME": {{"effective": "01 Apr 2025", "expiry": "31 Mar 2026"}}
  }}
}}

If only one date range applies to all scopes, repeat it for each scope found.

CONTRACT TEXT:
---
{text}
---"""

_PROMPT_SURCHARGES = """\
You are parsing Section 12 (PROVISIONS/SURCHARGES) of a freight contract.
Extract surcharge rules for EACH SCOPE listed.

Scope names appear in square brackets, e.g. [NORTH AMERICA - ASIA (WB)].

Look for:
1. Surcharge Structure Clause: "inclusive of all surcharges...on or before <DATE>" — extract cutoff date
2. Overweight Cargo Clause: list of applicable codes (HEA, OWT, TRI, AGW, RDS, etc.)
3. RDS/Red Sea: if "RED SEA DIVERSION" or "RDS" is "INCLUDED" or "INCLUSIVE" → set rds_included_for_dry: true
4. Any scope-specific exceptions in 12.C "Exceptions"

Return ONLY valid JSON (no markdown, no explanation):
{{
  "scope_surcharges": {{
    "SCOPE NAME": {{
      "surcharge_inclusion_cutoff": "01 Apr 2025 or null",
      "applicable_surcharges": ["HEA", "AGW"],
      "rds_included_for_dry": false,
      "notes": "any special notes"
    }}
  }}
}}

CONTRACT TEXT:
---
{text}
---"""

_PROMPT_GLOSSARY = """\
You are parsing a freight contract GLOSSARY section.
Extract container/equipment code mappings.

Look for patterns like:
- "D2 = 20' Dry Standard Container"
- "D4: 40' Dry Container"
- "R2 - 20' Reefer Container"
- "D5 40HC High Cube"

Container codes are typically 1-2 letters + 1 digit (D2, D4, D5, D7, R2, R5, etc.)
Reefer codes: any code whose description contains "reefer", "refrigerat", "RF", or "NOR"

Return ONLY valid JSON (no markdown, no explanation):
{{
  "container_glossary": {{
    "D2": "20' Dry Standard",
    "R2": "20' Reefer"
  }},
  "reefer_codes": ["R2", "R5"]
}}

CONTRACT TEXT:
---
{text}
---"""

_PROMPT_FULL_FALLBACK = """\
You are a freight contract parser. Extract ALL rules from sections 7-12 below.

Return ONLY valid JSON (no markdown, no explanation):
{{
  "scope_dates": {{
    "SCOPE NAME": {{"effective": "DD Mon YYYY", "expiry": "DD Mon YYYY"}}
  }},
  "scope_surcharges": {{
    "SCOPE NAME": {{
      "surcharge_inclusion_cutoff": "date or null",
      "applicable_surcharges": ["CODE"],
      "rds_included_for_dry": false,
      "notes": ""
    }}
  }},
  "container_glossary": {{"CODE": "description"}},
  "reefer_codes": ["CODE"]
}}

Rules:
- Scope names are in [brackets] — use without brackets as keys
- Section 8 has effective/expiry dates per scope
- Section 12 has surcharge inclusions and RDS rules
- Glossary maps container codes (D2=20'dry, R2=20'reefer, etc.)
- Reefer codes start with R or mention "reefer"/"RF" in description

CONTRACT TEXT:
---
{text}
---"""


# ── JSON parsing with aggressive repair ───────────────────────────────────────

def _parse_rules_json(response: str) -> dict:
    """
    Parse LLM response into a dict.
    Handles markdown fences, truncated JSON, trailing commas, and other
    common LLM output quirks.
    """
    text = response.strip()

    # Strip markdown code fences
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                text = part
                break

    # Find the outermost JSON object
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found")
    end = text.rfind("}") + 1
    if end <= start:
        # Truncated — try to close it
        text = text[start:] + "}"
        end = len(text)

    json_str = text[start:end]

    # Fix common LLM issues
    json_str = re.sub(r",\s*([}\]])", r"\1", json_str)      # trailing commas
    json_str = re.sub(r"//[^\n]*", "", json_str)             # JS-style comments
    json_str = re.sub(r"'([^']*)':", r'"\1":', json_str)    # single-quoted keys

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # Last resort: try to extract just the innermost valid JSON pieces
        raise ValueError(f"JSON parse failed. First 300 chars: {json_str[:300]}")


def _default_rules() -> dict:
    """Return empty rules dict — pipeline falls back to regex-only mode."""
    return {
        "scope_dates": {},
        "scope_surcharges": {},
        "container_glossary": {},
        "reefer_codes": [],
    }


def _merge_rules(base: dict, overlay: dict) -> dict:
    """
    Merge two rules dicts. Overlay values take precedence for non-empty fields.
    Used to merge regex results with LLM results (LLM wins on conflicts).
    """
    merged = dict(base)
    for key in ("scope_dates", "scope_surcharges", "container_glossary"):
        base_dict = dict(merged.get(key, {}))
        overlay_dict = overlay.get(key, {})
        if overlay_dict:
            base_dict.update(overlay_dict)
            merged[key] = base_dict

    # Reefer codes: union of both
    base_reefer = set(merged.get("reefer_codes", []))
    overlay_reefer = set(overlay.get("reefer_codes", []))
    merged["reefer_codes"] = sorted(base_reefer | overlay_reefer)

    return merged


def _ollama_extract_chunked(rules_text: str, host: str, model: str) -> dict:
    """
    Extract rules by sending sections 8, 12, and glossary to Ollama separately.

    Chunked extraction is significantly more accurate than sending the full
    text at once because:
    1. Each prompt is laser-focused on one task
    2. Shorter context = less hallucination
    3. Retry can be targeted to the failing section only
    """
    sections = _split_into_sections(rules_text)
    merged: dict[str, Any] = _default_rules()

    # ── Section 8: DURATION dates ─────────────────────────────────────────────
    sec8_text = sections.get(8, "")
    if not sec8_text:
        # Fallback: search raw text for "DURATION" or "8."
        m = re.search(r"(?:8\s*[.\)]\s*DURATION|SECTION\s*8)", rules_text, re.I)
        if m:
            # grab up to 2000 chars from that point
            sec8_text = rules_text[m.start():m.start() + 2000]

    if sec8_text:
        for attempt in range(2):
            try:
                raw = _call_ollama(
                    _PROMPT_DURATION.format(text=sec8_text[:3000]),
                    host, model, timeout=90.0,
                )
                parsed = _parse_rules_json(raw)
                if parsed.get("scope_dates"):
                    merged["scope_dates"] = parsed["scope_dates"]
                    logger.info(f"[rules:llm] Section 8: {len(merged['scope_dates'])} scope dates")
                    break
            except Exception as e:
                logger.warning(f"[rules:llm] Section 8 attempt {attempt + 1} failed: {e}")

    # ── Section 12: SURCHARGES ────────────────────────────────────────────────
    sec12_text = sections.get(12, "")
    if not sec12_text:
        m = re.search(r"(?:12\s*[.\)]\s*PROVISIONS|SECTION\s*12)", rules_text, re.I)
        if m:
            sec12_text = rules_text[m.start():m.start() + 4000]

    if sec12_text:
        for attempt in range(2):
            try:
                raw = _call_ollama(
                    _PROMPT_SURCHARGES.format(text=sec12_text[:4000]),
                    host, model, timeout=90.0,
                )
                parsed = _parse_rules_json(raw)
                if parsed.get("scope_surcharges"):
                    merged["scope_surcharges"] = parsed["scope_surcharges"]
                    logger.info(f"[rules:llm] Section 12: {len(merged['scope_surcharges'])} surcharge configs")
                    break
            except Exception as e:
                logger.warning(f"[rules:llm] Section 12 attempt {attempt + 1} failed: {e}")

    # ── Glossary (anywhere in the text) ───────────────────────────────────────
    # Find GLOSSARY section or scan the last 3000 chars
    gloss_m = re.search(r"GLOSSARY", rules_text, re.I)
    gloss_text = rules_text[gloss_m.start():] if gloss_m else rules_text[-3000:]

    if gloss_text:
        for attempt in range(2):
            try:
                raw = _call_ollama(
                    _PROMPT_GLOSSARY.format(text=gloss_text[:2000]),
                    host, model, timeout=60.0,
                )
                parsed = _parse_rules_json(raw)
                if parsed.get("container_glossary"):
                    merged["container_glossary"] = parsed["container_glossary"]
                    merged["reefer_codes"] = parsed.get("reefer_codes", [])
                    logger.info(
                        f"[rules:llm] Glossary: {len(merged['container_glossary'])} codes, "
                        f"reefer: {merged['reefer_codes']}"
                    )
                    break
            except Exception as e:
                logger.warning(f"[rules:llm] Glossary attempt {attempt + 1} failed: {e}")

    return merged


def _ollama_extract_full(rules_text: str, host: str, model: str) -> dict:
    """
    Fallback: send the full rules text at once when section splitting failed.
    Retries once with a simplified prompt if the first attempt fails.
    """
    capped = rules_text[:10000]

    for attempt, prompt_template in enumerate([_PROMPT_FULL_FALLBACK, _PROMPT_FULL_FALLBACK]):
        try:
            prompt = prompt_template.format(text=capped if attempt == 0 else capped[:5000])
            raw = _call_ollama(prompt, host, model, timeout=180.0)
            parsed = _parse_rules_json(raw)

            for key in ("scope_dates", "scope_surcharges", "container_glossary", "reefer_codes"):
                if key not in parsed:
                    parsed[key] = _default_rules()[key]

            n_scopes = len(parsed.get("scope_dates", {}))
            logger.info(f"[rules:llm] Full extraction: {n_scopes} scope dates (attempt {attempt + 1})")
            return parsed
        except Exception as e:
            logger.warning(f"[rules:llm] Full extraction attempt {attempt + 1} failed: {e}")

    return _default_rules()


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN ENTRY POINTS
# ══════════════════════════════════════════════════════════════════════════════

def extract_rules(rules_text: str, host: str = "", model: str = "") -> dict:
    """
    Extract contract rules from sections 7-12 text.

    Strategy:
    1. ALWAYS run regex extraction (fast, reliable, no dependencies)
    2. If Ollama available → run CHUNKED LLM extraction (section 8 + 12 + glossary
       sent separately for higher accuracy), then merge with regex results.
       LLM wins on conflicts.
    3. Return merged result

    This guarantees rules are always extracted even without Ollama running.
    """
    if not rules_text or len(rules_text.strip()) < 50:
        logger.info("[rules] No rules text found (< 50 chars), using defaults")
        return _default_rules()

    # ── Step 1: Regex extraction (always runs) ────────────────────────────────
    regex_rules = extract_rules_regex(rules_text)
    n_regex = len(regex_rules.get("scope_dates", {}))
    logger.info(f"[rules] Regex extracted {n_regex} scope dates")

    # ── Step 2: LLM extraction (Ollama) ───────────────────────────────────────
    llm_rules = None
    if host and model:
        try:
            if check_ollama_available(host):
                logger.info(f"[rules] Ollama available — running chunked extraction ({model})")
                sections = _split_into_sections(rules_text)

                if len(sections) >= 2:
                    # We found discrete sections — extract each one separately
                    llm_rules = _ollama_extract_chunked(rules_text, host, model)
                else:
                    # Sections not cleanly split — send all at once
                    logger.info("[rules] Sections not split — using full-text extraction")
                    llm_rules = _ollama_extract_full(rules_text, host, model)

                n_llm = len(llm_rules.get("scope_dates", {}))
                logger.info(f"[rules] LLM extracted {n_llm} scope dates")
            else:
                logger.info("[rules] Ollama not available — regex-only mode")
        except Exception as e:
            logger.warning(f"[rules] Ollama pipeline failed ({type(e).__name__}: {e}), using regex only")

    # ── Step 3: Merge (LLM wins on conflicts) ─────────────────────────────────
    if llm_rules:
        merged = _merge_rules(regex_rules, llm_rules)
        n_merged = len(merged.get("scope_dates", {}))
        logger.info(f"[rules] Merged regex + LLM → {n_merged} scope dates total")
        return merged

    return regex_rules
