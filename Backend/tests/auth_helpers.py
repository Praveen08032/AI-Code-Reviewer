from datetime import datetime, timezone
from types import SimpleNamespace
from app.models import User


def add_test_user(session_factory):
    stamp = datetime.now(timezone.utc).replace(tzinfo=None)
    fields = dict(id="test-user", google_sub="test-google-sub", email="test@example.com",
                  name="Test User", picture=None, first_login_at=stamp, last_login_at=stamp,
                  last_seen_at=stamp, login_count=1)
    with session_factory() as db:
        db.add(User(**fields))
        db.commit()
    return SimpleNamespace(**fields)
