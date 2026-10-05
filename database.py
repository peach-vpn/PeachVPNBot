import secrets
import sqlite3
from datetime import datetime, timezone, timedelta

from config import (
    DATABASE_FILE,
    EXPIRE_DAYS,
)


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
            total_bytes INTEGER NOT NULL DEFAULT 0,
            expires_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            blocked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS promo_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            promo_type TEXT NOT NULL DEFAULT 'Free',
            days INTEGER NOT NULL,
            max_uses INTEGER NOT NULL,
            uses INTEGER NOT NULL DEFAULT 0,
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
        "blocked",
        "INTEGER NOT NULL DEFAULT 0"
    )

    add_column_if_missing(
        "promo_codes",
        "promo_type",
        "TEXT NOT NULL DEFAULT 'Free'"
    )


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


def create_user(
    telegram_id,
    username=None
):
    user = get_user(
        telegram_id
    )

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

        return get_user(
            telegram_id
        )

    now = datetime.now(
        timezone.utc
    )

    expires = (
        now
        + timedelta(
            days=EXPIRE_DAYS
        )
    )

    token = secrets.token_urlsafe(
        24
    )

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
            created_at
        )
        VALUES (?, ?, ?, ?, 0, ?, 1, 0, ?)
        """,
        (
            telegram_id,
            username or "",
            token,
            None,
            expires.isoformat(),
            now.isoformat()
        )
    )

    conn.commit()
    conn.close()

    return get_user(
        telegram_id
    )


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


def refresh_user(telegram_id):
    user = get_user(
        telegram_id
    )

    if not user:
        return None

    try:
        expires = datetime.fromisoformat(
            user["expires_at"]
        )

        if expires.tzinfo is None:
            expires = expires.replace(
                tzinfo=timezone.utc
            )

        now = datetime.now(
            timezone.utc
        )

        active = int(
            expires > now
            and not user["blocked"]
        )

        conn = connect()

        conn.execute(
            """
            UPDATE users
            SET active = ?
            WHERE telegram_id = ?
            """,
            (
                active,
                telegram_id
            )
        )

        conn.commit()
        conn.close()

    except Exception:
        pass

    return get_user(
        telegram_id
    )


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
            subscription_url
        FROM users
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    return users


def add_days(
    telegram_id,
    days
):
    user = get_user(
        telegram_id
    )

    if not user:
        return None

    now = datetime.now(
        timezone.utc
    )

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

    new_expires = (
        expires
        + timedelta(
            days=days
        )
    )

    conn = connect()

    conn.execute(
        """
        UPDATE users
        SET expires_at = ?,
            active = 1,
            blocked = 0
        WHERE telegram_id = ?
        """,
        (
            new_expires.isoformat(),
            telegram_id
        )
    )

    conn.commit()
    conn.close()

    return get_user(
        telegram_id
    )


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


def delete_user(
    telegram_id
):
    conn = connect()

    conn.execute(
        """
        DELETE FROM promo_uses
        WHERE telegram_id = ?
        """,
        (telegram_id,)
    )

    conn.execute(
        """
        DELETE FROM users
        WHERE telegram_id = ?
        """,
        (telegram_id,)
    )

    conn.commit()
    conn.close()


def create_promo(
    code,
    days,
    max_uses
):
    code = code.strip().upper()

    now = datetime.now(
        timezone.utc
    )

    conn = connect()

    existing = conn.execute(
        """
        SELECT id
        FROM promo_codes
        WHERE code = ?
        """,
        (code,)
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE promo_codes
            SET days = ?,
                max_uses = ?
            WHERE code = ?
            """,
            (
                days,
                max_uses,
                code
            )
        )
    else:
        conn.execute(
            """
            INSERT INTO promo_codes (
                code,
                promo_type,
                days,
                max_uses,
                uses,
                created_at
            )
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (
                code,
                "Free",
                days,
                max_uses,
                now.isoformat()
            )
        )

    conn.commit()
    conn.close()


def list_promos():
    conn = connect()

    promos = conn.execute(
        """
        SELECT *
        FROM promo_codes
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    return promos


def use_promo(
    code,
    telegram_id
):
    code = code.strip().upper()

    conn = connect()

    try:
        conn.execute(
            "BEGIN IMMEDIATE"
        )

        promo = conn.execute(
            """
            SELECT *
            FROM promo_codes
            WHERE code = ?
            """,
            (code,)
        ).fetchone()

        if not promo:
            conn.rollback()
            return False, "Промокод не найден."

        if promo["uses"] >= promo["max_uses"]:
            conn.rollback()
            return False, (
                "Лимит использований "
                "промокода исчерпан."
            )

        used = conn.execute(
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

        if used:
            conn.rollback()
            return False, (
                "Ты уже использовал "
                "этот промокод."
            )

        now = datetime.now(
            timezone.utc
        )

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

        conn.commit()

        return True, promo["days"]

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()
