import asyncio
import html
from datetime import datetime, timezone
from urllib.parse import quote

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import BOT_TOKEN, ADMIN_ID, HAPP_PAGE

from database import (
    init_db,
    get_user,
    create_user,
    save_subscription_url,
    refresh_user,
    list_users,
    add_days,
    set_blocked,
    delete_user,
    create_promo,
    get_promo,
    list_promos,
    use_promo,
)

from github_api import (
    put_file,
    delete_file,
    raw_subscription_url,
    subscription_path,
)


if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не задан"
    )


bot = Bot(BOT_TOKEN)
dp = Dispatcher()


PROFILE_TITLE = (
    "#profile-title: 🍑 Персик VPN"
)

ANNOUNCE = (
    "#announce: 🆓 Бесплатный VPN"
)

UPDATE_INTERVAL = (
    "#profile-update-interval: 1"
)


def main_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🍑 Моя подписка",
                    callback_data="subscription"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Обновить подписку",
                    callback_data="refresh"
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
                    text="📊 Статистика",
                    callback_data="stats"
                )
            ],
            [
                InlineKeyboardButton(
                    text="ℹ️ Помощь",
                    callback_data="help"
                )
            ],
        ]
    )


def admin_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👥 Участники",
                    callback_data="admin_users"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎟 Создать промо",
                    callback_data="admin_promo"
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
                    text="➕ Выдать дни",
                    callback_data="admin_days"
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
                    text="🚫 Заблокировать",
                    callback_data="admin_block"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔓 Разблокировать",
                    callback_data="admin_unblock"
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data="back"
                )
            ],
        ]
    )


def fmt_date(value):
    try:
        return (
            datetime
            .fromisoformat(value)
            .astimezone()
            .strftime("%d.%m.%Y %H:%M")
        )
    except Exception:
        return value


def unix_expire(value):
    try:
        return int(
            datetime
            .fromisoformat(value)
            .timestamp()
        )
    except Exception:
        return 0


def node_text():
    try:
        with open(
            "nodes.txt",
            "r",
            encoding="utf-8"
        ) as file:
            return file.read().strip()

    except FileNotFoundError:
        return ""


def make_subscription(user):
    token = user["token"]

    nodes = node_text()

    if not nodes:
        raise RuntimeError(
            "Файл nodes.txt пуст или отсутствует"
        )

    content = (
        'id="{}"\n'
        "{}\n"
        "{}\n"
        "#subscription-userinfo: "
        "upload=0; "
        "download={}; "
        "expire={}\n"
        "{}\n\n"
        "{}\n"
    ).format(
        token[:6],
        PROFILE_TITLE,
        ANNOUNCE,
        user["total_bytes"],
        unix_expire(
            user["expires_at"]
        ),
        UPDATE_INTERVAL,
        nodes
    )

    path = subscription_path(token)

    put_file(
        path,
        content,
        "Update PeachVPN subscription "
        + token[:6]
    )

    url = raw_subscription_url(token)

    save_subscription_url(
        user["telegram_id"],
        url
    )

    return url


def happ_url(subscription_url):
    return (
        HAPP_PAGE
        + "?sub="
        + quote(
            subscription_url,
            safe=""
        )
    )


def ensure_subscription(user):
    if user["blocked"]:
        raise RuntimeError(
            "Пользователь заблокирован"
        )

    return make_subscription(user)


def subscription_text(
    user,
    url
):
    return (
        "🍑 Твоя подписка готова!\n\n"
        "📦 Безлимитный трафик\n"
        "📅 7 дней / до: "
        + fmt_date(user["expires_at"])
        + "\n\n"
        "🔗 Ссылка подписки:\n"
        + url
    )


@dp.message(Command("start"))
async def start(message: Message):
    user = create_user(
        message.from_user.id,
        message.from_user.username
    )

    user = refresh_user(
        message.from_user.id
    )

    if user["blocked"]:
        await message.answer(
            "🚫 Ты заблокирован."
        )
        return

    try:
        url = (
            user["subscription_url"]
            or ensure_subscription(user)
        )

        await message.answer(
            subscription_text(
                user,
                url
            ),
            reply_markup=main_keyboard()
        )

    except Exception as error:
        await message.answer(
            "🍑 Персик VPN\n\n"
            "❌ Не удалось создать подписку.\n"
            "Попробуй позже.\n\n"
            "Ошибка: "
            + html.escape(str(error))
        )


@dp.callback_query(
    F.data == "subscription"
)
async def subscription(
    call: CallbackQuery
):
    user = create_user(
        call.from_user.id,
        call.from_user.username
    )

    user = refresh_user(
        call.from_user.id
    )

    if user["blocked"]:
        await call.message.answer(
            "🚫 Ты заблокирован."
        )
        await call.answer()
        return

    try:
        url = (
            user["subscription_url"]
            or ensure_subscription(user)
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🍑 Открыть в Happ",
                        url=happ_url(url)
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔄 Обновить подписку",
                        callback_data="refresh"
                    )
                ],
            ]
        )

        await call.message.answer(
            subscription_text(
                user,
                url
            ),
            reply_markup=keyboard
        )

    except Exception as error:
        await call.message.answer(
            "❌ Ошибка: "
            + html.escape(str(error))
        )

    await call.answer()


