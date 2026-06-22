import deps


TRAILING_RUNTIME_FIELDS = {
    "trailing_enabled",
    "trailing_percent",
    "trailing_percent_mode",
    "trailing_order_type",
}


async def reset_trailing_state_if_needed(updates: dict, symbols: list[str] | None = None) -> None:
    if TRAILING_RUNTIME_FIELDS.intersection(updates or {}):
        reset = getattr(deps.engine, "reset_trailing_runtime_state", None)
        if reset:
            await reset(symbols)
