import asyncio
import os
import re
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import BOT_TOKEN, ADMIN_ID, HAPP_PAGE

from database import (
    init_db,
    get_user,
    create_user,
    refresh_user,
    list_users,
    add_days,
    set_blocked,
    delete_user,
    create_promo,
    list_promos,
    use_promo
)

from github_api import (
    get_file_content,
    put_file_verified,
    raw_subscription_url,
    subscription_path
)


NODES_FILE = "nodes.txt"


# ============================================================
# BOT
# ============================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ============================================================
# STATES
# ============================================================

class AdminStates(StatesGroup):
    add_days = State()
    create_promo = State()
    block_user = State()
    unblock_user = State()
    delete_user = State()


class UserStates(StatesGroup):
    promo = State()


# ============================================================
# BASIC HELPERS
# ============================================================

def is_admin(user_id):
    return int(user_id) == int(ADMIN_ID)


def now_unix():
    return int(
        datetime.now(
            timezone.utc
        ).timestamp()
    )


def datetime_to_unix(value):
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(
            str(value)
        )

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=timezone.utc
        )

    return int(
        dt.timestamp()
    )


def format_date(timestamp):
    try:
        dt = datetime.fromtimestamp(
            int(timestamp),
            timezone.utc
        )

        return dt.strftime(
            "%d.%m.%Y"
        )

    except Exception:
        return "Н/Д"


def days_left_from_expire(
    expire_timestamp
):
    try:
        seconds = (
            int(expire_timestamp)
            - now_unix()
        )

        if seconds <= 0:
            return 0

        return int(
            (seconds + 86399)
            // 86400
        )

    except Exception:
        return 0


def safe_username(message):
    if not message.from_user:
        return ""

    return (
        message.from_user.username
        or ""
    )


# ============================================================
# NODES
# ============================================================

