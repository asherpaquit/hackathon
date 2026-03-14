"""Hybrid freight extraction: rule-based for Docling grids, LLM fallback for the rest."""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
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


# ── Ollama REST call ──────────────────────────────────────────────────────────

def _call_ollama(
    prompt: str,
    model: str = "mistral:7b",
    host: str = "http://localhost:11434",
    max_tokens: int = 2048,
) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {
            "temperature":    0.05,
            "num_predict":    max_tokens,
            "num_ctx":        4096,   # halved from 8192 — structured JSON input is compact
            "top_p":          0.9,
            "repeat_penalty": 1.1,
        },
    }
    with httpx.Client(timeout=300.0) as client:
        response = client.post(f"{host}/api/chat", json=payload)
        response.raise_for_status()
        return response.json()["message"]["content"]


def _parse_json(text: str) -> Any:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for pattern in [r"(\[.*\])", r"(\{.*\})"]:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
    logger.warning(f"[ollama_extractor] JSON parse failed. Raw: {text[:300]}")
    return {}


def check_ollama_health(host: str = "http://localhost:11434") -> dict:
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(f"{host}/api/tags")
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
            return {"running": True, "models": models}
    except Exception as e:
        return {"running": False, "models": [], "error": str(e)}


# ── Text pre-filter ───────────────────────────────────────────────────────────

_SEPARATOR_RE = re.compile(r"^[-=_*~\s]{3,}$")


def _prefilter_text(text: str, max_chars: int = 5000) -> str:
    lines = text.split("\n")
    kept  = [l for l in lines if l.strip() and not _SEPARATOR_RE.match(l.strip())]
    return "\n".join(kept)[:max_chars]


# ── Rule-based grid extraction ────────────────────────────────────────────────

# Normalized column header → schema field name
_RATE_COL: dict[str, str] = {
    # 20 ft
    "20": "base_rate_20",        "20'": "base_rate_20",
    '20"': "base_rate_20",       "20ft": "base_rate_20",
    "20gp": "base_rate_20",      "20'gp": "base_rate_20",
    # 40 ft dry
    "40": "base_rate_40",        "40'": "base_rate_40",
    '40"': "base_rate_40",       "40ft": "base_rate_40",
    "40gp": "base_rate_40",      "40'gp": "base_rate_40",
    "40dv": "base_rate_40",      "40'dv": "base_rate_40",
    # 40 HC
    "40hc": "base_rate_40h",     "40h": "base_rate_40h",
    "40hq": "base_rate_40h",     "40'hc": "base_rate_40h",
    "40'h": "base_rate_40h",     "40'hq": "base_rate_40h",
    "40hicube": "base_rate_40h", "40hi": "base_rate_40h",
    "hc40": "base_rate_40h",
    # 45 ft
    "45": "base_rate_45",        "45'": "base_rate_45",
    '45"': "base_rate_45",       "45ft": "base_rate_45",
    "45hc": "base_rate_45",      "45'hc": "base_rate_45",
    # Destination
    "destination": "destination_city",
    "dest": "destination_city",
    "pod": "destination_city",
    "portof discharge": "destination_city",
    "port of discharge": "destination_city",
    "discharge port": "destination_city",
    "destination port": "destination_city",
    # Via
    "via": "destination_via_city",
    "dest via": "destination_via_city",
    "destination via": "destination_via_city",
    "t/s": "destination_via_city",
    "t/s port": "destination_via_city",
    "transship": "destination_via_city",
    "tranship": "destination_via_city",
    "transhipment": "destination_via_city",
    # Service
    "service": "service",        "term": "service",
    "type": "service",           "mode": "service",
    "service type": "service",
    # Remarks
    "remarks": "remarks",        "remark": "remarks",
    "note": "remarks",           "notes": "remarks",
    "comment": "remarks",        "comments": "remarks",
}

# Arb-specific additions
_ARB_ORIGIN_EXTRA: dict[str, str] = {
    "origin": "origin_city",
    "pol": "origin_city",
    "inland origin": "origin_city",
    "origin city": "origin_city",
    "via": "origin_via_city",
    "pol via": "origin_via_city",
    "agw 20": "agw_20",  "agw20": "agw_20",
    "agw 40": "agw_40",  "agw40": "agw_40",
    "agw 45": "agw_45",  "agw45": "agw_45",
}

