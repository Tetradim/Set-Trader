"""Static checks for code recovered from non-default repository branches."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class BranchConsolidationStaticTest(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_websocket_add_ticker_reports_duplicate_and_insert_errors(self):
        ws = self.read("backend/routes/ws.py")
        hook = self.read("frontend/src/hooks/useWebSocket.ts")
        dialog = self.read("frontend/src/components/AddTickerDialog.tsx")

        self.assertIn('find_one({"symbol": sym}', ws)
        self.assertIn('"TICKER_ERROR"', ws)
        self.assertIn("ticker-error", hook)
        self.assertIn("addEventListener('ticker-error'", dialog)

    def test_config_modal_uses_live_ticker_state_and_embedded_broker_selector(self):
        modal = self.read("frontend/src/components/ConfigModal.tsx")
        widgets = self.read("frontend/src/components/ticker-card/ConfigWidgets.tsx")
        watchlist = self.read("frontend/src/components/tabs/WatchlistTab.tsx")

        self.assertIn("symbol: string", modal)
        self.assertIn("s.tickers[symbol]", modal)
        self.assertIn("BrokerSelector", modal)
        self.assertIn("broker_ids", modal)
        self.assertIn("function BrokerSelector", widgets)
        self.assertIn("symbol={configSymbol}", watchlist)

    def test_settings_account_balance_does_not_overwrite_missing_values(self):
        settings = self.read("frontend/src/components/tabs/SettingsTab.tsx")

        self.assertIn("useState<number | null>(null)", settings)
        self.assertIn("data.account_balance !== null", settings)
        self.assertIn("balanceValue ??", settings)


if __name__ == "__main__":
    unittest.main()