def read_nodes():
    if not os.path.exists(
        NODES_FILE
    ):
        return []

    try:
        with open(
            NODES_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            lines = file.read().splitlines()

    except Exception:
        return []

    nodes = []

    for line in lines:
        line = line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        nodes.append(line)

    return nodes


# ============================================================
# GITHUB EXPIRE
# ============================================================

def get_github_expire(
    token
):
    path = subscription_path(
        token
    )

    content = get_file_content(
        path
    )

    if not content:
        return None

    match = re.search(
        r"(?m)^#subscription-userinfo:.*?expire=(\d+)",
        content
    )

    if not match:
        return None

    return int(
        match.group(1)
    )


# ============================================================
# DATABASE EXPIRE SYNC
# ============================================================

def set_database_expire(
    telegram_id,
    expire_timestamp
):
    from database import connect

    dt = datetime.fromtimestamp(
        int(expire_timestamp),
        timezone.utc
    )

    active = int(
        int(expire_timestamp)
        > now_unix()
    )

    conn = connect()

    try:
        conn.execute(
            """
            UPDATE users
            SET expires_at = ?,
                active = ?
            WHERE telegram_id = ?
            """,
            (
                dt.isoformat(),
                active,
                telegram_id
            )
        )

        conn.commit()

    finally:
        conn.close()

    return get_user(
        telegram_id
    )


# ============================================================
# BUILD TOKEN.TXT
# ============================================================

def build_subscription(
    user,
    expire_timestamp
):
    token = user["token"]

    lines = []

    lines.append(
        'id="' + token[:6] + '"'
    )

    lines.append(
        "#profile-title: 🍑 Персик VPN"
    )

    lines.append(
        "#announce: 🆓 Бесплатный VPN | "
        "🇳🇱 Нидерланды • "
        "🇩🇪 Германия • "
        "🇰🇿 Казахстан"
    )

    lines.append(
        "#subscription-userinfo: "
        "upload=0; "
        "download=0; "
        "total=0; "
        "expire="
        + str(int(expire_timestamp))
    )

    lines.append(
        "#profile-update-interval: 1"
    )

    lines.append("")

    nodes = read_nodes()

    for node in nodes:
        lines.append(node)

    lines.append("")

    return "\n".join(
        lines
    )


# ============================================================
# UPDATE GITHUB SUBSCRIPTION
# ============================================================

def update_github_subscription(
    user,
    expire_timestamp
):
    expire_timestamp = int(
        expire_timestamp
    )

    content = build_subscription(
        user,
        expire_timestamp
    )

    path = subscription_path(
        user["token"]
    )

    put_file_verified(
        path,
        content,
        "Update subscription "
        + str(user["telegram_id"])
        + " expire="
        + str(expire_timestamp)
    )

    # Проверяем именно GitHub API.
    github_expire = get_github_expire(
        user["token"]
    )

    if github_expire != expire_timestamp:
        raise RuntimeError(
            "GitHub expire не совпадает.\n"
            "Ожидалось: "
            + str(expire_timestamp)
            + "\n"
            "Получено: "
            + str(github_expire)
        )

    return True


# ============================================================
# EXPIRE SYNC
# ============================================================

def sync_user_from_github(
    user
):
    github_expire = get_github_expire(
        user["token"]
    )

    if github_expire is None:
        return user, None

    db_expire = datetime_to_unix(
        user["expires_at"]
    )

    if github_expire != db_expire:
        user = set_database_expire(
            user["telegram_id"],
            github_expire
        )

    return user, github_expire


# ============================================================
# CREATE/RESTORE SUBSCRIPTION
# ============================================================

def ensure_subscription(
    user
):
    github_expire = get_github_expire(
        user["token"]
    )

    if github_expire is None:
        expire = datetime_to_unix(
            user["expires_at"]
        )

        update_github_subscription(
            user,
            expire
        )

        return user, expire

    return sync_user_from_github(
        user
    )


# ============================================================
# DISABLE SUBSCRIPTION
# ============================================================

def disable_github_subscription(
    user
):
    # ВАЖНО:
    # TOKEN.txt НЕ удаляем.
    # Сохраняем все серверы.
    # Просто ставим expire=1.

    content = build_subscription(
        user,
        1
    )

    path = subscription_path(
        user["token"]
    )

    put_file_verified(
        path,
        content,
        "Disable subscription "
        + str(user["telegram_id"])
    )

    github_expire = get_github_expire(
        user["token"]
    )

    if github_expire != 1:
        raise RuntimeError(
            "GitHub не установил expire=1."
        )

    return True


# ============================================================
# UI
# ============================================================

def main_keyboard(
    user_id
):
    rows = [
        [
            InlineKeyboardButton(
                text="📦 Моя подписка",
                callback_data="subscription"
            )
        ],
        [
            InlineKeyboardButton(
                text="🎟 Промокод",
                callback_data="promo"
            )
        ],
        [
            InlineKeyboardButton(
                text="❓ Помощь",
                callback_data="help"
            )
        ]
    ]

    if is_admin(user_id):
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔐 Админ-панель",
                    callback_data="admin"
                )
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def subscription_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Обновить подписку",
                    callback_data="refresh_subscription"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить подписку",
                    callback_data="delete_subscription"
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data="back"
                )
            ]
        ]
    )


def admin_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👥 Пользователи",
                    callback_data="admin_users"
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ Выдать дни",
                    callback_data="admin_add_days"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎟 Создать промокод",
                    callback_data="admin_create_promo"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 Промокоды",
                    callback_data="admin_promos"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Заблокировать",
                    callback_data="admin_block"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🟢 Разблокировать",
                    callback_data="admin_unblock"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить подписку",
                    callback_data="admin_delete"
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data="back"
                )
            ]
        ]
    )


def back_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data="back"
                )
            ]
        ]
    )


# ============================================================
# TEXT
# ============================================================

def main_text(user):
    if not user:
        return (
            "🍑 ПЕРСИК VPN\n\n"
            "❌ Подписка не найдена."
        )

    expire = datetime_to_unix(
        user["expires_at"]
    )

    if user["blocked"]:
        status = "🔴 Подписка заблокирована"

    elif expire <= now_unix():
        status = "🔴 Подписка истекла"

    else:
        status = "🟢 Подписка: Free"

    return (
        "🍑 ПЕРСИК VPN\n\n"
        + status
        + "\n"
        + "📅 До: "
        + format_date(expire)
        + "\n"
        + "📦 Трафик: Безлимит\n\n"
        + "🔄 Серверы обновляются автоматически\n\n"
        + "👇 Выбери действие:"
    )


