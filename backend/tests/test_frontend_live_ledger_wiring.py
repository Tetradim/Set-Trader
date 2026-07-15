from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ORDERS_ROUTE = ROOT / "backend" / "routes" / "orders.py"
ORDERS_UI = ROOT / "frontend" / "src" / "components" / "tabs" / "OrdersExecutionTab.tsx"
RECON_UI = ROOT / "frontend" / "src" / "components" / "tabs" / "ReconciliationTab.tsx"


def test_orders_ui_reads_authoritative_live_ledger():
    route = ORDERS_ROUTE.read_text(encoding="utf-8")
    ui = ORDERS_UI.read_text(encoding="utf-8")

    assert '@router.get("/live")' in route
    assert 'getattr(deps.db, "broker_orders", None)' in route
    assert 'getattr(deps.db, "parent_orders", None)' in route
    assert 'getattr(deps.db, "strategy_cycles", None)' in route
    assert "'/api/orders/live?limit=250'" in ui
    assert "parent_orders" in ui
    assert "unapplied_quantity" in ui
    assert "Completed Strategy Cycles" in ui


def test_reconciliation_ui_accepts_raw_backend_list_and_exposes_actions():
    ui = RECON_UI.read_text(encoding="utf-8")

    assert "Array.isArray(value)" in ui
    assert "'/api/reconciliation/signoffs'" in ui
    assert "'/api/reconciliation/signoff'" in ui
    assert "/api/reconciliation/resolve-break/" in ui
    assert "Resolve" in ui


def test_orders_ui_does_not_use_legacy_response_envelope():
    ui = ORDERS_UI.read_text(encoding="utf-8")

    assert "ordersRes.orders" not in ui
    assert "statsRes" not in ui
