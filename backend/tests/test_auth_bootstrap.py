import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from routes.auth import BootstrapRequest, UserCreateRequest


class AuthBootstrapTest(unittest.TestCase):
    def test_bootstrap_accepts_admin_admin_without_email(self):
        request = BootstrapRequest(username="admin", password="admin")

        self.assertEqual("admin", request.username)
        self.assertEqual("admin", request.password)
        self.assertEqual("", request.email)

    def test_user_creation_still_requires_stronger_passwords(self):
        with self.assertRaises(ValidationError):
            UserCreateRequest(username="trader", email="trader@example.com", password="admin")


if __name__ == "__main__":
    unittest.main()
