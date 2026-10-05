import asyncio
import logging
import secrets

from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import (
    BOT_TOKEN,
    ADMIN_ID,
    SUBSCRIPTION_DAYS,
    EXPIRED_WARNING_HOURS,
    CHECK_INTERVAL_SECONDS,
)

from database import (
    init_db,
    get_user,
    create_user,
    activate_subscription,
    save_subscription_url,
    set_expired_page,
    set_blocked,
    replace_token,
    list_users,
)

from github_api import (
    publish_active,
    publish_expired,
    raw_subscription_url,
    delete_subscription,
)


# =========================================================
# НАСТРОЙКИ
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


# =========================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================================================

def now_timestamp():
    return int(
        datetime.now(
            timezone.utc
        ).timestamp()
    )


def format_date(timestamp):
    try:
        timestamp = int(timestamp)

        dt = datetime.fromtimestamp(
            timestamp,
            timezone.utc
        )

        return dt.strftime(
            "%d.%m.%Y %H:%M"
        )

    except Exception:
        return "—"


def is_admin(user_id):
    return int(user_id) == int(ADMIN_ID)


def subscription_active(user):
    if not user:
        return False

    if user["blocked"]:
        return False

    if user["expired_page"]:
        return False

    try:
        expires_at = int(
            user["expires_at"]
        )
    except Exception:
        return False

    return expires_at > now_timestamp()


# =========================================================
# ГЛАВНАЯ КЛАВИАТУРА
# =========================================================

def main_keyboard(user_id):
    buttons = [
        [
            InlineKeyboardButton(
                text="🍑 Моя подписка",
                callback_data="my_subscription"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔗 Моя ссылка",
                callback_data="my_link"
            )
        ],
    ]

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


# =========================================================
# КЛАВИАТУРА МОЕЙ ПОДПИСКИ
# =========================================================

def subscription_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Обновить",
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
                    text="⬅️ Назад",
                    callback_data="back_home"
                )
            ],
        ]
    )


# =========================================================
# ПОСЛЕ ОБНОВЛЕНИЯ
# =========================================================

def updated_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="back_subscription"
                )
            ]
        ]
    )


# =========================================================
# ССЫЛКА
# =========================================================

def link_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="back_home"
                )
            ]
        ]
    )


# =========================================================
# АДМИН
# =========================================================

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
                    text="⬅️ Назад",
                    callback_data="back_home"
                )
            ],
        ]
    )


# =========================================================
# ГЛАВНОЕ МЕНЮ
# =========================================================

def home_text(user):
    if not user:
        return (
            "🍑 ПЕРСИК VPN\n\n"
            "❌ Пользователь не найден."
        )

    if user["blocked"]:
        return (
            "🍑 ПЕРСИК VPN\n\n"
            "⛔ Доступ заблокирован."
        )

    if user["expired_page"]:
        return (
            "🍑 ПЕРСИК VPN\n\n"
            "🔴 Подписка закончилась\n"
            "📅 До: —\n"
            "📦 Трафик: Безлимит\n\n"
            "👇 Выбери действие:"
        )

    if subscription_active(user):
        return (
            "🍑 ПЕРСИК VPN\n\n"
            "🟢 Подписка: Free\n"
            "📅 До: "
            + format_date(
                user["expires_at"]
            )
            + "\n"
            "📦 Трафик: Безлимит\n\n"
            "👇 Выбери действие:"
        )

    return (
        "🍑 ПЕРСИК VPN\n\n"
        "🔴 Подписка закончилась\n"
        "📅 До: —\n"
        "📦 Трафик: Безлимит\n\n"
        "👇 Выбери действие:"
    )


# =========================================================
# МОЯ ПОДПИСКА
# =========================================================

