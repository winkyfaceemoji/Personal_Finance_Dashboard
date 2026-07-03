import json
import os
from pathlib import Path

BASE_DIR    = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"


DEFAULT_DATA_DIR = BASE_DIR / "Test Data"


def get_data_dir() -> Path | None:
    """Return the configured data directory, or None if not set."""
    env = os.environ.get("FINANCE_DATA_DIR")
    if env:
        return Path(env)
    if CONFIG_FILE.exists():
        try:
            d = json.loads(CONFIG_FILE.read_text()).get("data_dir")
            if d:
                return Path(d)
        except Exception:
            pass
    if DEFAULT_DATA_DIR.exists():
        return DEFAULT_DATA_DIR
    return None


def save_data_dir(path: str) -> None:
    CONFIG_FILE.write_text(json.dumps({"data_dir": path}, indent=2))