@dp.callback_query(
    F.data == "refresh"
)
async def refresh_subscription(
    call: CallbackQuery
):
    user = refresh_user(
        call.from_user.id
    )

    if not user:
        user = create_user(
            call.from_user.id,
            call.from_user.username
        )

    if user["blocked"]:
        await call.message.answer(
            "🚫 Ты заблокирован."
        )
        await call.answer()
        return

    try:
        url = ensure_subscription(user)

        await call.message.answer(
            "✅ Подписка обновлена!\n\n"
            + subscription_text(
                user,
                url
            ),
            reply_markup=main_keyboard()
        )

    except Exception as error:
        await call.message.answer(
            "❌ Ошибка обновления:\n"
            + html.escape(str(error))
        )

    await call.answer()


@dp.callback_query(
    F.data == "promo"
)
async def promo_button(
    call: CallbackQuery
):
    await call.message.answer(
        "🎟 Отправь промокод одним сообщением."
    )

    await call.answer()


@dp.callback_query(
    F.data == "stats"
)
async def stats(
    call: CallbackQuery
):
    user = get_user(
        call.from_user.id
    )

    if not user:
        await call.answer(
            "Подписка ещё не создана.",
            show_alert=True
        )
        return

    await call.message.answer(
        "📊 Статистика\n\n"
        "📤 Upload: 0 B\n"
        "📥 Download: 0 B\n"
        "📅 До: "
        + fmt_date(user["expires_at"])
    )

    await call.answer()


@dp.callback_query(
    F.data == "help"
)
async def help_callback(
    call: CallbackQuery
):
    await call.message.answer(
        "ℹ️ Помощь\n\n"
        "1. Открой «Моя подписка».\n"
        "2. Нажми «Открыть в Happ».\n"
        "3. В Happ добавь подписку.\n\n"
        "Если сервер временно недоступен, "
        "нажми «Обновить подписку»."
    )

    await call.answer()


@dp.message(Command("admin"))
async def admin(
    message: Message
):
    if message.from_user.id != ADMIN_ID:
        return

    await message.answer(
        "🔧 Админ-панель",
        reply_markup=admin_keyboard()
    )


@dp.callback_query(
    F.data == "admin_users"
)
async def admin_users(
    call: CallbackQuery
):
    if call.from_user.id != ADMIN_ID:
        return

    users = list_users()

    if not users:
        text = (
            "👥 Участников пока нет."
        )

    else:
        rows = []

        for user in users:
            username = (
                "@"
                + user["username"]
                if user["username"]
                else "без username"
            )

            status = (
                "🚫"
                if user["blocked"]
                else "✅"
            )

            rows.append(
                status
                + " ID: "
                + str(user["telegram_id"])
                + " | "
                + username
                + "\n📅 до "
                + fmt_date(
                    user["expires_at"]
                )
            )

        text = (
            "👥 Участники:\n\n"
            + "\n\n".join(rows)
        )

    await call.message.answer(
        text,
        reply_markup=admin_keyboard()
    )

    await call.answer()


@dp.callback_query(
    F.data == "admin_promo"
)
async def admin_promo(
    call: CallbackQuery
):
    if call.from_user.id != ADMIN_ID:
        return

    await call.message.answer(
        "🎟 Создание промокода\n\n"
        "Отправь одной строкой:\n"
        "КОД ДНИ ИСПОЛЬЗОВАНИЯ\n\n"
        "Пример:\n"
        "PEACH7 7 100"
    )

    await call.answer()


@dp.callback_query(
    F.data == "admin_promos"
)
async def admin_promos(
    call: CallbackQuery
):
    if call.from_user.id != ADMIN_ID:
        return

    promos = list_promos()

    if not promos:
        text = (
            "📋 Промокодов пока нет."
        )

    else:
        rows = []

        for promo in promos:
            rows.append(
                "🎟 "
                + promo["code"]
                + "\n➕ "
                + str(promo["days"])
                + " дней"
                + "\n👥 "
                + str(promo["uses"])
                + " / "
                + str(promo["max_uses"])
            )

        text = (
            "📋 Промокоды:\n\n"
            + "\n\n".join(rows)
        )

    await call.message.answer(
        text,
        reply_markup=admin_keyboard()
    )

    await call.answer()


@dp.callback_query(
    F.data == "admin_days"
)
async def admin_days(
    call: CallbackQuery
):
    if call.from_user.id != ADMIN_ID:
        return

    await call.message.answer(
        "➕ Формат:\n"
        "ID ДНИ\n\n"
        "Пример:\n"
        "123456789 30"
    )

    await call.answer()


@dp.callback_query(
    F.data == "admin_delete"
)
async def admin_delete(
    call: CallbackQuery
):
    if call.from_user.id != ADMIN_ID:
        return

    await call.message.answer(
        "🗑 Отправь Telegram ID пользователя."
    )

    await call.answer()


