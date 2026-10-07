import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import (
    BOT_TOKEN,
    ADMIN_ID,
)

from database import (
    connect,
    init_db,
    get_user,
    create_user,
    set_tariff,
    add_days,
    set_blocked,
    list_users,
    create_promo,
    list_promos,
    use_promo,
)

from github_api import (
    publish_subscription,
)


# ============================================================
# НАСТРОЙКИ
# ============================================================

logging.basicConfig(
    level=logging.INFO
)

bot = Bot(
    token=BOT_TOKEN
)

dp = Dispatcher()

ADMIN_STATES = {}


# ============================================================
# ПРОВЕРКА АДМИНА
# ============================================================

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# ============================================================
# ДАТА
# ============================================================

def fmt_date(value) -> str:
    if value is None:
        return "—"

    text = str(value).strip()

    if not text:
        return "—"

    # Unix timestamp
    try:
        if text.isdigit():
            timestamp = int(text)

            # Если вдруг timestamp в миллисекундах
            if timestamp > 100000000000:
                timestamp = timestamp / 1000

            dt = datetime.fromtimestamp(
                timestamp,
                tz=timezone.utc
            )

            return dt.strftime(
                "%d.%m.%Y %H:%M:%S"
            )
    except Exception:
        pass

    # ISO дата
    try:
        dt = datetime.fromisoformat(text)

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt.strftime(
            "%d.%m.%Y %H:%M:%S"
        )

    except Exception:
        return text


# ============================================================
# СОХРАНИТЬ URL ПОДПИСКИ
# ============================================================

def save_subscription_url(
    telegram_id: int,
    url: str
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


# ============================================================
# СОСТОЯНИЯ АДМИНА
# ============================================================

def set_state(
    user_id: int,
    data: dict
):
    ADMIN_STATES[user_id] = data


def get_state(user_id: int):
    return ADMIN_STATES.get(
        user_id
    )


def clear_state(user_id: int):
    ADMIN_STATES.pop(
        user_id,
        None
    )


# ============================================================
# ГЛАВНОЕ МЕНЮ
# ============================================================

def main_keyboard(
    user_id: int
):
    buttons = [
        [
            InlineKeyboardButton(
                text="🍑 Моя подписка",
                callback_data="my_subscription"
            )
        ],
        [
            InlineKeyboardButton(
                text="🎟 Промокод",
                callback_data="promo_menu"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔗 Моя ссылка",
                callback_data="my_link"
            )
        ],
    ]

    # Кнопка видна ТОЛЬКО админу
    if is_admin(user_id):
        buttons.append(
            [
                InlineKeyboardButton(
                    text="⚙️ Админ-панель",
                    callback_data="admin_panel"
                )
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )


# ============================================================
# АДМИН-КЛАВИАТУРА
# ============================================================

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
                    text="🎟 Промокоды",
                    callback_data="admin_promos"
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ Выдать тариф",
                    callback_data="admin_give_tariff"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⏳ Добавить дни",
                    callback_data="admin_add_days"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Блокировки",
                    callback_data="admin_blocks"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="back_main"
                )
            ],
        ]
    )


# ============================================================
# ТАРИФЫ
# ============================================================

def tariff_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="1️⃣ FREE",
                    callback_data="give_tariff_Free"
                ),
                InlineKeyboardButton(
                    text="2️⃣ PRO",
                    callback_data="give_tariff_PRO"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="admin_panel"
                )
            ],
        ]
    )


# ============================================================
# БЛОКИРОВКА
# ============================================================

def block_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚫 Заблокировать",
                    callback_data="block_yes"
                ),
                InlineKeyboardButton(
                    text="🟢 Разблокировать",
                    callback_data="block_no"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="admin_panel"
                )
            ],
        ]
    )


# ============================================================
# НАЗАД В АДМИНКУ
# ============================================================

def back_admin_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="admin_panel"
                )
            ]
        ]
    )


# ============================================================
# ПУБЛИКАЦИЯ ПОДПИСКИ
# ============================================================

def rebuild_subscription(user):
    if user is None:
        return None

    url = publish_subscription(
        token=user["token"],
        tariff=user["tariff"],
        expires_at=user["expires_at"],
    )

    save_subscription_url(
        user["telegram_id"],
        url
    )

    return url


# ============================================================
# ГЛАВНАЯ /START
# ============================================================

