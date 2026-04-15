"""
Central logging configuration for the trading engine.

Call configure_logging() once at startup (run_backtest.py / run_live.py).
All modules using logging.getLogger(__name__) will automatically inherit
the handlers and formatter configured here.
"""
import logging
import logging.handlers
import os

_FMT = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def configure_logging(
    log_dir: str = "logs",
    log_file: str = "trading.log",
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB per file
    backup_count: int = 5,
) -> None:
    """Configure root logger with a console handler and a rotating file handler.

    Args:
        log_dir: Directory where log files are written. Created if absent.
        log_file: Base filename for the rotating log.
        console_level: Minimum level emitted to stdout (default INFO).
        file_level: Minimum level written to file (default DEBUG).
        max_bytes: Max size of a single log file before rotation.
        backup_count: Number of rotated files to keep.
    """
    os.makedirs(log_dir, exist_ok=True)

    formatter = logging.Formatter(fmt=_FMT, datefmt=_DATE_FMT)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)

    file_handler = logging.handlers.RotatingFileHandler(
        filename=os.path.join(log_dir, log_file),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console_handler)
    root.addHandler(file_handler)
