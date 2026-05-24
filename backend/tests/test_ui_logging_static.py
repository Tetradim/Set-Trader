"""Static checks for browser-to-desktop UI logging."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class UiLoggingStaticTest(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_backend_accepts_batched_client_events_and_sanitizes_payloads(self):
        server = self.read("backend/server.py")
        logs = self.read("backend/routes/logs.py")

        self.assertIn("api.include_router(logs_router", server)
        self.assertIn("def get_runtime_log_path", logs)
        self.assertIn('os.getenv("LOG_FILE"', logs)
        self.assertIn('@router.post("/client-events")', logs)
        self.assertIn("async def log_client_events(request: Request)", logs)
        self.assertIn("sanitize_client_log_payload", logs)
        self.assertIn("token", logs)
        self.assertIn("password", logs)
        self.assertIn("logger.info(\"Frontend event", logs)
        self.assertIn("logger.error(\"Frontend event", logs)

    def test_frontend_installs_global_ui_logging(self):
        main = self.read("frontend/src/main.tsx")
        logger = self.read("frontend/src/lib/clientLogger.ts")

        self.assertIn("installUiLogging", main)
        self.assertIn("window.addEventListener('error'", logger)
        self.assertIn("window.addEventListener('unhandledrejection'", logger)
        self.assertIn("document.addEventListener('click'", logger)
        self.assertIn("document.addEventListener('submit'", logger)
        self.assertIn("document.addEventListener('change'", logger)
        self.assertIn("LOG_TYPED_VALUES", logger)
        self.assertNotIn("navigator.sendBeacon", logger)
        self.assertIn("/api/logs/client-events", logger)

    def test_api_and_websocket_paths_report_client_events(self):
        api = self.read("frontend/src/lib/api.ts")
        ws = self.read("frontend/src/hooks/useWebSocket.ts")
        boundary = self.read("frontend/src/components/ErrorBoundary.tsx")

        self.assertIn("uiLog.api", api)
        self.assertIn("uiLog.ws", ws)
        self.assertIn("uiLog.error", ws)
        self.assertIn("uiLog.reactError", boundary)


if __name__ == "__main__":
    unittest.main()
