"""Create (or, with --reset, recreate) the database tables.

Run from the project root as a module so `app` is importable:
    uv run python -m scripts.create_tables
"""
import argparse

from sqlalchemy import inspect

from app.db import engine
from app.models import Base  


def create_tables(reset: bool = False) -> None:

    if reset:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create the database tables.")
    parser.add_argument(
        "--reset", action="store_true", help="DROP all tables first (destroys data)"
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="Skip the confirmation prompt (needed for non-interactive shells, CI, etc.)",
    )
    args = parser.parse_args()

    if args.reset and not args.yes:
        target = engine.url.render_as_string(hide_password=True)
        try:
            confirmed = input(f"Drop ALL tables in {target}? [y/N] ").strip().lower() == "y"
        except EOFError:
            raise SystemExit(
                "No interactive input available to confirm --reset. "
                "Re-run with --yes to confirm non-interactively."
            )
        if not confirmed:
            raise SystemExit("Aborted.")

    create_tables(reset=args.reset)
    print("Tables:", ", ".join(sorted(inspect(engine).get_table_names())))