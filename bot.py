import asyncio
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import (
    BOT_TOKEN,
    ADMIN_ID,
    SUBSCRIPTION_DAYS,
    EXPIRED_WARNING_HOURS,
    CHECK_INTERVAL_SECONDS
)

from database import (
    init_db,
    create_user,
    get_user,
    activate_subscription,
    save_subscription_url,
    set_expired_page,
    set_blocked,
    list_users
)

from github_api import (
    publish_active,
    publish_expired
)


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# =========================================================
# ВРЕМЯ
# =========================================================

def now_timestamp():
    return int(
        datetime.now(timezone.utc).timestamp()
    )


def format_date(timestamp):
    try:
        timestamp = int(timestamp)
    except Exception:
        return "не выдана"

    if timestamp <= 0:
        return "не выдана"

    dt = datetime.fromtimestamp(
        timestamp,
        timezone.utc
    )

    return dt.strftime(
        "%d.%m.%Y %H:%M"
    )


def get_remaining_text(expires_at):
    try:
        expires_at = int(expires_at)
    except Exception:
        return "неизвестно"

    remaining = expires_at - now_timestamp()

    if remaining <= 0:
        return "закончилась"

    days = remaining // 86400
    hours = (remaining % 86400) // 3600
    minutes = (remaining % 3600) // 60

    if days > 0:
        return (
            str(days)
            + " д. "
            + str(hours)
            + " ч."
        )

    if hours > 0:
        return (
            str(hours)
            + " ч. "
            + str(minutes)
            + " мин."
        )

    return str(minutes) + " мин."


# =========================================================
# ПРОВЕРКИ
# =========================================================

def is_blocked(user):
    return int(user["blocked"]) == 1


def has_subscription(user):
    try:
        return int(user["expires_at"]) > 0
    except Exception:
        return False


def subscription_is_active(user):
    if not user:
        return False

    if is_blocked(user):
        return False

    try:
        expires_at = int(user["expires_at"])
    except Exception:
        return False

    return expires_at > now_timestamp()


# =========================================================
# ГЛАВНАЯ КЛАВИАТУРА
# =========================================================

def main_keyboard(user_id):
    builder = InlineKeyboardBuilder()

    builder.button(
        text="🍑 Моя подписка",
        callback_data="subscription"
    )

    builder.button(
        text="🔄 Получить подписку",
        callback_data="get_subscription"
    )

    builder.button(
        text="🔗 Моя ссылка",
        callback_data="my_link"
    )

    if user_id == ADMIN_ID:
        builder.button(
            text="⚙️ Админ-панель",
            callback_data="admin"
        )

    builder.adjust(1)

    return builder.as_markup()


# =========================================================
# АДМИНКА
# =========================================================

def admin_keyboard():
    builder = InlineKeyboardBuilder()

    builder.button(
        text="👥 Пользователи",
        callback_data="admin_users"
    )

    builder.button(
        text="⬅️ Назад",
        callback_data="back"
    )

    builder.adjust(1)

    return builder.as_markup()


def admin_user_keyboard(telegram_id, blocked):
    builder = InlineKeyboardBuilder()

    if blocked:
        builder.button(
            text="🔓 Разблокировать",
            callback_data="admin_unblock:"
            + str(telegram_id)
        )
    else:
        builder.button(
            text="🚫 Заблокировать",
            callback_data="admin_block:"
            + str(telegram_id)
        )

    builder.button(
        text="⬅️ Назад",
        callback_data="admin_users"
    )

    builder.adjust(1)

    return builder.as_markup()


# =========================================================
# ПОЛЬЗОВАТЕЛЬ
# =========================================================

async def get_or_create_user(
    telegram_id,
    username
):
    user = get_user(telegram_id)

    if not user:
        user = create_user(
            telegram_id,
            username
        )
    else:
        if (
            username is not None
            and user["username"] != username
        ):
            user = create_user(
                telegram_id,
                username
            )

    return user


# =========================================================
# ТЕКСТ ГЛАВНОГО МЕНЮ
# =========================================================

