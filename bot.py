import asyncio
import base64
import os
import re
import time
from datetime import datetime, timezone, timedelta

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

from config import (
    BOT_TOKEN,
    ADMIN_ID,
    HAPP_PAGE
)

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
    delete_file,
    raw_subscription_url,
    subscription_path
)


NODES_FILE = "nodes.txt"


# ============================================================
# BOT
# ============================================================

bot = Bot(
    token=BOT_TOKEN
)

dp = Dispatcher()


# ============================================================
# ADMIN STATES
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
# HELPERS
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


def unix_to_datetime(timestamp):
    return datetime.fromtimestamp(
        int(timestamp),
        tz=timezone.utc
    )


def format_date(timestamp):
    try:
        dt = unix_to_datetime(
            timestamp
        )

        return dt.strftime(
            "%d.%m.%Y"
        )

    except Exception:
        return "Н/Д"


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

    result = []

    for line in lines:
        line = line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        result.append(line)

    return result


def get_subscription_expire_from_github(
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


def replace_expire(
    content,
    expire_timestamp
):
    new_line = (
        "#subscription-userinfo: "
        "upload=0; "
        "download=0; "
        "total=0; "
        "expire="
        + str(expire_timestamp)
    )

    pattern = (
        r"(?m)^#subscription-userinfo:.*$"
    )

    if re.search(
        pattern,
        content
    ):
        return re.sub(
            pattern,
            new_line,
            content,
            count=1
        )

    lines = content.splitlines()

    insert_at = 0

    for index, line in enumerate(lines):
        if line.startswith(
            "#announce:"
        ):
            insert_at = index + 1
            break

    lines.insert(
        insert_at,
        new_line
    )

    return "\n".join(
        lines
    ) + "\n"


def set_user_expire_in_database(
    telegram_id,
    expire_timestamp
):
    from database import connect

    expires = unix_to_datetime(
        expire_timestamp
    )

    now = datetime.now(
        timezone.utc
    )

    active = int(
        expire_timestamp > int(
            now.timestamp()
        )
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
                expires.isoformat(),
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


def build_subscription(
    user,
    expire_timestamp=None
):
    token = user["token"]

    if expire_timestamp is None:
        expire_timestamp = datetime_to_unix(
            user["expires_at"]
        )

    nodes = read_nodes()

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
        + str(expire_timestamp)
    )

    lines.append(
        "#profile-update-interval: 1"
    )

    lines.append("")

    for node in nodes:
        lines.append(node)

    lines.append("")

    return "\n".join(
        lines
    )


def update_github_subscription(
    user,
    expire_timestamp=None
):
    if expire_timestamp is None:
        expire_timestamp = datetime_to_unix(
            user["expires_at"]
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

    github_expire = (
        get_subscription_expire_from_github(
            user["token"]
        )
    )

    if github_expire != expire_timestamp:
        raise RuntimeError(
            "GitHub expire не совпадает.\n"
            "Ожидалось: "
            + str(expire_timestamp)
            + "\n"
            "GitHub: "
            + str(github_expire)
        )

    return True


def invalidate_github_subscription(
    user
):
    path = subscription_path(
        user["token"]
    )

    content = build_subscription(
        user,
        1
    )

    put_file_verified(
        path,
        content,
        "Disable subscription "
        + str(user["telegram_id"])
    )

    return True


def delete_github_subscription(
    user
):
    path = subscription_path(
        user["token"]
    )

    delete_file(
        path,
        "Delete subscription "
        + str(user["telegram_id"])
    )


def safe_username(
    message
):
    if not message.from_user:
        return ""

    return (
        message.from_user.username
        or ""
    )


def days_left(
    user
):
    try:
        expire = datetime.fromisoformat(
            user["expires_at"]
        )

        if expire.tzinfo is None:
            expire = expire.replace(
                tzinfo=timezone.utc
            )

        seconds = (
            expire
            - datetime.now(
                timezone.utc
            )
        ).total_seconds()

        if seconds <= 0:
            return 0

        return int(
            (seconds + 86399)
            // 86400
        )

    except Exception:
        return 0


# ============================================================
# KEYBOARDS
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
    if user is None:
        return (
            "🍑 ПЕРСИК VPN\n\n"
            "❌ Подписка не найдена."
        )

    expire = datetime_to_unix(
        user["expires_at"]
    )

    if user["blocked"]:
        status = "🔴 Заблокирована"
    elif expire <= now_unix():
        status = "🔴 Истекла"
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
        + str(days_left(user))
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

    user = refresh_user(
        user_id
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

    url = raw_subscription_url(
        user["token"]
    )

    if not user["subscription_url"]:
        from database import save_subscription_url

        save_subscription_url(
            user_id,
            url
        )

        user = get_user(
            user_id
        )

    # Не перезаписываем существующий GitHub-файл
    # при каждом /start.
    # Сначала проверяем его.
    try:
        github_expire = (
            get_subscription_expire_from_github(
                user["token"]
            )
        )

        if github_expire is None:
            expire = datetime_to_unix(
                user["expires_at"]
            )

            update_github_subscription(
                user,
                expire
            )

        else:
            # GitHub является источником актуального expire.
            db_expire = datetime_to_unix(
                user["expires_at"]
            )

            if github_expire != db_expire:
                user = set_user_expire_in_database(
                    user_id,
                    github_expire
                )

    except Exception:
        # Пользователь всё равно должен получить меню.
        pass

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
# MY SUBSCRIPTION
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
        github_expire = (
            get_subscription_expire_from_github(
                user["token"]
            )
        )

        if github_expire is not None:
            db_expire = datetime_to_unix(
                user["expires_at"]
            )

            if github_expire != db_expire:
                user = set_user_expire_in_database(
                    callback.from_user.id,
                    github_expire
                )

    except Exception:
        pass

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
# REFRESH SUBSCRIPTION
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
        # GitHub — источник текущего expire.
        github_expire = (
            get_subscription_expire_from_github(
                user["token"]
            )
        )

        if github_expire is not None:
            user = set_user_expire_in_database(
                callback.from_user.id,
                github_expire
            )

        else:
            github_expire = datetime_to_unix(
                user["expires_at"]
            )

        # Пересобираем TOKEN.txt,
        # сохраняя текущий expire.
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

        try:
            await callback.message.answer(
                "❌ Ошибка обновления:\n\n"
                + str(error)
            )
        except Exception:
            pass


# ============================================================
# DELETE OWN SUBSCRIPTION
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
        # Физически удаляем TOKEN.txt.
        delete_github_subscription(
            user
        )

        delete_user(
            callback.from_user.id
        )

        await callback.message.edit_text(
            "🗑 Подписка удалена.\n\n"
            "Нажми /start, чтобы создать новую.",
        )

        await callback.answer(
            "✅ Подписка удалена."
        )

    except Exception as error:
        await callback.answer(
            "❌ Ошибка удаления.",
            show_alert=True
        )

        try:
            await callback.message.answer(
                "❌ Ошибка удаления:\n\n"
                + str(error)
            )
        except Exception:
            pass


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
        "4. Обновляй подписку после изменений серверов.\n\n"
        "🔄 Серверы в подписке обновляются автоматически."
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
# PROMO MENU
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

    code = message.text.strip()

    try:
        result, value = use_promo(
            code,
            user_id
        )

        if not result:
            await message.answer(
                "❌ " + str(value),
                reply_markup=back_keyboard()
            )

            await state.clear()
            return

        promo_days = int(value)

        # ВАЖНО:
        # Берём текущий expire именно из GitHub.
        github_expire = (
            get_subscription_expire_from_github(
                user["token"]
            )
        )

        current_time = now_unix()

        if github_expire is None:
            github_expire = max(
                current_time,
                datetime_to_unix(
                    user["expires_at"]
                )
            )

        base_expire = max(
            github_expire,
            current_time
        )

        new_expire = (
            base_expire
            + promo_days * 86400
        )

        # Сначала обновляем SQLite
        user = set_user_expire_in_database(
            user_id,
            new_expire
        )

        # Потом GitHub
        update_github_subscription(
            user,
            new_expire
        )

        await message.answer(
            "✅ ПРОМОКОД АКТИВИРОВАН\n\n"
            "🎟 Код: "
            + code.upper()
            + "\n"
            "➕ Добавлено: "
            + str(promo_days)
            + " дн.\n\n"
            "📅 До: "
            + format_date(new_expire)
            + "\n"
            "☁️ GitHub TOKEN.txt обновлён.",
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
        "Например:\n"
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
            "Например:\n"
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
        # ГЛАВНОЕ ИЗМЕНЕНИЕ:
        # GitHub TOKEN.txt является источником
        # текущей даты окончания.
        # ====================================================

        github_expire = (
            get_subscription_expire_from_github(
                user["token"]
            )
        )

        current_time = now_unix()

        if github_expire is None:
            github_expire = max(
                current_time,
                datetime_to_unix(
                    user["expires_at"]
                )
            )

        old_expire = max(
            github_expire,
            current_time
        )

        new_expire = (
            old_expire
            + days * 86400
        )

        # Обновляем БД ровно тем же timestamp.
        user = set_user_expire_in_database(
            target_id,
            new_expire
        )

        # Обновляем GitHub.
        update_github_subscription(
            user,
            new_expire
        )

        # Повторно читаем GitHub.
        github_after = (
            get_subscription_expire_from_github(
                user["token"]
            )
        )

        if github_after != new_expire:
            raise RuntimeError(
                "Проверка GitHub не пройдена.\n"
                "Ожидалось: "
                + str(new_expire)
                + "\n"
                "Получено: "
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
# ADMIN CREATE PROMO
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
        "Например:\n"
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
            "Например:\n"
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

        # Не удаляем TOKEN.txt,
        # а делаем его истёкшим.
        invalidate_github_subscription(
            user
        )

        await message.answer(
            "🚫 Пользователь заблокирован.\n\n"
            "ID: "
            + str(target_id)
            + "\n"
            "☁️ Подписка в GitHub отключена."
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

        current_time = now_unix()

        github_expire = (
            get_subscription_expire_from_github(
                user["token"]
            )
        )

        if github_expire is None:
            github_expire = datetime_to_unix(
                user["expires_at"]
            )

        if github_expire <= current_time:
            await message.answer(
                "🟢 Пользователь разблокирован.\n\n"
                "Но подписка уже истекла.\n"
                "Выдай ему дни через «Выдать дни»."
            )

        else:
            user = set_user_expire_in_database(
                target_id,
                github_expire
            )

            update_github_subscription(
                user,
                github_expire
            )

            await message.answer(
                "🟢 Пользователь разблокирован.\n\n"
                "ID: "
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
        "Отправь Telegram ID пользователя.",
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
        delete_github_subscription(
            user
        )

        delete_user(
            target_id
        )

        await message.answer(
            "🗑 ПОДПИСКА УДАЛЕНА\n\n"
            "👤 ID: "
            + str(target_id)
            + "\n"
            "☁️ TOKEN.txt удалён из GitHub."
        )

    except Exception as error:
        await message.answer(
            "❌ Ошибка удаления:\n\n"
            + str(error)
        )

    await state.clear()


# ============================================================
# UNKNOWN COMMANDS
# ============================================================

@dp.message(
    Command("help")
)
async def command_help(
    message: Message
):
    await message.answer(
        "❓ Помощь доступна через кнопку «❓ Помощь»."
    )


# ============================================================
# ERROR HANDLING
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
# STARTUP
# ============================================================

async def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN не задан."
        )

    init_db()

    print(
        "🍑 Персик VPN Bot запущен."
    )

    print(
        "GitHub subscriptions:",
        "enabled"
    )

    print(
        "HAPP_PAGE:",
        HAPP_PAGE
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
