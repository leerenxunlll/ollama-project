"""Run with ``python -m app.seed`` to load the development sample once."""

from app.db.init_db import create_tables
from app.db.session import SessionLocal, engine
from app.services.seed import seed_development_data


def main() -> None:
    """Initialize tables and insert the fixed development sample if absent."""
    create_tables(engine)
    with SessionLocal() as db:
        script = seed_development_data(db)
        print(f"开发样例已就绪：{script.title}（id={script.id}）")


if __name__ == "__main__":
    main()
