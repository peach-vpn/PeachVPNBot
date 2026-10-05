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

    conn.execute(
        "PRAGMA busy_timeout = 60000"
    )

    conn.execute(
        "PRAGMA journal_mode = WAL"
    )

    conn.execute(
        "PRAGMA foreign_keys = ON"
    )

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
            issue_count INTEGER NOT NULL DEFAULT 0,
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
        "issue_count",
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

    names = [
        row["name"]
        for row in columns
    ]

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

    # Уже Unix timestamp
    try:
        return int(float(value))
    except ValueError:
        pass

    # Старый ISO-формат:
    # 2029-07-30T16:46:46.447591+00:00
    try:
        dt = datetime.fromisoformat(value)

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return int(
            dt.timestamp()
        )

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

        new_value = convert_expire(
            old_value
        )

        # Обновляем только если значение
        # действительно отличается.
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

    # Дополнительная защита:
    # если старая дата ещё осталась —
    # конвертируем её прямо при чтении.
    value = user["expires_at"]
    converted = convert_expire(value)

    if str(value) != str(converted):
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

        user = get_user(telegram_id)

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
            issue_count,
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
    telegram_id,
    days
):
    user = get_user(
        telegram_id
    )

    if not user:
        return None

    now = int(
        datetime.now(
            timezone.utc
        ).timestamp()
    )

    new_expire = (
        now
        + days * 24 * 60 * 60
    )

    new_count = (
        int(user["issue_count"])
        + 1
    )

    conn = connect()

    conn.execute(
        """
        UPDATE users
        SET expires_at = ?,
            issue_count = ?,
            active = 1
        WHERE telegram_id = ?
        """,
        (
            new_expire,
            new_count,
            telegram_id
        )
    )

    conn.commit()
    conn.close()

    return get_user(
        telegram_id
    )


def deactivate_expired():
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
        WHERE expires_at > 0
        AND expires_at <= ?
        AND blocked = 0
        """,
        (now,)
    )

    conn.commit()
    conn.close()


def can_get_subscription(
    telegram_id
):
    user = get_user(
        telegram_id
    )

    if not user:
        return False

    if int(user["blocked"]) == 1:
        return False

    count = int(
        user["issue_count"]
    )

    if count >= 3:
        return False

    now = int(
        datetime.now(
            timezone.utc
        ).timestamp()
    )

    expires = convert_expire(
        user["expires_at"]
    )

    # Пока подписка активна —
    # следующую выдавать нельзя.
    if expires > now:
        return False

    return True


def next_issue_days(
    telegram_id
):
    user = get_user(
        telegram_id
    )

    if not user:
        return None

    count = int(
        user["issue_count"]
    )

    if count == 0:
        return 30

    if count == 1:
        return 15

    if count == 2:
        return 7

    return None


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

    return get_user(
        telegram_id
    )


def list_users():
    deactivate_expired()

    conn = connect()

    users = conn.execute(
        """
        SELECT
            telegram_id,
            username,
            token,
            subscription_url,
            expires_at,
            issue_count,
            active,
            blocked,
            created_at
        FROM users
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    return users
