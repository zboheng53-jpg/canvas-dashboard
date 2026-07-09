"""Canvas Dashboard - production entry point for background auto-start."""
import os
import sys
import socket
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import settings

os.chdir(Path(__file__).parent)

LOG_FILE = Path("data") / "server.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def _create_log_handlers(log_file: Path):
    log_file.parent.mkdir(parents=True, exist_ok=True)
    return [
        RotatingFileHandler(log_file, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"),
        logging.StreamHandler(sys.stderr),
    ]


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=_create_log_handlers(LOG_FILE),
)
logger = logging.getLogger("serve")

try:
    from app import app
except Exception:
    logger.exception("Failed to import app module")
    sys.exit(1)


def _is_port_in_use(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.settimeout(1)
            s.bind((host, port))
            return False
    except OSError:
        return True


def main():
    HOST = settings.APP_HOST
    PORT = settings.APP_PORT

    try:
        Path("data").mkdir(parents=True, exist_ok=True)
    except Exception:
        logger.exception("Failed to initialize data directory")
        sys.exit(1)

    if _is_port_in_use(HOST, PORT):
        logger.warning(
            "Port %s:%d already in use — another instance is running. Exiting.",
            HOST, PORT,
        )
        sys.exit(2)

    try:
        from waitress import serve
    except ImportError:
        logger.error("waitress not installed. Run: .venv\\Scripts\\pip.exe install waitress")
        sys.exit(1)

    logger.info("Canvas Dashboard starting on %s:%d (Waitress, 4 threads)", HOST, PORT)
    try:
        serve(app, host=HOST, port=PORT, threads=4)
    except KeyboardInterrupt:
        logger.info("Server stopped (KeyboardInterrupt)")
        sys.exit(0)
    except OSError:
        logger.exception("Server OS error")
        sys.exit(1)


if __name__ == "__main__":
    main()