def subscription_text(user):
    if not user:
        return (
            "🍑 МОЯ ПОДПИСКА\n\n"
            "❌ Пользователь не найден."
        )

    if user["blocked"]:
        return (
            "🍑 МОЯ ПОДПИСКА\n\n"
            "⛔ Статус: Заблокирована"
        )

    if user["expired_page"]:
        return (
            "🍑 МОЯ ПОДПИСКА\n\n"
            "🔴 Статус: Закончилась\n"
            "📅 До: "
            + format_date(
                user["expires_at"]
            )
        )

    if not subscription_active(user):
        return (
            "🍑 МОЯ ПОДПИСКА\n\n"
            "🔴 Статус: Закончилась\n"
            "📅 До: "
            + format_date(
                user["expires_at"]
            )
        )

    return (
        "🍑 МОЯ ПОДПИСКА\n\n"
        "🟢 Статус: Активна\n"
        "📅 До: "
        + format_date(
            user["expires_at"]
        )
        + "\n\n"
        "🔗 Ссылка:\n\n"
        + user["subscription_url"]
    )


# =========================================================
# СОЗДАНИЕ ПОЛЬЗОВАТЕЛЯ
# =========================================================

async def get_or_create_user(
    telegram_id,
    username=None
):
    user = get_user(
        telegram_id
    )

    if user:
        return user

    user = create_user(
        telegram_id,
        username
    )

    if (
        user
        and str(user["expires_at"]) == "0"
    ):
        user = activate_subscription(
            telegram_id,
            SUBSCRIPTION_DAYS
        )

        url = publish_active(
            user["token"],
            int(user["expires_at"])
        )

        save_subscription_url(
            telegram_id,
            url
        )

        user = get_user(
            telegram_id
        )

    return user


# =========================================================
# /START
# =========================================================

@dp.message(CommandStart())
async def start_handler(message: Message):
    try:
        user = await get_or_create_user(
            message.from_user.id,
            message.from_user.username
        )

        if not user:
            await message.answer(
                "❌ Не удалось создать пользователя."
            )
            return

        await message.answer(
            home_text(user),
            reply_markup=main_keyboard(
                message.from_user.id
            )
        )

    except Exception as error:
        logger.exception(
            "Ошибка /start"
        )

        await message.answer(
            "❌ Ошибка:\n"
            + str(error)
        )


# =========================================================
# МОЯ ПОДПИСКА
# =========================================================

@dp.callback_query(
    F.data == "my_subscription"
)
async def my_subscription_handler(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if not user:
        await callback.answer(
            "Пользователь не найден.",
            show_alert=True
        )
        return

    await callback.message.edit_text(
        subscription_text(user),
        reply_markup=subscription_keyboard()
    )

    await callback.answer()


# =========================================================
# ОБНОВИТЬ ПОДПИСКУ
# =========================================================

@dp.callback_query(
    F.data == "refresh_subscription"
)
async def refresh_subscription_handler(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if not user:
        await callback.answer(
            "Пользователь не найден.",
            show_alert=True
        )
        return

    if user["blocked"]:
        await callback.answer(
            "Доступ заблокирован.",
            show_alert=True
        )
        return

    if user["expired_page"]:
        await callback.answer(
            "Подписка уже закончилась.",
            show_alert=True
        )
        return

    try:
        expires_at = int(
            user["expires_at"]
        )

        remaining = (
            expires_at
            - now_timestamp()
        )

        # Если осталось 24 часа или меньше,
        # подписка переводится в оконченный режим.
        if remaining <= (
            EXPIRED_WARNING_HOURS * 3600
        ):
            publish_expired(
                user["token"]
            )

            set_expired_page(
                callback.from_user.id,
                True
            )

            await callback.message.edit_text(
                "🍑 МОЯ ПОДПИСКА\n\n"
                "🔴 Статус: Закончилась\n"
                "📅 До: "
                + format_date(
                    expires_at
                ),
                reply_markup=updated_keyboard()
            )

            await callback.answer(
                "Подписка закончилась."
            )
            return

        # Пересобираем тот же файл.
        # TOKEN и URL остаются прежними.
        url = publish_active(
            user["token"],
            expires_at
        )

        save_subscription_url(
            callback.from_user.id,
            url
        )

        await callback.message.edit_text(
            "🍑 ПОДПИСКА ОБНОВЛЕНА\n\n"
            "✅ Серверы проверены\n"
            "🔄 Файл подписки обновлён",
            reply_markup=updated_keyboard()
        )

        await callback.answer(
            "Подписка обновлена."
        )

    except Exception as error:
        logger.exception(
            "Ошибка обновления подписки"
        )

        await callback.answer(
            "Ошибка обновления:\n"
            + str(error),
            show_alert=True
        )


# =========================================================
# УДАЛИТЬ ПОДПИСКУ
# =========================================================

@dp.callback_query(
    F.data == "delete_subscription"
)
async def delete_subscription_handler(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if not user:
        await callback.answer(
            "Пользователь не найден.",
            show_alert=True
        )
        return

    if user["blocked"]:
        await callback.answer(
            "Доступ заблокирован.",
            show_alert=True
        )
        return

    await callback.message.edit_text(
        "⚠️ Удалить подписку?\n\n"
        "Будут удалены все серверы "
        "из текущей подписки.\n\n"
        "⏳ Оставшееся время сохранится.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Да, удалить",
                        callback_data="confirm_delete_subscription"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data="back_subscription"
                    )
                ],
            ]
        )
    )

    await callback.answer()