_ARB_DEST_EXTRA: dict[str, str] = {
    "destination": "destination_city",
    "inland dest": "destination_city",
    "dest city": "destination_city",
    "via": "destination_via_city",
}

_NUMERIC_RE = re.compile(r"[\d,]+(?:\.\d+)?")


def _normalize_header_key(cell: str) -> str:
    return (cell.lower().strip()
            .replace("\u2018", "'").replace("\u2019", "'")
            .replace("\u201c", '"').replace("\u201d", '"'))


def _detect_header_row(
    grid: list[list[str]],
    col_source: dict[str, str] | None = None,
) -> tuple[int, dict[int, str]]:
    """
    Find the header row in a table grid.
    Returns (row_index, {col_idx: field_name}), or (-1, {}) if not found.
    """
    if col_source is None:
        col_source = _RATE_COL

    for row_idx, row in enumerate(grid[:8]):
        col_map: dict[int, str] = {}
        for col_idx, cell in enumerate(row):
            key = _normalize_header_key(cell)
            if key in col_source:
                col_map[col_idx] = col_source[key]

        rate_fields = [v for v in col_map.values() if v.startswith("base_rate")]
        if len(rate_fields) >= 2:
            return row_idx, col_map

    return -1, {}


def _extract_from_grid(
    grid: list[list[str]],
    context: dict,
    col_source: dict[str, str] | None = None,
) -> list[dict] | None:
    """
    Rule-based extraction from a Docling table grid.
    Returns list of row dicts if successful, or None to signal LLM fallback needed.
    """
    header_idx, col_map = _detect_header_row(grid, col_source)
    if header_idx == -1:
        return None

    rows: list[dict] = []
    for row in grid[header_idx + 1:]:
        if not any(c.strip() for c in row):
            continue

        row_dict  = dict(context)
        has_rate  = False

        for col_idx, field in col_map.items():
            if col_idx >= len(row):
                continue
            cell = row[col_idx].strip()
            if not cell or cell in ("-", "—", "--", "N/A", "n/a", "TBN"):
                continue

            if field.startswith("base_rate") or field.startswith("agw"):
                m = _NUMERIC_RE.search(cell)
                if m:
                    try:
                        val = float(m.group().replace(",", ""))
                        row_dict[field] = val
                        if field.startswith("base_rate"):
                            has_rate = True
                    except ValueError:
                        pass
            else:
                row_dict[field] = cell

        if has_rate:
            if not row_dict.get("service"):
                row_dict["service"] = "CY/CY"
            rows.append(row_dict)

    return rows if rows else None


def _annotate_rows(
    rows: list[dict],
    carrier: str,
    contract_id: str,
    effective_date: str,
    expiration_date: str,
    commodity: str,
    scope: str,
    origin: str,
    origin_via: str,
    surcharges: dict,
) -> None:
    """Stamp metadata and surcharge values onto extracted rows in-place."""
    for row in rows:
        row.update({
            "carrier":            carrier,
            "contract_id":        contract_id,
            "effective_date":     effective_date,
            "expiration_date":    expiration_date,
            "commodity":          commodity,
            "scope":              scope,
            "origin_city":        origin,
            "origin_via_city":    origin_via or None,
            "ams_china_japan":    _numeric(surcharges.get("ams_china_japan")),
            "hea_heavy_surcharge": _numeric(surcharges.get("hea_heavy_surcharge")),
            "agw":                _numeric(surcharges.get("agw")),
            "rds_red_sea":        _numeric(surcharges.get("rds_red_sea")),
        })


# ── Section extractors ────────────────────────────────────────────────────────

