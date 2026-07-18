"""Extend the existing entry policy with the nested execution-style contract."""
from __future__ import annotations

from typing import Any, Dict

import trading.edge_entry_policy as entry_policy
from trading.edge_execution_style import normalise_style_policy


_ORIGINAL_NORMALISE = entry_policy.normalise_entry_policy
_PATCH_MARKER = "_pulse_edge_execution_style_contract_v1"


def normalise_entry_policy(intent: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
    policy = dict(_ORIGINAL_NORMALISE(intent, metadata))
    raw_intent = intent if isinstance(intent, dict) else {}
    raw_entry = raw_intent.get("entry_policy") if isinstance(raw_intent.get("entry_policy"), dict) else {}
    raw_style = raw_entry.get("execution_style_policy")
    if not isinstance(raw_style, dict):
        raw_style = metadata.get("execution_style_policy") if isinstance(metadata.get("execution_style_policy"), dict) else {}
    policy["execution_style_policy"] = normalise_style_policy(raw_style)
    policy["orb_evidence"] = raw_entry.get("orb_evidence") or metadata.get("orb_evidence")
    policy["short_squeeze"] = raw_entry.get("short_squeeze") or metadata.get("short_squeeze")
    return policy


if not getattr(entry_policy.normalise_entry_policy, _PATCH_MARKER, False):
    setattr(normalise_entry_policy, _PATCH_MARKER, True)
    entry_policy.normalise_entry_policy = normalise_entry_policy
