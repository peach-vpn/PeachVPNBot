import asyncio
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery
)
from aiogram.utils.keyboard import (
    InlineKeyboardBuilder
)

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


bot = Bot(
    token=BOT_TOKEN
)

dp = Dispatcher()


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


def now_timestamp():
    return int(
        datetime.now(
            timezone.utc
        ).timestamp()
    )


def format_date(timestamp):
    if not timestamp:
        return "не выдана"

    dt = datetime.fromtimestamp(
        int(timestamp),
        timezone.utc
    )

    return dt.strftime(
        "%d.%m.%Y %H:%M"
    )


def subscription_active(user):
    if not user:
        return False

    if int(user["blocked"]) == 1:
        return False

    expires = int(
        user["expires_at"]
    )

    return expires > now_timestamp()


def build_home_text(user):
    if not user:
        return (
            "🍑 ПЕРСИК VPN\n\n"
            "Ошибка пользователя."
        )

    if int(user["blocked"]) == 1:
        return (
            "🍑 ПЕРСИК VPN\n\n"
            "🔴 Ты заблокирован."
        )

    expires = int(
        user["expires_at"]
    )

    if expires > now_timestamp():
        return (
            "🍑 ПЕРСИК VPN\n\n"
            "🟢 Подписка: Free\n"
            "📅 До: "
            + format_date(expires)
            + "\n"
            "📦 Трафик: Безлимит\n"
            "🌍 Серверов: 4\n\n"
            "👇 Выбери действие:"
        )

    return (
        "🍑 ПЕРСИК VPN\n\n"
        "🔴 Подписка закончилась.\n\n"
        "👇 Выбери действие:"
    )


async def get_or_create_user(
    telegram_id,
    username
):
    user = get_user(
        telegram_id
    )

    if not user:
        user = create_user(
            telegram_id,
            username
        )

    return user


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
                if int(user["blocked"]) == 1:
                    continue

                expires = int(
                    user["expires_at"]
                )

                if expires <= 0:
                    continue

                remaining = (
                    expires - now
                )

                # Последние 24 часа.
                if (
                    remaining <= warning_seconds
                    and remaining > 0
                    and int(user["expired_page"]) == 0
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

                    except Exception as error:
                        print(
                            "Ошибка переключения "
                            "подписки "
                            + str(user["telegram_id"])
                            + ": "
                            + str(error)
                        )

                # Полностью закончилась.
                elif (
                    remaining <= 0
                    and int(user["expired_page"]) == 0
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

                    except Exception as error:
                        print(
                            "Ошибка окончания "
                            "подписки "
                            + str(user["telegram_id"])
                            + ": "
                            + str(error)
                        )

        except Exception as error:
            print(
                "Ошибка фоновой проверки: "
                + str(error)
            )

        await asyncio.sleep(
            CHECK_INTERVAL_SECONDS
        )


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


@dp.callback_query(F.data == "subscription")
async def subscription(
    callback: CallbackQuery
):
    user = await get_or_create_user(
        callback.from_user.id,
        callback.from_user.username
    )

    expires = int(
        user["expires_at"]
    )

    if expires > now_timestamp():
        text = (
            "🍑 МОЯ ПОДПИСКА\n\n"
            "🟢 Статус: Активна\n"
            "📅 До: "
            + format_date(expires)
            + "\n"
            "📦 Трафик: Безлимит\n"
            "🌍 Серверов: 4\n\n"
            "🔗 Ссылка постоянная."
        )
    else:
        text = (
            "🍑 МОЯ ПОДПИСКА\n\n"
            "🔴 Статус: Закончилась\n"
            "📦 Трафик: Безлимит\n\n"
            "Повторная бесплатная выдача "
            "не предусмотрена."
        )

    await callback.message.edit_text(
        text,
        reply_markup=main_keyboard(
            callback.from_user.id
        )
    )

    await callback.answer()


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

    if int(user["blocked"]) == 1:
        await callback.answer(
            "Ты заблокирован.",
            show_alert=True
        )
        return

    # Если подписка уже была выдана —
    # повторно её получить нельзя.
    if int(user["expires_at"]) > 0:
        await callback.answer(
            "Эта бесплатная подписка уже была выдана.",
            show_alert=True
        )
        return

    try:
        user = activate_subscription(
            callback.from_user.id,
            SUBSCRIPTION_DAYS
        )

        url = publish_active(
            user["token"],
            int(user["expires_at"])
        )

        save_subscription_url(
            callback.from_user.id,
            url
        )

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
            + "\n\n"
            "🔗 Твоя ссылка:\n"
            + url,
            reply_markup=main_keyboard(
                callback.from_user.id
            )
        )

        await callback.answer(
            "Подписка выдана!"
        )

    except Exception as error:
        await callback.answer(
            "Ошибка выдачи.",
            show_alert=True
        )

        await callback.message.answer(
            "❌ Ошибка:\n"
            + str(error)
        )


@dp.callback_query(F.data == "my_link")
async def my_link(
    callback: CallbackQuery
):
    user = await get_or_create_user(
        callback.from_user.id,
        callback.from_user.username
    )

    url = user["subscription_url"]

    if not url:
        await callback.answer(
            "Ссылка появится после выдачи подписки.",
            show_alert=True
        )
        return

    await callback.message.answer(
        "🔗 Твоя постоянная ссылка Happ:\n\n"
        + url
    )

    await callback.answer()


@dp.callback_query(F.data == "admin")
async def admin(
    callback: CallbackQuery
):
    if callback.from_user.id != ADMIN_ID:
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


@dp.callback_query(F.data == "admin_users")
async def admin_users(
    callback: CallbackQuery
):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "Нет доступа.",
            show_alert=True
        )
        return

    users = list_users()

    if not users:
        text = (
            "👥 Пользователей пока нет."
        )
    else:
        lines = [
            "👥 ПОЛЬЗОВАТЕЛИ\n"
        ]

        for user in users[:50]:
            username = user["username"]

            if username:
                name = "@" + username
            else:
                name = "без username"

            if int(user["blocked"]) == 1:
                status = "🚫"
            elif subscription_active(user):
                status = "🟢"
            elif int(user["expires_at"]) > 0:
                status = "🔴"
            else:
                status = "⚪"

            lines.append(
                status
                + " "
                + str(user["telegram_id"])
                + " "
                + name
                + "\n"
                + "До: "
                + format_date(
                    user["expires_at"]
                )
                + "\n"
            )

        text = "\n".join(lines)

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


async def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN не задан."
        )

    init_db()

    asyncio.create_task(
        update_expired_subscriptions()
    )

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":
    asyncio.run(main())