def _numeric(val) -> float | None:
    if val is None or val in ("TARIFF", "INCLUSIVE", ""):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _extract_section_rates(
    section: dict,
    model: str,
    host: str,
    carrier: str,
    contract_id: str,
    effective_date: str,
    expiration_date: str,
    commodity: str,
    surcharges: dict,
) -> list[dict]:
    origin     = section.get("origin", "")
    origin_via = section.get("origin_via", "")
    scope      = section.get("scope", "")
    raw_text   = section.get("raw_text", "")
    tables     = section.get("tables", [])   # list of list[list[str]] from Docling

    if not origin:
        return []

    base_context = {
        "origin_city":     origin,
        "origin_via_city": origin_via or None,
        "scope":           scope,
        "service":         "CY/CY",
    }

    # ── 1. Rule-based grid extraction ────────────────────────────────────────
    rule_rows: list[dict] = []
    for grid in tables:
        rows = _extract_from_grid(grid, base_context)
        if rows:
            rule_rows.extend(rows)

    if rule_rows:
        _annotate_rows(rule_rows, carrier, contract_id, effective_date,
                       expiration_date, commodity, scope, origin, origin_via, surcharges)
        logger.info(f"[rule] {len(rule_rows)} rows for origin={origin}")
        return rule_rows

    # ── 2. LLM fallback ──────────────────────────────────────────────────────
    if not raw_text.strip() and not tables:
        return []

    if tables:
        grid_repr  = json.dumps(tables[:2], ensure_ascii=False)
        text_input = f"TABLE GRIDS (JSON):\n{grid_repr}\n\nRAW TEXT:\n{_prefilter_text(raw_text)}"
    else:
        text_input = _prefilter_text(raw_text)

    prompt = RATES_PROMPT.format(
        carrier=carrier, contract_id=contract_id,
        effective_date=effective_date, expiration_date=expiration_date,
        commodity=commodity, scope=scope,
        origin_city=origin, origin_via=origin_via or "",
        text=text_input[:6000],
    )
    try:
        raw  = _call_ollama(prompt, model=model, host=host)
        rows = _parse_json(raw)
        if isinstance(rows, list):
            _annotate_rows(rows, carrier, contract_id, effective_date,
                           expiration_date, commodity, scope, origin, origin_via, surcharges)
            logger.info(f"[llm] {len(rows)} rows for origin={origin}")
            return rows
        return []
    except Exception as e:
        logger.error(f"[ollama_extractor] Rate extraction failed for origin={origin}: {e}")
        return []


def _extract_arb_section(
    arb_section: dict,
    arb_kind: str,
    prompt_template,
    model: str,
    host: str,
    carrier: str,
    contract_id: str,
    effective_date: str,
    expiration_date: str,
    commodity: str,
    scope: str,
) -> list[dict]:
    raw_text = arb_section.get("raw_text", "")
    tables   = arb_section.get("tables", [])

    if not raw_text.strip() and not tables:
        return []

    col_source = {**_RATE_COL, **(_ARB_ORIGIN_EXTRA if arb_kind == "ORIGIN" else _ARB_DEST_EXTRA)}
    base_context = {
        "carrier": carrier, "contract_id": contract_id,
        "effective_date": effective_date, "expiration_date": expiration_date,
        "commodity": commodity, "scope": scope,
    }

    # ── 1. Rule-based ────────────────────────────────────────────────────────
    rule_rows: list[dict] = []
    for grid in tables:
        rows = _extract_from_grid(grid, base_context, col_source=col_source)
        if rows:
            rule_rows.extend(rows)

    if rule_rows:
        logger.info(f"[rule] {len(rule_rows)} {arb_kind} arb rows")
        return rule_rows

    # ── 2. LLM fallback ──────────────────────────────────────────────────────
    if tables:
        grid_repr  = json.dumps(tables[:2], ensure_ascii=False)
        text_input = f"TABLE GRIDS (JSON):\n{grid_repr}\n\nRAW TEXT:\n{_prefilter_text(raw_text)}"
    else:
        text_input = _prefilter_text(raw_text)

    prompt = prompt_template.format(
        carrier=carrier, contract_id=contract_id,
        effective_date=effective_date, expiration_date=expiration_date,
        commodity=commodity, scope=scope,
        text=text_input[:6000],
    )
    try:
        raw  = _call_ollama(prompt, model=model, host=host)
        rows = _parse_json(raw)
        if isinstance(rows, list):
            for row in rows:
                row.update({
                    "carrier": carrier, "contract_id": contract_id,
                    "effective_date": effective_date, "expiration_date": expiration_date,
                    "commodity": commodity, "scope": scope,
                })
            logger.info(f"[llm] {len(rows)} {arb_kind} arb rows")
            return rows
    except Exception as e:
        logger.error(f"[ollama_extractor] {arb_kind} arb extraction failed: {e}")
    return []


