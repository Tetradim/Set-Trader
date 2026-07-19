"""Trading engine behavior mixins.

Importing the trading package installs compatibility guards that make live
state transitions depend on durable broker fill evidence and reconciliation.
"""

from trading import live_truth_patch as _live_truth_patch  # noqa: F401,E402
from trading import live_order_reconciliation_patch as _live_order_reconciliation_patch  # noqa: F401,E402
from trading import live_broker_scope_patch as _live_broker_scope_patch  # noqa: F401,E402
from trading import live_pretrade_patch as _live_pretrade_patch  # noqa: F401,E402
from trading import live_broker_capability_patch as _live_broker_capability_patch  # noqa: F401,E402

# Trade-card authorization wraps execution-intent handling. Durable idempotency
# is still installed later and remains the outermost exactly-once guard.
from trading import edge_strategy_contract_patch as _edge_strategy_contract_patch  # noqa: F401,E402
from trading import edge_handoff_contract_patch as _edge_handoff_contract_patch  # noqa: F401,E402

# The wrapper now supports execution-intent v2 and v3, but the v2 marker is an
# established readiness ABI used to verify that the execution-intent layer sits
# immediately inside durable idempotency. Keep that marker name on the route.
_edge_handoff_contract_patch._PATCH_MARKER = "_pulse_edge_execution_intent_v2"

# Idempotency must be installed after the execution-intent wrapper so it becomes
# the outermost guard on the final /api/edge/handoff route. Duplicate commands
# are claimed/replayed before expiry or broker submission logic can run.
from trading import edge_handoff_idempotency_patch as _edge_handoff_idempotency_patch  # noqa: F401,E402
from trading import live_position_publication_patch as _live_position_publication_patch  # noqa: F401,E402
from trading import live_publication_resilience_patch as _live_publication_resilience_patch  # noqa: F401,E402
# Execution-quality wrappers must load after publication reconciliation so their
# expiry/terminal-fill composition wraps the actual final fill reducer.
from trading import live_execution_quality_patch as _live_execution_quality_patch  # noqa: F401,E402
from trading import live_terminal_fill_patch as _live_terminal_fill_patch  # noqa: F401,E402
from trading import live_execution_orchestrator_patch as _live_execution_orchestrator_patch  # noqa: F401,E402
from trading import live_cycle_capital_patch as _live_cycle_capital_patch  # noqa: F401,E402
from trading import live_cycle_accounting_composition_patch as _live_cycle_accounting_composition_patch  # noqa: F401,E402

# Cross-feature safety composition must remain last. These guards preserve the
# public engine API while making partial fills, risk state, and multi-broker
# reconciliation use one authoritative execution path.
from trading import risk_safety_patch as _risk_safety_patch  # noqa: F401,E402
from trading import broker_position_safety_patch as _broker_position_safety_patch  # noqa: F401,E402
from trading import execution_order_safety_patch as _execution_order_safety_patch  # noqa: F401,E402
from trading import partial_publication_safety_patch as _partial_publication_safety_patch  # noqa: F401,E402
