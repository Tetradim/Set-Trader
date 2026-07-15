import sys
from pathlib import Path

from fastapi.routing import APIRoute


BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def test_running_application_installs_edge_handoff_contract_and_idempotency():
    import server

    routes = [
        route
        for route in server.app.routes
        if isinstance(route, APIRoute)
        and route.path == "/api/edge/handoff"
        and "POST" in (route.methods or set())
    ]
    assert len(routes) == 1

    endpoint = routes[0].endpoint
    assert getattr(endpoint, "_pulse_durable_edge_handoff_idempotency", False) is True

    wrapped = getattr(endpoint, "__wrapped__", None)
    assert wrapped is not None
    assert getattr(wrapped, "_pulse_edge_execution_intent_v2", False) is True
