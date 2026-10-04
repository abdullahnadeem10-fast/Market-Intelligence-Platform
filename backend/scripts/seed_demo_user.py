"""Create a local demo account (development only).

Usage:  python scripts/seed_demo_user.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services.bootstrap import init_db  # noqa: E402

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "DemoPass123"


def main() -> None:
    init_db()
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == DEMO_EMAIL)):
            print(f"Demo user already exists: {DEMO_EMAIL}")
            return
        db.add(User(email=DEMO_EMAIL, full_name="Demo User", password_hash=hash_password(DEMO_PASSWORD)))
        db.commit()
        print(f"Created demo user {DEMO_EMAIL} (password in scripts/seed_demo_user.py)")


if __name__ == "__main__":
    main()
