"""Tests for Sentinel Edge communication resilience."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from pymongo.errors import PyMongoError

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from shared.mongo_client import EdgeMongoClient


class _FailingAdmin:
    async def command(self, _command):
        raise PyMongoError("edge unavailable")


class _WorkingAdmin:
    async def command(self, _command):
        return {"ok": 1}


class _FailingCollection:
    async def create_index(self, _field):
        return None

    async def insert_one(self, _command):
        raise PyMongoError("edge write failed")


class _FailingDb:
    def __getitem__(self, _name):
        return _FailingCollection()


class _FailingStartupClient:
    admin = _FailingAdmin()

    def __getitem__(self, _name):
        return _FailingDb()

    def close(self):
        return None


class _ConnectedThenFailingClient:
    admin = _WorkingAdmin()

    def __getitem__(self, _name):
        return _FailingDb()

    def close(self):
        return None


class EdgeMongoClientResilienceTest(unittest.IsolatedAsyncioTestCase):
    async def test_startup_connection_failure_keeps_edge_configured_without_backoff(self):
        client = EdgeMongoClient(mongo_url="mongodb://edge")

        with patch("shared.mongo_client.AsyncIOMotorClient", return_value=_FailingStartupClient()):
            await client.connect()

        self.assertTrue(client.is_enabled)
        self.assertFalse(client.is_connected)
        self.assertFalse(client.has_ever_connected)
        self.assertEqual(client.retry_delay_seconds, 0)
        self.assertIsNone(client.next_retry_at)
        self.assertIn("edge unavailable", client.last_error)

    async def test_write_failures_after_connection_use_capped_exponential_backoff(self):
        client = EdgeMongoClient(mongo_url="mongodb://edge", base_retry_delay=1, max_retry_delay=8)

        with patch("shared.mongo_client.AsyncIOMotorClient", return_value=_ConnectedThenFailingClient()):
            await client.connect()

            self.assertTrue(client.has_ever_connected)
            self.assertTrue(client.is_connected)

            self.assertFalse(await client.insert_command({"command_type": "PULSE_STATUS"}))
            self.assertEqual(client.retry_delay_seconds, 1)
            self.assertIsNotNone(client.next_retry_at)

            client.clear_retry_backoff_for_test()
            self.assertFalse(await client.insert_command({"command_type": "PULSE_STATUS"}))
            self.assertEqual(client.retry_delay_seconds, 2)

            client.clear_retry_backoff_for_test()
            self.assertFalse(await client.insert_command({"command_type": "PULSE_STATUS"}))
            self.assertEqual(client.retry_delay_seconds, 4)

            client.clear_retry_backoff_for_test()
            self.assertFalse(await client.insert_command({"command_type": "PULSE_STATUS"}))
            self.assertEqual(client.retry_delay_seconds, 8)

    async def test_retry_attempt_limit_only_applies_after_successful_edge_connection(self):
        client = EdgeMongoClient(
            mongo_url="mongodb://edge",
            base_retry_delay=1,
            max_retry_delay=8,
            max_retry_attempts=2,
        )

        with patch("shared.mongo_client.AsyncIOMotorClient", return_value=_FailingStartupClient()):
            await client.connect()
            await client.connect()

        self.assertTrue(client.is_enabled)
        self.assertFalse(client.has_ever_connected)
        self.assertEqual(client.consecutive_failures, 0)
        self.assertFalse(client.retry_exhausted)

        with patch("shared.mongo_client.AsyncIOMotorClient", return_value=_ConnectedThenFailingClient()):
            await client.connect()
            self.assertTrue(client.has_ever_connected)

            self.assertFalse(await client.insert_command({"command_type": "PULSE_STATUS"}))
            self.assertFalse(client.retry_exhausted)
            client.clear_retry_backoff_for_test()

            self.assertFalse(await client.insert_command({"command_type": "PULSE_STATUS"}))
            self.assertTrue(client.retry_exhausted)
            self.assertEqual(client.consecutive_failures, 2)
            client.clear_retry_backoff_for_test()

            self.assertFalse(await client.insert_command({"command_type": "PULSE_STATUS"}))
            self.assertEqual(client.consecutive_failures, 2)


if __name__ == "__main__":
    unittest.main()
