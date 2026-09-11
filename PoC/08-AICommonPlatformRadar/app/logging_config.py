from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import get_settings


REDACT_KEYS = ("servicekey", "api_key", "authorization", "password", "token")


class SecretFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for key in REDACT_KEYS:
            if key in message.lower():
                record.msg = "민감정보가 포함될 수 있는 로그 메시지를 차단했습니다."
                record.args = ()
                break
        return True


def configure_logging() -> None:
    settings = get_settings()
    settings.ensure_directories()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    file_handler = RotatingFileHandler(
        settings.logs_dir / "app.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(SecretFilter())
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    if not any(isinstance(handler, RotatingFileHandler) for handler in root.handlers):
        root.addHandler(file_handler)