# =========================================================
# ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ
# =========================================================

@dp.callback_query(
    F.data == "confirm_delete_subscription"
)
async def confirm_delete_subscription_handler(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if not user:
        await callback.answer(
            "Пользователь не найден.",
            show_alert=True
        )
        return

    if user["blocked"]:
        await callback.answer(
            "Доступ заблокирован.",
            show_alert=True
        )
        return

    try:
        old_token = user["token"]

        old_expires_at = int(
            user["expires_at"]
        )

        now = now_timestamp()

        remaining = (
            old_expires_at
            - now
        )

        if remaining <= 0:
            await callback.answer(
                "Подписка уже закончилась.",
                show_alert=True
            )
            return

        # -----------------------------------------
        # 1. Удаляем старый GitHub-файл
        # -----------------------------------------

        delete_subscription(
            old_token
        )

        # -----------------------------------------
        # 2. Новый TOKEN
        # -----------------------------------------

        new_token = secrets.token_urlsafe(
            24
        )

        # -----------------------------------------
        # 3. Сохраняем старую дату окончания
        # -----------------------------------------

        replace_token(
            callback.from_user.id,
            new_token,
            old_expires_at
        )

        # -----------------------------------------
        # 4. Создаём новый GitHub-файл
        #    с актуальными nodes.txt
        # -----------------------------------------

        new_url = publish_active(
            new_token,
            old_expires_at
        )

        # -----------------------------------------
        # 5. Сохраняем новую ссылку
        # -----------------------------------------

        save_subscription_url(
            callback.from_user.id,
            new_url
        )

        new_user = get_user(
            callback.from_user.id
        )

        await callback.message.edit_text(
            "🍑 ПОДПИСКА ПЕРЕСОЗДАНА\n\n"
            "✅ Старая подписка удалена\n"
            "✅ Создана новая ссылка\n"
            "⏳ Оставшееся время сохранено\n\n"
            "📅 До: "
            + format_date(
                new_user["expires_at"]
            )
            + "\n\n"
            "🔗 Новая ссылка:\n\n"
            + new_user["subscription_url"],
            reply_markup=subscription_keyboard()
        )

        await callback.answer(
            "Подписка пересоздана."
        )

    except Exception as error:
        logger.exception(
            "Ошибка пересоздания подписки"
        )

        await callback.answer(
            "Ошибка:\n"
            + str(error),
            show_alert=True
        )


# =========================================================
# МОЯ ССЫЛКА
# =========================================================

@dp.callback_query(
    F.data == "my_link"
)
async def my_link_handler(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if not user:
        await callback.answer(
            "Пользователь не найден.",
            show_alert=True
        )
        return

    if not user["subscription_url"]:
        try:
            url = raw_subscription_url(
                user["token"]
            )

            save_subscription_url(
                callback.from_user.id,
                url
            )

            user = get_user(
                callback.from_user.id
            )

        except Exception as error:
            await callback.answer(
                str(error),
                show_alert=True
            )
            return

    await callback.message.edit_text(
        "🔗 МОЯ ССЫЛКА\n\n"
        + user["subscription_url"],
        reply_markup=link_keyboard()
    )

    await callback.answer()


# =========================================================
# НАЗАД В ГЛАВНОЕ МЕНЮ
# =========================================================

@dp.callback_query(
    F.data == "back_home"
)
async def back_home_handler(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if not user:
        await callback.answer(
            "Пользователь не найден.",
            show_alert=True
        )
        return

    await callback.message.edit_text(
        home_text(user),
        reply_markup=main_keyboard(
            callback.from_user.id
        )
    )

    await callback.answer()


# =========================================================
# НАЗАД В МОЮ ПОДПИСКУ
# =========================================================

@dp.callback_query(
    F.data == "back_subscription"
)
async def back_subscription_handler(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if not user:
        await callback.answer(
            "Пользователь не найден.",
            show_alert=True
        )
        return

    await callback.message.edit_text(
        subscription_text(user),
        reply_markup=subscription_keyboard()
    )

    await callback.answer()


# =========================================================
# АДМИН-ПАНЕЛЬ
# =========================================================

@dp.callback_query(
    F.data == "admin_panel"
)
async def admin_panel_handler(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "Нет доступа.",
            show_alert=True
        )
        return

    await callback.message.edit_text(
        "⚙️ АДМИН-ПАНЕЛЬ\n\n"
        "Выбери действие:",
        reply_markup=admin_keyboard()
    )

    await callback.answer()


# =========================================================
# ПОЛЬЗОВАТЕЛИ
# =========================================================

@dp.callback_query(
    F.data == "admin_users"
)
async def admin_users_handler(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "Нет доступа.",
            show_alert=True
        )
        return

    users = list_users()

    if not users:
        await callback.message.edit_text(
            "👥 ПОЛЬЗОВАТЕЛИ\n\n"
            "Пользователей пока нет.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⬅️ Назад",
                            callback_data="admin_panel"
                        )
                    ]
                ]
            )
        )

        await callback.answer()
        return

    buttons = []

    for user in users[:50]:
        username = user["username"]

        if username:
            title = "👤 @" + username
        else:
            title = (
                "👤 ID "
                + str(user["telegram_id"])
            )

        if user["blocked"]:
            title += " 🔴"
        elif user["expired_page"]:
            title += " ⚫"
        else:
            title += " 🟢"

        buttons.append(
            [
                InlineKeyboardButton(
                    text=title,
                    callback_data=(
                        "admin_user:"
                        + str(user["telegram_id"])
                    )
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="admin_panel"
            )
        ]
    )

    await callback.message.edit_text(
        "👥 ПОЛЬЗОВАТЕЛИ\n\n"
        "Всего: "
        + str(len(users)),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
    )

    await callback.answer()