@dp.message(Command("start"))
async def start_command(
    message: Message
):
    telegram_id = message.from_user.id

    user = get_user(
        telegram_id
    )

    # Заблокирован
    if user is not None:
        if user["blocked"]:
            await message.answer(
                "🚫 Вы заблокированы."
            )
            return

    # Новый пользователь
    if user is None:
        user = create_user(
            telegram_id=telegram_id,
            username=message.from_user.username
        )

        try:
            await asyncio.to_thread(
                rebuild_subscription,
                user
            )
        except Exception:
            logging.exception(
                "Ошибка создания подписки"
            )

        user = get_user(
            telegram_id
        )

    # Если ссылка почему-то отсутствует
    elif not user["subscription_url"]:
        try:
            await asyncio.to_thread(
                rebuild_subscription,
                user
            )
        except Exception:
            logging.exception(
                "Ошибка восстановления ссылки"
            )

        user = get_user(
            telegram_id
        )

    await message.answer(
        "🍑 ПЕРСИК VPN\n\n"
        f"🟢 Подписка: {user['tariff']}\n"
        f"📅 До: {fmt_date(user['expires_at'])}\n"
        "📦 Трафик: Безлимит\n\n"
        "👇 Выбери действие:",
        reply_markup=main_keyboard(
            telegram_id
        )
    )


# ============================================================
# /ADMIN
# ============================================================

@dp.message(Command("admin"))
async def admin_command(
    message: Message
):
    if not is_admin(
        message.from_user.id
    ):
        await message.answer(
            "⛔ Доступ запрещён."
        )
        return

    clear_state(
        message.from_user.id
    )

    await message.answer(
        "⚙️ АДМИН-ПАНЕЛЬ\n\n"
        "Выбери действие:",
        reply_markup=admin_keyboard()
    )


# ============================================================
# НАЗАД В ГЛАВНОЕ
# ============================================================

@dp.callback_query(
    F.data == "back_main"
)
async def back_main(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if user is None:
        await callback.answer(
            "Сначала нажми /start",
            show_alert=True
        )
        return

    if user["blocked"]:
        await callback.answer(
            "🚫 Вы заблокированы",
            show_alert=True
        )
        return

    clear_state(
        callback.from_user.id
    )

    await callback.message.edit_text(
        "🍑 ПЕРСИК VPN\n\n"
        f"🟢 Подписка: {user['tariff']}\n"
        f"📅 До: {fmt_date(user['expires_at'])}\n"
        "📦 Трафик: Безлимит\n\n"
        "👇 Выбери действие:",
        reply_markup=main_keyboard(
            callback.from_user.id
        )
    )

    await callback.answer()


# ============================================================
# ПРОМОКОД — МЕНЮ
# ============================================================

@dp.callback_query(
    F.data == "promo_menu"
)
async def promo_menu(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if user is None:
        await callback.answer(
            "Сначала нажми /start",
            show_alert=True
        )
        return

    if user["blocked"]:
        await callback.answer(
            "🚫 Вы заблокированы",
            show_alert=True
        )
        return

    await callback.message.edit_text(
        "🎟 ПРОМОКОД\n\n"
        "Введи промокод командой:\n\n"
        "/promo КОД\n\n"
        "Например:\n"
        "/promo PEACHPRO",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="back_main"
                    )
                ]
            ]
        )
    )

    await callback.answer()


# ============================================================
# МОЯ ПОДПИСКА
# ============================================================

@dp.callback_query(
    F.data == "my_subscription"
)
async def my_subscription(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if user is None:
        await callback.answer(
            "Сначала нажми /start",
            show_alert=True
        )
        return

    if user["blocked"]:
        await callback.answer(
            "🚫 Вы заблокированы",
            show_alert=True
        )
        return

    if not user["subscription_url"]:
        try:
            await asyncio.to_thread(
                rebuild_subscription,
                user
            )
        except Exception:
            logging.exception(
                "Ошибка создания URL"
            )

        user = get_user(
            callback.from_user.id
        )

    await callback.message.edit_text(
        "🍑 МОЯ ПОДПИСКА\n\n"
        "🟢 Статус: Активна\n"
        f"💎 Тариф: {user['tariff']}\n"
        f"📅 До: {fmt_date(user['expires_at'])}\n\n"
        "🔗 Ссылка:\n\n"
        f"{user['subscription_url'] or 'Ошибка создания ссылки'}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 Обновить",
                        callback_data="refresh_subscription"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="back_main"
                    )
                ],
            ]
        )
    )

    await callback.answer()


