from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_stop_buying_keeps_open_positions_enabled_for_exit_management():
    text = (ROOT / "routes" / "edge.py").read_text(encoding="utf-8")

    assert '"buying_paused": True' in text
    assert 'if position_qty > 0:' in text
    assert 'updates["enabled"] = True' in text
    assert 'updates["enabled"] = False' in text


def test_buying_paused_blocks_all_buy_paths_without_blocking_evaluation():
    ticker_eval = (ROOT / "trading" / "ticker_evaluation.py").read_text(encoding="utf-8")
    strategy = (ROOT / "trading" / "strategy_signals.py").read_text(encoding="utf-8")
    brackets = (ROOT / "trading" / "brackets.py").read_text(encoding="utf-8")

    assert 'buying_paused = ticker_doc.get("buying_paused", False)' in ticker_eval
    assert 'if pos["qty"] == 0 and not buying_paused:' in ticker_eval
    assert 'if ticker_doc.get("buying_paused", False):' in strategy
    assert "buy_legs and not buying_paused" in brackets


def test_start_bot_clears_buying_paused_flags():
    bot = (ROOT / "routes" / "bot.py").read_text(encoding="utf-8")
    ws = (ROOT / "routes" / "ws.py").read_text(encoding="utf-8")

    assert '"buying_paused": False' in bot
    assert '"buying_paused": False' in ws
