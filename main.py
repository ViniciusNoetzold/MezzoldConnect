from __future__ import annotations

import sys

from background_worker import run_background_worker
from database import initialize_database
from ui import run_app


def main() -> None:
    if "--background" in sys.argv:
        run_background_worker()
        return

    initialize_database()
    run_app()


if __name__ == "__main__":
    main()
