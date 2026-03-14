"""Hybrid freight extraction: rule-based for grids, LLM fallback — fully parallelized."""

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

# Reuse a single httpx client for connection pooling
_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.Client(timeout=300.0)
    return _client


# ── Ollama REST call ──────────────────────────────────────────────────────────

def _call_ollama(
    prompt: str,
    model: str = "mistral:7b",
    host: str = "http://localhost:11434",
    max_tokens: int = 1024,
    num_ctx: int = 2048,
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
            "temperature":    0.0,
            "num_predict":    max_tokens,
            "num_ctx":        num_ctx,
            "top_p":          0.9,
            "repeat_penalty": 1.05,
        },
    }
    client = _get_client()
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


def _prefilter_text(text: str, max_chars: int = 4000) -> str:
    lines = text.split("\n")
    kept  = [l for l in lines if l.strip() and not _SEPARATOR_RE.match(l.strip())]
    return "\n".join(kept)[:max_chars]


# ── Rule-based grid extraction ────────────────────────────────────────────────

_RATE_COL: dict[str, str] = {
    "20": "base_rate_20", "20'": "base_rate_20", '20"': "base_rate_20",
    "20ft": "base_rate_20", "20gp": "base_rate_20", "20'gp": "base_rate_20",
    "20st": "base_rate_20", "20'st": "base_rate_20",
    "40": "base_rate_40", "40'": "base_rate_40", '40"': "base_rate_40",
    "40ft": "base_rate_40", "40gp": "base_rate_40", "40'gp": "base_rate_40",
    "40dv": "base_rate_40", "40'dv": "base_rate_40",
    "40st": "base_rate_40", "40'st": "base_rate_40",
    "40hc": "base_rate_40h", "40h": "base_rate_40h", "40hq": "base_rate_40h",
    "40'hc": "base_rate_40h", "40'h": "base_rate_40h", "40'hq": "base_rate_40h",
    "40hicube": "base_rate_40h", "40hi": "base_rate_40h", "hc40": "base_rate_40h",
    "40'hi": "base_rate_40h", "40rhc": "base_rate_40h",
    "45": "base_rate_45", "45'": "base_rate_45", '45"': "base_rate_45",
    "45ft": "base_rate_45", "45hc": "base_rate_45", "45'hc": "base_rate_45",
    "45hq": "base_rate_45", "45'hq": "base_rate_45",
    # Destination columns
    "destination": "destination_city", "dest": "destination_city",
    "pod": "destination_city", "port of discharge": "destination_city",
    "portof discharge": "destination_city", "discharge port": "destination_city",
    "destination port": "destination_city", "del": "destination_city",
    "place of delivery": "destination_city", "final dest": "destination_city",
    # Via columns
    "via": "destination_via_city", "dest via": "destination_via_city",
    "destination via": "destination_via_city", "t/s": "destination_via_city",
    "t/s port": "destination_via_city", "transship": "destination_via_city",
    "tranship": "destination_via_city", "transhipment": "destination_via_city",
    "transshipment": "destination_via_city", "ts port": "destination_via_city",
    # Service
    "service": "service", "term": "service", "type": "service",
    "mode": "service", "service type": "service", "svc": "service",
    "move type": "service", "terms": "service",
    # Remarks / notes
    "remarks": "remarks", "remark": "remarks", "note": "remarks",
    "notes": "remarks", "comment": "remarks", "comments": "remarks",
    # Columns to map to remarks (carry through for reference)
    "direct call": "remarks", "directcall": "remarks",
    # Explicitly ignored columns — mapped to a sentinel so they're recognised but skipped
    # (the extractor skips any field not starting with base_rate/agw/known fields)
    "cntry": "_ignore", "country": "_ignore",
    "cur": "_ignore", "currency": "_ignore",
    "loading port": "_ignore", "pol": "_ignore",
}

_ARB_ORIGIN_EXTRA: dict[str, str] = {
    "origin": "origin_city", "pol": "origin_city",
    "inland origin": "origin_city", "origin city": "origin_city",
    "origin point": "origin_city", "port of loading": "origin_city",
    "via": "origin_via_city", "pol via": "origin_via_city",
    "trunk port": "origin_via_city",
    "agw 20": "agw_20", "agw20": "agw_20", "agw 20'": "agw_20",
    "agw 40": "agw_40", "agw40": "agw_40", "agw 40'": "agw_40",
    "agw 45": "agw_45", "agw45": "agw_45", "agw 45'": "agw_45",
}

_ARB_DEST_EXTRA: dict[str, str] = {
    "destination": "destination_city", "inland dest": "destination_city",
    "dest city": "destination_city", "delivery point": "destination_city",
    "via": "destination_via_city", "trunk port": "destination_via_city",
}