def build_home_text(user):
    if not user:
        return (
            "🍑 ПЕРСИК VPN\n\n"
            "❌ Пользователь не найден."
        )

    if is_blocked(user):
        return (
            "🍑 ПЕРСИК VPN\n\n"
            "🔴 Ты заблокирован.\n\n"
            "Доступ к подписке отключён."
        )

    if subscription_is_active(user):
        return (
            "🍑 ПЕРСИК VPN\n\n"
            "🟢 Подписка: Free\n"
            "📅 До: "
            + format_date(user["expires_at"])
            + "\n"
            "📦 Трафик: Безлимит\n"
            "🌍 Серверов: 4\n\n"
            "⏳ Осталось: "
            + get_remaining_text(
                user["expires_at"]
            )
            + "\n\n"
            "👇 Выбери действие:"
        )

    if has_subscription(user):
        return (
            "🍑 ПЕРСИК VPN\n\n"
            "🔴 Подписка закончилась.\n"
            "📦 Трафик: Безлимит\n\n"
            "⚠️ Бесплатная подписка уже была "
            "выдана этому аккаунту."
        )

    return (
        "🍑 ПЕРСИК VPN\n\n"
        "⚪ Подписка: Не активна\n"
        "📦 Трафик: Безлимит\n"
        "🌍 Серверов: 4\n\n"
        "👇 Выбери действие:"
    )


# =========================================================
# ФОНОВАЯ ПРОВЕРКА ПОДПИСОК
# =========================================================

async def update_expired_subscriptions():
    while True:
        try:
            users = list_users()

            now = now_timestamp()

            warning_seconds = (
                EXPIRED_WARNING_HOURS
                * 60
                * 60
            )

            for user in users:

                if is_blocked(user):
                    continue

                try:
                    expires_at = int(
                        user["expires_at"]
                    )
                except Exception:
                    continue

                if expires_at <= 0:
                    continue

                remaining = (
                    expires_at - now
                )

                expired_page = int(
                    user["expired_page"]
                )

                # -----------------------------------------
                # ПОПАЛИ В ПОСЛЕДНИЕ 24 ЧАСА
                # -----------------------------------------

                if (
                    remaining > 0
                    and remaining <= warning_seconds
                    and expired_page == 0
                ):
                    try:
                        url = publish_expired(
                            user["token"]
                        )

                        save_subscription_url(
                            user["telegram_id"],
                            url
                        )

                        set_expired_page(
                            user["telegram_id"],
                            True
                        )

                        print(
                            "⚠️ Подписка переключена "
                            "в expired: "
                            + str(
                                user["telegram_id"]
                            )
                        )

                    except Exception as error:
                        print(
                            "❌ Ошибка expired "
                            + str(
                                user["telegram_id"]
                            )
                            + ": "
                            + str(error)
                        )

                # -----------------------------------------
                # УЖЕ ЗАКОНЧИЛАСЬ
                # -----------------------------------------

                elif (
                    remaining <= 0
                    and expired_page == 0
                ):
                    try:
                        url = publish_expired(
                            user["token"]
                        )

                        save_subscription_url(
                            user["telegram_id"],
                            url
                        )

                        set_expired_page(
                            user["telegram_id"],
                            True
                        )

                        print(
                            "🔴 Подписка закончилась: "
                            + str(
                                user["telegram_id"]
                            )
                        )

                    except Exception as error:
                        print(
                            "❌ Ошибка окончания "
                            + str(
                                user["telegram_id"]
                            )
                            + ": "
                            + str(error)
                        )

        except Exception as error:
            print(
                "❌ Ошибка фоновой проверки: "
                + str(error)
            )

        await asyncio.sleep(
            CHECK_INTERVAL_SECONDS
        )


# =========================================================
# /start
# =========================================================

@dp.message(CommandStart())
async def start(message: Message):
    try:
        user = await get_or_create_user(
            message.from_user.id,
            message.from_user.username
        )

        await message.answer(
            build_home_text(user),
            reply_markup=main_keyboard(
                message.from_user.id
            )
        )

    except Exception as error:
        await message.answer(
            "❌ Ошибка:\n"
            + str(error)
        )


# =========================================================
# НАЗАД
# =========================================================