@dp.callback_query(
    F.data == "admin_block"
)
async def admin_block(
    call: CallbackQuery
):
    if call.from_user.id != ADMIN_ID:
        return

    await call.message.answer(
        "🚫 Отправь Telegram ID пользователя."
    )

    await call.answer()


@dp.callback_query(
    F.data == "admin_unblock"
)
async def admin_unblock(
    call: CallbackQuery
):
    if call.from_user.id != ADMIN_ID:
        return

    await call.message.answer(
        "🔓 Отправь Telegram ID пользователя."
    )

    await call.answer()


@dp.callback_query(
    F.data == "back"
)
async def back(
    call: CallbackQuery
):
    if call.from_user.id == ADMIN_ID:
        await call.message.answer(
            "🔧 Админ-панель",
            reply_markup=admin_keyboard()
        )
    else:
        await call.message.answer(
            "🍑 Персик VPN",
            reply_markup=main_keyboard()
        )

    await call.answer()


@dp.callback_query(
    F.data.startswith("confirm_delete:")
)
async def confirm_delete(
    call: CallbackQuery
):
    if call.from_user.id != ADMIN_ID:
        return

    try:
        target = int(
            call.data.split(
                ":",
                1
            )[1]
        )

    except ValueError:
        await call.answer(
            "Неверный ID",
            show_alert=True
        )
        return

    user = get_user(target)

    if not user:
        await call.message.answer(
            "❌ Пользователь не найден."
        )
        await call.answer()
        return

    try:
        if user["token"]:
            delete_file(
                subscription_path(
                    user["token"]
                ),
                "Delete PeachVPN subscription "
                + str(target)
            )

    except Exception:
        pass

    delete_user(target)

    await call.message.answer(
        "✅ Пользователь и его подписка удалены.\n"
        "ID: "
        + str(target),
        reply_markup=admin_keyboard()
    )

    await call.answer()


@dp.message()
async def text_handler(
    message: Message
):
    text_value = (
        message.text or ""
    ).strip()

    if not text_value:
        return

    user_id = message.from_user.id

    if user_id == ADMIN_ID:
        parts = text_value.split()

        if len(parts) == 3:
            try:
                days = int(parts[1])
                uses = int(parts[2])

                if days > 0 and uses > 0:
                    create_promo(
                        parts[0],
                        days,
                        uses
                    )

                    await message.answer(
                        "✅ Промокод создан.\n\n"
                        "🎟 Код: "
                        + parts[0].upper()
                        + "\n"
                        "📅 Дней: "
                        + str(days)
                        + "\n"
                        "👥 Использований: "
                        + str(uses),
                        reply_markup=admin_keyboard()
                    )

                    return

            except Exception as error:
                await message.answer(
                    "❌ Ошибка создания промокода:\n"
                    + html.escape(
                        str(error)
                    )
                )
                return

        if len(parts) == 2:
            try:
                target = int(parts[0])
                days = int(parts[1])

                user = get_user(target)

                if user and days > 0:
                    user = add_days(
                        target,
                        days
                    )

                    try:
                        make_subscription(
                            user
                        )
                    except Exception:
                        pass

                    await message.answer(
                        "✅ Дни выданы.\n\n"
                        "👤 ID: "
                        + str(target)
                        + "\n"
                        "➕ Дней: "
                        + str(days)
                        + "\n"
                        "📅 До: "
                        + fmt_date(
                            user["expires_at"]
                        ),
                        reply_markup=admin_keyboard()
                    )

                    return

            except ValueError:
                pass

        if len(parts) == 1:
            try:
                target = int(parts[0])

                user = get_user(target)

                if user:
                    keyboard = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="❌ Удалить",
                                    callback_data=(
                                        "confirm_delete:"
                                        + str(target)
                                    )
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    text="◀️ Отмена",
                                    callback_data="back"
                                )
                            ],
                        ]
                    )

                    await message.answer(
                        "🗑 Удалить подписку "
                        "пользователя "
                        + str(target)
                        + "?",
                        reply_markup=keyboard
                    )

                    return

            except ValueError:
                pass

    promo = get_promo(
        text_value
    )

    if promo:
        ok, result = use_promo(
            text_value,
            user_id
        )

        if ok:
            user = create_user(
                user_id,
                message.from_user.username
            )

            user = add_days(
                user_id,
                int(result)
            )

            try:
                url = make_subscription(
                    user
                )
            except Exception:
                url = (
                    user["subscription_url"]
                    or "не создана"
                )

            await message.answer(
                "🎉 Промокод активирован!\n\n"
                "➕ Добавлено дней: "
                + str(result)
                + "\n"
                "📅 До: "
                + fmt_date(
                    user["expires_at"]
                )
                + "\n\n"
                "🔗 "
                + url,
                reply_markup=main_keyboard()
            )

        else:
            await message.answer(
                "❌ "
                + str(result)
            )

        return


@dp.callback_query(
    F.data == "block_confirm"
)
async def block_confirm(
    call: CallbackQuery
):
    await call.answer()


async def main():
    init_db()

    print(
        "PeachVPN Bot started"
    )

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":
    asyncio.run(main())
