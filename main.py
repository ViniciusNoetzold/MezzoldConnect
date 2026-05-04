from __future__ import annotations

from database import initialize_database
from ui import run_app


def main() -> None:
    initialize_database()
    run_app()


if __name__ == "__main__":
    main()
