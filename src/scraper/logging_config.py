"""Logging configuration for the HLTV scraper pipeline.

Provides console + file + database logging. Console shows INFO+ with concise
timestamps; the log file captures DEBUG+ with full timestamps and logger names;
the database handler stores INFO+ for dashboard viewing.
"""

import logging
import sys
import threading
from datetime import datetime
from pathlib import Path


class DbLogHandler(logging.Handler):
    """Logging handler that batches records into the scraper_logs table.

    Buffers up to ``_MAX_BUFFER`` records (default 50) or ``_FLUSH_INTERVAL``
    seconds (default 5), whichever comes first.  Flushes with a single
    ``executemany()`` call to reduce DB round-trips by ~80-95%.

    On ``close()`` (called by ``logging.shutdown()``), the buffer is drained
    so no messages are lost during normal shutdown.

    If a DB write fails, the batch is printed to stderr as a fallback.
    """

    _MAX_BUFFER = 50
    _FLUSH_INTERVAL = 5.0  # seconds

    def __init__(self, conn, level: int = logging.INFO) -> None:
        super().__init__(level)
        self._conn = conn
        self._conn.autocommit = True
        self._buffer: list[tuple[str, str, str]] = []
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._closed = False

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            row = (record.levelname, record.name, msg)
            flush_now = False
            with self._lock:
                if self._closed:
                    return
                self._buffer.append(row)
                if len(self._buffer) >= self._MAX_BUFFER:
                    flush_now = True
                elif self._timer is None:
                    self._timer = threading.Timer(self._FLUSH_INTERVAL, self._flush)
                    self._timer.daemon = True
                    self._timer.start()
            if flush_now:
                self._flush()
        except Exception:
            pass  # never let logging break the scraper

    def _flush(self) -> None:
        """Write buffered records to DB in a single executemany() call."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            if not self._buffer:
                return
            batch = list(self._buffer)
            self._buffer.clear()

        try:
            with self._conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO scraper_logs (level, logger, message) VALUES (%s, %s, %s)",
                    batch,
                )
        except Exception:
            # Fallback: dump to stderr so messages aren't silently lost
            for level, logger_name, msg in batch:
                print(f"[DB LOG FALLBACK] {level} [{logger_name}] {msg}", file=sys.stderr)

    def close(self) -> None:
        """Drain buffer on shutdown so no messages are lost."""
        with self._lock:
            self._closed = True
        self._flush()
        super().close()


def setup_logging(
    data_dir: str = "data", console_level: int = logging.INFO, db_conn=None
) -> Path:
    """Configure logging with console and file handlers.

    Creates a timestamped log file under ``{data_dir}/logs/`` and attaches
    two handlers to the root logger:

    * **Console** -- ``console_level`` (default INFO), short time format.
    * **File** -- DEBUG, full datetime with logger name.

    Existing handlers on the root logger are cleared first so that calling
    this function multiple times (e.g. in tests) does not produce duplicate
    output.

    Args:
        data_dir: Base data directory. ``logs/`` is created inside it.
        console_level: Minimum level for console output.

    Returns:
        Path to the newly created log file.
    """
    log_dir = Path(data_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    log_file = log_dir / f"run-{timestamp}.log"

    # Root logger -- capture everything; handlers decide what to emit.
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    # Console handler: concise format with short time.
    console = logging.StreamHandler()
    console.setLevel(console_level)
    console.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-5s %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root.addHandler(console)

    # File handler: full format with logger name for diagnostics.
    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-5s [%(name)s] %(message)s")
    )
    root.addHandler(file_handler)

    # Database handler: INFO+ for dashboard viewing.
    if db_conn is not None:
        try:
            db_handler = DbLogHandler(db_conn, level=logging.INFO)
            db_handler.setFormatter(logging.Formatter("%(message)s"))
            root.addHandler(db_handler)
        except Exception:
            root.warning("Failed to attach DB log handler")

    # Suppress noisy third-party loggers.
    logging.getLogger("nodriver").setLevel(logging.WARNING)
    logging.getLogger("uc").setLevel(logging.WARNING)

    return log_file
