"""
Provision Registry — stores and applies contract rules to rate records.

A provision is a structured rule extracted from sections 1-12 of a freight
contract. Each provision has:
  - A condition (when it applies): scope, commodity, cargo type, etc.
  - An action (what it changes): set surcharge, override date, include RDS, etc.
  - A stable deterministic ID so the same rule always gets the same key.

Rate records carry an `applied_provisions` list of IDs referencing which
provisions were applied, enabling full auditability without duplication.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("provision_registry")


class ProvisionRegistry:
    """
    Stores every provision (rule) exactly once, keyed by a deterministic ID.

    A provision looks like:
      {
        "id":          "prov_<hash>",
        "source":      "rules_file" | "document" | "regex",
        "condition":   {"scope": "ASIA-NORTH AMERICA WEST COAST"},
        "action":      {"type": "set_surcharge", "column": "RDS", "value": "250"},
        "description": "Apply RED SEA DIVERSION surcharge of 250 for scope ..."
      }
    """

    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        condition: Dict[str, Any],
        action: Dict[str, Any],
        source: str = "rules_file",
        description: str = "",
    ) -> str:
        """
        Register a provision and return its stable ID.
        Identical provisions always map to the same ID (idempotent).
        """
        prov_id = self._make_id(condition, action)
        if prov_id not in self._store:
            self._store[prov_id] = {
                "id": prov_id,
                "source": source,
                "condition": condition,
                "action": action,
                "description": description or self._auto_describe(condition, action),
            }
        return prov_id

    def get(self, prov_id: str) -> Optional[Dict[str, Any]]:
        return self._store.get(prov_id)

    def all_provisions(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._store)

    def count(self) -> int:
        return len(self._store)

    # ── Bulk operations ────────────────────────────────────────────────────────

    def register_from_rules(self, rules: Dict[str, Any]) -> List[str]:
        """
        Register provisions from the LLM-extracted rules dict.

        Converts the flat rules format:
          {
            "scope_dates": {"SCOPE": {"effective": "...", "expiry": "..."}},
            "scope_surcharges": {"SCOPE": {"rds_included_for_dry": true, ...}},
            "container_glossary": {"D2": "20' Dry", ...},
            "reefer_codes": ["R2", "R5"]
          }

        Into individual provisions registered in the store.
        Returns list of registered provision IDs.
        """
        ids: List[str] = []

        # 1. Per-scope date overrides (Section 8)
        for scope, dates in rules.get("scope_dates", {}).items():
            eff = dates.get("effective", "")
            exp = dates.get("expiry", "")
            if eff or exp:
                prov_id = self.register(
                    condition={"scope": scope},
                    action={
                        "type": "override_dates",
                        "effective_date": eff,
                        "expiration_date": exp,
                    },
                    source="rules_file",
                    description=f"Override dates for [{scope}]: {eff} → {exp}",
                )
                ids.append(prov_id)

        # 2. Per-scope surcharge config (Section 12)
        for scope, surch in rules.get("scope_surcharges", {}).items():
            # RDS inclusion for dry cargo
            if surch.get("rds_included_for_dry") is True:
                prov_id = self.register(
                    condition={"scope": scope, "cargo_type": "dry"},
                    action={"type": "set_surcharge", "column": "rds_red_sea", "value": "included"},
                    source="rules_file",
                    description=f"RDS included for dry cargo in [{scope}]",
                )
                ids.append(prov_id)

            # Surcharge cutoff date
            cutoff = surch.get("surcharge_inclusion_cutoff")
            if cutoff:
                prov_id = self.register(
                    condition={"scope": scope},
                    action={"type": "surcharge_cutoff", "cutoff_date": cutoff},
                    source="rules_file",
                    description=f"Surcharge cutoff for [{scope}]: {cutoff}",
                )
                ids.append(prov_id)

            # Applicable surcharges list
            applicable = surch.get("applicable_surcharges", [])
            if applicable:
                prov_id = self.register(
                    condition={"scope": scope},
                    action={"type": "applicable_surcharges", "codes": applicable},
                    source="rules_file",
                    description=f"Applicable surcharges for [{scope}]: {', '.join(applicable)}",
                )
                ids.append(prov_id)

        # 3. Container glossary (maps D2→20', R2→Reefer 20', etc.)
        glossary = rules.get("container_glossary", {})
        if glossary:
            prov_id = self.register(
                condition={},
                action={"type": "container_glossary", "mapping": glossary},
                source="rules_file",
                description=f"Container glossary: {len(glossary)} codes",
            )
            ids.append(prov_id)

        # 4. Reefer codes
        reefer_codes = rules.get("reefer_codes", [])
        if reefer_codes:
            prov_id = self.register(
                condition={},
                action={"type": "reefer_codes", "codes": reefer_codes},
                source="rules_file",
                description=f"Reefer container codes: {', '.join(reefer_codes)}",
            )
            ids.append(prov_id)

        if ids:
            logger.info(f"[provisions] Registered {len(ids)} provisions from rules")
        return ids

    # ── Application ────────────────────────────────────────────────────────────

    def apply_to_rows(
        self,
        rates: List[Dict[str, Any]],
        origin_arbs: List[Dict[str, Any]],
        dest_arbs: List[Dict[str, Any]],
        rules: Dict[str, Any],
    ) -> None:
        """
        Apply all registered provisions to rate rows in-place.
        Also stamps `applied_provisions` list on each row for auditability.
        """
        scope_dates = rules.get("scope_dates", {})
        scope_surcharges = rules.get("scope_surcharges", {})
        reefer_codes = set(rules.get("reefer_codes", []))
        glossary = rules.get("container_glossary", {})

        # Build reefer type set from glossary
        reefer_types = set()
        for code, desc in glossary.items():
            if (code.upper().startswith("R")
                    or "reefer" in desc.lower()
                    or "RF" in desc.upper()):
                reefer_types.add(code.upper())

        all_rows = list(rates) + list(origin_arbs) + list(dest_arbs)
        dates_applied = 0
        rds_applied = 0
        reefer_remapped = 0

        for row in all_rows:
            # Ensure applied_provisions list exists
            if "applied_provisions" not in row:
                row["applied_provisions"] = []

            scope = row.get("scope", "")

            # ── 1. Per-scope dates (Section 8) ──
            date_key = _match_scope(scope, scope_dates)
            if date_key:
                sd = scope_dates[date_key]
                if sd.get("effective"):
                    row["effective_date"] = sd["effective"]
                if sd.get("expiry"):
                    row["expiration_date"] = sd["expiry"]
                dates_applied += 1

                # Find and stamp the provision ID
                for prov_id, prov in self._store.items():
                    if (prov["action"].get("type") == "override_dates"
                            and _normalize_scope_key(prov["condition"].get("scope", ""))
                            == _normalize_scope_key(date_key)):
                        if prov_id not in row["applied_provisions"]:
                            row["applied_provisions"].append(prov_id)
                        break

            # ── 2. RDS inclusion (Section 12.C) ──
            surch_key = _match_scope(scope, scope_surcharges)
            if surch_key:
                sc = scope_surcharges[surch_key]
                if sc.get("rds_included_for_dry") is True:
                    commodity = (row.get("commodity") or "").upper()
                    is_reefer = (
                        any(rc in commodity for rc in reefer_codes)
                        or "REEFER" in commodity
                        or "RF" in commodity
                    )
                    if not is_reefer:
                        row["rds_red_sea"] = "included"
                        rds_applied += 1

                        for prov_id, prov in self._store.items():
                            if (prov["action"].get("type") == "set_surcharge"
                                    and prov["action"].get("column") == "rds_red_sea"):
                                if prov_id not in row["applied_provisions"]:
                                    row["applied_provisions"].append(prov_id)
                                break

            # ── 3. Reefer column remapping ──
            commodity = (row.get("commodity") or "").upper()
            is_reefer = (
                any(rc in commodity for rc in reefer_codes)
                or "REEFER" in commodity
                or "RF" in commodity
            )
            if is_reefer:
                if row.get("base_rate_20"):
                    row["reefer_rate_20"] = row.pop("base_rate_20")
                if row.get("base_rate_40"):
                    row["reefer_rate_40"] = row.pop("base_rate_40")
                if row.get("base_rate_40h"):
                    row["reefer_rate_40h"] = row.pop("base_rate_40h")
                if row.get("base_rate_45"):
                    row["reefer_rate_nor40"] = row.pop("base_rate_45")
                reefer_remapped += 1

        if dates_applied or rds_applied or reefer_remapped:
            logger.info(
                f"[provisions] Applied: {dates_applied} scope-date overrides, "
                f"{rds_applied} RDS inclusions, {reefer_remapped} reefer remappings"
            )

    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _make_id(condition: Dict, action: Dict) -> str:
        fingerprint = json.dumps({"c": condition, "a": action}, sort_keys=True)
        h = hashlib.md5(fingerprint.encode()).hexdigest()[:10]
        return f"prov_{h}"

    @staticmethod
    def _auto_describe(condition: Dict, action: Dict) -> str:
        cond_str = (
            ", ".join(f"{k}={v}" for k, v in condition.items())
            if condition else "always"
        )
        act_type = action.get("type", "unknown")
        if act_type == "set_surcharge":
            act_str = f"set {action.get('column', '?')} = {action.get('value', '?')}"
        elif act_type == "override_dates":
            act_str = f"dates {action.get('effective_date', '?')} → {action.get('expiration_date', '?')}"
        else:
            act_str = f"{act_type}"
        return f"When [{cond_str}] → {act_str}"


# ── Scope matching helpers ────────────────────────────────────────────────────

def _normalize_scope_key(scope: str) -> str:
    """Normalize a scope string for comparison."""
    if not scope:
        return ""
    s = scope.upper().strip()
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s)
    s = s.strip("[]() ")
    return s


def _match_scope(row_scope: str, scope_dict: dict) -> Optional[str]:
    """
    Match a row's scope against the keys of a scope dict.
    Returns the matching key, or None.
    """
    if not row_scope or not scope_dict:
        return None
    norm = _normalize_scope_key(row_scope)
    # Pass 1: exact match
    for key in scope_dict:
        if _normalize_scope_key(key) == norm:
            return key
    # Pass 2: substring match
    for key in scope_dict:
        nk = _normalize_scope_key(key)
        if nk in norm or norm in nk:
            return key
    return None
