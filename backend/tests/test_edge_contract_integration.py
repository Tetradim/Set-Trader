"""Integration-style checks for Pulse -> Edge command contracts."""
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from shared.commands import CommandType
from shared.commands_utils import build_position_update, build_pulse_status
from shared.mongo_client import EdgeMongoClient


class _InsertResult:
    inserted_id = "cmd-1"


class _Collection:
    def __init__(self):
        self.documents = []

    async def insert_one(self, command):
        self.documents.append(command)
        return _InsertResult()


class _Db:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, _name):
        return self.collection


class EdgeContractIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_position_update_contract_calculates_pnl(self):
        update = build_position_update(
            symbol="AAPL",
            quantity=10,
            avg_entry=100,
            current_price=112.5,
            trading_mode="live",
            broker_id="alpaca",
        )

        self.assertEqual(CommandType.POSITION_UPDATE, update.command_type)
        self.assertEqual(1125.0, update.market_value)
        self.assertEqual(1000.0, update.cost_basis)
        self.assertEqual(125.0, update.unrealized_pnl)
        self.assertEqual(12.5, update.unrealized_pnl_percent)
        self.assertEqual("live", update.trading_mode)

    async def test_edge_client_inserts_command_and_tracks_counts(self):
        collection = _Collection()
        client = EdgeMongoClient(mongo_url="mongodb://edge")
        client._db = _Db(collection)
        client._has_ever_connected = True

        ok = await client.insert_command({"command_type": CommandType.POSITION_UPDATE, "symbol": "AAPL"})

        self.assertTrue(ok)
        self.assertEqual(1, len(collection.documents))
        self.assertEqual(1, client.status_snapshot()["command_counts"][CommandType.POSITION_UPDATE.value])
        self.assertNotIn("mongodb://edge", str(client.status_snapshot()))

    async def test_pulse_status_contract_includes_global_market_handoff(self):
        status = build_pulse_status(
            running=True,
            paused=False,
            trading_mode="live",
            market_state="open",
            market_open=True,
            open_markets=["US", "UK", "JP"],
            yfinance=True,
            telegram=True,
            ws_clients=1,
            brokers_connected=2,
        )

        self.assertEqual(CommandType.PULSE_STATUS, status.command_type)
        self.assertEqual(["US", "UK", "JP"], status.open_markets)
        self.assertEqual("live", status.trading_mode)


if __name__ == "__main__":
    unittest.main()
