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
    ISSUE_DAYS
)

from database import (
    init_db,
    create_user,
    get_user,
    save_subscription_url,
    activate_subscription,
    can_get_subscription,
    next_issue_days,
    deactivate_expired,
    list_users,
    set_blocked
)

from github_api import (
    publish_subscription,
    get_file_content,
    subscription_path
)


bot = Bot(
    token=BOT_TOKEN
)

dp = Dispatcher()


def main_keyboard(
    user_id
):
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
        text="🚫 Заблокировать",
        callback_data="admin_block_help"
    )

    builder.button(
        text="🔓 Разблокировать",
        callback_data="admin_unblock_help"
    )

    builder.button(
        text="⬅️ Назад",
        callback_data="back"
    )

    builder.adjust(1)

    return builder.as_markup()


def format_date(timestamp):
    if not timestamp:
        return "—"

    date = datetime.fromtimestamp(
        int(timestamp),
        timezone.utc
    )

    return date.strftime(
        "%d.%m.%Y %H:%M"
    )


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

    now = int(
        datetime.now(
            timezone.utc
        ).timestamp()
    )

    expires = int(
        user["expires_at"]
    )

    if expires > now:
        status = "🟢 Активна"
        until = format_date(expires)
    else:
        status = "🔴 Не активна"
        until = "истекла"

    count = int(
        user["issue_count"]
    )

    if count == 0:
        next_days = 30
    elif count == 1:
        next_days = 15
    elif count == 2:
        next_days = 7
    else:
        next_days = None

    if next_days:
        next_text = (
            "Следующая выдача: "
            + str(next_days)
            + " дней"
        )
    else:
        next_text = (
            "Выдачи закончились"
        )

    return (
        "🍑 ПЕРСИК VPN\n\n"
        + status
        + "\n"
        + "📅 До: "
        + until
        + "\n"
        + "📦 Трафик: Безлимит\n"
        + "🌍 Серверов: 4\n\n"
        + "🎁 Выдачи: "
        + str(count)
        + "/3\n"
        + next_text
        + "\n\n"
        + "👇 Выбери действие:"
    )


async def ensure_user(message):
    user = create_user(
        message.from_user.id,
        message.from_user.username
    )

    return user


@dp.message(CommandStart())
async def start(message: Message):
    try:
        user = await ensure_user(
            message
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
    user = get_user(
        callback.from_user.id
    )

    if not user:
        user = create_user(
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
    user = get_user(
        callback.from_user.id
    )

    if not user:
        user = create_user(
            callback.from_user.id,
            callback.from_user.username
        )

    now = int(
        datetime.now(
            timezone.utc
        ).timestamp()
    )

    expires = int(
        user["expires_at"]
    )

    if expires > now:
        status = "🟢 Активна"
        until = format_date(expires)
    else:
        status = "🔴 Не активна"
        until = "истекла"

    text = (
        "🍑 МОЯ ПОДПИСКА\n\n"
        + status
        + "\n"
        + "📅 До: "
        + until
        + "\n"
        + "📦 Трафик: Безлимит\n"
        + "🌍 Серверов: 4\n\n"
        + "🎁 Использовано выдач: "
        + str(user["issue_count"])
        + "/3"
    )

    await callback.message.edit_text(
        text,
        reply_markup=main_keyboard(
            callback.from_user.id
        )
    )

    await callback.answer()


@dp.callback_query(F.data == "my_link")
async def my_link(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if not user:
        user = create_user(
            callback.from_user.id,
            callback.from_user.username
        )

    url = user["subscription_url"]

    if not url:
        try:
            expires = int(
                user["expires_at"]
            )

            url = publish_subscription(
                user["token"],
                expires
            )

            save_subscription_url(
                callback.from_user.id,
                url
            )

        except Exception as error:
            await callback.answer(
                "Ошибка GitHub",
                show_alert=True
            )

            await callback.message.answer(
                "❌ Не удалось получить ссылку:\n"
                + str(error)
            )

            return

    await callback.message.answer(
        "🔗 Твоя ссылка Happ:\n\n"
        + url
    )

    await callback.answer()


@dp.callback_query(
    F.data == "get_subscription"
)
async def get_subscription(
    callback: CallbackQuery
):
    user = get_user(
        callback.from_user.id
    )

    if not user:
        user = create_user(
            callback.from_user.id,
            callback.from_user.username
        )

    if int(user["blocked"]) == 1:
        await callback.answer(
            "Ты заблокирован.",
            show_alert=True
        )
        return

    deactivate_expired()

    user = get_user(
        callback.from_user.id
    )

    if not can_get_subscription(
        callback.from_user.id
    ):
        if int(user["issue_count"]) >= 3:
            text = (
                "🔴 Все бесплатные выдачи "
                "уже использованы."
            )
        else:
            text = (
                "🟡 Текущая подписка ещё активна.\n\n"
                "Получить новую можно после её окончания."
            )

        await callback.answer(
            text,
            show_alert=True
        )
        return

    days = next_issue_days(
        callback.from_user.id
    )

    if days is None:
        await callback.answer(
            "Выдачи закончились.",
            show_alert=True
        )
        return

    try:
        # Сначала активируем срок.
        user = activate_subscription(
            callback.from_user.id,
            days
        )

        # TOKEN не меняется.
        # Файл подписки обновляется на тот же TOKEN.
        url = publish_subscription(
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
            "⏳ Срок: "
            + str(days)
            + " дней\n"
            + "📦 Трафик: Безлимит\n"
            + "🌍 Серверов: 4\n"
            + "🎁 Выдача: "
            + str(user["issue_count"])
            + "/3\n\n"
            "🔗 Ссылка:\n"
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
            "Ошибка",
            show_alert=True
        )

        await callback.message.answer(
            "❌ Ошибка выдачи:\n"
            + str(error)
        )


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
        text = "👥 Пользователей пока нет."
    else:
        parts = [
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
            elif int(user["active"]) == 1:
                status = "🟢"
            else:
                status = "🔴"

            parts.append(
                status
                + " "
                + str(user["telegram_id"])
                + " "
                + name
                + "\n"
                + "Выдач: "
                + str(user["issue_count"])
                + "/3"
                + "\n"
            )

        text = "\n".join(parts)

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


@dp.callback_query(
    F.data == "admin_block_help"
)
async def admin_block_help(
    callback: CallbackQuery
):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "Нет доступа.",
            show_alert=True
        )
        return

    await callback.message.answer(
        "🚫 Для блокировки используй:\n\n"
        "/block TELEGRAM_ID"
    )

    await callback.answer()


@dp.callback_query(
    F.data == "admin_unblock_help"
)
async def admin_unblock_help(
    callback: CallbackQuery
):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "Нет доступа.",
            show_alert=True
        )
        return

    await callback.message.answer(
        "🔓 Для разблокировки используй:\n\n"
        "/unblock TELEGRAM_ID"
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

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":
    asyncio.run(main())
