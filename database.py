import secrets
import sqlite3
from datetime import datetime, timezone, timedelta

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
            total_bytes INTEGER NOT NULL DEFAULT 0,
            expires_at TEXT NOT NULL DEFAULT '0',
            active INTEGER NOT NULL DEFAULT 1,
            blocked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            tariff TEXT NOT NULL DEFAULT 'Free'
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS promo_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            tariff TEXT NOT NULL DEFAULT 'Free',
            days INTEGER NOT NULL,
            max_uses INTEGER NOT NULL,
            uses INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS promo_uses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            promo_id INTEGER NOT NULL,
            telegram_id INTEGER NOT NULL,
            used_at TEXT NOT NULL,
            UNIQUE(promo_id, telegram_id)
        )
    """)

    conn.commit()
    conn.close()

    add_column_if_missing(
        "users",
        "tariff",
        "TEXT NOT NULL DEFAULT 'Free'"
    )

    add_column_if_missing(
        "promo_codes",
        "active",
        "INTEGER NOT NULL DEFAULT 1"
    )


def add_column_if_missing(table, column, definition):
    conn = connect()

    columns = conn.execute(
        "PRAGMA table_info(" + table + ")"
    ).fetchall()

    names = [row["name"] for row in columns]

    if column not in names:
        conn.execute(
            "ALTER TABLE " + table +
            " ADD COLUMN " + column +
            " " + definition
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
    return user


def create_user(telegram_id, username=None):
    user = get_user(telegram_id)

    if user:
        if username is not None and user["username"] != username:
            conn = connect()

            conn.execute(
                """
                UPDATE users
                SET username = ?
                WHERE telegram_id = ?
                """,
                (username, telegram_id)
            )

            conn.commit()
            conn.close()

        return get_user(telegram_id)

    now = datetime.now(timezone.utc)

    token = secrets.token_urlsafe(24)

    expires = now + timedelta(days=30)

    conn = connect()

    conn.execute(
        """
        INSERT INTO users (
            telegram_id,
            username,
            token,
            subscription_url,
            total_bytes,
            expires_at,
            active,
            blocked,
            created_at,
            tariff
        )
        VALUES (
            ?, ?, ?, NULL, 0, ?, 1, 0, ?, 'Free'
        )
        """,
        (
            telegram_id,
            username or "",
            token,
            expires.isoformat(),
            now.isoformat()
        )
    )

    conn.commit()
    conn.close()

    return get_user(telegram_id)


def set_tariff(telegram_id, tariff):
    if tariff not in ("Free", "PRO"):
        return None

    conn = connect()

    conn.execute(
        """
        UPDATE users
        SET tariff = ?
        WHERE telegram_id = ?
        """,
        (tariff, telegram_id)
    )

    conn.commit()
    conn.close()

    return get_user(telegram_id)


def add_days(telegram_id, days):
    user = get_user(telegram_id)

    if not user:
        return None

    now = datetime.now(timezone.utc)

    try:
        expires = datetime.fromisoformat(
            user["expires_at"]
        )

        if expires.tzinfo is None:
            expires = expires.replace(
                tzinfo=timezone.utc
            )

    except Exception:
        expires = now

    if expires < now:
        expires = now

    expires = expires + timedelta(days=days)

    conn = connect()

    conn.execute(
        """
        UPDATE users
        SET expires_at = ?,
            active = 1
        WHERE telegram_id = ?
        """,
        (
            expires.isoformat(),
            telegram_id
        )
    )

    conn.commit()
    conn.close()

    return get_user(telegram_id)


def set_blocked(telegram_id, blocked):
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


def create_promo(code, tariff, days, max_uses):
    if tariff not in ("Free", "PRO"):
        return None

    now = datetime.now(timezone.utc)

    conn = connect()

    try:
        conn.execute(
            """
            INSERT INTO promo_codes (
                code,
                tariff,
                days,
                max_uses,
                uses,
                active,
                created_at
            )
            VALUES (?, ?, ?, ?, 0, 1, ?)
            """,
            (
                code.upper(),
                tariff,
                days,
                max_uses,
                now.isoformat()
            )
        )

        conn.commit()

    except sqlite3.IntegrityError:
        conn.close()
        return None

    conn.close()

    return get_promo(code)


def get_promo(code):
    conn = connect()

    promo = conn.execute(
        """
        SELECT *
        FROM promo_codes
        WHERE code = ?
        """,
        (code.upper(),)
    ).fetchone()

    conn.close()
    return promo


def use_promo(telegram_id, code):
    conn = connect()

    promo = conn.execute(
        """
        SELECT *
        FROM promo_codes
        WHERE code = ?
        """,
        (code.upper(),)
    ).fetchone()

    if not promo:
        conn.close()
        return None, "not_found"

    if not promo["active"]:
        conn.close()
        return None, "disabled"

    if promo["uses"] >= promo["max_uses"]:
        conn.execute(
            """
            UPDATE promo_codes
            SET active = 0
            WHERE id = ?
            """,
            (promo["id"],)
        )

        conn.commit()
        conn.close()

        return None, "limit"

    already = conn.execute(
        """
        SELECT id
        FROM promo_uses
        WHERE promo_id = ?
          AND telegram_id = ?
        """,
        (
            promo["id"],
            telegram_id
        )
    ).fetchone()

    if already:
        conn.close()
        return None, "already_used"

    now = datetime.now(timezone.utc)

    conn.execute(
        """
        INSERT INTO promo_uses (
            promo_id,
            telegram_id,
            used_at
        )
        VALUES (?, ?, ?)
        """,
        (
            promo["id"],
            telegram_id,
            now.isoformat()
        )
    )

    conn.execute(
        """
        UPDATE promo_codes
        SET uses = uses + 1
        WHERE id = ?
        """,
        (promo["id"],)
    )

    if promo["uses"] + 1 >= promo["max_uses"]:
        conn.execute(
            """
            UPDATE promo_codes
            SET active = 0
            WHERE id = ?
            """,
            (promo["id"],)
        )

    conn.commit()
    conn.close()

    user = get_user(telegram_id)

    if not user:
        user = create_user(
            telegram_id
        )

    user = set_tariff(
        telegram_id,
        promo["tariff"]
    )

    user = add_days(
        telegram_id,
        promo["days"]
    )

    return user, "ok"


def list_users():
    conn = connect()

    users = conn.execute(
        """
        SELECT
            telegram_id,
            username,
            expires_at,
            active,
            blocked,
            subscription_url,
            tariff
        FROM users
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    return users


def list_promos():
    conn = connect()

    promos = conn.execute(
        """
        SELECT
            code,
            tariff,
            days,
            max_uses,
            uses,
            active,
            created_at
        FROM promo_codes
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    return promos
