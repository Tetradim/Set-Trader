import unittest
import sys
from pathlib import Path

from fastapi import Query

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from audit_service import _normalize_event_type_filters
import deps


class AuditServiceTest(unittest.TestCase):
    def test_normalizes_event_type_filters(self):
        self.assertIsNone(_normalize_event_type_filters())
        self.assertEqual(["SETTING_CHANGED"], _normalize_event_type_filters(event_type="SETTING_CHANGED"))
        self.assertEqual(
            ["BROKER_API_ERROR", "BROKER_CIRCUIT_OPEN"],
            _normalize_event_type_filters(event_types=["BROKER_API_ERROR", "BROKER_CIRCUIT_OPEN"]),
        )

    def test_ignores_fastapi_query_default_when_called_directly(self):
        self.assertIsNone(_normalize_event_type_filters(event_types=Query(None)))

    def test_lazy_db_supports_collection_indexing(self):
        class FakeDb:
            def __getitem__(self, name):
                return f"collection:{name}"

        old_db = deps._db
        try:
            deps._db = FakeDb()
            self.assertEqual("collection:audit_logs", deps.db["audit_logs"])
        finally:
            deps._db = old_db


if __name__ == "__main__":
    unittest.main()