# ============================================================
# МОЯ ССЫЛКА
# ============================================================

@dp.callback_query(
    F.data == "my_link"
)
async def my_link(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if user is None:
        await callback.answer(
            "Сначала нажми /start",
            show_alert=True
        )
        return

    if user["blocked"]:
        await callback.answer(
            "🚫 Вы заблокированы",
            show_alert=True
        )
        return

    if not user["subscription_url"]:
        try:
            await asyncio.to_thread(
                rebuild_subscription,
                user
            )
        except Exception:
            logging.exception(
                "Ошибка создания ссылки"
            )

        user = get_user(
            callback.from_user.id
        )

    await callback.message.edit_text(
        "🔗 МОЯ ССЫЛКА\n\n"
        f"{user['subscription_url'] or 'Ошибка создания ссылки'}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="back_main"
                    )
                ]
            ]
        )
    )

    await callback.answer()


# ============================================================
# ОБНОВИТЬ ПОДПИСКУ
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

    if user is None:
        await callback.answer(
            "Пользователь не найден",
            show_alert=True
        )
        return

    if user["blocked"]:
        await callback.answer(
            "🚫 Вы заблокированы",
            show_alert=True
        )
        return

    try:
        await asyncio.to_thread(
            rebuild_subscription,
            user
        )

        user = get_user(
            callback.from_user.id
        )

        await callback.message.edit_text(
            "🍑 МОЯ ПОДПИСКА\n\n"
            "🟢 Статус: Активна\n"
            f"💎 Тариф: {user['tariff']}\n"
            f"📅 До: {fmt_date(user['expires_at'])}\n\n"
            "🔗 Ссылка:\n\n"
            f"{user['subscription_url']}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔄 Обновить",
                            callback_data="refresh_subscription"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="⬅️ Назад",
                            callback_data="back_main"
                        )
                    ],
                ]
            )
        )

        await callback.answer(
            "✅ Подписка обновлена"
        )

    except Exception:
        logging.exception(
            "Ошибка обновления подписки"
        )

        await callback.answer(
            "❌ Ошибка обновления",
            show_alert=True
        )


# ============================================================
# АДМИН-ПАНЕЛЬ
# ============================================================

@dp.callback_query(
    F.data == "admin_panel"
)
async def admin_panel(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "⛔ Доступ запрещён",
            show_alert=True
        )
        return

    clear_state(
        callback.from_user.id
    )

    await callback.message.edit_text(
        "⚙️ АДМИН-ПАНЕЛЬ\n\n"
        "Выбери действие:",
        reply_markup=admin_keyboard()
    )

    await callback.answer()


# ============================================================
# АДМИН — ПОЛЬЗОВАТЕЛИ
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
            "⛔ Доступ запрещён",
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
        lines = [
            "👥 ПОЛЬЗОВАТЕЛИ",
            ""
        ]

        for user in users[:50]:
            status = (
                "🚫"
                if user["blocked"]
                else "🟢"
            )

            lines.append(
                f"{status} ID: {user['telegram_id']}\n"
                f"💎 Тариф: {user['tariff']}\n"
                f"📅 До: {fmt_date(user['expires_at'])}\n"
            )

        text = "\n".join(lines)

    await callback.message.edit_text(
        text,
        reply_markup=back_admin_keyboard()
    )

    await callback.answer()


# ============================================================
# АДМИН — ПРОМОКОДЫ
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
            "⛔ Доступ запрещён",
            show_alert=True
        )
        return

    promos = list_promos()

    lines = [
        "🎟 ПРОМОКОДЫ",
        ""
    ]

    if not promos:
        lines.append(
            "Промокодов пока нет."
        )

    else:
        for promo in promos:
            active = (
                "🟢 Да"
                if promo["active"]
                else "🔴 Нет"
            )

            lines.append(
                f"🎟 {promo['code']}\n"
                f"💎 Тариф: {promo['tariff']}\n"
                f"📅 Дней: {promo['days']}\n"
                f"👥 Использований: "
                f"{promo['uses']}/"
                f"{promo['max_uses']}\n"
                f"Статус: {active}\n"
            )

    lines.extend(
        [
            "",
            "Создание:",
            "/createpromo КОД ТАРИФ ДНИ ЛИМИТ",
            "",
            "1 = Free",
            "2 = PRO",
            "",
            "Пример:",
            "/createpromo PEACHPRO 2 30 100",
        ]
    )

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=back_admin_keyboard()
    )

    await callback.answer()


