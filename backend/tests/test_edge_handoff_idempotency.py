import asyncio
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from trading.edge_handoff_idempotency_patch import (
    _claim_or_replay,
    _normalise_execution_response,
    _store_response,
)


class _Result:
    def __init__(self, matched=0, modified=0):
        self.matched_count = matched
        self.modified_count = modified


class _Collection:
    def __init__(self):
        self.docs = {}

    async def create_index(self, *_args, **_kwargs):
        return "idempotency_key_1"

    async def find_one(self, query, projection=None):
        value = self.docs.get(query.get("idempotency_key"))
        return deepcopy(value) if value else None

    async def insert_one(self, document):
        key = document["idempotency_key"]
        if key in self.docs:
            raise RuntimeError("duplicate key")
        self.docs[key] = deepcopy(document)
        return SimpleNamespace(inserted_id=key)

    async def update_one(self, query, update):
        key = query.get("idempotency_key")
        doc = self.docs.get(key)
        if not doc:
            return _Result()
        if "owner" in query and doc.get("owner") != query["owner"]:
            return _Result()
        if "lease_expires_at" in query and doc.get("lease_expires_at") != query["lease_expires_at"]:
            return _Result()
        response_filter = query.get("response")
        if isinstance(response_filter, dict) and response_filter.get("$exists") is False and "response" in doc:
            return _Result()
        for name, value in update.get("$set", {}).items():
            doc[name] = deepcopy(value)
        for name in update.get("$unset", {}):
            doc.pop(name, None)
        self.docs[key] = doc
        return _Result(matched=1, modified=1)


class _EdgeModule:
    def __init__(self):
        self.deps = SimpleNamespace(
            db=SimpleNamespace(edge_handoffs=_Collection())
        )

    def _handoff_response(self, body, **kwargs):
        return {
            "symbol": body.symbol,
            "action": body.action.value,
            "handoff_id": body.idempotency_key,
            "sent": kwargs.get("accepted", False),
            **kwargs,
        }


def _body():
    return SimpleNamespace(
        idempotency_key="edge:ASTS:buy:stable-id",
        symbol="ASTS",
        action=SimpleNamespace(value="buy"),
        mode=SimpleNamespace(value="live"),
    )


def test_completed_handoff_is_replayed_without_new_claim():
    edge = _EdgeModule()
    body = _body()

    state, response = asyncio.run(_claim_or_replay(edge, body, "owner-1"))
    assert state == "claimed"
    assert response is None

    terminal = {
        "accepted": True,
        "sent": True,
        "status": "accepted",
        "reason": "pulse_accepted",
        "handoff_id": body.idempotency_key,
    }
    asyncio.run(_store_response(edge, body, "owner-1", terminal))

    state, response = asyncio.run(_claim_or_replay(edge, body, "owner-2"))
    assert state == "replay"
    assert response["duplicate"] is True
    assert response["idempotency_replayed"] is True
    assert response["handoff_id"] == body.idempotency_key
    assert edge.deps.db.edge_handoffs.docs[body.idempotency_key]["status"] == "accepted"


def test_concurrent_duplicate_returns_processing_without_execution():
    edge = _EdgeModule()
    body = _body()
    assert asyncio.run(_claim_or_replay(edge, body, "owner-1"))[0] == "claimed"

    state, response = asyncio.run(_claim_or_replay(edge, body, "owner-2"))
    assert state == "processing"
    assert response["accepted"] is True
    assert response["sent"] is True
    assert response["reason"] == "handoff_in_progress"
    assert response["reconciliation_required"] is True


def test_pending_broker_reconciliation_is_an_accepted_command_state():
    response = _normalise_execution_response(
        {
            "accepted": False,
            "sent": False,
            "status": "failed",
            "reason": "LiveOrderExecutionError",
            "message": "Broker reconciliation is required for broker_order_ids=['abc']",
        }
    )
    assert response["accepted"] is True
    assert response["sent"] is True
    assert response["status"] == "accepted"
    assert response["reason"] == "broker_reconciliation_pending"
    assert response["reconciliation_required"] is True
