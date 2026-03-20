"""
Extract contract rules from Sections 7-12 using Ollama LLM.

Sections 7-12 contain natural-language provisions, notes, and exceptions that
determine per-scope effective/expiry dates, surcharge inclusions, and special
rules. These are too varied for regex — an LLM extracts them into structured
JSON that the NLP pipeline uses as a post-processing correction pass.

Gracefully degrades: if Ollama is unavailable or returns bad JSON, returns
empty defaults and the existing NLP pipeline runs unchanged.
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger("rules_extractor")


# ── Ollama API ───────────────────────────────────────────────────────────────

def check_ollama_available(host: str) -> bool:
    """Check if Ollama is running and accessible."""
    try:
        import httpx
        resp = httpx.get(f"{host}/api/tags", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


def _call_ollama(prompt: str, host: str, model: str) -> str:
    """Send a prompt to Ollama and return the response text."""
    import httpx
    response = httpx.post(
        f"{host}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,   # near-deterministic for extraction
                "num_predict": 4096,  # rules JSON can be sizeable
            },
        },
        timeout=120.0,  # llama3.2:3b can take 30-60s on CPU
    )
    response.raise_for_status()
    return response.json().get("response", "")


# ── Prompt ───────────────────────────────────────────────────────────────────

RULES_PROMPT = """You are a freight shipping contract parser. Extract structured rules from the contract text below (Sections 7-12).

Return ONLY valid JSON — no markdown fences, no explanation, no extra text.

JSON structure:
{{
  "scope_dates": {{
    "<SCOPE_NAME>": {{
      "effective": "<DD Mon YYYY>",
      "expiry": "<DD Mon YYYY>"
    }}
  }},
  "scope_surcharges": {{
    "<SCOPE_NAME>": {{
      "surcharge_inclusion_cutoff": "<date string or null>",
      "applicable_surcharges": ["<CODE>", ...],
      "hazardous_surcharges": ["<CODE>", ...],
      "rds_included_for_dry": <true|false>,
      "notes": "<any special scope-level notes>"
    }}
  }},
  "container_glossary": {{
    "<CODE>": "<description>"
  }},
  "reefer_codes": ["<CODE>", ...]
}}

Extraction rules:
- SCOPE NAMES are in square brackets, e.g. [NORTH AMERICA - ASIA (WB)]. Use the text inside brackets as the key (without brackets).
- Section 8 "DURATION" has per-scope Effective and Effective Through dates.
- Section 12.B "Notes" has per-scope surcharge structure clauses (e.g. "TPW - Surcharge Structure Clause"). Extract the cutoff date from "inclusive of all surcharges ... published ... on or before <DATE>".
- Section 12.B Overweight Cargo Clause lists applicable surcharge codes (HEA, OWT, TRI, AGW, etc.) per scope.
- Section 12.C "Exceptions" has scope-specific overrides. Look for "RDS" / "RED SEA DIVERSION CHARGE" inclusions — set rds_included_for_dry=true for that scope.
- The GLOSSARY at the end maps container codes (D2, D4, D5, D7, R2, R5, etc.) to descriptions. Reefer codes start with R.
- If a surcharge code appears in "include, but are not limited to" list, add it to applicable_surcharges.
- Include ALL scopes you find, even if they have the same structure.

Contract text (Sections 7-12):
---
{rules_text}
---"""


# ── JSON parsing ─────────────────────────────────────────────────────────────

def _parse_rules_json(response: str) -> dict:
    """Parse LLM response, extracting JSON even if wrapped in markdown."""
    text = response.strip()

    # Strip markdown code fences if present
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
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        json_str = text[start:end]
        # Fix common LLM JSON issues: trailing commas
        json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
        return json.loads(json_str)

    raise ValueError(f"No JSON found in LLM response: {text[:200]}")


def _default_rules() -> dict:
    """Return empty rules dict — pipeline falls back to NLP-only mode."""
    return {
        "scope_dates": {},
        "scope_surcharges": {},
        "container_glossary": {},
        "reefer_codes": [],
    }


# ── Main entry point ─────────────────────────────────────────────────────────

def extract_rules(rules_text: str, host: str, model: str) -> dict:
    """
    Extract contract rules from sections 7-12 text using Ollama LLM.

    Returns a structured rules dict. On any failure, returns empty defaults
    so the NLP pipeline continues unmodified.
    """
    if not rules_text or len(rules_text.strip()) < 50:
        logger.info("[rules] No rules text found (< 50 chars), using defaults")
        return _default_rules()

    # Cap input size to avoid overwhelming small models
    # Sections 7-12 are typically 3-6 pages (~3000-8000 chars)
    capped_text = rules_text[:12000]
    prompt = RULES_PROMPT.format(rules_text=capped_text)

    try:
        logger.info(f"[rules] Sending {len(capped_text)} chars to Ollama ({model})...")
        raw_response = _call_ollama(prompt, host, model)
        rules = _parse_rules_json(raw_response)

        # Log what we found
        n_scopes = len(rules.get("scope_dates", {}))
        n_surcharges = len(rules.get("scope_surcharges", {}))
        n_glossary = len(rules.get("container_glossary", {}))
        reefer_codes = rules.get("reefer_codes", [])
        logger.info(
            f"[rules] Extracted: {n_scopes} scope dates, "
            f"{n_surcharges} scope surcharge configs, "
            f"{n_glossary} container codes, "
            f"reefer codes: {reefer_codes}"
        )

        # Validate structure — ensure required keys exist
        for key in ("scope_dates", "scope_surcharges", "container_glossary", "reefer_codes"):
            if key not in rules:
                rules[key] = _default_rules()[key]

        return rules

    except json.JSONDecodeError as e:
        logger.warning(f"[rules] Ollama returned invalid JSON: {e}")
        logger.debug(f"[rules] Raw response: {raw_response[:500] if 'raw_response' in dir() else 'N/A'}")
        return _default_rules()
    except Exception as e:
        logger.warning(f"[rules] Ollama extraction failed ({type(e).__name__}: {e}), using defaults")
        return _default_rules()