# ============================================================
# АДМИН — ВЫДАТЬ ТАРИФ
# ============================================================

@dp.callback_query(
    F.data == "admin_give_tariff"
)
async def admin_give_tariff(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "⛔ Доступ запрещён",
            show_alert=True
        )
        return

    clear_state(
        callback.from_user.id
    )

    await callback.message.edit_text(
        "➕ ВЫДАТЬ ТАРИФ\n\n"
        "Выбери тариф:\n\n"
        "1️⃣ FREE\n"
        "2️⃣ PRO",
        reply_markup=tariff_keyboard()
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith("give_tariff_")
)
async def select_tariff(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "⛔ Доступ запрещён",
            show_alert=True
        )
        return

    tariff = callback.data.replace(
        "give_tariff_",
        ""
    )

    if tariff not in (
        "Free",
        "PRO"
    ):
        await callback.answer(
            "❌ Неверный тариф",
            show_alert=True
        )
        return

    set_state(
        callback.from_user.id,
        {
            "action": "give_tariff",
            "tariff": tariff,
        }
    )

    await callback.message.edit_text(
        "➕ ВЫДАТЬ ТАРИФ\n\n"
        f"💎 Выбран тариф: {tariff}\n\n"
        "Введите Telegram ID пользователя:"
    )

    await callback.answer()


# ============================================================
# АДМИН — ДОБАВИТЬ ДНИ
# ============================================================

@dp.callback_query(
    F.data == "admin_add_days"
)
async def admin_add_days(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "⛔ Доступ запрещён",
            show_alert=True
        )
        return

    set_state(
        callback.from_user.id,
        {
            "action": "add_days_id"
        }
    )

    await callback.message.edit_text(
        "⏳ ДОБАВИТЬ ДНИ\n\n"
        "Введите Telegram ID пользователя:"
    )

    await callback.answer()


# ============================================================
# АДМИН — БЛОКИРОВКИ
# ============================================================

@dp.callback_query(
    F.data == "admin_blocks"
)
async def admin_blocks(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "⛔ Доступ запрещён",
            show_alert=True
        )
        return

    set_state(
        callback.from_user.id,
        {
            "action": "block_id"
        }
    )

    await callback.message.edit_text(
        "🚫 БЛОКИРОВКИ\n\n"
        "Введите Telegram ID пользователя:"
    )

    await callback.answer()


# ============================================================
# /CREATEPROMO
# ============================================================

@dp.message(
    Command("createpromo")
)
async def createpromo_command(
    message: Message
):
    if not is_admin(
        message.from_user.id
    ):
        await message.answer(
            "⛔ Доступ запрещён."
        )
        return

    parts = message.text.split()

    if len(parts) != 5:
        await message.answer(
            "❌ Формат:\n\n"
            "/createpromo КОД ТАРИФ ДНИ ЛИМИТ\n\n"
            "1 = Free\n"
            "2 = PRO\n\n"
            "Пример:\n"
            "/createpromo PEACHPRO 2 30 100"
        )
        return

    _, code, tariff, days_text, limit_text = parts

    if tariff.upper() in (
        "1",
        "FREE"
    ):
        tariff = "Free"

    elif tariff.upper() in (
        "2",
        "PRO"
    ):
        tariff = "PRO"

    else:
        await message.answer(
            "❌ Тариф должен быть:\n"
            "1 = Free\n"
            "2 = PRO"
        )
        return

    try:
        days = int(
            days_text
        )

        limit = int(
            limit_text
        )

        if days <= 0 or limit <= 0:
            raise ValueError

    except ValueError:
        await message.answer(
            "❌ Дни и лимит должны быть "
            "целыми числами больше 0."
        )
        return

    result = create_promo(
        code=code.upper(),
        tariff=tariff,
        days=days,
        max_uses=limit,
    )

    if result is None:
        await message.answer(
            "❌ Такой промокод уже существует "
            "или создать его не удалось."
        )
        return

    await message.answer(
        "✅ ПРОМОКОД СОЗДАН\n\n"
        f"🎟 Код: {code.upper()}\n"
        f"💎 Тариф: {tariff}\n"
        f"📅 Дней: {days}\n"
        f"👥 Лимит: {limit}"
    )


