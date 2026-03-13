"""Ollama-powered extraction of freight rate data — 100% free, no API required."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from ai.prompts import (
    SYSTEM_PROMPT,
    METADATA_PROMPT,
    RATES_PROMPT,
    SURCHARGE_PROMPT,
    ORIGIN_ARB_PROMPT,
    DEST_ARB_PROMPT,
)

logger = logging.getLogger("ollama_extractor")


def _call_ollama(
    prompt: str,
    model: str = "mistral:7b",
    host: str = "http://localhost:11434",
    max_tokens: int = 2048,
) -> str:
    """
    Call local Ollama REST API using chat format.
    Uses format='json' to force structured JSON output from the model.
    Timeout is 300s — local inference on CPU can take 30–120s per request.
    """
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.05,   # Very low — we want deterministic, accurate extraction
            "num_predict": max_tokens,
            "num_ctx": 8192,       # Mistral 7B context window
            "top_p": 0.9,
            "repeat_penalty": 1.1,
        },
    }

    with httpx.Client(timeout=300.0) as client:
        response = client.post(f"{host}/api/chat", json=payload)
        response.raise_for_status()
        return response.json()["message"]["content"]


def _parse_json(text: str) -> Any:
    """
    Robust JSON parsing — handles markdown fences, embedded JSON,
    and partial/malformed responses from local models.
    """
    text = text.strip()

    # Strip markdown fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find embedded JSON array or object
    for pattern in [r"(\[.*\])", r"(\{.*\})"]:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

    logger.warning(f"[ollama_extractor] JSON parse failed. Raw: {text[:300]}")
    return {}


def check_ollama_health(host: str = "http://localhost:11434") -> dict:
    """Check if Ollama is running and which models are available."""
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{host}/api/tags")
            response.raise_for_status()
            models = [m["name"] for m in response.json().get("models", [])]
            return {"running": True, "models": models}
    except Exception as e:
        return {"running": False, "models": [], "error": str(e)}


def extract_with_ollama(
    extracted: dict,
    model: str = "mistral:7b",
    host: str = "http://localhost:11434",
) -> dict:
    """
    Main entry point: takes pdf_extractor output, calls local Ollama LLM,
    returns structured freight rate data.

    Drop-in replacement for extract_with_claude() — same input/output contract.

    Returns:
        {
          "metadata": {...},
          "surcharges": {...},
          "rates": [...],
          "origin_arbitraries": [...],
          "destination_arbitraries": [...],
        }
    """

    # ── 1. Metadata ──────────────────────────────────────────────────────────
    metadata = extracted.get("metadata", {})
    if not all([metadata.get("carrier"), metadata.get("contract_id")]):
        first_page_text = ""
        if extracted.get("sections"):
            first_page_text = extracted["sections"][0].get("raw_text", "")[:2000]
        if first_page_text:
            try:
                raw = _call_ollama(
                    METADATA_PROMPT.format(text=first_page_text),
                    model=model,
                    host=host,
                    max_tokens=512,
                )
                parsed = _parse_json(raw)
                if isinstance(parsed, dict):
                    metadata.update(parsed)
                logger.info(f"[ollama_extractor] Metadata: {metadata}")
            except Exception as e:
                logger.warning(f"[ollama_extractor] Metadata extraction failed: {e}")

    carrier = metadata.get("carrier", "")
    contract_id = metadata.get("contract_id", "")
    effective_date = metadata.get("effective_date", "")
    expiration_date = metadata.get("expiration_date", "")
    commodity = metadata.get("commodity", "")

    # ── 2. Surcharges ─────────────────────────────────────────────────────────
    surcharges = {
        "ams_china_japan": 35,
        "hea_heavy_surcharge": "TARIFF",
        "agw": "TARIFF",
        "rds_red_sea": "INCLUSIVE",
    }
    surcharge_text = extracted.get("surcharge_text", "")
    if surcharge_text.strip():
        try:
            raw = _call_ollama(
                SURCHARGE_PROMPT.format(text=surcharge_text[:3000]),
                model=model,
                host=host,
                max_tokens=256,
            )
            parsed = _parse_json(raw)
            if isinstance(parsed, dict):
                surcharges.update(parsed)
            logger.info(f"[ollama_extractor] Surcharges: {surcharges}")
        except Exception as e:
            logger.warning(f"[ollama_extractor] Surcharge extraction failed: {e}")

    # ── 3. Rate rows per origin section ───────────────────────────────────────
    all_rates: list[dict] = []
    sections = extracted.get("sections", [])

    for section in sections:
        origin = section.get("origin", "")
        origin_via = section.get("origin_via", "")
        scope = section.get("scope", metadata.get("scope", ""))
        raw_text = section.get("raw_text", "")

        if not raw_text.strip() or not origin:
            continue

        # Keep within Mistral's context — 5000 chars is ~1250 tokens
        text_chunk = raw_text[:5000]

        prompt = RATES_PROMPT.format(
            carrier=carrier,
            contract_id=contract_id,
            effective_date=effective_date,
            expiration_date=expiration_date,
            commodity=commodity,
            scope=scope,
            origin_city=origin,
            origin_via=origin_via or "",
            text=text_chunk,
        )

        try:
            raw = _call_ollama(prompt, model=model, host=host)
            rows = _parse_json(raw)

            if isinstance(rows, list):
                for row in rows:
                    row.update({
                        "carrier": carrier,
                        "contract_id": contract_id,
                        "effective_date": effective_date,
                        "expiration_date": expiration_date,
                        "commodity": commodity,
                        "scope": scope,
                        "origin_city": origin,
                        "origin_via_city": origin_via or None,
                        "ams_china_japan": _numeric(surcharges.get("ams_china_japan")),
                        "hea_heavy_surcharge": _numeric(surcharges.get("hea_heavy_surcharge")),
                        "agw": _numeric(surcharges.get("agw")),
                        "rds_red_sea": _numeric(surcharges.get("rds_red_sea")),
                    })
                all_rates.extend(rows)
                logger.info(f"[ollama_extractor] {len(rows)} rows extracted for origin={origin}")
            else:
                logger.warning(f"[ollama_extractor] Unexpected response type for origin={origin}: {type(rows)}")

        except Exception as e:
            logger.error(f"[ollama_extractor] Rate extraction failed for origin={origin}: {e}")
            continue

    # ── 4. Origin arbitraries ─────────────────────────────────────────────────
    origin_arbs: list[dict] = []
    for arb_section in extracted.get("origin_arb_sections", []):
        raw_text = arb_section.get("raw_text", "")
        if not raw_text.strip():
            continue

        prompt = ORIGIN_ARB_PROMPT.format(
            carrier=carrier,
            contract_id=contract_id,
            effective_date=effective_date,
            expiration_date=expiration_date,
            commodity=commodity,
            scope=metadata.get("scope", ""),
            text=raw_text[:5000],
        )
        try:
            raw = _call_ollama(prompt, model=model, host=host)
            rows = _parse_json(raw)
            if isinstance(rows, list):
                for row in rows:
                    row.update({
                        "carrier": carrier,
                        "contract_id": contract_id,
                        "effective_date": effective_date,
                        "expiration_date": expiration_date,
                        "commodity": commodity,
                        "scope": metadata.get("scope", ""),
                    })
                origin_arbs.extend(rows)
                logger.info(f"[ollama_extractor] {len(rows)} origin arb rows extracted")
        except Exception as e:
            logger.error(f"[ollama_extractor] Origin arb extraction failed: {e}")

    # ── 5. Destination arbitraries ────────────────────────────────────────────
    dest_arbs: list[dict] = []
    for arb_section in extracted.get("dest_arb_sections", []):
        raw_text = arb_section.get("raw_text", "")
        if not raw_text.strip():
            continue

        prompt = DEST_ARB_PROMPT.format(
            carrier=carrier,
            contract_id=contract_id,
            effective_date=effective_date,
            expiration_date=expiration_date,
            commodity=commodity,
            scope=metadata.get("scope", ""),
            text=raw_text[:5000],
        )
        try:
            raw = _call_ollama(prompt, model=model, host=host)
            rows = _parse_json(raw)
            if isinstance(rows, list):
                for row in rows:
                    row.update({
                        "carrier": carrier,
                        "contract_id": contract_id,
                        "effective_date": effective_date,
                        "expiration_date": expiration_date,
                        "commodity": commodity,
                        "scope": metadata.get("scope", ""),
                    })
                dest_arbs.extend(rows)
                logger.info(f"[ollama_extractor] {len(rows)} dest arb rows extracted")
        except Exception as e:
            logger.error(f"[ollama_extractor] Dest arb extraction failed: {e}")

    return {
        "metadata": metadata,
        "surcharges": surcharges,
        "rates": all_rates,
        "origin_arbitraries": origin_arbs,
        "destination_arbitraries": dest_arbs,
    }


def _numeric(val):
    """Convert surcharge value to float or None (handles TARIFF/INCLUSIVE strings)."""
    if val is None or val in ("TARIFF", "INCLUSIVE", ""):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
