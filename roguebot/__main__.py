"""Entry point: python -m roguebot [--dry-run] [-v]."""

import argparse
import logging
import sys
import threading
from pathlib import Path

from roguebot import settings
from roguebot.runner import make_runner

log = logging.getLogger("roguebot")
LOG_FILE_BYTES = 5_000_000


def _log_to_file(level: int) -> None:
    """Also keep the log in debug/bot.log (rotated), to see afterwards why a run stopped or restarted."""
    from logging.handlers import RotatingFileHandler
    try:
        Path("debug").mkdir(exist_ok=True)
        handler = RotatingFileHandler(Path("debug") / "bot.log", maxBytes=LOG_FILE_BYTES, backupCount=2, encoding="utf-8")
    except OSError as e:  # a read-only folder: the window still shows the log
        log.warning("No log file: %s", e)
        return
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-5s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)


def main() -> int:
    parser = argparse.ArgumentParser(prog="roguebot")
    parser.add_argument("--dry-run", action="store_true",
                        help="navigate to the level but do not start it (no energy spent)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    _log_to_file(logging.DEBUG if args.verbose else logging.INFO)

    try:
        from roguebot.ui import App
    except ImportError:
        log.error("tkinter is missing. Re-run the Python installer -> Modify -> tick 'tcl/tk and IDLE'.")
        return 1

    if getattr(sys, "frozen", False):
        settings.seed_data(settings.DATA_DIR, Path(sys._MEIPASS) / "data" / "skills.json")
    stop = threading.Event()
    App(make_runner(args.dry_run, stop), stop=stop.set).mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