def subscription_text(
    user
):
    expire = datetime_to_unix(
        user["expires_at"]
    )

    if user["blocked"]:
        status = "🔴 Заблокирована"

    elif expire <= now_unix():
        status = "🔴 Истекла"

    else:
        status = "🟢 Активна"

    url = user["subscription_url"]

    if not url:
        url = raw_subscription_url(
            user["token"]
        )

    return (
        "📦 МОЯ ПОДПИСКА\n\n"
        + status
        + "\n\n"
        + "📅 До: "
        + format_date(expire)
        + "\n"
        + "⏳ Осталось: "
        + str(
            days_left_from_expire(
                expire
            )
        )
        + " дн.\n"
        + "📦 Трафик: Безлимит\n\n"
        + "🔗 Ссылка для Happ:\n"
        + url
    )


# ============================================================
# /START
# ============================================================

@dp.message(
    CommandStart()
)
async def start(
    message: Message
):
    user_id = message.from_user.id

    user = create_user(
        user_id,
        safe_username(message)
    )

    if not user:
        await message.answer(
            "❌ Не удалось создать пользователя."
        )
        return

    if user["blocked"]:
        await message.answer(
            "🚫 Твоя подписка заблокирована."
        )
        return

    try:
        user, github_expire = (
            ensure_subscription(
                user
            )
        )

    except Exception as error:
        print(
            "GitHub sync error:",
            error
        )

    user = refresh_user(
        user_id
    )

    await message.answer(
        main_text(user),
        reply_markup=main_keyboard(
            user_id
        )
    )


# ============================================================
# BACK
# ============================================================