# =========================================================
# ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ
# =========================================================

@dp.callback_query(
    F.data.startswith("admin_user:")
)
async def admin_user_handler(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "Нет доступа.",
            show_alert=True
        )
        return

    try:
        telegram_id = int(
            callback.data.split(
                ":",
                1
            )[1]
        )
    except Exception:
        await callback.answer(
            "Ошибка ID.",
            show_alert=True
        )
        return

    user = get_user(
        telegram_id
    )

    if not user:
        await callback.answer(
            "Пользователь не найден.",
            show_alert=True
        )
        return

    if user["blocked"]:
        status = "🔴 Заблокирован"
    elif user["expired_page"]:
        status = "⚫ Закончилась"
    elif subscription_active(user):
        status = "🟢 Активна"
    else:
        status = "⚫ Закончилась"

    username = (
        "@"
        + user["username"]
        if user["username"]
        else "—"
    )

    text = (
        "👤 ПОЛЬЗОВАТЕЛЬ\n\n"
        "🆔 ID: "
        + str(user["telegram_id"])
        + "\n"
        "👤 Username: "
        + username
        + "\n\n"
        "📌 Статус: "
        + status
        + "\n"
        "📅 До: "
        + format_date(
            user["expires_at"]
        )
        + "\n\n"
        "🔑 TOKEN:\n"
        + user["token"]
    )

    buttons = []

    if user["blocked"]:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="🟢 Разблокировать",
                    callback_data=(
                        "admin_unblock:"
                        + str(telegram_id)
                    )
                )
            ]
        )
    else:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="🔴 Заблокировать",
                    callback_data=(
                        "admin_block:"
                        + str(telegram_id)
                    )
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                text="⬅️ К пользователям",
                callback_data="admin_users"
            )
        ]
    )

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
    )

    await callback.answer()