@dp.callback_query(F.data == "back")
async def back(callback: CallbackQuery):
    user = await get_or_create_user(
        callback.from_user.id,
        callback.from_user.username
    )

    await callback.message.edit_text(
        build_home_text(user),
        reply_markup=main_keyboard(
            callback.from_user.id
        )
    )

    await callback.answer()


# =========================================================
# МОЯ ПОДПИСКА
# =========================================================

@dp.callback_query(F.data == "subscription")
async def subscription(
    callback: CallbackQuery
):
    user = await get_or_create_user(
        callback.from_user.id,
        callback.from_user.username
    )

    if is_blocked(user):
        text = (
            "🍑 МОЯ ПОДПИСКА\n\n"
            "🔴 Ты заблокирован."
        )

    elif subscription_is_active(user):
        text = (
            "🍑 МОЯ ПОДПИСКА\n\n"
            "🟢 Статус: Активна\n"
            "📅 До: "
            + format_date(user["expires_at"])
            + "\n"
            "⏳ Осталось: "
            + get_remaining_text(
                user["expires_at"]
            )
            + "\n"
            "📦 Трафик: Безлимит\n"
            "🌍 Серверов: 4\n\n"
            "🔗 Ссылка постоянная."
        )

    elif has_subscription(user):
        text = (
            "🍑 МОЯ ПОДПИСКА\n\n"
            "🔴 Статус: Закончилась\n"
            "📦 Трафик: Безлимит\n\n"
            "⚠️ Бесплатная подписка уже была "
            "выдана.\n"
            "Повторная выдача не предусмотрена."
        )

    else:
        text = (
            "🍑 МОЯ ПОДПИСКА\n\n"
            "⚪ Статус: Не активна\n\n"
            "Можно получить бесплатную подписку "
            "на 30 дней."
        )

    await callback.message.edit_text(
        text,
        reply_markup=main_keyboard(
            callback.from_user.id
        )
    )

    await callback.answer()


# =========================================================
# ПОЛУЧИТЬ ПОДПИСКУ
# =========================================================

@dp.callback_query(
    F.data == "get_subscription"
)
async def get_subscription(
    callback: CallbackQuery
):
    user = await get_or_create_user(
        callback.from_user.id,
        callback.from_user.username
    )

    if is_blocked(user):
        await callback.answer(
            "🚫 Ты заблокирован.",
            show_alert=True
        )
        return

    # Уже когда-либо выдавали
    if has_subscription(user):
        if subscription_is_active(user):
            message = (
                "🟢 Подписка уже активна.\n"
                "Новая подписка не нужна."
            )
        else:
            message = (
                "🔴 Эта бесплатная подписка "
                "уже была выдана.\n\n"
                "Повторная выдача невозможна."
            )

        await callback.answer(
            message,
            show_alert=True
        )
        return

    try:
        # Выдаём ровно 30 дней
        user = activate_subscription(
            callback.from_user.id,
            SUBSCRIPTION_DAYS
        )

        if not user:
            raise RuntimeError(
                "Не удалось активировать пользователя."
            )

        # Создаём активный GitHub-файл
        url = publish_active(
            user["token"],
            int(user["expires_at"])
        )

        # Сохраняем постоянную ссылку
        save_subscription_url(
            callback.from_user.id,
            url
        )

        # Получаем свежие данные
        user = get_user(
            callback.from_user.id
        )

        await callback.message.edit_text(
            "🍑 ПОДПИСКА ВЫДАНА\n\n"
            "🟢 Срок: 30 дней\n"
            "📦 Трафик: Безлимит\n"
            "🌍 Серверов: 4\n"
            "📅 До: "
            + format_date(
                user["expires_at"]
            )
            + "\n"
            "⏳ Осталось: "
            + get_remaining_text(
                user["expires_at"]
            )
            + "\n\n"
            "🔗 Твоя постоянная ссылка:\n"
            + url,
            reply_markup=main_keyboard(
                callback.from_user.id
            )
        )

        await callback.answer(
            "🍑 Подписка выдана!"
        )

    except Exception as error:
        await callback.answer(
            "❌ Ошибка выдачи.",
            show_alert=True
        )

        await callback.message.answer(
            "❌ Ошибка:\n"
            + str(error)
        )


