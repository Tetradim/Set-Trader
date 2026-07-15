"""Trading engine behavior mixins.

Importing the trading package installs compatibility guards that make live
state transitions depend on durable broker fill evidence and reconciliation.
"""

from trading import live_truth_patch as _live_truth_patch  # noqa: F401,E402
from trading import live_order_reconciliation_patch as _live_order_reconciliation_patch  # noqa: F401,E402
from trading import live_broker_scope_patch as _live_broker_scope_patch  # noqa: F401,E402
from trading import live_pretrade_patch as _live_pretrade_patch  # noqa: F401,E402
from trading import live_broker_capability_patch as _live_broker_capability_patch  # noqa: F401,E402
from trading import edge_handoff_contract_patch as _edge_handoff_contract_patch  # noqa: F401,E402
from trading import live_position_publication_patch as _live_position_publication_patch  # noqa: F401,E402
from trading import live_publication_resilience_patch as _live_publication_resilience_patch  # noqa: F401,E402