# =========================================================
# БЛОКИРОВКА
# =========================================================

@dp.callback_query(
    F.data.startswith("admin_block:")
)
async def admin_block_handler(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "Нет доступа.",
            show_alert=True
        )
        return

    try:
        telegram_id = int(
            callback.data.split(
                ":",
                1
            )[1]
        )
    except Exception:
        await callback.answer(
            "Ошибка ID.",
            show_alert=True
        )
        return

    if telegram_id == ADMIN_ID:
        await callback.answer(
            "Нельзя заблокировать администратора.",
            show_alert=True
        )
        return

    set_blocked(
        telegram_id,
        True
    )

    await callback.answer(
        "Пользователь заблокирован."
    )

    user = get_user(
        telegram_id
    )

    if user:
        await callback.message.edit_text(
            "👤 ПОЛЬЗОВАТЕЛЬ\n\n"
            "🆔 ID: "
            + str(user["telegram_id"])
            + "\n"
            "📌 Статус: 🔴 Заблокирован\n"
            "📅 До: "
            + format_date(
                user["expires_at"]
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🟢 Разблокировать",
                            callback_data=(
                                "admin_unblock:"
                                + str(telegram_id)
                            )
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="⬅️ К пользователям",
                            callback_data="admin_users"
                        )
                    ],
                ]
            )
        )


# =========================================================
# РАЗБЛОКИРОВКА
# =========================================================

@dp.callback_query(
    F.data.startswith("admin_unblock:")
)
async def admin_unblock_handler(
    callback: CallbackQuery
):
    if not is_admin(
        callback.from_user.id
    ):
        await callback.answer(
            "Нет доступа.",
            show_alert=True
        )
        return

    try:
        telegram_id = int(
            callback.data.split(
                ":",
                1
            )[1]
        )
    except Exception:
        await callback.answer(
            "Ошибка ID.",
            show_alert=True
        )
        return

    set_blocked(
        telegram_id,
        False
    )

    await callback.answer(
        "Пользователь разблокирован."
    )

    user = get_user(
        telegram_id
    )

    if user:
        status = (
            "🟢 Активна"
            if subscription_active(user)
            else "⚫ Закончилась"
        )

        await callback.message.edit_text(
            "👤 ПОЛЬЗОВАТЕЛЬ\n\n"
            "🆔 ID: "
            + str(user["telegram_id"])
            + "\n"
            "📌 Статус: "
            + status
            + "\n"
            "📅 До: "
            + format_date(
                user["expires_at"]
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔴 Заблокировать",
                            callback_data=(
                                "admin_block:"
                                + str(telegram_id)
                            )
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="⬅️ К пользователям",
                            callback_data="admin_users"
                        )
                    ],
                ]
            )
        )


# =========================================================
# АВТОМАТИЧЕСКАЯ ПРОВЕРКА ОКОНЧАНИЯ
# =========================================================

async def subscription_checker():
    while True:
        try:
            users = list_users()

            for user in users:
                if user["blocked"]:
                    continue

                if user["expired_page"]:
                    continue

                try:
                    expires_at = int(
                        user["expires_at"]
                    )
                except Exception:
                    continue

                remaining = (
                    expires_at
                    - now_timestamp()
                )

                if remaining <= (
                    EXPIRED_WARNING_HOURS * 3600
                ):
                    try:
                        publish_expired(
                            user["token"]
                        )

                        set_expired_page(
                            user["telegram_id"],
                            True
                        )

                        logger.info(
                            "Subscription ended: %s",
                            user["telegram_id"]
                        )

                    except Exception:
                        logger.exception(
                            "Ошибка окончания подписки: %s",
                            user["telegram_id"]
                        )

        except Exception:
            logger.exception(
                "Ошибка фоновой проверки"
            )

        await asyncio.sleep(
            CHECK_INTERVAL_SECONDS
        )


# =========================================================
# ЗАПУСК
# =========================================================

async def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN не задан."
        )

    init_db()

    asyncio.create_task(
        subscription_checker()
    )

    logger.info(
        "🍑 Персик VPN запущен"
    )

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":
    asyncio.run(
        main()
        )