# =========================================================
# МОЯ ССЫЛКА
# =========================================================

@dp.callback_query(F.data == "my_link")
async def my_link(
    callback: CallbackQuery
):
    user = await get_or_create_user(
        callback.from_user.id,
        callback.from_user.username
    )

    if is_blocked(user):
        await callback.answer(
            "🚫 Ты заблокирован.",
            show_alert=True
        )
        return

    url = user["subscription_url"]

    if not url:
        await callback.answer(
            "Ссылка появится после выдачи подписки.",
            show_alert=True
        )
        return

    if subscription_is_active(user):
        text = (
            "🔗 Твоя постоянная ссылка Happ:\n\n"
            + url
            + "\n\n"
            "🟢 Подписка активна\n"
            "📅 До: "
            + format_date(
                user["expires_at"]
            )
        )
    else:
        text = (
            "🔗 Твоя постоянная ссылка Happ:\n\n"
            + url
            + "\n\n"
            "🔴 Подписка закончилась."
        )

    await callback.message.answer(
        text
    )

    await callback.answer()


# =========================================================
# АДМИН-ПАНЕЛЬ
# =========================================================

@dp.callback_query(F.data == "admin")
async def admin(
    callback: CallbackQuery
):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "⛔ Нет доступа.",
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
# СПИСОК ПОЛЬЗОВАТЕЛЕЙ
# =========================================================

@dp.callback_query(F.data == "admin_users")
async def admin_users(
    callback: CallbackQuery
):
    if callback.from_user.id != ADMIN_ID:
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

        builder = InlineKeyboardBuilder()

        builder.button(
            text="⬅️ Назад",
            callback_data="admin"
        )

        await callback.message.edit_text(
            text,
            reply_markup=builder.as_markup()
        )

        await callback.answer()
        return

    lines = [
        "👥 ПОЛЬЗОВАТЕЛИ\n"
    ]

    builder = InlineKeyboardBuilder()

    for user in users[:50]:

        telegram_id = int(
            user["telegram_id"]
        )

        username = user["username"]

        if username:
            name = "@" + username
        else:
            name = "без username"

        if is_blocked(user):
            status = "🚫"
        elif subscription_is_active(user):
            status = "🟢"
        elif has_subscription(user):
            status = "🔴"
        else:
            status = "⚪"

        lines.append(
            status
            + " "
            + str(telegram_id)
            + " "
            + name
            + "\n"
            "До: "
            + format_date(
                user["expires_at"]
            )
            + "\n"
        )

        builder.button(
            text=(
                status
                + " "
                + name
                + " "
                + str(telegram_id)
            ),
            callback_data=(
                "admin_user:"
                + str(telegram_id)
            )
        )

    builder.button(
        text="⬅️ Назад",
        callback_data="admin"
    )

    builder.adjust(1)

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=builder.as_markup()
    )

    await callback.answer()


# =========================================================
# ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ В АДМИНКЕ
# =========================================================

