"""Static checks for the Sentinel Edge REST contract."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]


class EdgeRouteContractStaticTest(unittest.TestCase):
    def read_edge(self) -> str:
        return (ROOT / "backend" / "routes" / "edge.py").read_text(encoding="utf-8")

    def test_edge_route_has_single_signal_response_model(self):
        text = self.read_edge()

        self.assertEqual(text.count("class SignalResponse(BaseModel):"), 1)

    def test_edge_auth_accepts_api_key_header_and_bearer_token(self):
        text = self.read_edge()

        self.assertIn("authorization: Optional[str] = Header(None)", text)
        self.assertIn("Authorization", text)
        self.assertIn("Bearer ", text)
        self.assertIn("secrets.compare_digest(provided_key, expected_key)", text)

    def test_edge_status_endpoint_exposes_connection_health(self):
        text = self.read_edge()

        self.assertRegex(text, r'@router\.get\("/status"')
        self.assertIn("edge_client.status_snapshot()", text)
        self.assertIn('"api_key_configured"', text)
        self.assertIn('"max_retry_attempts"', text)

    def test_edge_get_routes_do_not_write_back_to_edge(self):
        text = self.read_edge()

        position_route = re.search(
            r'@router\.get\("/positions/\{symbol\}".*?return \{',
            text,
            re.DOTALL,
        )
        account_route = re.search(
            r'@router\.get\("/account/status".*?return \{',
            text,
            re.DOTALL,
        )
        self.assertIsNotNone(position_route)
        self.assertIsNotNone(account_route)
        self.assertNotIn("send_position_update", position_route.group(0))
        self.assertNotIn("send_account_update", account_route.group(0))

    def test_decision_route_refreshes_position_before_edge_update(self):
        text = self.read_edge()

        self.assertIn("def _current_position", text)
        decision_update = re.search(
            r"# Send position update to Edge if enabled.*?build_position_update",
            text,
            re.DOTALL,
        )
        self.assertIsNotNone(decision_update)
        self.assertIn("position = _current_position(sym)", decision_update.group(0))

    def test_signal_request_supports_legacy_decision_fields(self):
        text = self.read_edge()

        signal_request = re.search(
            r"class SignalRequest\(BaseModel\):(.*?)class SignalResponse",
            text,
            re.DOTALL,
        )
        self.assertIsNotNone(signal_request)
        body = signal_request.group(1)
        self.assertIn("price: Optional[float]", body)
        self.assertIn("trailing_percent: Optional[float]", body)


if __name__ == "__main__":
    unittest.main()