# ============================================================
# /PROMO
# ============================================================

@dp.message(
    Command("promo")
)
async def promo_command(
    message: Message
):
    user = get_user(
        message.from_user.id
    )

    if user is None:
        await message.answer(
            "Сначала нажми /start."
        )
        return

    if user["blocked"]:
        await message.answer(
            "🚫 Вы заблокированы."
        )
        return

    parts = message.text.split(
        maxsplit=1
    )

    if len(parts) != 2:
        await message.answer(
            "❌ Используй:\n"
            "/promo КОД"
        )
        return

    code = parts[1].strip()

    result, status = use_promo(
        message.from_user.id,
        code
    )

    if status != "ok":

        errors = {
            "not_found":
                "❌ Промокод не найден.",

            "disabled":
                "❌ Промокод отключён.",

            "limit":
                "❌ Лимит активаций исчерпан.",

            "already_used":
                "❌ Ты уже использовал "
                "этот промокод.",
        }

        await message.answer(
            errors.get(
                status,
                "❌ Не удалось активировать "
                "промокод."
            )
        )

        return

    updated_user = get_user(
        message.from_user.id
    )

    try:
        await asyncio.to_thread(
            rebuild_subscription,
            updated_user
        )
    except Exception:
        logging.exception(
            "Ошибка публикации после промокода"
        )

    updated_user = get_user(
        message.from_user.id
    )

    await message.answer(
        "🎉 ПРОМОКОД АКТИВИРОВАН!\n\n"
        f"💎 Тариф: {updated_user['tariff']}\n"
        f"📅 До: {fmt_date(updated_user['expires_at'])}\n"
        "📦 Трафик: Безлимит"
    )


# ============================================================
# ВВОД ТЕКСТА АДМИНА
# ============================================================

