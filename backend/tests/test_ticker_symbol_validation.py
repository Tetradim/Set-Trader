from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from schemas import validate_symbol


def test_validate_symbol_accepts_ui_supported_formats():
    assert validate_symbol("aapl") == "AAPL"
    assert validate_symbol("7203.T") == "7203.T"
    assert validate_symbol("BHP.AX") == "BHP.AX"
    assert validate_symbol("BRK-B") == "BRK-B"


def test_validate_symbol_rejects_unsafe_formats():
    for symbol in ["", "BAD SYMBOL", "AAPL/USD", "AAPL;DROP"]:
        try:
            validate_symbol(symbol)
        except ValueError:
            continue
        raise AssertionError(f"{symbol!r} should be rejected")
