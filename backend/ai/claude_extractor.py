"""Claude AI-powered extraction of freight rate data from OCR text."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import anthropic

from ai.prompts import (
    SYSTEM_PROMPT,
    METADATA_PROMPT,
    RATES_PROMPT,
    SURCHARGE_PROMPT,
    ORIGIN_ARB_PROMPT,
    DEST_ARB_PROMPT,
)

HAIKU = "claude-haiku-4-5-20251001"
OPUS = "claude-opus-4-6"


def _call_claude(client: anthropic.Anthropic, prompt: str, model: str = OPUS, max_tokens: int = 4096) -> str:
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def _parse_json(text: str) -> Any:
    """Strip markdown fences and parse JSON."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _extract_section_rates(
    section: dict,
    client: anthropic.Anthropic,
    carrier: str,
    contract_id: str,
    effective_date: str,
    expiration_date: str,
    commodity: str,
    surcharges: dict,
) -> list[dict]:
    """Extract rate rows for a single origin section (runs in a thread)."""
    origin = section.get("origin", "")
    origin_via = section.get("origin_via", "")
    scope = section.get("scope", "")
    raw_text = section.get("raw_text", "")

    if not raw_text.strip() or not origin:
        return []

    prompt = RATES_PROMPT.format(
        carrier=carrier,
        contract_id=contract_id,
        effective_date=effective_date,
        expiration_date=expiration_date,
        commodity=commodity,
        scope=scope,
        origin_city=origin,
        origin_via=origin_via or "",
        text=raw_text[:6000],
    )
    try:
        raw = _call_claude(client, prompt, model=OPUS)
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
            return rows
    except Exception as e:
        print(f"[claude_extractor] Rate extraction failed for origin={origin}: {e}")
    return []


def _extract_arb_section(
    arb_section: dict,
    prompt_template,
    client: anthropic.Anthropic,
    carrier: str,
    contract_id: str,
    effective_date: str,
    expiration_date: str,
    commodity: str,
    scope: str,
) -> list[dict]:
    """Extract arb rows for a single arb section (runs in a thread)."""
    raw_text = arb_section.get("raw_text", "")
    if not raw_text.strip():
        return []

    prompt = prompt_template.format(
        carrier=carrier,
        contract_id=contract_id,
        effective_date=effective_date,
        expiration_date=expiration_date,
        commodity=commodity,
        scope=scope,
        text=raw_text[:6000],
    )
    try:
        raw = _call_claude(client, prompt, model=OPUS)
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
                })
            return rows
    except Exception as e:
        print(f"[claude_extractor] Arb extraction failed: {e}")
    return []


def extract_with_claude(extracted: dict, api_key: str, max_workers: int = 10) -> dict:
    """
    Main entry point: takes pdf_extractor output, calls Claude, returns structured data.

    Returns:
        {
          "metadata": {...},
          "surcharges": {...},
          "rates": [...],
          "origin_arbitraries": [...],
          "destination_arbitraries": [...],
        }
    """
    client = anthropic.Anthropic(api_key=api_key)

    # 1. Refine metadata with Claude (use haiku for speed/cost)
    metadata = extracted.get("metadata", {})
    if not all([metadata.get("carrier"), metadata.get("contract_id")]):
        first_page_text = ""
        if extracted.get("sections"):
            first_page_text = extracted["sections"][0].get("raw_text", "")[:2000]
        if first_page_text:
            try:
                raw = _call_claude(
                    client,
                    METADATA_PROMPT.format(text=first_page_text),
                    model=HAIKU,
                    max_tokens=512,
                )
                metadata.update(_parse_json(raw))
            except Exception:
                pass

    carrier = metadata.get("carrier", "")
    contract_id = metadata.get("contract_id", "")
    effective_date = metadata.get("effective_date", "")
    expiration_date = metadata.get("expiration_date", "")
    commodity = metadata.get("commodity", "")

    # 2. Extract surcharges
    surcharges = {
        "ams_china_japan": 35,
        "hea_heavy_surcharge": "TARIFF",
        "agw": "TARIFF",
        "rds_red_sea": "INCLUSIVE",
    }
    surcharge_text = extracted.get("surcharge_text", "")
    if surcharge_text.strip():
        try:
            raw = _call_claude(
                client,
                SURCHARGE_PROMPT.format(text=surcharge_text[:3000]),
                model=HAIKU,
                max_tokens=256,
            )
            parsed = _parse_json(raw)
            surcharges.update(parsed)
        except Exception:
            pass

    # 3. Extract rate rows per section — parallel
    all_rates: list[dict] = []
    sections = extracted.get("sections", [])

    for s in sections:
        if not s.get("scope"):
            s["scope"] = metadata.get("scope", "")

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _extract_section_rates,
                section, client,
                carrier, contract_id, effective_date, expiration_date,
                commodity, surcharges,
            ): section.get("origin", "?")
            for section in sections
            if section.get("raw_text", "").strip() and section.get("origin")
        }
        for future in as_completed(futures):
            all_rates.extend(future.result())

    # 4. Extract origin arbitraries — parallel
    origin_arbs: list[dict] = []
    scope = metadata.get("scope", "")

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [
            pool.submit(
                _extract_arb_section,
                arb_section, ORIGIN_ARB_PROMPT, client,
                carrier, contract_id, effective_date, expiration_date,
                commodity, scope,
            )
            for arb_section in extracted.get("origin_arb_sections", [])
            if arb_section.get("raw_text", "").strip()
        ]
        for future in as_completed(futures):
            origin_arbs.extend(future.result())

    # 5. Extract destination arbitraries — parallel
    dest_arbs: list[dict] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [
            pool.submit(
                _extract_arb_section,
                arb_section, DEST_ARB_PROMPT, client,
                carrier, contract_id, effective_date, expiration_date,
                commodity, scope,
            )
            for arb_section in extracted.get("dest_arb_sections", [])
            if arb_section.get("raw_text", "").strip()
        ]
        for future in as_completed(futures):
            dest_arbs.extend(future.result())

    return {
        "metadata": metadata,
        "surcharges": surcharges,
        "rates": all_rates,
        "origin_arbitraries": origin_arbs,
        "destination_arbitraries": dest_arbs,
    }


def _numeric(val):
    """Convert surcharge value to number or None."""
    if val is None or val in ("TARIFF", "INCLUSIVE", ""):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