@dp.message(
    F.text
)
async def admin_text_input(
    message: Message
):
    if not is_admin(
        message.from_user.id
    ):
        return

    state = get_state(
        message.from_user.id
    )

    if not state:
        return

    text = message.text.strip()

    action = state.get(
        "action"
    )

    # ========================================================
    # ВЫДАТЬ ТАРИФ
    # ========================================================

    if action == "give_tariff":

        try:
            telegram_id = int(
                text
            )
        except ValueError:
            await message.answer(
                "❌ Telegram ID должен быть числом."
            )
            return

        user = get_user(
            telegram_id
        )

        if user is None:
            clear_state(
                message.from_user.id
            )

            await message.answer(
                "❌ Пользователь не найден.",
                reply_markup=admin_keyboard()
            )
            return

        old_expires = user[
            "expires_at"
        ]

        tariff = state[
            "tariff"
        ]

        # Меняем ТОЛЬКО тариф.
        # Срок НЕ меняется.
        set_tariff(
            telegram_id,
            tariff
        )

        updated_user = get_user(
            telegram_id
        )

        try:
            await asyncio.to_thread(
                rebuild_subscription,
                updated_user
            )
        except Exception:
            logging.exception(
                "Ошибка публикации тарифа"
            )

        clear_state(
            message.from_user.id
        )

        await message.answer(
            "✅ ТАРИФ ВЫДАН\n\n"
            f"👤 ID: {telegram_id}\n"
            f"💎 Тариф: {tariff}\n\n"
            "📅 Срок НЕ изменён:\n"
            f"{fmt_date(old_expires)}\n\n"
            "➕ Дни не добавлялись.",
            reply_markup=admin_keyboard()
        )

        return

    # ========================================================
    # ДОБАВИТЬ ДНИ — ID
    # ========================================================

    if action == "add_days_id":

        try:
            telegram_id = int(
                text
            )
        except ValueError:
            await message.answer(
                "❌ Telegram ID должен быть числом."
            )
            return

        user = get_user(
            telegram_id
        )

        if user is None:
            clear_state(
                message.from_user.id
            )

            await message.answer(
                "❌ Пользователь не найден.",
                reply_markup=admin_keyboard()
            )
            return

        set_state(
            message.from_user.id,
            {
                "action":
                    "add_days_value",
                "telegram_id":
                    telegram_id,
            }
        )

        await message.answer(
            "⏳ ДОБАВИТЬ ДНИ\n\n"
            f"👤 ID: {telegram_id}\n"
            f"📅 Сейчас до: "
            f"{fmt_date(user['expires_at'])}\n\n"
            "Введите количество дней:"
        )

        return

    # ========================================================
    # ДОБАВИТЬ ДНИ — КОЛИЧЕСТВО
    # ========================================================

    if action == "add_days_value":

        try:
            days = int(
                text
            )

            if days <= 0:
                raise ValueError

        except ValueError:
            await message.answer(
                "❌ Введите целое число "
                "дней больше 0."
            )
            return

        telegram_id = state[
            "telegram_id"
        ]

        user = get_user(
            telegram_id
        )

        if user is None:
            clear_state(
                message.from_user.id
            )

            await message.answer(
                "❌ Пользователь не найден.",
                reply_markup=admin_keyboard()
            )
            return

        old_expires = user[
            "expires_at"
        ]

        add_days(
            telegram_id,
            days
        )

        updated_user = get_user(
            telegram_id
        )

        try:
            await asyncio.to_thread(
                rebuild_subscription,
                updated_user
            )
        except Exception:
            logging.exception(
                "Ошибка публикации после добавления дней"
            )

        clear_state(
            message.from_user.id
        )

        await message.answer(
            "✅ ДНИ ДОБАВЛЕНЫ\n\n"
            f"👤 ID: {telegram_id}\n"
            f"➕ Добавлено: {days} дн.\n\n"
            "📅 Было до:\n"
            f"{fmt_date(old_expires)}\n\n"
            "📅 Стало до:\n"
            f"{fmt_date(updated_user['expires_at'])}",
            reply_markup=admin_keyboard()
        )

        return

    # ========================================================
    # БЛОКИРОВКА — ID
    # ========================================================

    if action == "block_id":

        try:
            telegram_id = int(
                text
            )
        except ValueError:
            await message.answer(
                "❌ Telegram ID должен быть числом."
            )
            return

        user = get_user(
            telegram_id
        )

        if user is None:
            clear_state(
                message.from_user.id
            )

            await message.answer(
                "❌ Пользователь не найден.",
                reply_markup=admin_keyboard()
            )
            return

        set_state(
            message.from_user.id,
            {
                "action":
                    "block_choice",
                "telegram_id":
                    telegram_id,
            }
        )

        await message.answer(
            "🚫 БЛОКИРОВКА\n\n"
            f"👤 ID: {telegram_id}\n"
            f"📌 Сейчас: "
            f"{'Заблокирован' if user['blocked'] else 'Не заблокирован'}\n\n"
            "Выбери действие:",
            reply_markup=block_keyboard()
        )

        return


# ============================================================
# БЛОКИРОВКА
# ============================================================

@dp.callback_query(
    F.data == "block_yes"
)
async def block_yes(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "⛔ Доступ запрещён",
            show_alert=True
        )
        return

    state = get_state(
        callback.from_user.id
    )

    if not state:
        await callback.answer(
            "❌ Сессия закончилась",
            show_alert=True
        )
        return

    telegram_id = state[
        "telegram_id"
    ]

    set_blocked(
        telegram_id,
        True
    )

    clear_state(
        callback.from_user.id
    )

    await callback.message.edit_text(
        f"🚫 Пользователь {telegram_id} заблокирован.",
        reply_markup=admin_keyboard()
    )

    await callback.answer()


@dp.callback_query(
    F.data == "block_no"
)
async def block_no(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "⛔ Доступ запрещён",
            show_alert=True
        )
        return

    state = get_state(
        callback.from_user.id
    )

    if not state:
        await callback.answer(
            "❌ Сессия закончилась",
            show_alert=True
        )
        return

    telegram_id = state[
        "telegram_id"
    ]

    set_blocked(
        telegram_id,
        False
    )

    clear_state(
        callback.from_user.id
    )

    await callback.message.edit_text(
        f"🟢 Пользователь {telegram_id} разблокирован.",
        reply_markup=admin_keyboard()
    )

    await callback.answer()


# ============================================================
# ЗАПУСК
# ============================================================

async def main():

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN не задан"
        )

    init_db()

    logging.info(
        "🍑 PeachVPN Bot запущен"
    )

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":
    asyncio.run(
        main()
    )