@dp.callback_query(
    F.data.startswith("admin_user:")
)
async def admin_user(
    callback: CallbackQuery
):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )
        return

    try:
        telegram_id = int(
            callback.data.split(":")[1]
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

    username = user["username"]

    if username:
        name = "@" + username
    else:
        name = "без username"

    if is_blocked(user):
        status = "🚫 Заблокирован"
    elif subscription_is_active(user):
        status = "🟢 Активна"
    elif has_subscription(user):
        status = "🔴 Закончилась"
    else:
        status = "⚪ Не выдавалась"

    text = (
        "👤 ПОЛЬЗОВАТЕЛЬ\n\n"
        "🆔 ID: "
        + str(user["telegram_id"])
        + "\n"
        "👤 Username: "
        + name
        + "\n"
        "📊 Статус: "
        + status
        + "\n"
        "📅 До: "
        + format_date(
            user["expires_at"]
        )
        + "\n"
        "⏳ Осталось: "
        + get_remaining_text(
            user["expires_at"]
        )
        + "\n"
        "🔑 TOKEN: "
        + str(user["token"])
        + "\n"
        "🔗 Ссылка: "
        + (
            user["subscription_url"]
            or "нет"
        )
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_user_keyboard(
            telegram_id,
            is_blocked(user)
        )
    )

    await callback.answer()


# =========================================================
# БЛОКИРОВКА
# =========================================================

@dp.callback_query(
    F.data.startswith("admin_block:")
)
async def admin_block(
    callback: CallbackQuery
):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )
        return

    try:
        telegram_id = int(
            callback.data.split(":")[1]
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

    set_blocked(
        telegram_id,
        True
    )

    await callback.answer(
        "🚫 Пользователь заблокирован."
    )

    user = get_user(
        telegram_id
    )

    username = user["username"]

    if username:
        name = "@" + username
    else:
        name = "без username"

    await callback.message.edit_text(
        "👤 ПОЛЬЗОВАТЕЛЬ\n\n"
        "🆔 ID: "
        + str(telegram_id)
        + "\n"
        "👤 Username: "
        + name
        + "\n"
        "📊 Статус: 🚫 Заблокирован\n"
        "📅 До: "
        + format_date(
            user["expires_at"]
        ),
        reply_markup=admin_user_keyboard(
            telegram_id,
            True
        )
    )


# =========================================================
# РАЗБЛОКИРОВКА
# =========================================================

@dp.callback_query(
    F.data.startswith("admin_unblock:")
)
async def admin_unblock(
    callback: CallbackQuery
):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )
        return

    try:
        telegram_id = int(
            callback.data.split(":")[1]
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

    set_blocked(
        telegram_id,
        False
    )

    user = get_user(
        telegram_id
    )

    await callback.answer(
        "🔓 Пользователь разблокирован."
    )

    username = user["username"]

    if username:
        name = "@" + username
    else:
        name = "без username"

    if subscription_is_active(user):
        status = "🟢 Активна"
    elif has_subscription(user):
        status = "🔴 Закончилась"
    else:
        status = "⚪ Не выдавалась"

    await callback.message.edit_text(
        "👤 ПОЛЬЗОВАТЕЛЬ\n\n"
        "🆔 ID: "
        + str(telegram_id)
        + "\n"
        "👤 Username: "
        + name
        + "\n"
        "📊 Статус: "
        + status
        + "\n"
        "📅 До: "
        + format_date(
            user["expires_at"]
        ),
        reply_markup=admin_user_keyboard(
            telegram_id,
            False
        )
    )


# =========================================================
# КОМАНДА /block ID
# =========================================================

@dp.message(F.text.startswith("/block "))
async def block_user(
    message: Message
):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        telegram_id = int(
            message.text.split()[1]
        )

        user = get_user(
            telegram_id
        )

        if not user:
            await message.answer(
                "❌ Пользователь не найден."
            )
            return

        set_blocked(
            telegram_id,
            True
        )

        await message.answer(
            "🚫 Пользователь "
            + str(telegram_id)
            + " заблокирован."
        )

    except Exception:
        await message.answer(
            "❌ Использование:\n"
            "/block TELEGRAM_ID"
        )


# =========================================================
# КОМАНДА /unblock ID
# =========================================================

@dp.message(F.text.startswith("/unblock "))
async def unblock_user(
    message: Message
):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        telegram_id = int(
            message.text.split()[1]
        )

        user = get_user(
            telegram_id
        )

        if not user:
            await message.answer(
                "❌ Пользователь не найден."
            )
            return

        set_blocked(
            telegram_id,
            False
        )

        await message.answer(
            "🔓 Пользователь "
            + str(telegram_id)
            + " разблокирован."
        )

    except Exception:
        await message.answer(
            "❌ Использование:\n"
            "/unblock TELEGRAM_ID"
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

    print("🍑 PeachVPN Bot запущен.")
    print(
        "⏱ Проверка подписок каждые "
        + str(CHECK_INTERVAL_SECONDS)
        + " секунд."
    )

    asyncio.create_task(
        update_expired_subscriptions()
    )

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":
    asyncio.run(main())