@dp.callback_query(
    F.data == "back"
)
async def back(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if not user:
        user = create_user(
            callback.from_user.id,
            callback.from_user.username or ""
        )

    try:
        await callback.message.edit_text(
            main_text(user),
            reply_markup=main_keyboard(
                callback.from_user.id
            )
        )

    except Exception as error:
        if "message is not modified" not in str(error).lower():
            raise

    await callback.answer()


# ============================================================
# SUBSCRIPTION
# ============================================================

@dp.callback_query(
    F.data == "subscription"
)
async def subscription(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if not user:
        user = create_user(
            callback.from_user.id,
            callback.from_user.username or ""
        )

    try:
        user, github_expire = (
            ensure_subscription(
                user
            )
        )

    except Exception as error:
        print(
            "Subscription sync error:",
            error
        )

    user = refresh_user(
        callback.from_user.id
    )

    try:
        await callback.message.edit_text(
            subscription_text(user),
            reply_markup=subscription_keyboard()
        )

    except Exception as error:
        if "message is not modified" not in str(error).lower():
            raise

    await callback.answer()


# ============================================================
# REFRESH
# ============================================================

@dp.callback_query(
    F.data == "refresh_subscription"
)
async def refresh_subscription(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if not user:
        await callback.answer(
            "❌ Подписка не найдена.",
            show_alert=True
        )
        return

    try:
        user, github_expire = (
            ensure_subscription(
                user
            )
        )

        if github_expire is None:
            github_expire = datetime_to_unix(
                user["expires_at"]
            )

        update_github_subscription(
            user,
            github_expire
        )

        user = refresh_user(
            callback.from_user.id
        )

        try:
            await callback.message.edit_text(
                subscription_text(user),
                reply_markup=subscription_keyboard()
            )

        except Exception as error:
            if "message is not modified" not in str(error).lower():
                raise

        await callback.answer(
            "✅ Подписка обновлена."
        )

    except Exception as error:
        await callback.answer(
            "❌ Ошибка обновления.",
            show_alert=True
        )

        await callback.message.answer(
            "❌ Ошибка обновления:\n\n"
            + str(error)
        )


# ============================================================
# USER DELETE
# ============================================================

@dp.callback_query(
    F.data == "delete_subscription"
)
async def delete_subscription(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if not user:
        await callback.answer(
            "Подписка уже удалена.",
            show_alert=True
        )
        return

    try:
        # НЕ удаляем TOKEN.txt.
        disable_github_subscription(
            user
        )

        # БД тоже не удаляем.
        # Оставляем пользователя и token,
        # чтобы можно было восстановить подписку.
        user = set_database_expire(
            callback.from_user.id,
            1
        )

        await callback.message.edit_text(
            "🗑 Подписка отключена.\n\n"
            "📦 Серверы сохранены.\n"
            "🔗 Ссылка Happ сохранена.\n"
            "🔴 Подписка отмечена как истёкшая.\n\n"
            "Чтобы вернуть подписку, используй промокод "
            "или попроси администратора выдать дни."
        )

        await callback.answer(
            "✅ Подписка отключена."
        )

    except Exception as error:
        await callback.answer(
            "❌ Ошибка.",
            show_alert=True
        )

        await callback.message.answer(
            "❌ Ошибка отключения:\n\n"
            + str(error)
        )


# ============================================================
# HELP
# ============================================================

@dp.callback_query(
    F.data == "help"
)
async def help_callback(
    callback: CallbackQuery
):
    text = (
        "❓ ПОМОЩЬ\n\n"
        "🍑 Персик VPN работает через персональную "
        "ссылку подписки.\n\n"
        "1. Открой «Моя подписка».\n"
        "2. Скопируй ссылку.\n"
        "3. Добавь её в Happ.\n"
        "4. После изменения подписки нажми "
        "«Обновить подписку».\n\n"
        "🔄 Серверы обновляются автоматически."
    )

    try:
        await callback.message.edit_text(
            text,
            reply_markup=back_keyboard()
        )

    except Exception as error:
        if "message is not modified" not in str(error).lower():
            raise

    await callback.answer()


# ============================================================
# PROMO
# ============================================================

@dp.callback_query(
    F.data == "promo"
)
async def promo_menu(
    callback: CallbackQuery,
    state: FSMContext
):
    await state.set_state(
        UserStates.promo
    )

    await callback.message.edit_text(
        "🎟 ПРОМОКОД\n\n"
        "Отправь промокод одним сообщением.",
        reply_markup=back_keyboard()
    )

    await callback.answer()


@dp.message(
    UserStates.promo
)
async def promo_user(
    message: Message,
    state: FSMContext
):
    user_id = message.from_user.id

    user = get_user(
        user_id
    )

    if not user:
        user = create_user(
            user_id,
            safe_username(message)
        )

    if user["blocked"]:
        await message.answer(
            "🚫 Твоя подписка заблокирована."
        )

        await state.clear()
        return

    code = (
        message.text or ""
    ).strip()

    try:
        success, value = use_promo(
            code,
            user_id
        )

        if not success:
            await message.answer(
                "❌ " + str(value),
                reply_markup=back_keyboard()
            )

            await state.clear()
            return

        promo_days = int(
            value
        )

        # Берём expire из GitHub.
        github_expire = get_github_expire(
            user["token"]
        )

        current = now_unix()

        if github_expire is None:
            github_expire = max(
                current,
                datetime_to_unix(
                    user["expires_at"]
                )
            )

        base_expire = max(
            github_expire,
            current
        )

        new_expire = (
            base_expire
            + promo_days * 86400
        )

        # БД.
        user = set_database_expire(
            user_id,
            new_expire
        )

        # GitHub.
        update_github_subscription(
            user,
            new_expire
        )

        await message.answer(
            "✅ ПРОМОКОД АКТИВИРОВАН\n\n"
            "🎟 Код: "
            + code.upper()
            + "\n"
            + "➕ Добавлено: "
            + str(promo_days)
            + " дн.\n\n"
            + "📅 До: "
            + format_date(new_expire)
            + "\n"
            + "☁️ TOKEN.txt обновлён.",
            reply_markup=main_keyboard(
                user_id
            )
        )

    except Exception as error:
        await message.answer(
            "❌ Ошибка применения промокода:\n\n"
            + str(error)
        )

    await state.clear()


# ============================================================
# ADMIN PANEL
# ============================================================

@dp.callback_query(
    F.data == "admin"
)
async def admin_panel(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )
        return

    await callback.message.edit_text(
        "🔐 АДМИН-ПАНЕЛЬ\n\n"
        "Выбери действие:",
        reply_markup=admin_keyboard()
    )

    await callback.answer()


# ============================================================
# ADMIN USERS
# ============================================================

@dp.callback_query(
    F.data == "admin_users"
)
async def admin_users(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )
        return

    users = list_users()

    if not users:
        text = (
            "👥 ПОЛЬЗОВАТЕЛИ\n\n"
            "Пользователей пока нет."
        )

    else:
        parts = [
            "👥 ПОЛЬЗОВАТЕЛИ",
            ""
        ]

        for user in users:
            expire = datetime_to_unix(
                user["expires_at"]
            )

            username = (
                "@"
                + user["username"]
                if user["username"]
                else "без username"
            )

            if user["blocked"]:
                status = "🚫"

            elif expire > now_unix():
                status = "🟢"

            else:
                status = "🔴"

            parts.append(
                status
                + " "
                + str(user["telegram_id"])
                + " "
                + username
            )

            parts.append(
                "📅 "
                + format_date(expire)
            )

            parts.append("")

        text = "\n".join(
            parts
        )

    await callback.message.edit_text(
        text,
        reply_markup=back_keyboard()
    )

    await callback.answer()


# ============================================================
# ADMIN ADD DAYS
# ============================================================

@dp.callback_query(
    F.data == "admin_add_days"
)
async def admin_add_days_start(
    callback: CallbackQuery,
    state: FSMContext
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )
        return

    await state.set_state(
        AdminStates.add_days
    )

    await callback.message.edit_text(
        "➕ ВЫДАТЬ ДНИ\n\n"
        "Отправь:\n\n"
        "ID ДНИ\n\n"
        "Пример:\n"
        "123456789 30",
        reply_markup=back_keyboard()
    )

    await callback.answer()


@dp.message(
    AdminStates.add_days
)
async def admin_add_days_message(
    message: Message,
    state: FSMContext
):
    if not is_admin(
        message.from_user.id
    ):
        await state.clear()
        return

    parts = (
        message.text or ""
    ).split()

    if len(parts) != 2:
        await message.answer(
            "❌ Формат:\n\n"
            "ID ДНИ\n\n"
            "Пример:\n"
            "123456789 30"
        )
        return

    try:
        target_id = int(
            parts[0]
        )

        days = int(
            parts[1]
        )

    except ValueError:
        await message.answer(
            "❌ ID и дни должны быть числами."
        )
        return

    if days <= 0:
        await message.answer(
            "❌ Дни должны быть больше нуля."
        )
        return

    user = get_user(
        target_id
    )

    if not user:
        await message.answer(
            "❌ Пользователь не найден."
        )

        await state.clear()
        return

    try:
        # ====================================================
        # GITHUB = SOURCE OF TRUTH
        # ====================================================

        github_expire = get_github_expire(
            user["token"]
        )

        current = now_unix()

        if github_expire is None:
            github_expire = datetime_to_unix(
                user["expires_at"]
            )

        old_expire = max(
            github_expire,
            current
        )

        new_expire = (
            old_expire
            + days * 86400
        )

        # Синхронизируем SQLite.
        user = set_database_expire(
            target_id,
            new_expire
        )

        # Записываем новый expire в GitHub.
        update_github_subscription(
            user,
            new_expire
        )

        # Финальная проверка GitHub.
        github_after = get_github_expire(
            user["token"]
        )

        if github_after != new_expire:
            raise RuntimeError(
                "GitHub проверка не пройдена.\n\n"
                "Ожидалось:\n"
                + str(new_expire)
                + "\n\n"
                "Получено:\n"
                + str(github_after)
            )

        await message.answer(
            "✅ ДНИ ВЫДАНЫ\n\n"
            "👤 ID: "
            + str(target_id)
            + "\n"
            "➕ Добавлено: "
            + str(days)
            + " дн.\n\n"
            "Было expire:\n"
            + str(old_expire)
            + "\n\n"
            "Стало expire:\n"
            + str(new_expire)
            + "\n\n"
            "📅 До: "
            + format_date(new_expire)
            + "\n\n"
            "☁️ TOKEN.txt обновлён.\n"
            "🔎 GitHub проверен."
        )

    except Exception as error:
        await message.answer(
            "❌ Ошибка выдачи дней:\n\n"
            + str(error)
        )

    await state.clear()


# ============================================================
# ADMIN PROMO CREATE
# ============================================================

@dp.callback_query(
    F.data == "admin_create_promo"
)
async def admin_create_promo_start(
    callback: CallbackQuery,
    state: FSMContext
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )
        return

    await state.set_state(
        AdminStates.create_promo
    )

    await callback.message.edit_text(
        "🎟 СОЗДАНИЕ ПРОМОКОДА\n\n"
        "Формат:\n\n"
        "КОД ДНИ КОЛИЧЕСТВО\n\n"
        "Пример:\n"
        "666M 30 10",
        reply_markup=back_keyboard()
    )

    await callback.answer()


@dp.message(
    AdminStates.create_promo
)
async def admin_create_promo_message(
    message: Message,
    state: FSMContext
):
    if not is_admin(
        message.from_user.id
    ):
        await state.clear()
        return

    parts = (
        message.text or ""
    ).split()

    if len(parts) != 3:
        await message.answer(
            "❌ Формат:\n\n"
            "КОД ДНИ КОЛИЧЕСТВО\n\n"
            "Пример:\n"
            "666M 30 10"
        )
        return

    code = parts[0]

    try:
        days = int(
            parts[1]
        )

        max_uses = int(
            parts[2]
        )

    except ValueError:
        await message.answer(
            "❌ Дни и количество должны быть числами."
        )
        return

    if days <= 0:
        await message.answer(
            "❌ Дни должны быть больше нуля."
        )
        return

    if max_uses <= 0:
        await message.answer(
            "❌ Количество использований должно быть больше нуля."
        )
        return

    try:
        create_promo(
            code,
            days,
            max_uses
        )

        await message.answer(
            "✅ ПРОМОКОД СОЗДАН\n\n"
            "🎟 Код: "
            + code.upper()
            + "\n"
            "📅 Дней: "
            + str(days)
            + "\n"
            "👥 Использований: "
            + str(max_uses)
        )

    except Exception as error:
        await message.answer(
            "❌ Ошибка создания промокода:\n\n"
            + str(error)
        )

    await state.clear()


# ============================================================
# ADMIN PROMOS
# ============================================================

@dp.callback_query(
    F.data == "admin_promos"
)
async def admin_promos(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )
        return

    promos = list_promos()

    if not promos:
        text = (
            "📋 ПРОМОКОДЫ\n\n"
            "Промокодов пока нет."
        )

    else:
        parts = [
            "📋 ПРОМОКОДЫ",
            ""
        ]

        for promo in promos:
            parts.append(
                "🎟 "
                + promo["code"]
            )

            parts.append(
                "📅 "
                + str(promo["days"])
                + " дн."
            )

            parts.append(
                "👥 "
                + str(promo["uses"])
                + "/"
                + str(promo["max_uses"])
            )

            parts.append("")

        text = "\n".join(
            parts
        )

    await callback.message.edit_text(
        text,
        reply_markup=back_keyboard()
    )

    await callback.answer()


# ============================================================
# ADMIN BLOCK
# ============================================================

@dp.callback_query(
    F.data == "admin_block"
)
async def admin_block_start(
    callback: CallbackQuery,
    state: FSMContext
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )
        return

    await state.set_state(
        AdminStates.block_user
    )

    await callback.message.edit_text(
        "🚫 БЛОКИРОВКА\n\n"
        "Отправь Telegram ID пользователя.",
        reply_markup=back_keyboard()
    )

    await callback.answer()


@dp.message(
    AdminStates.block_user
)
async def admin_block_message(
    message: Message,
    state: FSMContext
):
    if not is_admin(
        message.from_user.id
    ):
        await state.clear()
        return

    try:
        target_id = int(
            message.text.strip()
        )

    except ValueError:
        await message.answer(
            "❌ ID должен быть числом."
        )
        return

    user = get_user(
        target_id
    )

    if not user:
        await message.answer(
            "❌ Пользователь не найден."
        )

        await state.clear()
        return

    try:
        user = set_blocked(
            target_id,
            True
        )

        # Серверы сохраняются.
        # Просто expire=1.
        disable_github_subscription(
            user
        )

        await message.answer(
            "🚫 Пользователь заблокирован.\n\n"
            "👤 ID: "
            + str(target_id)
            + "\n"
            "📦 Серверы сохранены.\n"
            "☁️ expire=1 установлен."
        )

    except Exception as error:
        await message.answer(
            "❌ Ошибка блокировки:\n\n"
            + str(error)
        )

    await state.clear()


# ============================================================
# ADMIN UNBLOCK
# ============================================================

@dp.callback_query(
    F.data == "admin_unblock"
)
async def admin_unblock_start(
    callback: CallbackQuery,
    state: FSMContext
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )
        return

    await state.set_state(
        AdminStates.unblock_user
    )

    await callback.message.edit_text(
        "🟢 РАЗБЛОКИРОВКА\n\n"
        "Отправь Telegram ID пользователя.",
        reply_markup=back_keyboard()
    )

    await callback.answer()


@dp.message(
    AdminStates.unblock_user
)
async def admin_unblock_message(
    message: Message,
    state: FSMContext
):
    if not is_admin(
        message.from_user.id
    ):
        await state.clear()
        return

    try:
        target_id = int(
            message.text.strip()
        )

    except ValueError:
        await message.answer(
            "❌ ID должен быть числом."
        )
        return

    user = get_user(
        target_id
    )

    if not user:
        await message.answer(
            "❌ Пользователь не найден."
        )

        await state.clear()
        return

    try:
        user = set_blocked(
            target_id,
            False
        )

        github_expire = get_github_expire(
            user["token"]
        )

        if github_expire is None:
            github_expire = datetime_to_unix(
                user["expires_at"]
            )

        if github_expire <= now_unix():
            await message.answer(
                "🟢 Пользователь разблокирован.\n\n"
                "Но подписка истекла.\n"
                "Выдай дни через «➕ Выдать дни»."
            )

        else:
            user = set_database_expire(
                target_id,
                github_expire
            )

            update_github_subscription(
                user,
                github_expire
            )

            await message.answer(
                "🟢 Пользователь разблокирован.\n\n"
                "👤 ID: "
                + str(target_id)
                + "\n"
                "📅 До: "
                + format_date(github_expire)
            )

    except Exception as error:
        await message.answer(
            "❌ Ошибка разблокировки:\n\n"
            + str(error)
        )

    await state.clear()


# ============================================================
# ADMIN DELETE
# ============================================================

@dp.callback_query(
    F.data == "admin_delete"
)
async def admin_delete_start(
    callback: CallbackQuery,
    state: FSMContext
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )
        return

    await state.set_state(
        AdminStates.delete_user
    )

    await callback.message.edit_text(
        "🗑 УДАЛЕНИЕ ПОДПИСКИ\n\n"
        "Отправь Telegram ID пользователя.\n\n"
        "TOKEN.txt и серверы сохранятся.",
        reply_markup=back_keyboard()
    )

    await callback.answer()


@dp.message(
    AdminStates.delete_user
)
async def admin_delete_message(
    message: Message,
    state: FSMContext
):
    if not is_admin(
        message.from_user.id
    ):
        await state.clear()
        return

    try:
        target_id = int(
            message.text.strip()
        )

    except ValueError:
        await message.answer(
            "❌ ID должен быть числом."
        )
        return

    user = get_user(
        target_id
    )

    if not user:
        await message.answer(
            "❌ Пользователь не найден."
        )

        await state.clear()
        return

    try:
        # ====================================================
        # ГЛАВНОЕ:
        # НЕ удаляем TOKEN.txt.
        # НЕ удаляем пользователя из БД.
        # НЕ удаляем серверы.
        #
        # Просто делаем подписку истёкшей.
        # ====================================================

        disable_github_subscription(
            user
        )

        user = set_database_expire(
            target_id,
            1
        )

        await message.answer(
            "🗑 ПОДПИСКА ОТКЛЮЧЕНА\n\n"
            "👤 ID: "
            + str(target_id)
            + "\n\n"
            "📦 Серверы сохранены.\n"
            "🔗 TOKEN.txt сохранён.\n"
            "🔴 expire=1.\n\n"
            "Пользователю можно снова выдать дни."
        )

    except Exception as error:
        await message.answer(
            "❌ Ошибка отключения:\n\n"
            + str(error)
        )

    await state.clear()


# ============================================================
# /HELP
# ============================================================

@dp.message(
    Command("help")
)
async def command_help(
    message: Message
):
    await message.answer(
        "❓ Используй кнопку «❓ Помощь»."
    )


# ============================================================
# ERROR HANDLER
# ============================================================

@dp.errors()
async def errors_handler(
    event
):
    try:
        error = event.exception

        if (
            "message is not modified"
            in str(error).lower()
        ):
            return True

        print(
            "BOT ERROR:",
            repr(error)
        )

    except Exception:
        pass

    return True


# ============================================================
# MAIN
# ============================================================

async def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN не задан."
        )

    init_db()

    print(
        "🍑 Персик VPN Bot 2.0 запущен."
    )

    print(
        "GitHub synchronization: ON"
    )

    print(
        "GitHub is source of expire: ON"
    )

    print(
        "Subscription files are preserved: ON"
    )

    await dp.start_polling(
        bot
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    try:
        asyncio.run(
            main()
        )

    except KeyboardInterrupt:
        print(
            "Бот остановлен."
)