# Handles plain numbers like "360" AND commodity/rate codes like "R2/2298" → extracts 2298
_NUMERIC_RE = re.compile(r"(?:[A-Za-z]\d*/)?(\d[\d,]*(?:\.\d+)?)")


def _normalize_header_key(cell: str) -> str:
    s = (cell.lower().strip()
         .replace("\u2018", "'").replace("\u2019", "'")
         .replace("\u201c", '"').replace("\u201d", '"')
         .replace("'", "'").replace("'", "'"))
    # Remove trailing colon, parens, extra spaces
    s = re.sub(r"[:()\[\]]", "", s).strip()
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s)
    return s


def _detect_header_row(
    grid: list[list[str]],
    col_source: dict[str, str] | None = None,
) -> tuple[int, dict[int, str]]:
    if col_source is None:
        col_source = _RATE_COL

    for row_idx, row in enumerate(grid[:8]):
        col_map: dict[int, str] = {}
        for col_idx, cell in enumerate(row):
            key = _normalize_header_key(cell)
            if key in col_source:
                col_map[col_idx] = col_source[key]
            else:
                # Fuzzy: try removing all spaces/punctuation
                compact = re.sub(r"[^a-z0-9]", "", key)
                for known, field in col_source.items():
                    if compact == re.sub(r"[^a-z0-9]", "", known):
                        col_map[col_idx] = field
                        break

        rate_fields = [v for v in col_map.values() if v.startswith("base_rate")]
        if len(rate_fields) >= 2:
            return row_idx, col_map

    return -1, {}


