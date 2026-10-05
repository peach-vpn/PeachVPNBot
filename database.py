import secrets
import sqlite3
from datetime import datetime, timezone

from config import DATABASE_FILE


def connect():
    conn = sqlite3.connect(
        DATABASE_FILE,
        timeout=60,
        isolation_level=None
    )

    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA busy_timeout = 60000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def init_db():
    conn = connect()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            token TEXT UNIQUE NOT NULL,
            subscription_url TEXT,
            expires_at INTEGER NOT NULL DEFAULT 0,
            issued INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 0,
            blocked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

    add_column_if_missing(
        "users",
        "subscription_url",
        "TEXT"
    )

    add_column_if_missing(
        "users",
        "expires_at",
        "INTEGER NOT NULL DEFAULT 0"
    )

    add_column_if_missing(
        "users",
        "issued",
        "INTEGER NOT NULL DEFAULT 0"
    )

    add_column_if_missing(
        "users",
        "active",
        "INTEGER NOT NULL DEFAULT 0"
    )

    add_column_if_missing(
        "users",
        "blocked",
        "INTEGER NOT NULL DEFAULT 0"
    )

    migrate_old_dates()


def add_column_if_missing(
    table,
    column,
    definition
):
    conn = connect()

    columns = conn.execute(
        "PRAGMA table_info(" + table + ")"
    ).fetchall()

    names = [row["name"] for row in columns]

    if column not in names:
        conn.execute(
            "ALTER TABLE "
            + table
            + " ADD COLUMN "
            + column
            + " "
            + definition
        )

    conn.commit()
    conn.close()


def convert_expire(value):
    if value is None:
        return 0

    value = str(value).strip()

    if not value:
        return 0

    try:
        return int(float(value))
    except ValueError:
        pass

    try:
        dt = datetime.fromisoformat(value)

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return int(dt.timestamp())

    except Exception:
        return 0


def migrate_old_dates():
    conn = connect()

    rows = conn.execute(
        """
        SELECT telegram_id, expires_at
        FROM users
        """
    ).fetchall()

    for row in rows:
        old_value = row["expires_at"]
        new_value = convert_expire(old_value)

        if str(old_value) != str(new_value):
            conn.execute(
                """
                UPDATE users
                SET expires_at = ?
                WHERE telegram_id = ?
                """,
                (
                    new_value,
                    row["telegram_id"]
                )
            )

    conn.commit()
    conn.close()


def get_user(telegram_id):
    conn = connect()

    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE telegram_id = ?
        """,
        (telegram_id,)
    ).fetchone()

    conn.close()

    if not user:
        return None

    converted = convert_expire(
        user["expires_at"]
    )

    if str(user["expires_at"]) != str(converted):
        conn = connect()

        conn.execute(
            """
            UPDATE users
            SET expires_at = ?
            WHERE telegram_id = ?
            """,
            (
                converted,
                telegram_id
            )
        )

        conn.commit()
        conn.close()

        return get_user(telegram_id)

    return user


def create_user(
    telegram_id,
    username=None
):
    user = get_user(telegram_id)

    if user:
        if (
            username is not None
            and user["username"] != username
        ):
            conn = connect()

            conn.execute(
                """
                UPDATE users
                SET username = ?
                WHERE telegram_id = ?
                """,
                (
                    username,
                    telegram_id
                )
            )

            conn.commit()
            conn.close()

        return get_user(telegram_id)

    now = datetime.now(
        timezone.utc
    )

    token = secrets.token_urlsafe(24)

    conn = connect()

    conn.execute(
        """
        INSERT INTO users (
            telegram_id,
            username,
            token,
            subscription_url,
            expires_at,
            issued,
            active,
            blocked,
            created_at
        )
        VALUES (
            ?, ?, ?, NULL,
            0, 0, 0, 0, ?
        )
        """,
        (
            telegram_id,
            username or "",
            token,
            now.isoformat()
        )
    )

    conn.commit()
    conn.close()

    return get_user(telegram_id)


def save_subscription_url(
    telegram_id,
    url
):
    conn = connect()

    conn.execute(
        """
        UPDATE users
        SET subscription_url = ?
        WHERE telegram_id = ?
        """,
        (
            url,
            telegram_id
        )
    )

    conn.commit()
    conn.close()


def activate_subscription(
    telegram_id
):
    user = get_user(telegram_id)

    if not user:
        return None

    # Повторную бесплатную выдачу не разрешаем.
    if int(user["issued"]) == 1:
        return user

    now = int(
        datetime.now(
            timezone.utc
        ).timestamp()
    )

    expires_at = (
        now
        + 30 * 24 * 60 * 60
    )

    conn = connect()

    conn.execute(
        """
        UPDATE users
        SET expires_at = ?,
            issued = 1,
            active = 1
        WHERE telegram_id = ?
        """,
        (
            expires_at,
            telegram_id
        )
    )

    conn.commit()
    conn.close()

    return get_user(telegram_id)


def is_subscription_active(
    telegram_id
):
    user = get_user(telegram_id)

    if not user:
        return False

    if int(user["blocked"]) == 1:
        return False

    if int(user["issued"]) == 0:
        return False

    now = int(
        datetime.now(
            timezone.utc
        ).timestamp()
    )

    expires = int(
        user["expires_at"]
    )

    return expires > now


def expire_old_subscriptions():
    now = int(
        datetime.now(
            timezone.utc
        ).timestamp()
    )

    conn = connect()

    conn.execute(
        """
        UPDATE users
        SET active = 0
        WHERE issued = 1
        AND expires_at > 0
        AND expires_at <= ?
        AND active = 1
        """,
        (now,)
    )

    conn.commit()
    conn.close()


def set_blocked(
    telegram_id,
    blocked
):
    conn = connect()

    conn.execute(
        """
        UPDATE users
        SET blocked = ?,
            active = ?
        WHERE telegram_id = ?
        """,
        (
            int(blocked),
            0 if blocked else 1,
            telegram_id
        )
    )

    conn.commit()
    conn.close()

    return get_user(telegram_id)


def list_users():
    expire_old_subscriptions()

    conn = connect()

    users = conn.execute(
        """
        SELECT
            telegram_id,
            username,
            token,
            subscription_url,
            expires_at,
            issued,
            active,
            blocked,
            created_at
        FROM users
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    return users