# ── Main entry point ──────────────────────────────────────────────────────────

def extract_with_ollama(
    extracted: dict,
    model: str = "mistral:7b",
    host: str = "http://localhost:11434",
    max_workers: int = 4,
) -> dict:
    """
    Main entry: takes pdf_extractor output, returns structured freight data.
    Rule-based extraction is tried first for every section (no LLM call needed
    when Docling grids are clean). LLM is only used as fallback.
    """

    # ── 1. Metadata ───────────────────────────────────────────────────────────
    metadata = extracted.get("metadata", {})
    if not all([metadata.get("carrier"), metadata.get("contract_id")]):
        first_text = ""
        if extracted.get("sections"):
            first_text = extracted["sections"][0].get("raw_text", "")[:2000]
        if first_text:
            try:
                raw    = _call_ollama(METADATA_PROMPT.format(text=first_text),
                                      model=model, host=host, max_tokens=512)
                parsed = _parse_json(raw)
                if isinstance(parsed, dict):
                    metadata.update(parsed)
                logger.info(f"[ollama_extractor] Metadata: {metadata}")
            except Exception as e:
                logger.warning(f"[ollama_extractor] Metadata extraction failed: {e}")

    carrier         = metadata.get("carrier", "")
    contract_id     = metadata.get("contract_id", "")
    effective_date  = metadata.get("effective_date", "")
    expiration_date = metadata.get("expiration_date", "")
    commodity       = metadata.get("commodity", "")
    scope           = metadata.get("scope", "")

    # ── 2. Surcharges ─────────────────────────────────────────────────────────
    surcharges = {
        "ams_china_japan":    35,
        "hea_heavy_surcharge": "TARIFF",
        "agw":                 "TARIFF",
        "rds_red_sea":         "INCLUSIVE",
    }
    surcharge_text = extracted.get("surcharge_text", "")
    if surcharge_text.strip():
        try:
            raw    = _call_ollama(
                SURCHARGE_PROMPT.format(text=_prefilter_text(surcharge_text, 3000)),
                model=model, host=host, max_tokens=256,
            )
            parsed = _parse_json(raw)
            if isinstance(parsed, dict):
                surcharges.update(parsed)
            logger.info(f"[ollama_extractor] Surcharges: {surcharges}")
        except Exception as e:
            logger.warning(f"[ollama_extractor] Surcharge extraction failed: {e}")

    # ── 3. Rate sections — parallel ───────────────────────────────────────────
    sections = extracted.get("sections", [])
    for s in sections:
        if not s.get("scope"):
            s["scope"] = scope

    all_rates: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _extract_section_rates,
                section, model, host,
                carrier, contract_id, effective_date, expiration_date,
                commodity, surcharges,
            ): section.get("origin", "?")
            for section in sections
            if section.get("origin")
        }
        for future in as_completed(futures):
            all_rates.extend(future.result())

    # ── 4. Origin arbitraries — parallel ─────────────────────────────────────
    origin_arbs: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [
            pool.submit(
                _extract_arb_section,
                arb, "ORIGIN", ORIGIN_ARB_PROMPT, model, host,
                carrier, contract_id, effective_date, expiration_date, commodity, scope,
            )
            for arb in extracted.get("origin_arb_sections", [])
            if arb.get("raw_text", "").strip() or arb.get("tables")
        ]
        for future in as_completed(futures):
            origin_arbs.extend(future.result())

    # ── 5. Destination arbitraries — parallel ─────────────────────────────────
    dest_arbs: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [
            pool.submit(
                _extract_arb_section,
                arb, "DESTINATION", DEST_ARB_PROMPT, model, host,
                carrier, contract_id, effective_date, expiration_date, commodity, scope,
            )
            for arb in extracted.get("dest_arb_sections", [])
            if arb.get("raw_text", "").strip() or arb.get("tables")
        ]
        for future in as_completed(futures):
            dest_arbs.extend(future.result())

    return {
        "metadata":                metadata,
        "surcharges":              surcharges,
        "rates":                   all_rates,
        "origin_arbitraries":      origin_arbs,
        "destination_arbitraries": dest_arbs,
    }
