"""Trading engine behavior mixins.

Importing the trading package installs the compatibility guards that make
live state transitions depend on durable broker fill evidence.
"""

from trading import live_truth_patch as _live_truth_patch  # noqa: F401,E402
