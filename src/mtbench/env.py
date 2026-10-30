"""Load .env, hand out API keys, and keep key values out of logs and manifests."""
import logging
import os
import re

from dotenv import load_dotenv

from mtbench.path import resolve_root_dir

load_dotenv(resolve_root_dir() / ".env")

KNOWN_KEYS = ("FRED_API_KEY", "EIA_API_KEY", "DELPHI_EPIDATA_API_KEY", "QUICK_STATS_API_KEY")
REDACTED = "***REDACTED***"
MIN_SECRET_LEN = 8

_SECRET_NAME = re.compile(r"(API_?KEY|TOKEN|SECRET|PASSWORD)$", re.IGNORECASE)
_QUERY_PARAM = re.compile(
    r"(?i)([?&;\s](?:api[_-]?key|apikey|key|token|access_token|secret)=)[^&\s\"']+"
)
_AUTH_HEADER = re.compile(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+|basic\s+)?[^\s,;\"']+")


def get_key(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set; add it to .env (see src/mtbench/env.py)")
    return value


def get_user_agent() -> str:
    """Descriptive User-Agent for api.weather.gov, read from NWS_USER_AGENT."""
    value = os.environ.get("NWS_USER_AGENT", "").strip()
    if not value:
        raise RuntimeError(
            "NWS_USER_AGENT is not set; add NWS_USER_AGENT=<app name and contact> to .env"
        )
    return value


def _secret_values() -> list[str]:
    values = {os.environ.get(k, "") for k in KNOWN_KEYS}
    values |= {v for k, v in os.environ.items() if _SECRET_NAME.search(k)}
    return sorted((v for v in values if len(v) >= MIN_SECRET_LEN), key=len, reverse=True)


def redact(text) -> str:
    """Replace key values, key-like URL query parameters and auth headers in `text`."""
    text = str(text)
    for value in _secret_values():
        text = text.replace(value, REDACTED)
    text = _QUERY_PARAM.sub(r"\g<1>" + REDACTED, text)
    return _AUTH_HEADER.sub(r"\g<1>" + REDACTED, text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        return True


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not any(isinstance(f, RedactingFilter) for f in logger.filters):
        logger.addFilter(RedactingFilter())
    if not logger.handlers and not logging.getLogger().handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
        handler.addFilter(RedactingFilter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
