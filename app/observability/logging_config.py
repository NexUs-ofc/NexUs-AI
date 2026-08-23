import json
import logging
from datetime import datetime, timezone

_STANDARD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys())


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and key != "message":
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


_LOGGERS_RUIDOSOS = (
    "pymongo",
    "httpcore",
    "httpx",
    "urllib3",
    "groq",
    "openai",
    "google",
    "google_genai",
    "langchain",
    "langsmith",
    "langchain_core",
    "langchain_google_genai",
    "langgraph",
)


def configure_logging() -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root_logger.addHandler(handler)

    for nome in _LOGGERS_RUIDOSOS:
        logging.getLogger(nome).setLevel(logging.WARNING)
