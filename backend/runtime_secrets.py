"""Persistent local runtime secrets for beta desktop installs."""
import os
import secrets
from pathlib import Path


def _secret_file() -> Path:
    configured = os.getenv("SENTINEL_SECRET_FILE")
    if configured:
        return Path(configured)
    if getattr(__import__("sys"), "frozen", False):
        return Path.cwd() / "data" / "runtime_secrets.env"
    return Path(__file__).parent / "data" / "runtime_secrets.env"


def _load_pairs(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    pairs: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.strip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        pairs[key.strip()] = value.strip()
    return pairs


def _write_pairs(path: Path, pairs: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items())) + "\n"
    path.write_text(body, encoding="utf-8")


def get_or_create_secret(name: str, length_bytes: int = 32) -> str:
    """Read a secret from env or a local persistent secret file, creating it once."""
    value = os.getenv(name)
    if value:
        return value

    path = _secret_file()
    pairs = _load_pairs(path)
    if name not in pairs:
        pairs[name] = secrets.token_urlsafe(length_bytes)
        _write_pairs(path, pairs)
    os.environ[name] = pairs[name]
    return pairs[name]