def _extract_from_grid(
    grid: list[list[str]],
    context: dict,
    col_source: dict[str, str] | None = None,
) -> list[dict] | None:
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
            if field == "_ignore":
                continue  # explicitly ignored columns (Cntry, Cur, etc.)
            if col_idx >= len(row):
                continue
            cell = row[col_idx].strip()
            if not cell or cell in ("-", "—", "--", "N/A", "n/a", "TBN", "None"):
                continue

            if field.startswith("base_rate") or field.startswith("agw"):
                m = _NUMERIC_RE.search(cell)
                if m:
                    try:
                        val = float(m.group(1).replace(",", ""))
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
    carrier: str, contract_id: str,
    effective_date: str, expiration_date: str,
    commodity: str, scope: str,
    origin: str, origin_via: str,
    surcharges: dict,
) -> None:
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
    section: dict, model: str, host: str,
    carrier: str, contract_id: str,
    effective_date: str, expiration_date: str,
    commodity: str, surcharges: dict,
    num_ctx: int = 4096, max_text: int = 4000,
) -> list[dict]:
    origin     = section.get("origin", "")
    origin_via = section.get("origin_via", "")
    scope      = section.get("scope", "")
    raw_text   = section.get("raw_text", "")
    tables     = section.get("tables", [])

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
        grid_repr  = json.dumps(tables[:2], ensure_ascii=False)[:2000]
        text_input = f"GRIDS:\n{grid_repr}\n\nTEXT:\n{_prefilter_text(raw_text, 1000)}"
    else:
        text_input = _prefilter_text(raw_text, max_text)

    prompt = RATES_PROMPT.format(
        carrier=carrier, contract_id=contract_id,
        effective_date=effective_date, expiration_date=expiration_date,
        commodity=commodity, scope=scope,
        origin_city=origin, origin_via=origin_via or "",
        text=text_input,
    )
    try:
        raw  = _call_ollama(prompt, model=model, host=host, max_tokens=1024, num_ctx=num_ctx)
        data = _parse_json(raw)
        rows = data if isinstance(data, list) else data.get("rows", data.get("rates", []))
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
    arb_section: dict, arb_kind: str, prompt_template,
    model: str, host: str,
    carrier: str, contract_id: str,
    effective_date: str, expiration_date: str,
    commodity: str, scope: str,
    num_ctx: int = 4096, max_text: int = 4000,
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
        grid_repr  = json.dumps(tables[:2], ensure_ascii=False)[:2000]
        text_input = f"GRIDS:\n{grid_repr}\n\nTEXT:\n{_prefilter_text(raw_text, 1000)}"
    else:
        text_input = _prefilter_text(raw_text, max_text)

    prompt = prompt_template.format(
        carrier=carrier, contract_id=contract_id,
        effective_date=effective_date, expiration_date=expiration_date,
        commodity=commodity, scope=scope,
        text=text_input,
    )
    try:
        raw  = _call_ollama(prompt, model=model, host=host, max_tokens=1024, num_ctx=num_ctx)
        data = _parse_json(raw)
        rows = data if isinstance(data, list) else data.get("rows", [])
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
    low_memory: bool = False,
) -> dict:
    """
    Main entry: takes pdf_extractor output, returns structured freight data.
    All LLM calls (metadata, surcharges, rates, arbs) run in ONE shared pool.
    low_memory=True → 2 workers, smaller context, shorter input (for 8GB RAM machines).
    """
    if low_memory:
        max_workers = 2

    metadata = extracted.get("metadata", {})
    carrier         = metadata.get("carrier", "")
    contract_id     = metadata.get("contract_id", "")
    effective_date  = metadata.get("effective_date", "")
    expiration_date = metadata.get("expiration_date", "")
    commodity       = metadata.get("commodity", "")
    scope           = metadata.get("scope", "")

    sections = extracted.get("sections", [])
    for s in sections:
        if not s.get("scope"):
            s["scope"] = scope

    # Default surcharges (used if no surcharge text or LLM fails)
    surcharges = {
        "ams_china_japan":    35,
        "hea_heavy_surcharge": "TARIFF",
        "agw":                 "TARIFF",
        "rds_red_sea":         "INCLUSIVE",
    }

    # ── ALL work in ONE thread pool — metadata, surcharges, rates, arbs ──────
    all_rates:    list[dict] = []
    origin_arbs:  list[dict] = []
    dest_arbs:    list[dict] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}

        # Metadata (if regex missed it)
        if not all([carrier, contract_id]):
            first_text = ""
            if sections:
                first_text = sections[0].get("raw_text", "")[:2000]
            if first_text:
                def do_metadata():
                    raw = _call_ollama(METADATA_PROMPT.format(text=first_text),
                                       model=model, host=host, max_tokens=256, num_ctx=2048)
                    return _parse_json(raw)
                futures[pool.submit(do_metadata)] = ("metadata", None)

        # Surcharges
        surcharge_text = extracted.get("surcharge_text", "")
        if surcharge_text.strip():
            def do_surcharges():
                raw = _call_ollama(
                    SURCHARGE_PROMPT.format(text=_prefilter_text(surcharge_text, 2000)),
                    model=model, host=host, max_tokens=128, num_ctx=2048,
                )
                return _parse_json(raw)
            futures[pool.submit(do_surcharges)] = ("surcharges", None)

        # Tune context/input sizes based on available memory
        rate_ctx      = 2048 if low_memory else 4096
        rate_max_text = 2000 if low_memory else 4000

        # Rate sections
        for section in sections:
            if not section.get("origin"):
                continue
            futures[pool.submit(
                _extract_section_rates,
                section, model, host,
                carrier, contract_id, effective_date, expiration_date,
                commodity, surcharges, rate_ctx, rate_max_text,
            )] = ("rate", section.get("origin", "?"))

        # Origin arbitraries
        for arb in extracted.get("origin_arb_sections", []):
            if arb.get("raw_text", "").strip() or arb.get("tables"):
                futures[pool.submit(
                    _extract_arb_section,
                    arb, "ORIGIN", ORIGIN_ARB_PROMPT, model, host,
                    carrier, contract_id, effective_date, expiration_date, commodity, scope,
                    rate_ctx, rate_max_text,
                )] = ("origin_arb", None)

        # Destination arbitraries
        for arb in extracted.get("dest_arb_sections", []):
            if arb.get("raw_text", "").strip() or arb.get("tables"):
                futures[pool.submit(
                    _extract_arb_section,
                    arb, "DESTINATION", DEST_ARB_PROMPT, model, host,
                    carrier, contract_id, effective_date, expiration_date, commodity, scope,
                    rate_ctx, rate_max_text,
                )] = ("dest_arb", None)

        # Collect results as they complete
        for future in as_completed(futures):
            task_type, label = futures[future]
            try:
                result = future.result()
                if task_type == "metadata" and isinstance(result, dict):
                    metadata.update(result)
                    carrier         = metadata.get("carrier", carrier)
                    contract_id     = metadata.get("contract_id", contract_id)
                    effective_date  = metadata.get("effective_date", effective_date)
                    expiration_date = metadata.get("expiration_date", expiration_date)
                    commodity       = metadata.get("commodity", commodity)
                    logger.info(f"[ollama_extractor] Metadata: {metadata}")
                elif task_type == "surcharges" and isinstance(result, dict):
                    surcharges.update(result)
                    logger.info(f"[ollama_extractor] Surcharges: {surcharges}")
                elif task_type == "rate" and isinstance(result, list):
                    all_rates.extend(result)
                elif task_type == "origin_arb" and isinstance(result, list):
                    origin_arbs.extend(result)
                elif task_type == "dest_arb" and isinstance(result, list):
                    dest_arbs.extend(result)
            except Exception as e:
                logger.error(f"[ollama_extractor] {task_type} failed: {e}")

    return {
        "metadata":                metadata,
        "surcharges":              surcharges,
        "rates":                   all_rates,
        "origin_arbitraries":      origin_arbs,
        "destination_arbitraries": dest_arbs,
    }
