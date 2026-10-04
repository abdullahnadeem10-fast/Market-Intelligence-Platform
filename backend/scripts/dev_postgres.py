"""Start a local PostgreSQL for development WITHOUT Docker (uses the `pgserver` pip package).

Usage:  python scripts/dev_postgres.py
Prints the DATABASE_URL to put in backend/.env. The server keeps running after this script exits;
stop it with:  python scripts/dev_postgres.py --stop
"""

import os
import sys
from pathlib import Path

import pgserver

DATA_DIR = Path(os.environ.get("MIP_PGDATA", Path.home() / ".mip_pgdata"))


def main() -> None:
    server = pgserver.get_server(DATA_DIR, cleanup_mode=None)
    if "--stop" in sys.argv:
        server.cleanup()
        print("PostgreSQL stopped")
        return
    exists = server.psql("SELECT 1 FROM pg_database WHERE datname = 'mip';")
    if "1 row" not in exists:
        server.psql("CREATE DATABASE mip;")
    uri = server.get_uri("mip").replace("postgresql://", "postgresql+psycopg://", 1)
    print(f"PostgreSQL running. Data dir: {DATA_DIR}")
    print(f"DATABASE_URL={uri}")


if __name__ == "__main__":
    main()
